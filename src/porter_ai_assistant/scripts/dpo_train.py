#!/usr/bin/env python3
# Copyright 2026 VirtusCo
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""DPO reinforcement learning for Porter AI Assistant.

Uses Direct Preference Optimization to improve model output quality.
Creates preference pairs:
  - chosen: ground-truth responses from SFT training data
  - rejected: model-generated responses (capturing actual failure modes)

This avoids the merge_and_unload problem that degraded the 4-bit model in GRPO.

Usage:
    source .venv-finetune/bin/activate

    # Generate preference dataset + train (tool_use):
    python3 scripts/dpo_train.py --adapter tool_use

    # Conversational:
    python3 scripts/dpo_train.py --adapter conversational

    # Both:
    python3 scripts/dpo_train.py --adapter both

    # Skip generation (reuse existing preference dataset):
    python3 scripts/dpo_train.py --adapter tool_use --skip-generation

Requirements:
    pip install torch transformers peft datasets trl bitsandbytes accelerate
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import torch

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = SCRIPT_DIR.parent
DATA_DIR = PACKAGE_DIR / "data"
MODELS_DIR = PACKAGE_DIR / "models"
ADAPTER_DIR = MODELS_DIR / "lora_adapters"


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Generate Preference Dataset
# ══════════════════════════════════════════════════════════════════════════════

def generate_rejections(adapter_type: str, max_examples: int = 1000):
    """Generate rejected responses using the SFT model.

    Load the SFT adapter, generate responses for training prompts,
    and pair with ground-truth "chosen" responses from training data.
    """
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer, BitsAndBytesConfig

    sft_path = ADAPTER_DIR / adapter_type / "final"
    if not sft_path.exists():
        print(f"ERROR: SFT adapter not found: {sft_path}")
        sys.exit(1)

    # Load the SFT model
    print(f"Loading SFT adapter from {sft_path} for rejection generation...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoPeftModelForCausalLM.from_pretrained(
        str(sft_path),
        quantization_config=bnb_config,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
        attn_implementation="eager",
    )
    tokenizer = AutoTokenizer.from_pretrained(str(sft_path))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load training data
    data_path = DATA_DIR / adapter_type / "train.jsonl"
    examples = []
    with open(data_path) as f:
        for i, line in enumerate(f):
            if i >= max_examples:
                break
            examples.append(json.loads(line.strip()))

    print(f"Generating rejections for {len(examples)} examples...")
    preference_data = []
    t_start = time.monotonic()

    for i, example in enumerate(examples):
        if i % 50 == 0:
            elapsed = time.monotonic() - t_start
            rate = (i + 1) / max(elapsed, 0.01)
            print(f"  [{i}/{len(examples)}] {rate:.1f} ex/s")

        messages = example["messages"]

        # Extract prompt (system + user) and chosen (assistant)
        prompt_msgs = []
        chosen_text = ""
        for msg in messages:
            if msg["role"] in ("system", "user"):
                prompt_msgs.append(msg)
            elif msg["role"] == "assistant":
                chosen_text = msg["content"]
                break

        if not prompt_msgs or not chosen_text:
            continue

        # Generate rejection from model
        try:
            input_text = tokenizer.apply_chat_template(
                prompt_msgs, tokenize=False, add_generation_prompt=True,
            )
        except Exception:
            system_text = ""
            user_text = ""
            for m in prompt_msgs:
                if m["role"] == "system":
                    system_text = m["content"]
                elif m["role"] == "user":
                    user_text = m["content"]
            input_text = (
                f"<start_of_turn>user\n{system_text}\n\n"
                f"User: {user_text}<end_of_turn>\n<start_of_turn>model\n"
            )

        inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
        input_len = inputs["input_ids"].shape[1]

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=200,
                temperature=0.9,
                top_p=0.9,
                top_k=50,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
            )

        new_tokens = outputs[0][input_len:]
        rejected_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

        # Only keep if rejected differs meaningfully from chosen
        if rejected_text and rejected_text != chosen_text:
            preference_data.append({
                "prompt": prompt_msgs,
                "chosen": [{"role": "assistant", "content": chosen_text}],
                "rejected": [{"role": "assistant", "content": rejected_text}],
            })

    elapsed = time.monotonic() - t_start
    print(f"Generated {len(preference_data)} preference pairs in {elapsed:.0f}s")

    # Save
    out_path = DATA_DIR / adapter_type / "dpo_preferences.jsonl"
    with open(out_path, "w") as f:
        for item in preference_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Saved to: {out_path}")

    # Cleanup
    del model
    torch.cuda.empty_cache()

    return out_path, len(preference_data)


def generate_synthetic_rejections(adapter_type: str, max_examples: int = 1000):
    """Create synthetic rejected responses by corrupting chosen responses.

    Faster alternative to model generation — creates rejection patterns that
    match the actual failure modes we observed in inference testing:
    - Missing <tool_call> tags
    - Rambling without structure
    - Wrong tool selection
    - Invalid JSON
    """
    data_path = DATA_DIR / adapter_type / "train.jsonl"
    examples = []
    with open(data_path) as f:
        for i, line in enumerate(f):
            if i >= max_examples:
                break
            examples.append(json.loads(line.strip()))

    preference_data = []
    random.seed(42)

    for example in examples:
        messages = example["messages"]
        prompt_msgs = []
        chosen_text = ""

        for msg in messages:
            if msg["role"] in ("system", "user"):
                prompt_msgs.append(msg)
            elif msg["role"] == "assistant":
                chosen_text = msg["content"]
                break

        if not prompt_msgs or not chosen_text:
            continue

        # Create rejected response using random corruption
        corruption = random.choice(["strip_tags", "ramble", "wrong_json", "echo"])

        if corruption == "strip_tags" and "<tool_call>" in chosen_text:
            # Remove tool_call tags — model mentions tool but doesn't format properly
            rejected = chosen_text.replace("<tool_call>", "").replace("</tool_call>", "")
            rejected = rejected.replace("<tool_response>", "").replace("</tool_response>", "")
            rejected = f"I'll use the tool for that. {rejected}"

        elif corruption == "ramble":
            # Generic rambling response
            ramblings = [
                "I am an airport assistant robot made by VirtusCo. Use the tools to help passengers. "
                "Call tools when you need real-time data or to perform actions. Respond naturally after "
                "receiving tool results. Available tools include get_directions, get_flight_status, "
                "call_assistance, escort_passenger, and more. I can help you with many things at the "
                "airport. Please let me know what you need and I will try my best to assist you.",
                "Thank you for your question. As an airport assistant, I have access to various systems "
                "that can help you. I can look up flight information, provide directions, call for "
                "assistance, and much more. The airport has many terminals and gates. Let me know "
                "the specific details and I'll do my best to help you with your request.",
                "I understand you need help. I'm Porter, your airport assistant robot. "
                "I have access to airport systems and tools. I can search for information, "
                "provide directions, and assist with various airport services. "
                "Would you like me to help you with something specific?",
            ]
            rejected = random.choice(ramblings)

        elif corruption == "wrong_json" and "<tool_call>" in chosen_text:
            # Malformed JSON
            rejected = '<tool_call>\n{"name": "unknown_tool", "arguments": {"query": "help"}}\n</tool_call>'

        elif corruption == "echo":
            # Just echo part of the system prompt or repeat the query
            user_msg = ""
            for m in prompt_msgs:
                if m["role"] == "user":
                    user_msg = m["content"]
            rejected = f"You asked: {user_msg}. Let me look into that for you. Please wait while I process your request."

        else:
            # Default: strip and ramble
            rejected = "I can help you with that. Let me check our systems. Please wait a moment while I look up that information for you."

        preference_data.append({
            "prompt": prompt_msgs,
            "chosen": [{"role": "assistant", "content": chosen_text}],
            "rejected": [{"role": "assistant", "content": rejected}],
        })

    # Save
    out_path = DATA_DIR / adapter_type / "dpo_preferences_synthetic.jsonl"
    with open(out_path, "w") as f:
        for item in preference_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Generated {len(preference_data)} synthetic preference pairs → {out_path}")

    return out_path, len(preference_data)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: DPO Training
# ══════════════════════════════════════════════════════════════════════════════

def train_dpo(adapter_type: str, args):
    """Run DPO training on preference data.

    CRITICAL: Loads the pre-trained SFT adapter so policy != reference
    from step 0. A fresh LoRA (B=0) with ref_model=None produces
    zero gradients (CLAUDE.md lesson #35).
    """
    from datasets import Dataset
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import DPOConfig, DPOTrainer

    print(f"\n{'=' * 70}")
    print(f"  DPO Training: {adapter_type}")
    print(f"{'=' * 70}\n")

    # ── Check GPU ────────────────────────────────────────────────────────
    if not torch.cuda.is_available():
        print("ERROR: CUDA GPU required.")
        sys.exit(1)
    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU: {gpu_name} ({vram_gb:.1f} GB)")

    # ── Generate preference data ─────────────────────────────────────────
    max_examples = args.max_examples or (1000 if adapter_type == "tool_use" else 1500)

    if args.use_synthetic:
        pref_path, n_pairs = generate_synthetic_rejections(adapter_type, max_examples)
    elif not args.skip_generation:
        pref_path, n_pairs = generate_rejections(adapter_type, max_examples)
    else:
        # Try model-generated first, fall back to synthetic
        pref_path = DATA_DIR / adapter_type / "dpo_preferences.jsonl"
        if not pref_path.exists():
            pref_path = DATA_DIR / adapter_type / "dpo_preferences_synthetic.jsonl"
        if not pref_path.exists():
            print("ERROR: No preference data found. Run without --skip-generation.")
            sys.exit(1)
        n_pairs = sum(1 for _ in open(pref_path))

    # ── Load preference dataset ──────────────────────────────────────────
    records = []
    with open(pref_path) as f:
        for line in f:
            records.append(json.loads(line.strip()))

    # Split into train/eval
    random.seed(42)
    random.shuffle(records)
    split_idx = int(len(records) * 0.9)
    train_records = records[:split_idx]
    eval_records = records[split_idx:]

    train_dataset = Dataset.from_list(train_records)
    eval_dataset = Dataset.from_list(eval_records)
    print(f"Train: {len(train_records)} pairs, Eval: {len(eval_records)} pairs")

    # ── Load base model (bf16, no quantization) ─────────────────────────
    # DPO needs proper logprobs. 1.5B model at bf16 ≈ 3 GB — fits in 8 GB.
    # CRITICAL: Load SFT adapter to avoid lesson #35 zero-gradient bug.
    # With SFT LoRA loaded, policy (adapter enabled) != ref (adapter disabled)
    # from step 0, so DPO loss is meaningful immediately.
    base_model = "Qwen/Qwen2.5-1.5B-Instruct"
    sft_path = ADAPTER_DIR / adapter_type / "final"

    if not sft_path.exists():
        print(f"ERROR: SFT adapter not found: {sft_path}")
        print("Run finetune.py first to create the base SFT adapter.")
        sys.exit(1)

    print(f"\nLoading base model: {base_model} (bf16)")
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
        attn_implementation="eager",
    )

    print(f"Loading SFT adapter from: {sft_path}")
    model = PeftModel.from_pretrained(
        model, str(sft_path), is_trainable=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(str(sft_path))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    mem_gb = torch.cuda.memory_allocated() / 1e9
    print(f"Model + SFT LoRA loaded: {mem_gb:.2f} GB VRAM")

    # ── DPO config ───────────────────────────────────────────────────────
    output_dir = ADAPTER_DIR / adapter_type / "dpo"
    batch_size = args.batch_size
    grad_accum = args.grad_accum

    # 262K vocab creates massive logit tensors: batch*seq*262144*4 bytes
    # Force batch=1 and precompute ref logprobs to halve VRAM during training
    if vram_gb < 12.0:
        batch_size = 1
        grad_accum = max(grad_accum, 8)
        print(f"VRAM {vram_gb:.0f} GB — batch=1, grad_accum={grad_accum}, precompute_ref=True")

    dpo_config = DPOConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=5e-5,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        weight_decay=0.01,
        max_grad_norm=0.5,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="none",
        seed=42,
        # DPO-specific
        beta=0.1,                       # KL divergence coefficient
        loss_type="sigmoid",            # Standard DPO loss
        max_length=512,                 # prompt + chosen/rejected combined
        label_smoothing=0.0,
        precompute_ref_log_probs=True,  # Compute ref probs upfront — halves VRAM
        precompute_ref_batch_size=1,    # Batch 1 for ref precompute too
    )

    # ── Train ────────────────────────────────────────────────────────────
    print(f"\nStarting DPO training:")
    print(f"  Batch: {batch_size} × {grad_accum} = {batch_size * grad_accum} effective")
    print(f"  Epochs: {args.epochs}")
    print(f"  Beta (KL): {dpo_config.beta}")
    print(f"  LR: {dpo_config.learning_rate}")
    print()

    t_start = time.monotonic()

    trainer = DPOTrainer(
        model=model,
        ref_model=None,                 # TRL uses adapter-disabled model as ref
        args=dpo_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        # NO peft_config — we train the existing SFT LoRA directly
        # This avoids CLAUDE.md lesson #35 (fresh LoRA B=0 → zero gradients)
    )

    trainer.train()
    t_elapsed = time.monotonic() - t_start
    print(f"\nDPO training complete in {t_elapsed / 60:.1f} minutes")

    # ── Save ─────────────────────────────────────────────────────────────
    final_dir = output_dir / "final"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # Get eval metrics
    eval_results = trainer.evaluate()

    metadata = {
        "adapter_type": adapter_type,
        "training_type": "DPO",
        "base_model": base_model,
        "preference_data": str(pref_path),
        "num_pairs": n_pairs,
        "epochs": args.epochs,
        "batch_size": batch_size,
        "grad_accum": grad_accum,
        "learning_rate": dpo_config.learning_rate,
        "beta": dpo_config.beta,
        "training_time_min": round(t_elapsed / 60, 1),
        "eval_loss": round(eval_results.get("eval_loss", -1), 4),
        "eval_rewards_chosen": round(eval_results.get("eval_rewards/chosen", 0), 4),
        "eval_rewards_rejected": round(eval_results.get("eval_rewards/rejected", 0), 4),
        "eval_rewards_margins": round(eval_results.get("eval_rewards/margins", 0), 4),
        "gpu": gpu_name,
        "vram_gb": round(vram_gb, 1),
    }
    with open(final_dir / "dpo_training_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nEval results: {json.dumps(eval_results, indent=2)}")
    print(f"DPO adapter saved to: {final_dir}")

    del trainer, model
    torch.cuda.empty_cache()

    return metadata


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Parse args and run DPO training."""
    parser = argparse.ArgumentParser(
        description="DPO reinforcement learning for Porter AI Assistant"
    )
    parser.add_argument(
        "--adapter", type=str, choices=["conversational", "tool_use", "both"],
        default="both", help="Which adapter to train (default: both)"
    )
    parser.add_argument(
        "--epochs", type=int, default=2,
        help="Number of training epochs (default: 2)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=2,
        help="Per-device batch size (default: 2)"
    )
    parser.add_argument(
        "--grad-accum", type=int, default=4,
        help="Gradient accumulation steps (default: 4)"
    )
    parser.add_argument(
        "--max-examples", type=int, default=None,
        help="Max preference pairs (default: 1000 tool_use, 1500 conversational)"
    )
    parser.add_argument(
        "--skip-generation", action="store_true",
        help="Skip rejection generation (use existing preference data)"
    )
    parser.add_argument(
        "--use-synthetic", action="store_true",
        help="Use synthetic (corrupted) rejections instead of model-generated"
    )
    args = parser.parse_args()

    adapters = ["conversational", "tool_use"] if args.adapter == "both" else [args.adapter]

    all_results = {}
    for adapter_type in adapters:
        result = train_dpo(adapter_type, args)
        all_results[adapter_type] = result

    print(f"\n{'#' * 70}")
    print(f"  DPO TRAINING COMPLETE")
    print(f"{'#' * 70}")
    for name, meta in all_results.items():
        print(f"  {name:20s}: eval_loss={meta['eval_loss']}, "
              f"margin={meta['eval_rewards_margins']}, "
              f"{meta['training_time_min']} min")
    print(f"\nTest with: python3 scripts/inference_test.py --variant dpo/final")


if __name__ == "__main__":
    main()

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
"""GRPO reinforcement learning for Porter AI Assistant.

Uses Group Relative Policy Optimization (GRPO) with rule-based reward
functions to improve model quality after supervised fine-tuning.

Key improvements targeted:
  - Tool_use: structured <tool_call> JSON output, correct tool selection
  - Conversational: conciseness, relevance, helpfulness

Usage:
    source .venv-finetune/bin/activate

    # RL for tool_use adapter (most needed):
    python3 scripts/rl_train.py --adapter tool_use

    # RL for conversational adapter:
    python3 scripts/rl_train.py --adapter conversational

    # Both sequentially:
    python3 scripts/rl_train.py --adapter both

    # Custom settings:
    python3 scripts/rl_train.py --adapter tool_use --max-steps 500 --batch-size 2

Requirements:
    pip install torch transformers peft datasets trl bitsandbytes accelerate
"""

import argparse
import json
import re
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

# ── Valid tools in our system ────────────────────────────────────────────────
VALID_TOOLS = {
    "call_assistance", "check_wait_time", "escort_passenger",
    "find_nearest", "get_airline_counter", "get_directions",
    "get_flight_status", "get_transport_options", "report_incident",
    "set_reminder", "show_map", "translate_text", "weigh_luggage",
}

# ── Tool routing: query keywords → expected tool ─────────────────────────────
TOOL_ROUTING = {
    "get_directions": ["gate", "terminal", "direction", "how to get", "where is", "way to", "walk to"],
    "get_flight_status": ["flight", "status", "delayed", "departing", "arriving", "on time"],
    "call_assistance": ["help", "emergency", "medical", "security", "wheelchair", "assistance", "urgent"],
    "escort_passenger": ["escort", "accompany", "walk me", "take me", "guide me"],
    "find_nearest": ["nearest", "closest", "find me", "where can i find", "nearby", "coffee", "restaurant", "restroom", "shop", "lounge"],
    "show_map": ["map", "show me", "layout", "floor plan"],
    "get_airline_counter": ["counter", "check-in", "checkin", "airline desk", "boarding pass"],
    "weigh_luggage": ["weigh", "luggage weight", "bag weight", "how heavy", "overweight"],
    "translate_text": ["translate", "language", "say in", "how to say"],
    "set_reminder": ["remind", "reminder", "alert", "notify", "connection", "connecting flight", "layover"],
    "check_wait_time": ["wait time", "queue", "how long", "busy", "line"],
    "get_transport_options": ["taxi", "bus", "train", "uber", "transport", "ride", "shuttle", "metro"],
    "report_incident": ["report", "incident", "lost", "stolen", "found", "suspicious"],
}


# ══════════════════════════════════════════════════════════════════════════════
# REWARD FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def reward_tool_format(prompts: list, completions: list, **kwargs) -> list[float]:
    """Reward for correct <tool_call> JSON format.

    +1.0  has <tool_call> with valid parseable JSON inside
    +0.5  has <tool_call> tag but JSON is malformed
    +0.0  mentions a tool name but no <tool_call> tag
    -0.5  no tool-related output at all
    """
    rewards = []
    for completion in completions:
        text = _extract_text(completion)
        if "<tool_call>" in text:
            # Try to extract and parse JSON
            json_str = _extract_tool_json(text)
            if json_str is not None:
                try:
                    parsed = json.loads(json_str)
                    if "name" in parsed and "arguments" in parsed:
                        rewards.append(1.0)
                    else:
                        rewards.append(0.5)
                except (json.JSONDecodeError, TypeError):
                    rewards.append(0.5)
            else:
                rewards.append(0.5)
        elif any(tool in text.lower() for tool in VALID_TOOLS):
            rewards.append(0.0)
        else:
            rewards.append(-0.5)
    return rewards


def reward_tool_selection(prompts: list, completions: list, **kwargs) -> list[float]:
    """Reward for selecting the correct tool based on query content.

    +1.0  correct tool selected
    +0.3  valid tool but wrong one
    -0.5  no tool or invalid tool
    """
    rewards = []
    for prompt, completion in zip(prompts, completions):
        prompt_text = _extract_text(prompt).lower()
        comp_text = _extract_text(completion)

        # Find which tool was called
        called_tool = _extract_tool_name(comp_text)
        if called_tool is None:
            rewards.append(-0.5)
            continue

        if called_tool not in VALID_TOOLS:
            rewards.append(-0.5)
            continue

        # Determine expected tool from query
        expected = _get_expected_tool(prompt_text)
        if expected is None:
            # Can't determine — give partial credit for any valid tool
            rewards.append(0.3)
        elif called_tool == expected:
            rewards.append(1.0)
        else:
            rewards.append(0.3)

    return rewards


def reward_conciseness(prompts: list, completions: list, **kwargs) -> list[float]:
    """Reward for concise, non-rambling output.

    Penalise outputs that hit max_tokens (256) — likely rambling.
    Reward outputs in the sweet spot (20-150 tokens).
    """
    rewards = []
    for completion in completions:
        text = _extract_text(completion)
        length = len(text.split())

        if length < 5:
            rewards.append(-1.0)      # Too short / empty
        elif length <= 20:
            rewards.append(0.3)       # Very terse — ok for tool calls
        elif length <= 80:
            rewards.append(1.0)       # Sweet spot
        elif length <= 150:
            rewards.append(0.5)       # A bit long
        else:
            rewards.append(-0.5)      # Rambling
    return rewards


def reward_no_repetition(prompts: list, completions: list, **kwargs) -> list[float]:
    """Penalise repetitive text (common failure mode for small models)."""
    rewards = []
    for completion in completions:
        text = _extract_text(completion)
        words = text.lower().split()
        if len(words) < 5:
            rewards.append(0.0)
            continue

        # Check trigram repetition rate
        trigrams = [" ".join(words[i:i+3]) for i in range(len(words) - 2)]
        if not trigrams:
            rewards.append(0.0)
            continue
        unique_ratio = len(set(trigrams)) / len(trigrams)

        if unique_ratio > 0.8:
            rewards.append(1.0)       # Low repetition
        elif unique_ratio > 0.5:
            rewards.append(0.0)       # Some repetition
        else:
            rewards.append(-1.0)      # Heavy repetition
    return rewards


def reward_conversational_quality(prompts: list, completions: list, **kwargs) -> list[float]:
    """Reward for helpful, relevant conversational responses.

    Checks: mentions airport concepts, offers help, is polite.
    """
    rewards = []
    airport_terms = {
        "gate", "terminal", "flight", "luggage", "baggage", "boarding",
        "check-in", "security", "lounge", "passport", "departure",
        "arrival", "counter", "level", "floor", "bus", "taxi", "train",
        "restaurant", "restroom", "shop", "minutes", "walk", "meter",
    }
    help_phrases = [
        "i can", "let me", "shall i", "would you like", "i'll",
        "follow me", "here's", "you'll find", "you can",
    ]

    for prompt, completion in zip(prompts, completions):
        text = _extract_text(completion).lower()

        if len(text) < 10:
            rewards.append(-1.0)
            continue

        score = 0.0

        # Check airport relevance
        term_hits = sum(1 for t in airport_terms if t in text)
        if term_hits >= 3:
            score += 0.5
        elif term_hits >= 1:
            score += 0.2

        # Check helpfulness
        help_hits = sum(1 for p in help_phrases if p in text)
        if help_hits >= 1:
            score += 0.3

        # Check it doesn't just repeat the question
        prompt_text = _extract_text(prompt).lower()
        if text[:50] != prompt_text[:50]:
            score += 0.2

        rewards.append(min(score, 1.0))

    return rewards


# ── Helper functions ─────────────────────────────────────────────────────────

def _extract_text(item) -> str:
    """Extract text from various TRL completion formats."""
    if isinstance(item, str):
        return item
    if isinstance(item, list):
        # List of message dicts
        parts = []
        for msg in item:
            if isinstance(msg, dict):
                parts.append(msg.get("content", ""))
            elif isinstance(msg, str):
                parts.append(msg)
        return " ".join(parts)
    if isinstance(item, dict):
        return item.get("content", str(item))
    return str(item)


def _extract_tool_json(text: str) -> str | None:
    """Extract JSON from <tool_call>...</tool_call> block."""
    match = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    if match:
        return match.group(1)
    # Try without closing tag
    match = re.search(r"<tool_call>\s*(\{.*?\})", text, re.DOTALL)
    if match:
        return match.group(1)
    return None


def _extract_tool_name(text: str) -> str | None:
    """Extract tool name from completion."""
    json_str = _extract_tool_json(text)
    if json_str:
        try:
            parsed = json.loads(json_str)
            return parsed.get("name")
        except (json.JSONDecodeError, TypeError):
            pass
    # Fallback: look for tool name mentions
    for tool in VALID_TOOLS:
        if tool in text.lower():
            return tool
    return None


def _get_expected_tool(query: str) -> str | None:
    """Determine the expected tool from query keywords."""
    query = query.lower()
    best_tool = None
    best_hits = 0
    for tool, keywords in TOOL_ROUTING.items():
        hits = sum(1 for kw in keywords if kw in query)
        if hits > best_hits:
            best_hits = hits
            best_tool = tool
    return best_tool


# ══════════════════════════════════════════════════════════════════════════════
# DATASET PREPARATION
# ══════════════════════════════════════════════════════════════════════════════

def build_rl_dataset(adapter_type: str, max_examples: int = 2000):
    """Build prompt-only dataset for GRPO from existing training data.

    GRPO needs prompts only — the model generates completions, and
    reward functions score them. We extract system+user messages.
    """
    from datasets import Dataset

    if adapter_type == "tool_use":
        data_path = DATA_DIR / "tool_use" / "train.jsonl"
    else:
        data_path = DATA_DIR / "conversational" / "train.jsonl"

    prompts = []
    with open(data_path) as f:
        for i, line in enumerate(f):
            if i >= max_examples:
                break
            example = json.loads(line.strip())
            messages = example["messages"]

            # Extract system + user messages as the prompt
            prompt_msgs = []
            for msg in messages:
                if msg["role"] in ("system", "user"):
                    prompt_msgs.append(msg)
                else:
                    break  # Stop at first assistant message

            if prompt_msgs:
                prompts.append({"prompt": prompt_msgs})

    print(f"Built RL dataset: {len(prompts)} prompts from {data_path.name}")
    return Dataset.from_list(prompts)


def build_eval_dataset(adapter_type: str, max_examples: int = 200):
    """Build eval prompt dataset."""
    from datasets import Dataset

    if adapter_type == "tool_use":
        data_path = DATA_DIR / "tool_use" / "eval.jsonl"
    else:
        data_path = DATA_DIR / "conversational" / "eval.jsonl"

    prompts = []
    with open(data_path) as f:
        for i, line in enumerate(f):
            if i >= max_examples:
                break
            example = json.loads(line.strip())
            messages = example["messages"]

            prompt_msgs = []
            for msg in messages:
                if msg["role"] in ("system", "user"):
                    prompt_msgs.append(msg)
                else:
                    break

            if prompt_msgs:
                prompts.append({"prompt": prompt_msgs})

    print(f"Built RL eval dataset: {len(prompts)} prompts from {data_path.name}")
    return Dataset.from_list(prompts)


# ══════════════════════════════════════════════════════════════════════════════
# TRAINING
# ══════════════════════════════════════════════════════════════════════════════

def train_adapter(adapter_type: str, args):
    """Run GRPO training for a specific adapter."""
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import GRPOConfig, GRPOTrainer

    print(f"\n{'=' * 70}")
    print(f"  GRPO RL Training: {adapter_type}")
    print(f"{'=' * 70}\n")

    # ── Check GPU ────────────────────────────────────────────────────────
    if not torch.cuda.is_available():
        print("ERROR: CUDA GPU required for GRPO training.")
        sys.exit(1)

    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU: {gpu_name} ({vram_gb:.1f} GB)")

    # ── Paths ────────────────────────────────────────────────────────────
    sft_adapter_path = ADAPTER_DIR / adapter_type / "final"
    output_dir = ADAPTER_DIR / adapter_type / "rl"

    if not sft_adapter_path.exists():
        print(f"ERROR: SFT adapter not found: {sft_adapter_path}")
        print("Run finetune.py first to create the base adapter.")
        sys.exit(1)

    print(f"SFT adapter: {sft_adapter_path}")
    print(f"RL output:   {output_dir}")

    # ── Load base model + SFT adapter ────────────────────────────────────
    print("\nLoading base model with SFT LoRA adapter...")
    base_model = "Qwen/Qwen2.5-1.5B-Instruct"

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(str(sft_adapter_path))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load base model + merge SFT adapter → new base for RL
    from peft import AutoPeftModelForCausalLM
    model = AutoPeftModelForCausalLM.from_pretrained(
        str(sft_adapter_path),
        quantization_config=bnb_config,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
        attn_implementation="eager",
    )

    # Merge SFT adapter into the base weights so GRPO trains a fresh LoRA on top
    print("Merging SFT adapter into base weights...")
    model = model.merge_and_unload()

    param_count = sum(p.numel() for p in model.parameters())
    mem_gb = torch.cuda.memory_allocated() / 1e9
    print(f"Model loaded: {param_count / 1e6:.0f}M params, {mem_gb:.2f} GB VRAM")

    # ── New LoRA for RL ──────────────────────────────────────────────────
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
        bias="none",
    )

    # ── Datasets ─────────────────────────────────────────────────────────
    max_train = args.max_examples or (1500 if adapter_type == "tool_use" else 2000)
    train_dataset = build_rl_dataset(adapter_type, max_examples=max_train)
    eval_dataset = build_eval_dataset(adapter_type, max_examples=200)

    # ── Reward functions ─────────────────────────────────────────────────
    if adapter_type == "tool_use":
        reward_funcs = [
            reward_tool_format,
            reward_tool_selection,
            reward_conciseness,
            reward_no_repetition,
        ]
        reward_weights = [2.0, 1.5, 0.5, 1.0]  # Format is most important
    else:
        reward_funcs = [
            reward_conversational_quality,
            reward_conciseness,
            reward_no_repetition,
        ]
        reward_weights = [2.0, 0.5, 1.0]

    # ── GRPO config ──────────────────────────────────────────────────────
    batch_size = args.batch_size
    grad_accum = args.grad_accum
    max_steps = args.max_steps

    # Auto-adjust for VRAM
    if vram_gb < 6.0:
        batch_size = min(batch_size, 1)
        grad_accum = max(grad_accum, 16)
        print(f"Low VRAM — batch={batch_size}, grad_accum={grad_accum}")

    grpo_config = GRPOConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        max_steps=max_steps,
        learning_rate=5e-7,             # Much smaller LR for RL (vs 2e-4 for SFT)
        lr_scheduler_type="cosine",
        warmup_steps=max(10, max_steps // 20),
        weight_decay=0.01,
        max_grad_norm=0.5,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=5,
        save_strategy="steps",
        save_steps=max(50, max_steps // 5),
        save_total_limit=3,
        report_to="none",
        seed=42,
        # GRPO-specific
        num_generations=args.num_generations,   # Completions per prompt
        max_completion_length=args.max_completion_length,
        temperature=0.8,
        top_p=0.9,
        top_k=50,
        beta=0.04,                      # KL penalty coefficient
        loss_type="grpo",
        scale_rewards="group",
        log_completions=True,
        num_completions_to_print=2,
        reward_weights=reward_weights,
    )

    # ── Trainer ──────────────────────────────────────────────────────────
    print(f"\nStarting GRPO training:")
    print(f"  Batch size: {batch_size} × {grad_accum} accum = {batch_size * grad_accum} effective")
    print(f"  Max steps:  {max_steps}")
    print(f"  Num generations per prompt: {args.num_generations}")
    print(f"  Max completion length: {args.max_completion_length}")
    print(f"  Learning rate: {grpo_config.learning_rate}")
    print(f"  Rewards: {[f.__name__ for f in reward_funcs]}")
    print(f"  Reward weights: {reward_weights}")
    print()

    t_start = time.monotonic()

    trainer = GRPOTrainer(
        model=model,
        reward_funcs=reward_funcs,
        args=grpo_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    trainer.train()

    t_elapsed = time.monotonic() - t_start
    print(f"\nTraining complete in {t_elapsed / 60:.1f} minutes")

    # ── Save ─────────────────────────────────────────────────────────────
    final_dir = output_dir / "final"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # Save metadata
    metadata = {
        "adapter_type": adapter_type,
        "training_type": "GRPO",
        "base_model": base_model,
        "sft_adapter": str(sft_adapter_path),
        "max_steps": max_steps,
        "batch_size": batch_size,
        "grad_accum": grad_accum,
        "num_generations": args.num_generations,
        "learning_rate": grpo_config.learning_rate,
        "beta": grpo_config.beta,
        "reward_functions": [f.__name__ for f in reward_funcs],
        "reward_weights": reward_weights,
        "training_time_min": round(t_elapsed / 60, 1),
        "gpu": gpu_name,
        "vram_gb": round(vram_gb, 1),
    }
    with open(final_dir / "rl_training_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"RL adapter saved to: {final_dir}")

    # Cleanup
    del trainer, model
    torch.cuda.empty_cache()

    return metadata


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Parse arguments and run GRPO RL training."""
    parser = argparse.ArgumentParser(
        description="GRPO reinforcement learning for Porter AI Assistant"
    )
    parser.add_argument(
        "--adapter", type=str, choices=["conversational", "tool_use", "both"],
        default="both", help="Which adapter to train (default: both)"
    )
    parser.add_argument(
        "--max-steps", type=int, default=300,
        help="Max training steps (default: 300)"
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
        "--num-generations", type=int, default=4,
        help="Number of completions per prompt for GRPO (default: 4)"
    )
    parser.add_argument(
        "--max-completion-length", type=int, default=256,
        help="Max tokens per generated completion (default: 256)"
    )
    parser.add_argument(
        "--max-examples", type=int, default=None,
        help="Max training prompts to use (default: 1500 tool_use, 2000 conv)"
    )
    args = parser.parse_args()

    adapters = ["conversational", "tool_use"] if args.adapter == "both" else [args.adapter]

    all_results = {}
    for adapter_type in adapters:
        result = train_adapter(adapter_type, args)
        all_results[adapter_type] = result

    # Summary
    print(f"\n{'#' * 70}")
    print(f"  GRPO RL TRAINING COMPLETE")
    print(f"{'#' * 70}")
    for name, meta in all_results.items():
        print(f"  {name:20s}: {meta['max_steps']} steps in {meta['training_time_min']} min")
    print(f"\nNext: run inference_test.py to verify improvement.")
    print(f"  python3 scripts/inference_test.py --adapter-dir models/lora_adapters/<type>/rl/final")


if __name__ == "__main__":
    main()

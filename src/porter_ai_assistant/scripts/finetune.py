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
"""QLoRA fine-tuning for Porter AI Assistant.

Fine-tunes Qwen 2.5 1.5B Instruct with LoRA adapters on airport domain data.
Uses 4-bit quantization (QLoRA) to fit in 8 GB VRAM (RTX 5070).

Produces two modular LoRA adapters:
  - conversational: General airport Q&A, directions, services
  - tool_use: Function calling (escort, luggage, flight lookup)

Usage:
    # Activate the fine-tuning venv first:
    source .venv-finetune/bin/activate

    # Fine-tune conversational adapter (default):
    python3 scripts/finetune.py --adapter conversational

    # Fine-tune tool-use adapter:
    python3 scripts/finetune.py --adapter tool_use

    # Fine-tune both sequentially:
    python3 scripts/finetune.py --adapter both

    # Custom base model:
    python3 scripts/finetune.py --base-model Qwen/Qwen2.5-0.5B-Instruct --adapter conversational

    # Resume from checkpoint:
    python3 scripts/finetune.py --adapter conversational --resume

Requirements:
    pip install torch transformers peft datasets trl bitsandbytes accelerate scipy PyYAML
    (NVIDIA GPU with >=8 GB VRAM required)
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import torch
import yaml

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = SCRIPT_DIR.parent
DATA_DIR = PACKAGE_DIR / "data"
MODELS_DIR = PACKAGE_DIR / "models"
OUTPUT_DIR = MODELS_DIR / "lora_adapters"


# ── Training Configuration ───────────────────────────────────────────────────
@dataclass
class TrainingConfig:
    """QLoRA training hyperparameters optimised for 8 GB VRAM."""

    # Base model
    base_model: str = "Qwen/Qwen2.5-1.5B-Instruct"

    # QLoRA quantization
    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True

    # LoRA config
    lora_r: int = 16                # Rank — 16 is good balance for 1.5B model
    lora_alpha: int = 32            # Alpha = 2 * r is a safe default
    lora_dropout: float = 0.05
    lora_target_modules: list = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ])

    # Training hyperparams
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    per_device_eval_batch_size: int = 4
    gradient_accumulation_steps: int = 4        # Effective batch = 4 * 4 = 16
    learning_rate: float = 2e-4
    weight_decay: float = 0.01
    warmup_ratio: float = 0.03
    lr_scheduler_type: str = "cosine"
    max_seq_length: int = 512                   # Match RPi deployment context window

    # Optimisation
    optim: str = "paged_adamw_8bit"             # Memory-efficient optimiser
    fp16: bool = False
    bf16: bool = True                           # RTX 5070 supports bf16

    # Logging & saving
    logging_steps: int = 10
    save_strategy: str = "steps"
    save_steps: int = 100
    save_total_limit: int = 3
    eval_strategy: str = "steps"
    eval_steps: int = 100

    # Misc
    gradient_checkpointing: bool = True          # Required for 262K vocab — logits tensor too large without it
    max_grad_norm: float = 0.3
    seed: int = 42
    report_to: str = "none"                     # No wandb/tensorboard


# ── Adapter Configurations ───────────────────────────────────────────────────
ADAPTER_CONFIGS = {
    "conversational": {
        "train_data": str(DATA_DIR / "conversational" / "train.jsonl"),
        "eval_data": str(DATA_DIR / "conversational" / "eval.jsonl"),
        "output_dir": str(OUTPUT_DIR / "conversational"),
        "description": "General airport Q&A, directions, services, amenities",
    },
    "tool_use": {
        "train_data": str(DATA_DIR / "tool_use" / "train.jsonl"),
        "eval_data": str(DATA_DIR / "tool_use" / "eval.jsonl"),
        "output_dir": str(OUTPUT_DIR / "tool_use"),
        "description": "Function/tool calling (escort, luggage, flights)",
    },
}


def check_gpu():
    """Verify GPU is available and has enough VRAM."""
    if not torch.cuda.is_available():
        print("ERROR: No CUDA GPU detected. QLoRA requires an NVIDIA GPU.")
        print("Check: nvidia-smi")
        sys.exit(1)

    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU: {gpu_name} ({vram_gb:.1f} GB VRAM)")

    if vram_gb < 6.0:
        print(f"WARNING: {vram_gb:.1f} GB VRAM may be insufficient for QLoRA.")
        print("Minimum recommended: 8 GB. Reduce batch size if OOM occurs.")

    return gpu_name, vram_gb


def load_dataset_jsonl(path: str):
    """Load a JSONL dataset in chat-completion format."""
    from datasets import Dataset

    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    print(f"  Loaded {len(records)} examples from {Path(path).name}")
    return Dataset.from_list(records)


def create_bnb_config(config: TrainingConfig):
    """Create BitsAndBytes 4-bit quantization config."""
    from transformers import BitsAndBytesConfig

    compute_dtype = getattr(torch, config.bnb_4bit_compute_dtype)

    return BitsAndBytesConfig(
        load_in_4bit=config.load_in_4bit,
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_quant_type=config.bnb_4bit_quant_type,
        bnb_4bit_use_double_quant=config.bnb_4bit_use_double_quant,
    )


def load_base_model(config: TrainingConfig):
    """Load the base model with 4-bit quantization."""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"\nLoading base model: {config.base_model}")
    print("  (4-bit quantized — this may take a minute on first download)")

    bnb_config = create_bnb_config(config)

    tokenizer = AutoTokenizer.from_pretrained(
        config.base_model,
        trust_remote_code=True,
    )
    # Qwen uses <|endoftext|> as pad token
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        quantization_config=bnb_config,
        device_map={"": 0},             # Force ALL layers to GPU 0 — no CPU offload
        trust_remote_code=True,
        attn_implementation="eager",  # sdpa can cause issues with QLoRA
    )
    model.config.use_cache = False  # Required for gradient checkpointing

    # Print model size
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"  Model loaded: {total / 1e6:.0f}M params total")

    return model, tokenizer


def create_lora_model(model, config: TrainingConfig):
    """Apply LoRA adapters to the model."""
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    # Prepare model for QLoRA training
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=config.gradient_checkpointing,
    )

    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.lora_target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    pct = 100 * trainable / total
    print(f"  LoRA applied: {trainable / 1e6:.2f}M trainable / "
          f"{total / 1e6:.0f}M total ({pct:.2f}%)")

    return model


def train_adapter(
    adapter_name: str,
    config: TrainingConfig,
    resume: bool = False,
):
    """Fine-tune a single LoRA adapter."""
    from trl import SFTConfig, SFTTrainer

    adapter_info = ADAPTER_CONFIGS[adapter_name]
    output_dir = adapter_info["output_dir"]

    print(f"\n{'='*70}")
    print(f"Training LoRA adapter: {adapter_name}")
    print(f"  {adapter_info['description']}")
    print(f"  Output: {output_dir}")
    print(f"{'='*70}")

    # ── Load data ────────────────────────────────────────────────────────────
    print("\nLoading datasets...")
    train_dataset = load_dataset_jsonl(adapter_info["train_data"])
    eval_dataset = load_dataset_jsonl(adapter_info["eval_data"])

    # ── Load model ───────────────────────────────────────────────────────────
    model, tokenizer = load_base_model(config)
    model = create_lora_model(model, config)

    # ── Configure trainer ────────────────────────────────────────────────────
    training_args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=config.num_train_epochs,
        per_device_train_batch_size=config.per_device_train_batch_size,
        per_device_eval_batch_size=config.per_device_eval_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        warmup_ratio=config.warmup_ratio,
        lr_scheduler_type=config.lr_scheduler_type,
        max_length=config.max_seq_length,
        optim=config.optim,
        fp16=config.fp16,
        bf16=config.bf16,
        logging_steps=config.logging_steps,
        save_strategy=config.save_strategy,
        save_steps=config.save_steps,
        save_total_limit=config.save_total_limit,
        eval_strategy=config.eval_strategy,
        eval_steps=config.eval_steps,
        gradient_checkpointing=config.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_grad_norm=config.max_grad_norm,
        seed=config.seed,
        report_to=config.report_to,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        packing=False,  # Don't pack — our examples are already sized well
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=training_args,
    )

    # ── Train ────────────────────────────────────────────────────────────────
    print(f"\nStarting training...")
    print(f"  Epochs: {config.num_train_epochs}")
    print(f"  Batch: {config.per_device_train_batch_size} × "
          f"{config.gradient_accumulation_steps} = "
          f"{config.per_device_train_batch_size * config.gradient_accumulation_steps}")
    print(f"  LR: {config.learning_rate}")
    print(f"  Max seq len: {config.max_seq_length}")
    print()

    start_time = time.monotonic()

    if resume:
        # Find latest checkpoint
        checkpoints = sorted(Path(output_dir).glob("checkpoint-*"))
        if checkpoints:
            print(f"  Resuming from: {checkpoints[-1]}")
            trainer.train(resume_from_checkpoint=str(checkpoints[-1]))
        else:
            print("  No checkpoint found, starting fresh.")
            trainer.train()
    else:
        trainer.train()

    elapsed = time.monotonic() - start_time
    print(f"\nTraining complete in {elapsed / 60:.1f} minutes")

    # ── Save final adapter ───────────────────────────────────────────────────
    final_dir = Path(output_dir) / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    print(f"Saving final adapter to: {final_dir}")
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # Save training metadata
    metadata = {
        "adapter_name": adapter_name,
        "base_model": config.base_model,
        "lora_r": config.lora_r,
        "lora_alpha": config.lora_alpha,
        "lora_target_modules": config.lora_target_modules,
        "num_train_epochs": config.num_train_epochs,
        "learning_rate": config.learning_rate,
        "max_seq_length": config.max_seq_length,
        "train_examples": len(train_dataset),
        "eval_examples": len(eval_dataset),
        "training_time_minutes": round(elapsed / 60, 1),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A",
        "final_train_loss": trainer.state.log_history[-1].get("train_loss", None),
        "best_eval_loss": trainer.state.best_metric,
    }
    with open(final_dir / "training_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to: {final_dir / 'training_metadata.json'}")

    # ── Evaluate ─────────────────────────────────────────────────────────────
    print("\nRunning final evaluation...")
    eval_results = trainer.evaluate()
    print(f"  Eval loss: {eval_results['eval_loss']:.4f}")

    # Clean up GPU memory
    del model, trainer
    torch.cuda.empty_cache()

    return eval_results


def main():
    """Parse arguments and run fine-tuning."""
    parser = argparse.ArgumentParser(
        description="QLoRA fine-tuning for Porter AI Assistant"
    )
    parser.add_argument(
        "--adapter",
        type=str,
        default="conversational",
        choices=["conversational", "tool_use", "both"],
        help="Which adapter to train (default: conversational)",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="Qwen/Qwen2.5-1.5B-Instruct",
        help="HuggingFace base model ID (default: Qwen/Qwen2.5-1.5B-Instruct)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs (default: 3)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Per-device batch size (default: 4)",
    )
    parser.add_argument(
        "--grad-accum",
        type=int,
        default=4,
        help="Gradient accumulation steps (default: 4)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=2e-4,
        help="Learning rate (default: 2e-4)",
    )
    parser.add_argument(
        "--lora-r",
        type=int,
        default=16,
        help="LoRA rank (default: 16)",
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=32,
        help="LoRA alpha (default: 32)",
    )
    parser.add_argument(
        "--max-seq-len",
        type=int,
        default=512,
        help="Max sequence length (default: 512)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from latest checkpoint",
    )
    parser.add_argument(
        "--no-4bit",
        action="store_true",
        help="Disable 4-bit quantization (needs >16 GB VRAM)",
    )

    args = parser.parse_args()

    # ── GPU check ────────────────────────────────────────────────────────────
    gpu_name, vram_gb = check_gpu()

    # ── Build config ─────────────────────────────────────────────────────────
    config = TrainingConfig(
        base_model=args.base_model,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        max_seq_length=args.max_seq_len,
        load_in_4bit=not args.no_4bit,
    )

    # Auto-adjust for smaller VRAM
    if vram_gb < 6 and config.per_device_train_batch_size > 2:
        print(f"  Reducing batch size to 2 for {vram_gb:.0f} GB VRAM")
        config.per_device_train_batch_size = 2
        config.gradient_accumulation_steps = 8  # Keep effective batch = 16
        config.gradient_checkpointing = True    # Enable to save VRAM on small GPUs

    print(f"\nConfiguration:")
    print(f"  Base model:     {config.base_model}")
    print(f"  4-bit QLoRA:    {config.load_in_4bit}")
    print(f"  LoRA rank:      {config.lora_r}")
    print(f"  LoRA alpha:     {config.lora_alpha}")
    print(f"  Epochs:         {config.num_train_epochs}")
    print(f"  Effective batch: {config.per_device_train_batch_size * config.gradient_accumulation_steps}")
    print(f"  Learning rate:  {config.learning_rate}")
    print(f"  Max seq len:    {config.max_seq_length}")

    # ── Train ────────────────────────────────────────────────────────────────
    adapters_to_train = (
        ["conversational", "tool_use"] if args.adapter == "both"
        else [args.adapter]
    )

    all_results = {}
    for adapter_name in adapters_to_train:
        results = train_adapter(adapter_name, config, resume=args.resume)
        all_results[adapter_name] = results

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("TRAINING SUMMARY")
    print(f"{'='*70}")
    for name, results in all_results.items():
        print(f"  {name}: eval_loss = {results['eval_loss']:.4f}")
    print(f"\nAdapters saved to: {OUTPUT_DIR}")
    print(f"\nNext steps:")
    print(f"  1. Convert to GGUF: python3 scripts/convert_to_gguf.py")
    print(f"  2. Benchmark:       python3 scripts/benchmark.py --model <gguf_path>")
    print(f"  3. Deploy to RPi:   Copy GGUF to porter_ai_assistant/models/")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

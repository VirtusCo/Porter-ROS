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
"""Convert fine-tuned LoRA adapter to GGUF for RPi deployment.

Merges the LoRA adapter into the base model, exports to HuggingFace
format, then converts to GGUF with quantization. The resulting GGUF
file runs on the RPi via llama-cpp-python.

Pipeline: LoRA adapter + base model → merged HF model → GGUF (quantized)

Usage:
    # Activate the fine-tuning venv first:
    source .venv-finetune/bin/activate

    # Convert conversational adapter to GGUF Q4_K_M:
    python3 scripts/convert_to_gguf.py --adapter conversational

    # Convert with different quantization:
    python3 scripts/convert_to_gguf.py --adapter conversational --quant Q8_0

    # Convert tool-use adapter:
    python3 scripts/convert_to_gguf.py --adapter tool_use

    # Both adapters:
    python3 scripts/convert_to_gguf.py --adapter both

Requirements:
    pip install torch transformers peft
    llama.cpp must be cloned for convert_hf_to_gguf.py
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import torch

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = SCRIPT_DIR.parent
MODELS_DIR = PACKAGE_DIR / "models"
LORA_DIR = MODELS_DIR / "lora_adapters"
MERGED_DIR = MODELS_DIR / "merged"
GGUF_DIR = MODELS_DIR / "gguf"

# Default llama.cpp location — user can override with --llama-cpp
DEFAULT_LLAMA_CPP_DIR = Path.home() / "llama.cpp"

# Available quantization types (from llama.cpp)
QUANT_TYPES = {
    "Q4_K_M": "4-bit (medium) — best RPi 5 balance (~1.0 GB for 1.5B)",
    "Q4_K_S": "4-bit (small) — slightly smaller, slightly less accurate",
    "Q5_K_M": "5-bit (medium) — better quality, more RAM (~1.2 GB for 1.5B)",
    "Q8_0": "8-bit — highest quality, needs >2 GB RAM (~1.6 GB for 1.5B)",
    "Q4_0": "4-bit (basic) — fastest, lowest quality",
    "Q5_0": "5-bit (basic) — balanced basic",
}


def check_llama_cpp(llama_cpp_dir: Path) -> Path:
    """Verify llama.cpp is available for GGUF conversion."""
    convert_script = llama_cpp_dir / "convert_hf_to_gguf.py"
    quantize_bin = llama_cpp_dir / "build" / "bin" / "llama-quantize"

    if not convert_script.exists():
        print(f"ERROR: llama.cpp not found at {llama_cpp_dir}")
        print()
        print("Install llama.cpp:")
        print(f"  git clone https://github.com/ggerganov/llama.cpp {llama_cpp_dir}")
        print(f"  cd {llama_cpp_dir}")
        print("  cmake -B build -DCMAKE_BUILD_TYPE=Release")
        print("  cmake --build build --config Release -j $(nproc)")
        print()
        print("Or specify path: --llama-cpp /path/to/llama.cpp")
        sys.exit(1)

    if not quantize_bin.exists():
        # Try alternate location
        quantize_bin = llama_cpp_dir / "build" / "llama-quantize"
        if not quantize_bin.exists():
            print(f"WARNING: llama-quantize not found at expected paths.")
            print(f"  Build it: cd {llama_cpp_dir} && cmake -B build && cmake --build build")
            print("  Conversion will produce unquantized GGUF (F16).")
            return convert_script

    return convert_script


def merge_lora_adapter(
    adapter_dir: str,
    base_model: str,
    output_dir: str,
) -> str:
    """Merge LoRA adapter into base model and save as full HF model."""
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    output_path = Path(output_dir)
    if output_path.exists():
        print(f"  Merged model already exists: {output_path}")
        print("  Use --force to re-merge.")
        return str(output_path)

    print(f"\n  Loading base model: {base_model}")
    print("  (Full precision for merging — needs more RAM temporarily)")

    # Load base model in full precision for clean merge
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

    print(f"  Loading LoRA adapter: {adapter_dir}")
    # Load tokenizer from adapter (may have extra tokens from fine-tuning)
    adapter_tokenizer = AutoTokenizer.from_pretrained(
        adapter_dir, trust_remote_code=True,
    )

    # Resize model embeddings if adapter's tokenizer is larger (e.g. pad token added)
    if len(adapter_tokenizer) > model.config.vocab_size:
        print(f"  Resizing embeddings: {model.config.vocab_size} → {len(adapter_tokenizer)}")
        model.resize_token_embeddings(len(adapter_tokenizer))

    model = PeftModel.from_pretrained(model, adapter_dir)

    print("  Merging LoRA weights into base model...")
    model = model.merge_and_unload()

    print(f"  Saving merged model to: {output_path}")
    output_path.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_path))
    adapter_tokenizer.save_pretrained(str(output_path))

    # Copy tokenizer.model (SentencePiece) if available from base model cache.
    # llama.cpp convert needs this file for proper vocab handling.
    from huggingface_hub import try_to_load_from_cache

    sp_path = try_to_load_from_cache(base_model, "tokenizer.model")
    if sp_path and isinstance(sp_path, (str, Path)) and Path(sp_path).exists():
        dest = output_path / "tokenizer.model"
        if not dest.exists():
            shutil.copy2(str(sp_path), str(dest))
            print(f"  Copied tokenizer.model from base model cache")

    # Report size
    total_size = sum(
        f.stat().st_size for f in output_path.rglob("*") if f.is_file()
    )
    print(f"  Merged model size: {total_size / 1e9:.2f} GB")

    # Clean up GPU memory
    del model
    torch.cuda.empty_cache()

    return str(output_path)


def convert_to_gguf(
    merged_dir: str,
    output_path: str,
    convert_script: Path,
):
    """Convert HuggingFace model to GGUF F16 format."""
    print(f"\n  Converting to GGUF (F16): {output_path}")

    cmd = [
        sys.executable,
        str(convert_script),
        merged_dir,
        "--outfile", output_path,
        "--outtype", "f16",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  ERROR: GGUF conversion failed:")
        print(f"  {result.stderr[-500:]}")
        sys.exit(1)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  GGUF F16 created: {size_mb:.0f} MB")
    return output_path


def quantize_gguf(
    input_path: str,
    output_path: str,
    quant_type: str,
    llama_cpp_dir: Path,
):
    """Quantize GGUF F16 to a smaller quantization level."""
    # Find llama-quantize binary
    quantize_bin = None
    for candidate in [
        llama_cpp_dir / "build" / "bin" / "llama-quantize",
        llama_cpp_dir / "build" / "llama-quantize",
        llama_cpp_dir / "llama-quantize",
    ]:
        if candidate.exists():
            quantize_bin = candidate
            break

    if quantize_bin is None:
        print(f"  WARNING: llama-quantize not found. Keeping F16 GGUF.")
        print(f"  Build llama.cpp to get quantize tool.")
        return input_path

    print(f"\n  Quantizing to {quant_type}: {output_path}")

    cmd = [
        str(quantize_bin),
        input_path,
        output_path,
        quant_type,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  ERROR: Quantization failed:")
        print(f"  {result.stderr[-500:]}")
        return input_path

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Quantized GGUF ({quant_type}): {size_mb:.0f} MB")
    return output_path


def process_adapter(
    adapter_name: str,
    base_model: str,
    quant_type: str,
    llama_cpp_dir: Path,
    convert_script: Path,
    force: bool = False,
    variant: str = "sft",
):
    """Full pipeline: merge LoRA → HF → GGUF F16 → quantized GGUF."""
    if variant == "dpo":
        adapter_dir = LORA_DIR / adapter_name / "dpo" / "final"
    else:
        adapter_dir = LORA_DIR / adapter_name / "final"
    if not adapter_dir.exists():
        print(f"ERROR: Adapter not found: {adapter_dir}")
        print(f"Run fine-tuning first: python3 scripts/finetune.py --adapter {adapter_name}")
        sys.exit(1)

    # Read training metadata if available
    meta_path = adapter_dir / "training_metadata.json"
    if not meta_path.exists():
        meta_path = adapter_dir / "dpo_training_metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        base_model = meta.get("base_model", base_model)
        print(f"  Using base model from metadata: {base_model}")

    variant_label = f"{adapter_name}-{variant}" if variant != "sft" else adapter_name

    print(f"\n{'='*70}")
    print(f"Converting adapter: {variant_label}")
    print(f"  Base model: {base_model}")
    print(f"  Adapter:    {adapter_dir}")
    print(f"  Variant:    {variant}")
    print(f"  Quant:      {quant_type}")
    print(f"{'='*70}")

    # Step 1: Merge LoRA into base model
    merged_dir = str(MERGED_DIR / variant_label)
    if force and Path(merged_dir).exists():
        shutil.rmtree(merged_dir)

    merged_path = merge_lora_adapter(
        adapter_dir=str(adapter_dir),
        base_model=base_model,
        output_dir=merged_dir,
    )

    # Step 2: Convert to GGUF F16
    GGUF_DIR.mkdir(parents=True, exist_ok=True)
    model_short = base_model.split("/")[-1]
    f16_path = str(GGUF_DIR / f"porter-{variant_label}-{model_short}-f16.gguf")

    if not Path(f16_path).exists() or force:
        convert_to_gguf(merged_path, f16_path, convert_script)
    else:
        print(f"\n  F16 GGUF exists: {f16_path}")

    # Step 3: Quantize
    quant_path = str(GGUF_DIR / f"porter-{variant_label}-{model_short}-{quant_type}.gguf")

    if not Path(quant_path).exists() or force:
        quantize_gguf(f16_path, quant_path, quant_type, llama_cpp_dir)
    else:
        print(f"\n  Quantized GGUF exists: {quant_path}")

    # Optionally remove F16 to save space (it's large)
    if Path(f16_path).exists() and Path(quant_path).exists() and f16_path != quant_path:
        f16_size = os.path.getsize(f16_path) / (1024 * 1024)
        quant_size = os.path.getsize(quant_path) / (1024 * 1024)
        print(f"\n  F16 ({f16_size:.0f} MB) can be deleted to save space.")
        print(f"  Quantized file: {quant_size:.0f} MB")

    return quant_path


def main():
    """Parse arguments and run conversion pipeline."""
    parser = argparse.ArgumentParser(
        description="Convert LoRA adapters to GGUF for RPi deployment"
    )
    parser.add_argument(
        "--adapter",
        type=str,
        default="conversational",
        choices=["conversational", "tool_use", "both"],
        help="Which adapter to convert (default: conversational)",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="Qwen/Qwen2.5-1.5B-Instruct",
        help="HuggingFace base model (default: Qwen/Qwen2.5-1.5B-Instruct)",
    )
    parser.add_argument(
        "--quant",
        type=str,
        default="Q4_K_M",
        choices=list(QUANT_TYPES.keys()),
        help="Quantization type (default: Q4_K_M)",
    )
    parser.add_argument(
        "--llama-cpp",
        type=str,
        default=str(DEFAULT_LLAMA_CPP_DIR),
        help=f"Path to llama.cpp directory (default: {DEFAULT_LLAMA_CPP_DIR})",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default="sft",
        choices=["sft", "dpo"],
        help="Adapter variant to convert (default: sft)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-conversion even if output exists",
    )
    parser.add_argument(
        "--list-quants",
        action="store_true",
        help="List available quantization types and exit",
    )

    args = parser.parse_args()

    if args.list_quants:
        print("\nAvailable quantization types:")
        for qt, desc in QUANT_TYPES.items():
            marker = " ← recommended" if qt == "Q4_K_M" else ""
            print(f"  {qt}: {desc}{marker}")
        return

    llama_cpp_dir = Path(args.llama_cpp)
    convert_script = check_llama_cpp(llama_cpp_dir)

    adapters = (
        ["conversational", "tool_use"] if args.adapter == "both"
        else [args.adapter]
    )

    results = {}
    for adapter_name in adapters:
        gguf_path = process_adapter(
            adapter_name=adapter_name,
            base_model=args.base_model,
            quant_type=args.quant,
            llama_cpp_dir=llama_cpp_dir,
            convert_script=convert_script,
            force=args.force,
            variant=args.variant,
        )
        results[adapter_name] = gguf_path

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("CONVERSION COMPLETE")
    print(f"{'='*70}")
    for name, path in results.items():
        size_mb = os.path.getsize(path) / (1024 * 1024) if Path(path).exists() else 0
        print(f"  {name}: {path} ({size_mb:.0f} MB)")
    print()
    print("Deploy to RPi:")
    print("  scp models/gguf/*.gguf pi@<rpi-ip>:/path/to/porter_ai_assistant/models/")
    print()
    print("Benchmark on RPi:")
    print("  python3 scripts/benchmark.py --model models/gguf/<file>.gguf")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

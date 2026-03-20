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
"""Download and prepare GGUF models for Porter AI Assistant.

Downloads pre-quantized GGUF models from HuggingFace Hub for use with
llama-cpp-python on Raspberry Pi 4/5.

Usage:
    python3 scripts/download_model.py --model qwen2.5-1.5b --quant Q4_K_M
    python3 scripts/download_model.py --model qwen2.5-1.5b --quant Q8_0
    python3 scripts/download_model.py --list

Models are saved to the models/ directory (Git LFS tracked).
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

# ── Model Registry ───────────────────────────────────────────────────────────
# Maps model aliases to HuggingFace GGUF repository info.
# Using community-quantized GGUF files from HuggingFace.
MODEL_REGISTRY = {
    "qwen2.5-1.5b": {
        "description": "Qwen 2.5 1.5B Instruct — community gold standard sub-2B (primary)",
        "hf_repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "quants": {
            "Q4_K_M": {
                "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
                "size_mb": 1000,
                "description": "4-bit (medium) — best RPi 5 balance (~1.0 GB)",
            },
            "Q4_K_S": {
                "filename": "qwen2.5-1.5b-instruct-q4_k_s.gguf",
                "size_mb": 960,
                "description": "4-bit (small) — slightly smaller, slightly less accurate",
            },
            "Q5_K_M": {
                "filename": "qwen2.5-1.5b-instruct-q5_k_m.gguf",
                "size_mb": 1120,
                "description": "5-bit (medium) — better quality, ~1.1 GB",
            },
            "Q6_K": {
                "filename": "qwen2.5-1.5b-instruct-q6_k.gguf",
                "size_mb": 1290,
                "description": "6-bit — high quality, ~1.3 GB",
            },
            "Q8_0": {
                "filename": "qwen2.5-1.5b-instruct-q8_0.gguf",
                "size_mb": 1620,
                "description": "8-bit — highest quality, ~1.6 GB",
            },
            "F16": {
                "filename": "qwen2.5-1.5b-instruct-fp16.gguf",
                "size_mb": 3090,
                "description": "Full precision float16 — reference quality (~3 GB)",
            },
        },
        "recommended": "Q4_K_M",
    },
    "qwen2.5-0.5b": {
        "description": "Qwen 2.5 0.5B Instruct — fallback for RPi 4 (smaller, faster)",
        "hf_repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "quants": {
            "Q4_K_M": {
                "filename": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
                "size_mb": 397,
                "description": "4-bit (medium) — tiny, fast (~400 MB)",
            },
            "Q8_0": {
                "filename": "qwen2.5-0.5b-instruct-q8_0.gguf",
                "size_mb": 531,
                "description": "8-bit — better quality, still small (~530 MB)",
            },
        },
        "recommended": "Q4_K_M",
    },
    "gemma-3-270m": {
        "description": "Google Gemma 3 270M Instruct — legacy (replaced by Qwen 2.5)",
        "hf_repo": "unsloth/gemma-3-270m-it-GGUF",
        "quants": {
            "Q4_K_M": {
                "filename": "gemma-3-270m-it-Q4_K_M.gguf",
                "size_mb": 253,
                "description": "4-bit (medium) — ~253 MB (legacy)",
            },
            "Q8_0": {
                "filename": "gemma-3-270m-it-Q8_0.gguf",
                "size_mb": 292,
                "description": "8-bit — ~292 MB (legacy)",
            },
        },
        "recommended": "Q4_K_M",
    },
}

# ── Output directory ─────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
MODELS_DIR = SCRIPT_DIR.parent / "models" / "gguf"


def list_models():
    """Print available models and quantization options."""
    print("\n=== Porter AI Assistant — Available Models ===\n")
    for alias, info in MODEL_REGISTRY.items():
        print(f"  {alias}: {info['description']}")
        if info.get("note"):
            print(f"    NOTE: {info['note']}")
        if info["quants"]:
            print(f"    HuggingFace repo: {info['hf_repo']}")
            print(f"    Recommended: {info['recommended']}")
            print("    Quantizations:")
            for qname, qinfo in info["quants"].items():
                marker = " ← recommended" if qname == info["recommended"] else ""
                print(
                    f"      {qname}: {qinfo['filename']} "
                    f"({qinfo['size_mb']} MB) — {qinfo['description']}{marker}"
                )
        print()


def download_model(model_alias: str, quant: str, force: bool = False):
    """Download a GGUF model from HuggingFace Hub."""
    if model_alias not in MODEL_REGISTRY:
        print(f"ERROR: Unknown model '{model_alias}'")
        print(f"Available: {', '.join(MODEL_REGISTRY.keys())}")
        sys.exit(1)

    model_info = MODEL_REGISTRY[model_alias]

    if model_info.get("note") and not model_info["quants"]:
        print(f"ERROR: {model_info['note']}")
        print("Use 'qwen2.5-0.5b' with Q4_K_M instead.")
        sys.exit(1)

    if quant not in model_info["quants"]:
        print(f"ERROR: Unknown quantization '{quant}' for {model_alias}")
        print(f"Available: {', '.join(model_info['quants'].keys())}")
        sys.exit(1)

    qinfo = model_info["quants"][quant]
    output_path = MODELS_DIR / qinfo["filename"]

    if output_path.exists() and not force:
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"Model already exists: {output_path} ({size_mb:.1f} MB)")
        print("Use --force to re-download.")
        return str(output_path)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Downloading {model_alias} {quant} ===")
    print(f"  Repo:     {model_info['hf_repo']}")
    print(f"  File:     {qinfo['filename']}")
    print(f"  Size:     ~{qinfo['size_mb']} MB")
    print(f"  Output:   {output_path}")
    print()

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub not installed.")
        print("Install it: pip install huggingface-hub")
        print()
        print("Or download manually:")
        print(
            f"  wget https://huggingface.co/{model_info['hf_repo']}"
            f"/resolve/main/{qinfo['filename']} -O {output_path}"
        )
        sys.exit(1)

    try:
        downloaded_path = hf_hub_download(
            repo_id=model_info["hf_repo"],
            filename=qinfo["filename"],
            local_dir=str(MODELS_DIR),
            local_dir_use_symlinks=False,
        )
        print(f"\nDownloaded: {downloaded_path}")

        # Verify size
        actual_size = os.path.getsize(downloaded_path) / (1024 * 1024)
        print(f"Size: {actual_size:.1f} MB (expected ~{qinfo['size_mb']} MB)")

        if actual_size < qinfo["size_mb"] * 0.5:
            print("WARNING: File seems too small — may be corrupted.")

        return downloaded_path

    except Exception as e:
        print(f"ERROR: Download failed: {e}")
        print()
        print("Manual download:")
        print(
            f"  wget https://huggingface.co/{model_info['hf_repo']}"
            f"/resolve/main/{qinfo['filename']} -O {output_path}"
        )
        sys.exit(1)


def verify_model(model_path: str):
    """Verify a GGUF model file is valid."""
    path = Path(model_path)
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        return False

    size_mb = path.stat().st_size / (1024 * 1024)

    # Check GGUF magic bytes
    with open(path, "rb") as f:
        magic = f.read(4)

    if magic != b"GGUF":
        print(f"ERROR: Not a valid GGUF file (magic: {magic!r})")
        return False

    # Compute SHA256
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    print(f"Model: {path.name}")
    print(f"Size:  {size_mb:.1f} MB")
    print(f"Magic: GGUF ✓")
    print(f"SHA256: {sha256.hexdigest()}")
    return True


def main():
    """Parse arguments and execute download or list command."""
    parser = argparse.ArgumentParser(
        description="Download GGUF models for Porter AI Assistant"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="qwen2.5-1.5b",
        help="Model alias (default: qwen2.5-1.5b)",
    )
    parser.add_argument(
        "--quant",
        type=str,
        default="Q4_K_M",
        help="Quantization level (default: Q4_K_M)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available models and exit",
    )
    parser.add_argument(
        "--verify",
        type=str,
        metavar="PATH",
        help="Verify a GGUF model file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if file exists",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory (default: models/)",
    )

    args = parser.parse_args()

    if args.output_dir:
        global MODELS_DIR
        MODELS_DIR = Path(args.output_dir)

    if args.list:
        list_models()
        return

    if args.verify:
        ok = verify_model(args.verify)
        sys.exit(0 if ok else 1)

    download_model(args.model, args.quant, force=args.force)


if __name__ == "__main__":
    main()

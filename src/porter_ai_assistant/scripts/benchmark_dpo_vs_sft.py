#!/usr/bin/env python3
# Copyright 2026 VirtusCo
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Compare DPO-trained vs SFT-only GGUF models.

Runs identical prompts against SFT and DPO variants, comparing:
- Response quality (manual inspection)
- Latency
- Tool call accuracy (for tool_use models)

Usage:
    source .venv-finetune/bin/activate
    python3 scripts/benchmark_dpo_vs_sft.py
"""

import json
import sys
import time
from pathlib import Path

try:
    from llama_cpp import Llama
except ImportError:
    print("ERROR: pip install llama-cpp-python")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
MODELS_DIR = SCRIPT_DIR.parent / "models"
GGUF_DIR = MODELS_DIR / "gguf"
DATA_DIR = SCRIPT_DIR.parent / "data"

# Model paths
MODELS = {
    "conv_sft": GGUF_DIR / "porter-conversational-Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
    "conv_dpo": GGUF_DIR / "porter-conversational-dpo-Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
    "tool_sft": GGUF_DIR / "porter-tool_use-Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
    "tool_dpo": GGUF_DIR / "porter-tool_use-dpo-Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
}

# Test prompts for conversational model
CONV_PROMPTS = [
    "Where is Gate B7?",
    "What restaurants are near Terminal 2?",
    "My flight is delayed, what should I do?",
    "Where can I find a wheelchair?",
    "Is there free WiFi at the airport?",
    "How do I get to baggage claim from Gate A3?",
    "What time does the lounge close?",
    "Can you help me find a charging station?",
    "Where is the nearest restroom?",
    "I need to exchange currency, where can I go?",
]

# System prompts
CONV_SYSTEM = (
    "You are Virtue, the friendly AI assistant on a Porter airport robot made by VirtusCo. "
    "You help passengers with directions, flight info, dining, services, and accessibility. "
    "Be concise, helpful, and warm."
)

# Load the compact tool prompt from training data
TOOL_SYSTEM = None
tool_prompts_file = DATA_DIR / "system_prompts.yaml"
if tool_prompts_file.exists():
    import yaml
    with open(tool_prompts_file) as f:
        prompts = yaml.safe_load(f)
    TOOL_SYSTEM = prompts.get("tool_use", "")

# Test prompts for tool_use model
TOOL_PROMPTS = [
    "What is the status of flight BA456?",
    "Can you find the nearest coffee shop?",
    "I need directions to Gate C12.",
    "What's the weather forecast for today?",
    "Check if flight EK202 is on time.",
    "Where is the closest ATM?",
    "Find me a restaurant that serves sushi.",
    "I need to weigh my luggage.",
    "What time is sunset today?",
    "Where can I find a pharmacy nearby?",
]


def run_comparison(model_name: str, model_path: Path, prompts: list, system: str, n_runs: int = 10):
    """Run benchmark for a single model."""
    if not model_path.exists():
        print(f"  SKIP: {model_path.name} not found")
        return None

    print(f"\n  Loading: {model_path.name}")
    llm = Llama(
        model_path=str(model_path),
        n_ctx=768,
        n_threads=4,
        n_gpu_layers=-1,  # Use GPU if available
        verbose=False,
    )

    results = []
    for i, prompt in enumerate(prompts[:n_runs]):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        t0 = time.monotonic()
        response = llm.create_chat_completion(
            messages=messages,
            max_tokens=256,
            temperature=0.7,
            top_p=0.9,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000

        text = response["choices"][0]["message"]["content"]
        tokens_out = response["usage"]["completion_tokens"]
        tok_per_sec = tokens_out / (elapsed_ms / 1000) if elapsed_ms > 0 else 0

        results.append({
            "prompt": prompt,
            "response": text[:200],  # Truncate for display
            "latency_ms": round(elapsed_ms),
            "tokens": tokens_out,
            "tok_per_sec": round(tok_per_sec, 1),
        })

        status = "OK" if elapsed_ms < 2000 else "SLOW"
        print(f"    [{status}] {elapsed_ms:.0f}ms | {tokens_out}tok | {tok_per_sec:.1f}t/s | {prompt[:40]}")

    # Aggregate stats
    latencies = [r["latency_ms"] for r in results]
    under_2s = sum(1 for l in latencies if l < 2000) / len(latencies) * 100

    stats = {
        "model": model_path.name,
        "n_runs": len(results),
        "avg_latency_ms": round(sum(latencies) / len(latencies)),
        "p50_latency_ms": round(sorted(latencies)[len(latencies) // 2]),
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)]),
        "min_latency_ms": min(latencies),
        "max_latency_ms": max(latencies),
        "pct_under_2s": round(under_2s, 1),
        "avg_tok_per_sec": round(sum(r["tok_per_sec"] for r in results) / len(results), 1),
        "results": results,
    }

    # For tool_use: check how many responses contain tool calls
    if "tool" in model_name:
        tool_calls = sum(1 for r in results if "<tool_call>" in r["response"])
        stats["tool_call_rate"] = round(tool_calls / len(results) * 100, 1)

    del llm
    return stats


def main():
    """Run SFT vs DPO comparison benchmarks."""
    print("=" * 70)
    print("  DPO vs SFT Benchmark Comparison")
    print("=" * 70)

    all_results = {}

    # --- Conversational ---
    print("\n--- CONVERSATIONAL MODELS ---")
    for name in ["conv_sft", "conv_dpo"]:
        path = MODELS[name]
        stats = run_comparison(name, path, CONV_PROMPTS, CONV_SYSTEM)
        if stats:
            all_results[name] = stats

    # --- Tool Use ---
    print("\n--- TOOL USE MODELS ---")
    for name in ["tool_sft", "tool_dpo"]:
        path = MODELS[name]
        stats = run_comparison(name, path, TOOL_PROMPTS, TOOL_SYSTEM)
        if stats:
            all_results[name] = stats

    # --- Summary Table ---
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"{'Model':<45} {'Avg ms':>8} {'P50 ms':>8} {'<2s':>6} {'tok/s':>7} {'Tool%':>6}")
    print("-" * 80)
    for name, stats in all_results.items():
        tool_rate = f"{stats.get('tool_call_rate', '-'):>5}%" if "tool_call_rate" in stats else "   N/A"
        print(f"{stats['model']:<45} {stats['avg_latency_ms']:>8} {stats['p50_latency_ms']:>8} {stats['pct_under_2s']:>5}% {stats['avg_tok_per_sec']:>7} {tool_rate}")

    # --- Side-by-side response comparison ---
    print("\n" + "=" * 70)
    print("  SAMPLE RESPONSE COMPARISON")
    print("=" * 70)

    for category, sft_name, dpo_name in [("Conversational", "conv_sft", "conv_dpo"), ("Tool Use", "tool_sft", "tool_dpo")]:
        if sft_name in all_results and dpo_name in all_results:
            print(f"\n--- {category} ---")
            sft_results = all_results[sft_name]["results"]
            dpo_results = all_results[dpo_name]["results"]
            for i in range(min(3, len(sft_results))):
                print(f"\n  Q: {sft_results[i]['prompt']}")
                print(f"  SFT: {sft_results[i]['response'][:150]}")
                print(f"  DPO: {dpo_results[i]['response'][:150]}")

    # Save results
    out_path = MODELS_DIR / "dpo_vs_sft_benchmark.json"
    # Remove per-run results for cleaner JSON
    summary = {}
    for name, stats in all_results.items():
        summary[name] = {k: v for k, v in stats.items() if k != "results"}
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()

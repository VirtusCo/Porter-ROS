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
r"""Benchmark GGUF model inference on the current hardware.

Measures latency, throughput, and memory usage for the Porter AI Assistant
models. Designed to run on RPi 4/5 to validate <2s latency constraint.

Supports base GGUF + optional LoRA adapter (runtime loading pattern).

Usage:
    # Base model only
    python3 scripts/benchmark.py --model models/gguf/qwen2.5-1.5b-instruct-q4_k_m.gguf

    # Base model + LoRA adapter
    python3 scripts/benchmark.py --model models/gguf/qwen2.5-1.5b-instruct-q4_k_m.gguf \\
        --lora models/gguf/porter-conversational-lora-f16.gguf

    # With options
    python3 scripts/benchmark.py --model models/gguf/qwen2.5-1.5b-instruct-q4_k_m.gguf \\
        --lora models/gguf/porter-conversational-lora-f16.gguf \\
        --n-runs 50 --output bench.json

Requirements:
    pip install llama-cpp-python psutil
"""

import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None


# ── Test Prompts ─────────────────────────────────────────────────────────────
# Representative airport queries for realistic benchmarking
TEST_PROMPTS = [
    # Short queries (typical passenger questions)
    "Where is Gate B12?",
    "What time does my flight board?",
    "Where can I find an ATM?",
    "Is there free WiFi?",
    "Where is the nearest restroom?",
    # Medium queries
    "I need to get to Terminal 2 from here. Can you help me find the way?",
    "My flight AI-302 to Mumbai has been delayed. What should I do?",
    "Can you recommend a good vegetarian restaurant in the airport?",
    "I have a connecting flight in 2 hours. Will I make it through security?",
    "I lost my luggage. Where do I report it?",
    # Long / complex queries
    (
        "I'm traveling with my elderly mother who needs wheelchair assistance. "
        "We need to get to Gate C15 for our flight to Delhi at 3 PM. "
        "Can you help us?"
    ),
    (
        "I have 4 hours until my next flight. I'd like to find a lounge, "
        "get some food, and maybe buy some souvenirs. What do you suggest?"
    ),
]

SYSTEM_PROMPT = (
    "You are Virtue, a helpful and friendly airport assistant robot made by VirtusCo. "
    "You help passengers with directions, flight information, and luggage. "
    "Keep responses concise and actionable."
)


def get_system_info() -> dict:
    """Collect system hardware information."""
    info = {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    if psutil:
        mem = psutil.virtual_memory()
        info["total_ram_mb"] = round(mem.total / (1024 * 1024))
        info["available_ram_mb"] = round(mem.available / (1024 * 1024))
    return info


def get_process_memory_mb() -> float:
    """Get current process RSS in MB."""
    if psutil:
        proc = psutil.Process(os.getpid())
        return proc.memory_info().rss / (1024 * 1024)
    return 0.0


def benchmark_model(
    model_path: str,
    lora_path: str = None,
    n_runs: int = 20,
    max_tokens: int = 256,
    n_ctx: int = 768,
    n_threads: int = 4,
    temperature: float = 1.0,
    verbose: bool = False,
) -> dict:
    """Run benchmark on a GGUF model and return detailed metrics."""
    try:
        from llama_cpp import Llama
    except ImportError:
        print("ERROR: llama-cpp-python not installed.")
        print("Install: pip install llama-cpp-python")
        sys.exit(1)

    model_path = str(Path(model_path).resolve())
    model_size_mb = os.path.getsize(model_path) / (1024 * 1024)
    lora_size_mb = 0.0
    if lora_path:
        lora_path = str(Path(lora_path).resolve())
        lora_size_mb = os.path.getsize(lora_path) / (1024 * 1024)

    print(f"\n{'=' * 70}")
    print(f"Porter AI Assistant — Benchmark")
    print(f"{'=' * 70}")
    print(f"Model:      {Path(model_path).name}")
    print(f"Size:       {model_size_mb:.1f} MB")
    if lora_path:
        print(f"LoRA:       {Path(lora_path).name} ({lora_size_mb:.1f} MB)")
    print(f"Runs:       {n_runs}")
    print(f"Max tokens: {max_tokens}")
    print(f"Context:    {n_ctx}")
    print(f"Threads:    {n_threads}")
    print(f"{'=' * 70}\n")

    # ── Memory before loading ────────────────────────────────────────────────
    mem_before = get_process_memory_mb()

    # ── Load model ───────────────────────────────────────────────────────────
    print("Loading model...", end=" ", flush=True)
    load_start = time.monotonic()

    kwargs = dict(
        model_path=model_path,
        n_ctx=n_ctx,
        n_batch=64,
        n_threads=n_threads,
        n_gpu_layers=0,
        use_mmap=True,
        use_mlock=False,
        verbose=verbose,
    )
    if lora_path:
        kwargs['lora_path'] = lora_path
    llm = Llama(**kwargs)

    load_time = time.monotonic() - load_start
    mem_after_load = get_process_memory_mb()
    print(f"done in {load_time:.2f}s (RSS: {mem_after_load:.0f} MB)")

    # ── Warmup ───────────────────────────────────────────────────────────────
    print("Warmup inference...", end=" ", flush=True)
    warmup_start = time.monotonic()
    llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Hello"},
        ],
        max_tokens=32,
        temperature=temperature,
    )
    warmup_time = time.monotonic() - warmup_start
    mem_after_warmup = get_process_memory_mb()
    print(f"done in {warmup_time:.2f}s (RSS: {mem_after_warmup:.0f} MB)")

    # ── Benchmark runs ───────────────────────────────────────────────────────
    results = []
    prompts_cycle = TEST_PROMPTS * ((n_runs // len(TEST_PROMPTS)) + 1)

    print(f"\nRunning {n_runs} inference passes...")
    for i in range(n_runs):
        prompt = prompts_cycle[i]

        t_start = time.monotonic()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.9,
            top_k=40,
            repeat_penalty=1.1,
        )
        t_end = time.monotonic()

        latency_ms = (t_end - t_start) * 1000

        # Extract output tokens
        reply = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        tokens_per_sec = (
            completion_tokens / (latency_ms / 1000) if latency_ms > 0 else 0
        )

        run_result = {
            "run": i + 1,
            "prompt": prompt[:60] + "..." if len(prompt) > 60 else prompt,
            "latency_ms": round(latency_ms, 1),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tokens_per_sec": round(tokens_per_sec, 1),
            "reply_length": len(reply),
        }
        results.append(run_result)

        status = "✓" if latency_ms < 2000 else "✗ SLOW"
        if verbose:
            print(
                f"  [{i+1:3d}/{n_runs}] {latency_ms:7.0f}ms | "
                f"{completion_tokens:3d} tok | "
                f"{tokens_per_sec:5.1f} tok/s | {status}"
            )
        else:
            print(
                f"  [{i+1:3d}/{n_runs}] {latency_ms:7.0f}ms | "
                f"{completion_tokens:3d} tok | {status}"
            )

    # ── Peak memory ──────────────────────────────────────────────────────────
    mem_peak = get_process_memory_mb()

    # ── Statistics ───────────────────────────────────────────────────────────
    latencies = [r["latency_ms"] for r in results]
    tps_values = [r["tokens_per_sec"] for r in results]
    comp_tokens = [r["completion_tokens"] for r in results]

    stats = {
        "model": Path(model_path).name,
        "model_size_mb": round(model_size_mb, 1),
        "lora": Path(lora_path).name if lora_path else None,
        "lora_size_mb": round(lora_size_mb, 1) if lora_path else None,
        "system": get_system_info(),
        "config": {
            "n_runs": n_runs,
            "max_tokens": max_tokens,
            "n_ctx": n_ctx,
            "n_threads": n_threads,
            "temperature": temperature,
        },
        "load_time_sec": round(load_time, 2),
        "warmup_time_sec": round(warmup_time, 2),
        "memory": {
            "before_load_mb": round(mem_before, 1),
            "after_load_mb": round(mem_after_load, 1),
            "after_warmup_mb": round(mem_after_warmup, 1),
            "peak_mb": round(mem_peak, 1),
            "model_footprint_mb": round(mem_after_load - mem_before, 1),
        },
        "latency_ms": {
            "min": round(min(latencies), 1),
            "max": round(max(latencies), 1),
            "mean": round(statistics.mean(latencies), 1),
            "median": round(statistics.median(latencies), 1),
            "stdev": round(statistics.stdev(latencies), 1) if len(latencies) > 1 else 0,
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 1),
            "p99": round(sorted(latencies)[int(len(latencies) * 0.99)], 1),
        },
        "throughput": {
            "mean_tokens_per_sec": round(statistics.mean(tps_values), 1),
            "median_tokens_per_sec": round(statistics.median(tps_values), 1),
        },
        "completion_tokens": {
            "mean": round(statistics.mean(comp_tokens), 1),
            "median": round(statistics.median(comp_tokens), 1),
        },
        "pass_rate": {
            "under_2s": round(sum(1 for l in latencies if l < 2000) / len(latencies) * 100, 1),
            "under_3s": round(sum(1 for l in latencies if l < 3000) / len(latencies) * 100, 1),
            "under_5s": round(sum(1 for l in latencies if l < 5000) / len(latencies) * 100, 1),
        },
        "runs": results,
    }

    # ── Print summary ────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"RESULTS SUMMARY")
    print(f"{'=' * 70}")
    print(f"Model:            {stats['model']}")
    print(f"Model size:       {stats['model_size_mb']} MB")
    print(f"Load time:        {stats['load_time_sec']}s")
    print(f"Peak RSS:         {stats['memory']['peak_mb']} MB")
    print(f"Model footprint:  {stats['memory']['model_footprint_mb']} MB")
    print(f"{'─' * 70}")
    print(f"Latency (ms):     mean={stats['latency_ms']['mean']:.0f}  "
          f"median={stats['latency_ms']['median']:.0f}  "
          f"p95={stats['latency_ms']['p95']:.0f}  "
          f"p99={stats['latency_ms']['p99']:.0f}")
    print(f"Throughput:       {stats['throughput']['mean_tokens_per_sec']} tok/s")
    print(f"Completion tokens: {stats['completion_tokens']['mean']:.0f} mean")
    print(f"{'─' * 70}")
    print(f"Pass rates:       <2s: {stats['pass_rate']['under_2s']}%  "
          f"<3s: {stats['pass_rate']['under_3s']}%  "
          f"<5s: {stats['pass_rate']['under_5s']}%")

    rpi_ok = stats["memory"]["peak_mb"] < 2048 and stats["pass_rate"]["under_2s"] >= 80
    print(f"{'─' * 70}")
    print(f"RPi 4 target:     {'✓ PASS' if rpi_ok else '✗ FAIL'}  "
          f"(<2 GB RSS + >80% under 2s)")
    print(f"{'=' * 70}\n")

    return stats


def main():
    """Parse arguments and run benchmark."""
    parser = argparse.ArgumentParser(
        description="Benchmark GGUF model for Porter AI Assistant"
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Path to base GGUF model file",
    )
    parser.add_argument(
        "--lora",
        type=str,
        default=None,
        help="Path to GGUF LoRA adapter file (optional)",
    )
    parser.add_argument(
        "--n-runs",
        type=int,
        default=20,
        help="Number of inference runs (default: 20)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Max output tokens per response (default: 256)",
    )
    parser.add_argument(
        "--n-ctx",
        type=int,
        default=768,
        help="Context window size (default: 768, matches SFT training)",
    )
    parser.add_argument(
        "--n-threads",
        type=int,
        default=4,
        help="CPU threads (default: 4 for RPi 4)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature (default: 1.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save results to JSON file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output per run",
    )

    args = parser.parse_args()

    if not Path(args.model).exists():
        print(f"ERROR: Model file not found: {args.model}")
        sys.exit(1)

    if args.lora and not Path(args.lora).exists():
        print(f"ERROR: LoRA adapter file not found: {args.lora}")
        sys.exit(1)

    stats = benchmark_model(
        model_path=args.model,
        lora_path=args.lora,
        n_runs=args.n_runs,
        max_tokens=args.max_tokens,
        n_ctx=args.n_ctx,
        n_threads=args.n_threads,
        temperature=args.temperature,
        verbose=args.verbose,
    )

    # Save results
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"Results saved to: {output_path}")
    else:
        default_output = (
            Path(__file__).resolve().parent.parent
            / "models"
            / f"benchmark_{Path(args.model).stem}.json"
        )
        default_output.parent.mkdir(parents=True, exist_ok=True)
        with open(default_output, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"Results saved to: {default_output}")


if __name__ == "__main__":
    main()

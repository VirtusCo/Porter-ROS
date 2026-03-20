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
"""Inference test for fine-tuned LoRA adapters (PyTorch + PEFT).

Loads the base model with merged LoRA adapter and runs test prompts
to validate quality before GGUF conversion (Task 18d).

Usage:
    python3 scripts/inference_test.py --adapter conversational
    python3 scripts/inference_test.py --adapter tool_use
    python3 scripts/inference_test.py --adapter both
    python3 scripts/inference_test.py --adapter both --output results.json

Requirements:
    pip install torch transformers peft bitsandbytes accelerate
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PKG_DIR = SCRIPT_DIR.parent
MODELS_DIR = PKG_DIR / "models" / "lora_adapters"


# ── Test Cases ───────────────────────────────────────────────────────────────

CONVERSATIONAL_TESTS = [
    {
        "id": "conv_01",
        "category": "wayfinding",
        "query": "Where is Gate B12?",
        "expect_keywords": ["gate", "b12", "terminal", "minute", "walk"],
    },
    {
        "id": "conv_02",
        "category": "dining",
        "query": "Can you recommend a vegetarian restaurant?",
        "expect_keywords": ["vegetarian", "haldiram", "dosa", "food"],
    },
    {
        "id": "conv_03",
        "category": "accessibility",
        "query": "I need wheelchair assistance to get to my gate.",
        "expect_keywords": ["wheelchair", "free", "assist", "desk"],
    },
    {
        "id": "conv_04",
        "category": "flight_info",
        "query": "My flight AI-302 is delayed. What should I do?",
        "expect_keywords": ["delay", "airline", "counter", "rebook"],
    },
    {
        "id": "conv_05",
        "category": "services",
        "query": "Where can I find a currency exchange?",
        "expect_keywords": ["currency", "exchange", "level"],
    },
    {
        "id": "conv_06",
        "category": "luggage",
        "query": "I lost my luggage. Where do I report it?",
        "expect_keywords": ["lost", "baggage", "counter", "claim"],
    },
    {
        "id": "conv_07",
        "category": "transit",
        "query": "I have a 2-hour layover. Will I make my connection?",
        "expect_keywords": ["layover", "connection", "time", "security"],
    },
    {
        "id": "conv_08",
        "category": "greeting",
        "query": "Hello! What can you help me with?",
        "expect_keywords": ["porter", "luggage", "carry", "assist", "guide"],
    },
]

TOOL_USE_TESTS = [
    {
        "id": "tool_01",
        "category": "directions",
        "query": "How do I get to Gate C22?",
        "expect_in_response": ["<tool_call>", "get_directions"],
    },
    {
        "id": "tool_02",
        "category": "flight_lookup",
        "query": "What's the status of flight AI-302?",
        "expect_in_response": ["<tool_call>", "get_flight_status"],
    },
    {
        "id": "tool_03",
        "category": "call_assistance",
        "query": "I need medical help urgently!",
        "expect_in_response": ["<tool_call>", "call_assistance"],
    },
    {
        "id": "tool_04",
        "category": "weigh_luggage",
        "query": "Can you weigh my suitcase before I check in?",
        "expect_in_response": ["<tool_call>", "weigh_luggage"],
    },
    {
        "id": "tool_05",
        "category": "find_nearest",
        "query": "Find me a coffee shop nearby",
        "expect_in_response": ["<tool_call>", "find_nearest"],
    },
]

def _load_tool_use_system_prompt() -> str:
    """Load the compact tool_use system prompt matching training data."""
    # This MUST match the compact prompt used in training data.
    # The full JSON schemas are too long (2491 tokens) for small models.
    return (
        'You are Virtue, an airport assistant robot by VirtusCo. '
        'Call tools using <tool_call>{"name": "tool_name", "arguments": {...}}'
        '</tool_call> format. After tool results in '
        '<tool_response>...</tool_response>, respond naturally.\n\n'
        'Tools:\n'
        '- get_directions(destination, from_location?) - Walking directions in airport\n'
        '- get_flight_status(flight_number) - Real-time flight status, gate, delays\n'
        '- find_nearest(facility_type, accessible?) - Nearest facility '
        '(restroom, cafe, atm, pharmacy, etc.)\n'
        '- weigh_luggage(num_bags) - Weigh bags on built-in scale\n'
        '- get_gate_info(gate_id) - Gate terminal and concourse info\n'
        '- call_assistance(assistance_type, location, priority?) - Request staff '
        '(wheelchair, medical, security, etc.)\n'
        '- escort_passenger(destination, carry_luggage?, pace?) - Navigate passenger '
        'to destination\n'
        '- show_map(area, highlight?, show_route?) - Display airport map on screen\n'
        '- check_wait_time(queue_type, terminal?) - Queue wait times '
        '(security, immigration, etc.)\n'
        '- set_reminder(flight_number, reminder_minutes_before?) - Set boarding reminder\n'
        '- get_airline_counter(airline, service_type?) - Find airline counter location\n'
        '- get_transport_options(destination, transport_type?) - Ground transportation '
        'options\n'
        '- translate_text(text, target_language) - Translate to another language\n'
        '- report_incident(incident_type, location, severity, description?) - Report '
        'safety incident'
    )


SYSTEM_PROMPTS = {
    "conversational": (
        "You are Virtue, a helpful airport assistant robot made by VirtusCo. "
        "Provide concise, accurate information to help passengers navigate "
        "the airport and answer their questions. Be friendly and professional."
    ),
    "tool_use": _load_tool_use_system_prompt(),
}


@dataclass
class InferenceResult:
    """Result from a single inference test."""

    test_id: str
    category: str
    query: str
    response: str
    latency_ms: float
    tokens_generated: int
    tokens_per_sec: float
    keyword_hits: int = 0
    keyword_total: int = 0
    passed: bool = False
    notes: str = ""


def load_model(adapter_path: str, device_map: Optional[dict] = None):
    """Load base model with merged LoRA adapter."""
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer, BitsAndBytesConfig

    adapter_dir = Path(adapter_path)
    if not adapter_dir.exists():
        print(f"ERROR: Adapter not found: {adapter_dir}")
        sys.exit(1)

    print(f"Loading adapter from: {adapter_dir}")

    # Check GPU availability
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"GPU: {gpu_name} ({gpu_mem:.1f} GB)")
        if device_map is None:
            device_map = {"": 0}
    else:
        print("No GPU — running on CPU (will be slow)")
        device_map = {"": "cpu"}

    # 4-bit quantization config (same as training)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    t0 = time.monotonic()
    model = AutoPeftModelForCausalLM.from_pretrained(
        str(adapter_dir),
        quantization_config=bnb_config,
        device_map=device_map,
        torch_dtype=torch.bfloat16,
        attn_implementation="eager",
    )
    tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir))
    load_time = time.monotonic() - t0

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    param_count = sum(p.numel() for p in model.parameters())
    print(f"Model loaded in {load_time:.1f}s — {param_count / 1e6:.0f}M params")

    if torch.cuda.is_available():
        mem_used = torch.cuda.memory_allocated() / (1024**3)
        print(f"GPU memory used: {mem_used:.2f} GB")

    return model, tokenizer, load_time


def generate_response(
    model, tokenizer, system_prompt: str, user_query: str,
    max_new_tokens: int = 256, temperature: float = 0.7,
) -> tuple:
    """Generate a response and return (text, latency_ms, num_tokens)."""
    # Use proper system/user role format matching training data
    messages = [
        {"role": "user", "content": system_prompt + "\n\n" + user_query},
    ]

    # Try chat template first, fall back to manual formatting
    try:
        input_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
    except Exception:
        input_text = (
            f"<start_of_turn>user\n{system_prompt}\n\n"
            f"{user_query}<end_of_turn>\n<start_of_turn>model\n"
        )

    inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[1]

    t_start = time.monotonic()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=0.9,
            top_k=40,
            repetition_penalty=1.1,
            do_sample=True,
            pad_token_id=tokenizer.pad_token_id,
        )
    t_end = time.monotonic()

    latency_ms = (t_end - t_start) * 1000
    new_tokens = outputs[0][input_len:]
    num_tokens = len(new_tokens)
    response = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    return response, latency_ms, num_tokens


def run_conversational_tests(model, tokenizer) -> list:
    """Run conversational adapter tests."""
    results = []
    system_prompt = SYSTEM_PROMPTS["conversational"]

    for test in CONVERSATIONAL_TESTS:
        print(f"  [{test['id']}] {test['category']}: {test['query'][:50]}...", end=" ")

        response, latency_ms, num_tokens = generate_response(
            model, tokenizer, system_prompt, test["query"],
        )

        tps = num_tokens / (latency_ms / 1000) if latency_ms > 0 else 0

        # Check keywords
        response_lower = response.lower()
        keywords = test.get("expect_keywords", [])
        hits = sum(1 for kw in keywords if kw.lower() in response_lower)

        passed = (
            len(response) > 10          # Not empty
            and hits >= 1               # At least 1 keyword
            and latency_ms < 30000      # Reasonable time (GPU)
        )

        result = InferenceResult(
            test_id=test["id"],
            category=test["category"],
            query=test["query"],
            response=response,
            latency_ms=round(latency_ms, 1),
            tokens_generated=num_tokens,
            tokens_per_sec=round(tps, 1),
            keyword_hits=hits,
            keyword_total=len(keywords),
            passed=passed,
        )
        results.append(result)

        status = "PASS" if passed else "FAIL"
        print(f"{latency_ms:.0f}ms | {num_tokens} tok | {hits}/{len(keywords)} kw | {status}")

    return results


def run_tool_use_tests(model, tokenizer) -> list:
    """Run tool_use adapter tests."""
    results = []
    system_prompt = SYSTEM_PROMPTS["tool_use"]

    for test in TOOL_USE_TESTS:
        print(f"  [{test['id']}] {test['category']}: {test['query'][:50]}...", end=" ")

        response, latency_ms, num_tokens = generate_response(
            model, tokenizer, system_prompt, test["query"],
        )

        tps = num_tokens / (latency_ms / 1000) if latency_ms > 0 else 0

        # Check expected strings
        expected = test.get("expect_in_response", [])
        hits = sum(1 for ex in expected if ex in response)

        passed = (
            len(response) > 5
            and hits >= 1
            and latency_ms < 30000
        )

        notes = ""
        if "<tool_call>" in response:
            notes = "Tool call detected"
        elif not any(ex in response for ex in expected):
            notes = "No tool call in response"

        result = InferenceResult(
            test_id=test["id"],
            category=test["category"],
            query=test["query"],
            response=response,
            latency_ms=round(latency_ms, 1),
            tokens_generated=num_tokens,
            tokens_per_sec=round(tps, 1),
            keyword_hits=hits,
            keyword_total=len(expected),
            passed=passed,
            notes=notes,
        )
        results.append(result)

        status = "PASS" if passed else "FAIL"
        print(f"{latency_ms:.0f}ms | {num_tokens} tok | {hits}/{len(expected)} | {status}")

    return results


def print_summary(adapter_name: str, results: list, load_time: float):
    """Print test summary."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    latencies = [r.latency_ms for r in results]
    tps_vals = [r.tokens_per_sec for r in results if r.tokens_per_sec > 0]

    import statistics

    print(f"\n{'=' * 70}")
    print(f"  {adapter_name.upper()} ADAPTER — INFERENCE TEST RESULTS")
    print(f"{'=' * 70}")
    print(f"  Pass rate:          {passed}/{total} ({100*passed/total:.0f}%)")
    print(f"  Model load time:    {load_time:.1f}s")
    print(f"  Latency mean:       {statistics.mean(latencies):.0f} ms")
    print(f"  Latency median:     {statistics.median(latencies):.0f} ms")
    print(f"  Latency min/max:    {min(latencies):.0f} / {max(latencies):.0f} ms")
    if tps_vals:
        print(f"  Throughput mean:    {statistics.mean(tps_vals):.1f} tok/s")
    print(f"{'=' * 70}")

    # Print sample responses
    print(f"\n  Sample responses:")
    for r in results[:3]:
        print(f"  ── {r.test_id} ({r.category}) ──")
        print(f"  Q: {r.query}")
        resp_preview = r.response[:200] + "..." if len(r.response) > 200 else r.response
        print(f"  A: {resp_preview}")
        print()


def main():
    """Run inference tests on LoRA adapters."""
    parser = argparse.ArgumentParser(
        description="Test fine-tuned LoRA adapters via PyTorch inference"
    )
    parser.add_argument(
        "--adapter",
        type=str,
        choices=["conversational", "tool_use", "both"],
        default="both",
        help="Which adapter to test (default: both)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save results to JSON file",
    )
    parser.add_argument(
        "--adapter-dir",
        type=str,
        default=None,
        help="Override adapter path (e.g. models/lora_adapters/tool_use/rl/final)",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default="final",
        help="Adapter variant subdirectory (default: final, use 'rl/final' for RL)",
    )
    args = parser.parse_args()

    adapters = (
        ["conversational", "tool_use"] if args.adapter == "both"
        else [args.adapter]
    )

    all_results = {}

    for adapter_name in adapters:
        if args.adapter_dir:
            adapter_path = Path(args.adapter_dir)
        else:
            adapter_path = MODELS_DIR / adapter_name / args.variant
        if not adapter_path.exists():
            print(f"SKIP: {adapter_path} not found")
            continue

        print(f"\n{'#' * 70}")
        print(f"  Testing: {adapter_name} adapter")
        print(f"{'#' * 70}\n")

        model, tokenizer, load_time = load_model(str(adapter_path))

        if adapter_name == "conversational":
            results = run_conversational_tests(model, tokenizer)
        else:
            results = run_tool_use_tests(model, tokenizer)

        print_summary(adapter_name, results, load_time)

        all_results[adapter_name] = {
            "load_time_sec": round(load_time, 2),
            "total_tests": len(results),
            "passed": sum(1 for r in results if r.passed),
            "results": [
                {
                    "test_id": r.test_id,
                    "category": r.category,
                    "query": r.query,
                    "response": r.response,
                    "latency_ms": r.latency_ms,
                    "tokens_generated": r.tokens_generated,
                    "tokens_per_sec": r.tokens_per_sec,
                    "keyword_hits": r.keyword_hits,
                    "keyword_total": r.keyword_total,
                    "passed": r.passed,
                    "notes": r.notes,
                }
                for r in results
            ],
        }

        # Free GPU memory before loading next adapter
        del model
        del tokenizer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # Save results
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {out_path}")

    # Overall summary
    print(f"\n{'#' * 70}")
    print(f"  OVERALL SUMMARY")
    print(f"{'#' * 70}")
    for name, data in all_results.items():
        pct = 100 * data["passed"] / data["total_tests"] if data["total_tests"] > 0 else 0
        print(f"  {name:20s}: {data['passed']}/{data['total_tests']} passed ({pct:.0f}%)")
    print()


if __name__ == "__main__":
    main()

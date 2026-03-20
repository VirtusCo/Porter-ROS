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
"""Configuration constants for Porter AI Assistant.

Centralised configuration defaults, model registry, and paths. Runtime
parameters come from assistant_params.yaml via ROS 2 parameter server;
these are compile-time defaults and constants.
"""

from pathlib import Path

# ── Package Paths ────────────────────────────────────────────────────────────
PACKAGE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = PACKAGE_DIR / 'models'
DATA_DIR = PACKAGE_DIR / 'data'
CONFIG_DIR = PACKAGE_DIR / 'config'
SCRIPTS_DIR = PACKAGE_DIR / 'scripts'

# ── Default Model Configuration ─────────────────────────────────────────────
# Qwen 2.5 1.5B Instruct Q4_K_M — ~1.0 GB RSS on RPi 5 (good fit)
DEFAULT_MODEL_FILENAME = 'qwen2.5-1.5b-instruct-q4_k_m.gguf'

# Default LoRA adapter directory (contains porter-*-lora-*.gguf files)
DEFAULT_LORA_DIR = 'models/gguf'

# Default adapter loaded on startup
DEFAULT_ADAPTER = 'conversational'

# Context window (tokens) — 1024 for airport Q&A (rarely exceeds 800 tokens).
# Saves ~28 MB RAM vs 2048. Increase to 2048 if longer conversations needed.
DEFAULT_N_CTX = 1024

# Batch size for prompt processing — 512 is optimal for CPU inference
# (llama.cpp default). Old value of 64 was unnecessarily restrictive.
DEFAULT_N_BATCH = 512

# CPU threads for inference — 2 reserves 2 cores for SLAM/Nav2/LIDAR.
# On RPi 4/5 (4 cores): 2 threads for AI + 2 for safety-critical ROS 2 nodes.
# Set to 0 to let llama.cpp auto-detect (uses ALL cores — only safe standalone).
DEFAULT_N_THREADS = 2

# Separate thread count for batch/prompt processing.
# 0 = use same as n_threads. Match n_threads for RPi coexistence.
DEFAULT_N_THREADS_BATCH = 0

# GPU offload layers — 0 for RPi (CPU only), >0 for Jetson
DEFAULT_N_GPU_LAYERS = 0

# Flash attention — can improve memory efficiency on some architectures.
# Disabled by default: slower on x86 AVX512, may help on ARM NEON (RPi 5).
DEFAULT_FLASH_ATTN = False

# ── Generation Defaults ──────────────────────────────────────────────────────
DEFAULT_MAX_TOKENS = 256
DEFAULT_TEMPERATURE = 0.7      # Lower than Unsloth default (1.0) for grounded responses
DEFAULT_TOP_P = 0.9            # Slightly tighter nucleus sampling
DEFAULT_TOP_K = 50             # Balanced sampling for Qwen 2.5
DEFAULT_REPEAT_PENALTY = 1.1
DEFAULT_MIN_P = 0.0

# ── Model Selection Rationale ────────────────────────────────────────────────
# Decision: Qwen 2.5 1.5B Instruct → quantized to Q4_K_M GGUF.
#
# Why Qwen 2.5 1.5B (switch from Gemma 3 270M):
#   - Qwen 2.5 1.5B is the community gold standard for sub-2B models.
#   - Much stronger instruction following & reasoning than 270M.
#   - Natively supports tool calling / function calling.
#   - Q4_K_M GGUF = ~1.0 GB RSS — fits on RPi 5 (8 GB) comfortably.
#   - RPi 4 (4 GB) is tight but viable with careful memory management.
#   - Inference latency: ~1-3s on RPi 5 ARM Cortex-A76 (within target).
#   - Better multilingual support than Gemma 270M.
#
# Why not other models:
#   - Gemma 3 270M: too small, poor instruction following, language mixing
#   - Phi-3.8B: too large for RPi (even Q4 = 2.2 GB)
#   - TinyLlama-1.1B: worse quality than Qwen 2.5 at similar size
#   - Qwen2-0.5B: too small for quality tool calling

MODEL_SELECTION_NOTES = {
    'primary': 'Qwen 2.5 1.5B Instruct (Q4_K_M GGUF, ~1.0 GB)',
    'fallback': 'Qwen 2.5 0.5B Instruct (Q4_K_M GGUF, ~400 MB)',
    'tool_use': 'Qwen 2.5 1.5B Instruct + tool LoRA',
    'source': 'Qwen/Qwen2.5-1.5B-Instruct-GGUF',
    'base_model_hf': 'Qwen/Qwen2.5-1.5B-Instruct',
    'actual_model_size_mb': 1000,
    'rpi4_ram_budget_mb': 2048,
    'rpi4_os_ros_overhead_mb': 1500,
    'model_budget_mb': 1200,
    'target_latency_ms': 3000,
}

# ── Health Thresholds ────────────────────────────────────────────────────────
MAX_RSS_MB = 1800           # Alert if process RSS exceeds this
LATENCY_WARN_MS = 2000.0    # Warn if inference takes >2s
LATENCY_ERROR_MS = 5000.0   # Error if inference takes >5s
HEALTH_CHECK_INTERVAL_SEC = 30.0

# ── Query Classification ─────────────────────────────────────────────────────
# Keywords that route to tool-use adapter.
# Plain strings = exact substring match (case-insensitive).
# Prefix 'r:' = regex pattern for flexible word-order matching.
DEFAULT_TOOL_KEYWORDS = [
    # Exact substring matches
    'take me', 'escort me', 'carry my', 'weigh my',
    'flight status', 'flight number', 'flight info',
    'directions to', 'navigate to', 'how do i get to',
    'find nearest', 'find the nearest', 'where is the nearest',
    'nearest', 'closest',
    'call assistance', 'wheelchair', 'accessibility',
    'check my flight', 'track my', 'luggage',
    'translate', 'remind me', 'set reminder',
    'wait time', 'queue', 'show map',
    'report', 'incident', 'lost and found',
    'where is gate', 'which gate', 'gate number',
    'boarding', 'departure', 'arrival',
    'transport', 'shuttle', 'taxi', 'uber',
    'lounge', 'priority', 'check-in', 'checkin',
    'currency', 'exchange', 'atm',
    'parking', 'duty free', 'shop',
    # Regex patterns for flexible word order
    'r:status.*flight', 'r:flight.*status',
    'r:where.*gate', 'r:gate.*where',
    'r:find.*(?:coffee|food|restaurant|shop|lounge|atm)',
    'r:(?:book|reserve|get).*(?:wheelchair|assistance|cart)',
    'r:how.*(?:long|far|much)',
    'r:(?:my|the)\\s+flight',
]

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
"""Inference engine for Porter AI Assistant using llama-cpp-python.

Wraps llama-cpp-python to provide a simple interface for loading GGUF models,
managing modular LoRA adapters, and running inference on RPi 4/5.

Supports:
- Base GGUF model loading with memory-mapping
- Modular LoRA adapter hot-swapping (conversational vs tool-use)
- Query classification for adapter routing
- System prompt management from YAML templates
- Health monitoring (memory, latency tracking)
"""

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Generator, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    """Result from a single inference call."""

    text: str = ''
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_per_sec: float = 0.0
    adapter_used: str = 'none'
    success: bool = True
    error: str = ''


@dataclass
class ModelConfig:
    """Configuration for model loading and inference."""

    model_path: str = ''
    lora_dir: str = ''
    n_ctx: int = 1024            # 1024 for airport Q&A (saves ~28 MB vs 2048)
    n_batch: int = 512
    n_threads: int = 2           # 2 = reserve 2 cores for SLAM/Nav2 on RPi
    n_threads_batch: int = 0     # 0 = use same as n_threads
    n_gpu_layers: int = 0
    use_mmap: bool = True
    use_mlock: bool = False
    flash_attn: bool = False     # May help on ARM NEON (RPi 5)
    max_tokens: int = 256
    temperature: float = 0.7     # Balanced for grounded airport responses
    top_p: float = 0.9           # Slightly tighter nucleus sampling
    top_k: int = 50              # Balanced sampling for Qwen 2.5
    repeat_penalty: float = 1.1
    min_p: float = 0.0


@dataclass
class HealthStats:
    """Live health statistics for the inference engine."""

    model_loaded: bool = False
    model_name: str = ''
    rss_mb: float = 0.0
    total_queries: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    last_latency_ms: float = 0.0
    errors: int = 0
    active_adapter: str = 'none'
    latency_history: list = field(default_factory=list)


class InferenceEngine:
    """GGUF model inference engine with modular LoRA adapter support.

    Manages model lifecycle, adapter routing, and inference for the
    Porter AI Assistant running on resource-constrained hardware.

    Attributes:
        config: Model configuration dataclass.
        health: Live health statistics.
    """

    # Maximum latency samples to retain for percentile calculation
    MAX_LATENCY_HISTORY = 200

    def __init__(self, config: Optional[ModelConfig] = None):
        """Initialize inference engine.

        Args:
            config: Model configuration. If None, uses defaults.
        """
        self.config = config or ModelConfig()
        self.health = HealthStats()
        self._llm = None
        self._active_lora: str = ''
        self._lora_adapters: dict = {}
        self._merged_models: dict = {}
        self._system_prompts: dict = {}
        self._tool_schemas: list = []
        self._tool_keywords: list = []
        self._tool_patterns: list = []

    def _discover_lora_adapters(self):
        """Scan lora_dir for available GGUF LoRA adapter files."""
        self._lora_adapters = {}
        lora_dir = Path(self.config.lora_dir)
        if not lora_dir.is_dir():
            return
        for f in lora_dir.glob('porter-*-lora-*.gguf'):
            # Extract adapter name from filename: porter-<name>-lora-<type>.gguf
            parts = f.stem.split('-')
            if len(parts) >= 3 and 'lora' in parts:
                lora_idx = parts.index('lora')
                name = '-'.join(parts[1:lora_idx])
                self._lora_adapters[name] = str(f)
        if self._lora_adapters:
            logger.info(
                'Found LoRA adapters: %s',
                ', '.join(self._lora_adapters.keys()),
            )

    def _discover_merged_models(self):
        """Scan lora_dir for merged GGUF model files.

        Merged models have LoRA weights baked in and are standalone
        GGUF files. They are preferred over base+LoRA for faster load
        and better inference quality.

        Expected naming: porter-<adapter>-<BaseModel>-<Quant>.gguf
        Examples:
            porter-conversational-Qwen2.5-1.5B-Instruct-Q4_K_M.gguf
            porter-tool_use-Qwen2.5-1.5B-Instruct-Q4_K_M.gguf
        """
        self._merged_models = {}
        lora_dir = Path(self.config.lora_dir)
        if not lora_dir.is_dir():
            return
        for f in lora_dir.glob('porter-*-Q*_K_*.gguf'):
            stem = f.stem  # e.g. porter-conversational-Qwen2.5-1.5B-Instruct-Q4_K_M
            # Skip separate LoRA adapter files
            if '-lora-' in stem:
                continue
            # Extract adapter name: everything between 'porter-' and
            # the first uppercase segment (model name)
            after_porter = stem[len('porter-'):]
            # Find where the model name starts (first uppercase letter)
            match = re.search(r'-[A-Z]', after_porter)
            if match:
                adapter_name = after_porter[:match.start()]
                self._merged_models[adapter_name] = str(f)
        if self._merged_models:
            logger.info(
                'Found merged fine-tuned models: %s',
                ', '.join(
                    f'{k} ({Path(v).name})'
                    for k, v in self._merged_models.items()
                ),
            )

    def load_model(
        self,
        model_path: Optional[str] = None,
        lora_adapter: str = 'conversational',
    ) -> bool:
        """Load a GGUF model into memory with optional LoRA adapter.

        Uses base GGUF + separate LoRA adapter files to avoid the
        QLoRA merge degradation issue (see CLAUDE.md lesson #36).

        Args:
            model_path: Path to base GGUF file. Uses config if not specified.
            lora_adapter: Name of LoRA adapter to load ('conversational' or
                         'tool_use'). Empty string for no adapter.

        Returns:
            True if model loaded successfully.
        """
        path = model_path or self.config.model_path
        if not path:
            logger.error('No model path specified')
            return False

        resolved = Path(path).resolve()
        if not resolved.exists():
            logger.error('Model file not found: %s', resolved)
            return False

        try:
            from llama_cpp import Llama
        except ImportError:
            logger.error(
                'llama-cpp-python not installed. '
                'Install: pip install llama-cpp-python'
            )
            return False

        # Discover available adapters (merged models preferred over LoRA)
        self._discover_merged_models()
        self._discover_lora_adapters()

        # Check for merged fine-tuned model first (preferred)
        if lora_adapter and lora_adapter in self._merged_models:
            merged_path = Path(self._merged_models[lora_adapter]).resolve()
            if merged_path.exists():
                logger.info(
                    'Using merged fine-tuned model for "%s": %s',
                    lora_adapter,
                    merged_path.name,
                )
                resolved = merged_path  # Override model path
                # No separate LoRA needed — weights are baked in
                lora_adapter_resolved = lora_adapter
                lora_path = None
            else:
                lora_adapter_resolved = lora_adapter
                lora_path = None
        else:
            lora_adapter_resolved = lora_adapter
            lora_path = None

        # Fall back to separate LoRA adapter if no merged model
        if lora_adapter and lora_adapter not in self._merged_models:
            if lora_adapter in self._lora_adapters:
                lora_path = self._lora_adapters[lora_adapter]
                logger.info(
                    'Using LoRA adapter: %s (%s)',
                    lora_adapter,
                    lora_path,
                )
            elif lora_adapter:
                logger.warning(
                    'Adapter "%s" not found (merged or LoRA). '
                    'Available merged: %s, LoRA: %s. Loading base only.',
                    lora_adapter,
                    list(self._merged_models.keys()),
                    list(self._lora_adapters.keys()),
                )

        logger.info('Loading model: %s', resolved.name)
        t_start = time.monotonic()

        try:
            # Resolve thread counts: 0 = let llama.cpp auto-detect
            n_threads = self.config.n_threads if self.config.n_threads > 0 else None
            n_threads_batch = (
                self.config.n_threads_batch
                if self.config.n_threads_batch > 0
                else n_threads
            )

            kwargs = {
                'model_path': str(resolved),
                'n_ctx': self.config.n_ctx,
                'n_batch': self.config.n_batch,
                'n_threads': n_threads,
                'n_threads_batch': n_threads_batch,
                'n_gpu_layers': self.config.n_gpu_layers,
                'use_mmap': self.config.use_mmap,
                'use_mlock': self.config.use_mlock,
                'flash_attn': self.config.flash_attn,
                'verbose': False,
            }
            if lora_path:
                kwargs['lora_path'] = lora_path
            self._llm = Llama(**kwargs)
            self._active_lora = lora_adapter_resolved or ''

            load_time = time.monotonic() - t_start
            self.health.model_loaded = True
            self.health.model_name = resolved.name
            self.health.rss_mb = self._get_rss_mb()

            logger.info(
                'Model loaded in %.2fs (RSS: %.0f MB)',
                load_time,
                self.health.rss_mb,
            )
            return True

        except Exception as e:
            logger.error('Failed to load model: %s', e)
            self.health.model_loaded = False
            return False

    def unload_model(self):
        """Unload the current model from memory."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            self.health.model_loaded = False
            self.health.model_name = ''
            self._active_lora = ''
            logger.info('Model unloaded')

    def switch_adapter(self, adapter_name: str) -> bool:
        """Switch to a different adapter by reloading the model.

        Supports both merged GGUF models and separate LoRA adapters.
        Merged models are preferred for faster load and better quality.

        Args:
            adapter_name: Name of adapter ('conversational' or 'tool_use').

        Returns:
            True if switch succeeded.
        """
        if adapter_name == self._active_lora:
            return True  # Already loaded

        # Use merged model if available, otherwise fall back to base
        if adapter_name in self._merged_models:
            model_path = self._merged_models[adapter_name]
        else:
            model_path = self.config.model_path
        self.unload_model()
        return self.load_model(model_path=model_path, lora_adapter=adapter_name)

    def load_system_prompts(self, yaml_path: str) -> bool:
        """Load system prompt templates from a YAML file.

        Args:
            yaml_path: Path to system_prompts.yaml.

        Returns:
            True if loaded successfully.
        """
        path = Path(yaml_path)
        if not path.exists():
            logger.warning('System prompts file not found: %s', path)
            return False

        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)

            self._system_prompts = {}

            # Support two formats:
            # 1. Nested: {system_prompts: [{key: ..., prompt: ...}, ...]}
            # 2. Flat:   {default: "...", wayfinding: "...", ...}
            if 'system_prompts' in data and isinstance(data['system_prompts'], list):
                for entry in data['system_prompts']:
                    key = entry.get('key', '')
                    prompt = entry.get('prompt', '')
                    if key and prompt:
                        self._system_prompts[key] = prompt
            elif isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, str) and value.strip():
                        self._system_prompts[key] = value.strip()

            logger.info(
                'Loaded %d system prompts from %s',
                len(self._system_prompts),
                path.name,
            )
            return True

        except Exception as e:
            logger.error('Failed to load system prompts: %s', e)
            return False

    def load_tool_schemas(self, json_path: str) -> bool:
        """Load tool schemas for tool-use adapter.

        Args:
            json_path: Path to tool_schemas.json.

        Returns:
            True if loaded successfully.
        """
        path = Path(json_path)
        if not path.exists():
            logger.warning('Tool schemas file not found: %s', path)
            return False

        try:
            with open(path, 'r') as f:
                data = json.load(f)
            self._tool_schemas = data.get('tools', [])
            logger.info('Loaded %d tool schemas', len(self._tool_schemas))
            return True

        except Exception as e:
            logger.error('Failed to load tool schemas: %s', e)
            return False

    def set_tool_keywords(self, keywords: list):
        """Set keywords used for query classification.

        Args:
            keywords: List of keyword strings or regex patterns that
                      trigger tool-use adapter. Strings starting with
                      'r:' are treated as regex patterns.
        """
        self._tool_keywords = []
        self._tool_patterns = []
        for kw in keywords:
            if kw.startswith('r:'):
                try:
                    self._tool_patterns.append(
                        re.compile(kw[2:], re.IGNORECASE)
                    )
                except re.error:
                    logger.warning('Invalid tool regex: %s', kw)
            else:
                self._tool_keywords.append(kw.lower())

    def classify_query(self, query: str) -> str:
        """Classify a query as 'conversational' or 'tool_use'.

        Check exact substring keywords first, then regex patterns.
        No ML overhead — critical for RPi latency budget.

        Args:
            query: User query text.

        Returns:
            'tool_use' or 'conversational'.
        """
        query_lower = query.lower()
        for kw in self._tool_keywords:
            if kw in query_lower:
                return 'tool_use'
        for pat in self._tool_patterns:
            if pat.search(query_lower):
                return 'tool_use'
        return 'conversational'

    def get_system_prompt(self, key: str = 'default') -> str:
        """Retrieve a system prompt template by key.

        Args:
            key: Prompt key from system_prompts.yaml.

        Returns:
            System prompt string, or default fallback.
        """
        if key in self._system_prompts:
            return self._system_prompts[key]

        if 'default' in self._system_prompts:
            logger.warning(
                "Prompt key '%s' not found, using 'default'", key
            )
            return self._system_prompts['default']

        # Hardcoded fallback
        return (
            'You are Virtue, a helpful airport assistant robot made by VirtusCo. '
            'Keep responses concise and actionable.'
        )

    def query(
        self,
        user_query: str,
        system_prompt_key: str = 'default',
        context: str = '',
        adapter: Optional[str] = None,
        history: Optional[list] = None,
    ) -> InferenceResult:
        """Run inference on a user query.

        Args:
            user_query: The passenger's question.
            system_prompt_key: Key for system prompt selection.
            context: Additional context (e.g., current location).
            adapter: Force adapter type ('conversational' or 'tool_use').
                     If None, auto-classifies.
            history: Optional conversation history as a list of dicts
                     with 'role' ('user'/'assistant') and 'content' keys.
                     Most recent messages last. Capped to last 6 turns.

        Returns:
            InferenceResult with text, latency, and metadata.
        """
        result = InferenceResult()

        if not self.health.model_loaded or self._llm is None:
            result.success = False
            result.error = 'Model not loaded'
            self.health.errors += 1
            return result

        # Classify query for adapter routing
        adapter_type = adapter or self.classify_query(user_query)
        result.adapter_used = adapter_type

        # Auto-switch adapter if needed and available (merged or LoRA)
        available = set(self._merged_models) | set(self._lora_adapters)
        if adapter_type != self._active_lora and adapter_type in available:
            logger.info('Switching adapter: %s → %s', self._active_lora, adapter_type)
            if not self.switch_adapter(adapter_type):
                logger.warning('Adapter switch failed, continuing with %s', self._active_lora)
                result.adapter_used = self._active_lora

        # Select system prompt
        if adapter_type == 'tool_use':
            prompt_key = 'tool_use'
        else:
            prompt_key = system_prompt_key
        system_prompt = self.get_system_prompt(prompt_key)

        # Build tool schema context for tool-use queries
        # Uses compact format matching the training data:
        # - tool_name(param1, param2?) - Description
        # Full JSON schemas are too large (~2000+ tokens) and cause
        # context overflow or training truncation (see CLAUDE.md #34).
        if adapter_type == 'tool_use' and self._tool_schemas:
            tool_lines = []
            for t in self._tool_schemas:
                name = t['name']
                desc = t['description']
                props = t.get('parameters', {}).get('properties', {})
                req = t.get('parameters', {}).get('required', [])
                parts = []
                for pname in props:
                    parts.append(pname if pname in req else f'{pname}?')
                tool_lines.append(f'- {name}({", ".join(parts)}) - {desc}')
            system_prompt = (
                f'{system_prompt}\n\nAvailable tools:\n'
                + '\n'.join(tool_lines)
            )

        # Build messages
        messages = [{'role': 'system', 'content': system_prompt}]
        if context:
            messages.append({'role': 'user', 'content': f'Context: {context}'})
            messages.append(
                {'role': 'assistant', 'content': 'Understood, I have that context.'}
            )

        # Append conversation history (last 6 turns max to fit context)
        if history:
            for turn in history[-6:]:
                role = turn.get('role', '')
                content = turn.get('content', '')
                if role in ('user', 'assistant') and content:
                    msg_role = 'user' if role == 'user' else 'assistant'
                    messages.append({'role': msg_role, 'content': content})

        messages.append({'role': 'user', 'content': user_query})

        # Run inference
        t_start = time.monotonic()
        try:
            response = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                top_k=self.config.top_k,
                repeat_penalty=self.config.repeat_penalty,
                min_p=self.config.min_p,
            )
            t_end = time.monotonic()

            result.latency_ms = (t_end - t_start) * 1000
            result.text = response['choices'][0]['message']['content']

            usage = response.get('usage', {})
            result.prompt_tokens = usage.get('prompt_tokens', 0)
            result.completion_tokens = usage.get('completion_tokens', 0)
            if result.latency_ms > 0:
                result.tokens_per_sec = (
                    result.completion_tokens / (result.latency_ms / 1000)
                )

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.latency_ms = (time.monotonic() - t_start) * 1000
            self.health.errors += 1
            logger.error('Inference failed: %s', e)

        # Update health stats
        self.health.total_queries += 1
        self.health.last_latency_ms = result.latency_ms
        self.health.active_adapter = self._active_lora
        self.health.rss_mb = self._get_rss_mb()

        self.health.latency_history.append(result.latency_ms)
        if len(self.health.latency_history) > self.MAX_LATENCY_HISTORY:
            self.health.latency_history = self.health.latency_history[
                -self.MAX_LATENCY_HISTORY:
            ]

        if self.health.latency_history:
            self.health.avg_latency_ms = (
                sum(self.health.latency_history) / len(self.health.latency_history)
            )
            sorted_lat = sorted(self.health.latency_history)
            idx_95 = min(
                int(len(sorted_lat) * 0.95), len(sorted_lat) - 1
            )
            self.health.p95_latency_ms = sorted_lat[idx_95]

        return result

    def _prepare_inference(
        self,
        user_query: str,
        system_prompt_key: str = 'default',
        context: str = '',
        adapter: Optional[str] = None,
        history: Optional[list] = None,
    ) -> Tuple[Optional[list], str]:
        """Prepare messages and adapter for inference.

        Shared logic between query() and query_stream(). Handles adapter
        routing, system prompt selection, tool schema injection, and
        message list construction.

        Returns:
            (messages, adapter_type) tuple. messages is None if model not loaded.
        """
        if not self.health.model_loaded or self._llm is None:
            return None, ''

        adapter_type = adapter or self.classify_query(user_query)

        available = set(self._merged_models) | set(self._lora_adapters)
        if adapter_type != self._active_lora and adapter_type in available:
            logger.info('Switching adapter: %s → %s', self._active_lora, adapter_type)
            if not self.switch_adapter(adapter_type):
                logger.warning(
                    'Adapter switch failed, continuing with %s',
                    self._active_lora,
                )
                adapter_type = self._active_lora

        if adapter_type == 'tool_use':
            prompt_key = 'tool_use'
        else:
            prompt_key = system_prompt_key
        system_prompt = self.get_system_prompt(prompt_key)

        if adapter_type == 'tool_use' and self._tool_schemas:
            tool_lines = []
            for t in self._tool_schemas:
                name = t['name']
                desc = t['description']
                props = t.get('parameters', {}).get('properties', {})
                req = t.get('parameters', {}).get('required', [])
                parts = []
                for pname in props:
                    parts.append(pname if pname in req else f'{pname}?')
                tool_lines.append(f'- {name}({", ".join(parts)}) - {desc}')
            system_prompt = (
                f'{system_prompt}\n\nAvailable tools:\n'
                + '\n'.join(tool_lines)
            )

        messages = [{'role': 'system', 'content': system_prompt}]
        if context:
            messages.append({'role': 'user', 'content': f'Context: {context}'})
            messages.append(
                {'role': 'assistant', 'content': 'Understood, I have that context.'}
            )
        if history:
            for turn in history[-6:]:
                role = turn.get('role', '')
                content = turn.get('content', '')
                if role in ('user', 'assistant') and content:
                    msg_role = 'user' if role == 'user' else 'assistant'
                    messages.append({'role': msg_role, 'content': content})
        messages.append({'role': 'user', 'content': user_query})

        return messages, adapter_type

    def query_stream(
        self,
        user_query: str,
        system_prompt_key: str = 'default',
        context: str = '',
        adapter: Optional[str] = None,
        history: Optional[list] = None,
    ) -> Generator[str, None, InferenceResult]:
        """Run streaming inference, yielding tokens as they are generated.

        Yields each token string as it arrives from llama.cpp. After the
        generator is exhausted, the return value is the full InferenceResult
        (access via StopIteration.value or use the wrapper helper).

        Args:
            user_query: The passenger's question.
            system_prompt_key: Key for system prompt selection.
            context: Additional context.
            adapter: Force adapter type or None for auto.
            history: Optional conversation history.

        Yields:
            Token strings as they are generated.

        Returns:
            InferenceResult with full text, latency, and metadata.
        """
        result = InferenceResult()

        messages, adapter_type = self._prepare_inference(
            user_query, system_prompt_key, context, adapter, history,
        )
        if messages is None:
            result.success = False
            result.error = 'Model not loaded'
            self.health.errors += 1
            return result

        result.adapter_used = adapter_type

        t_start = time.monotonic()
        full_text = []
        try:
            stream = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                top_k=self.config.top_k,
                repeat_penalty=self.config.repeat_penalty,
                min_p=self.config.min_p,
                stream=True,
            )
            for chunk in stream:
                delta = chunk['choices'][0].get('delta', {})
                token = delta.get('content', '')
                if token:
                    full_text.append(token)
                    yield token

            t_end = time.monotonic()
            result.text = ''.join(full_text)
            result.latency_ms = (t_end - t_start) * 1000
            result.completion_tokens = len(full_text)
            if result.latency_ms > 0:
                result.tokens_per_sec = (
                    result.completion_tokens / (result.latency_ms / 1000)
                )

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.text = ''.join(full_text)
            result.latency_ms = (time.monotonic() - t_start) * 1000
            self.health.errors += 1
            logger.error('Streaming inference failed: %s', e)

        # Update health stats
        self.health.total_queries += 1
        self.health.last_latency_ms = result.latency_ms
        self.health.active_adapter = self._active_lora
        self.health.rss_mb = self._get_rss_mb()
        self.health.latency_history.append(result.latency_ms)
        if len(self.health.latency_history) > self.MAX_LATENCY_HISTORY:
            self.health.latency_history = self.health.latency_history[
                -self.MAX_LATENCY_HISTORY:
            ]
        if self.health.latency_history:
            self.health.avg_latency_ms = (
                sum(self.health.latency_history)
                / len(self.health.latency_history)
            )
            sorted_lat = sorted(self.health.latency_history)
            idx_95 = min(
                int(len(sorted_lat) * 0.95), len(sorted_lat) - 1
            )
            self.health.p95_latency_ms = sorted_lat[idx_95]

        return result

    def parse_tool_call(self, text: str) -> Optional[dict]:
        """Extract tool call from model output.

        Parses <tool_call>...</tool_call> format from model output.

        Args:
            text: Model output text.

        Returns:
            Dict with 'name' and 'arguments', or None if no tool call.
        """
        pattern = r'<tool_call>(.*?)</tool_call>'
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None

        try:
            call_data = json.loads(match.group(1).strip())
            if 'name' in call_data:
                return call_data
        except json.JSONDecodeError:
            logger.warning('Failed to parse tool call JSON: %s', match.group(1))

        return None

    def get_health(self) -> dict:
        """Get current health status as a dictionary.

        Returns:
            Health stats dict suitable for serialization.
        """
        return {
            'model_loaded': self.health.model_loaded,
            'model_name': self.health.model_name,
            'rss_mb': round(self.health.rss_mb, 1),
            'total_queries': self.health.total_queries,
            'avg_latency_ms': round(self.health.avg_latency_ms, 1),
            'p95_latency_ms': round(self.health.p95_latency_ms, 1),
            'last_latency_ms': round(self.health.last_latency_ms, 1),
            'errors': self.health.errors,
            'active_adapter': self.health.active_adapter,
        }

    @staticmethod
    def _get_rss_mb() -> float:
        """Get current process RSS in MB."""
        try:
            import psutil
            return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        except ImportError:
            # Fallback: read /proc on Linux
            try:
                with open('/proc/self/status', 'r') as f:
                    for line in f:
                        if line.startswith('VmRSS:'):
                            return int(line.split()[1]) / 1024  # kB → MB
            except (FileNotFoundError, ValueError):
                pass
        return 0.0

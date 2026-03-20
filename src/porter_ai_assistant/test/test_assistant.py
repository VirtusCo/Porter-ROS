# Copyright 2026 VirtusCo
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for Porter AI Assistant components."""

from porter_ai_assistant.config import (
    DEFAULT_MODEL_FILENAME,
    DEFAULT_N_CTX,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
    MODEL_SELECTION_NOTES,
)
from porter_ai_assistant.inference_engine import (
    HealthStats,
    InferenceEngine,
    InferenceResult,
    ModelConfig,
)
from porter_ai_assistant.prompt_templates import FALLBACK_PROMPTS, PromptManager


class TestModelConfig:
    """Test ModelConfig dataclass defaults."""

    def test_default_model_filename(self):
        """Verify default model filename is Qwen 2.5 1.5B."""
        assert 'qwen2.5-1.5b' in DEFAULT_MODEL_FILENAME

    def test_default_context_window(self):
        """Verify default context window optimized for airport Q&A + SLAM."""
        assert DEFAULT_N_CTX == 1024

    def test_default_generation_params(self):
        """Verify generation params for grounded airport responses."""
        assert DEFAULT_TEMPERATURE == 0.7
        assert DEFAULT_TOP_P == 0.9
        assert DEFAULT_TOP_K == 50

    def test_model_selection_notes(self):
        """Verify model selection notes contain Qwen 2.5."""
        assert 'Qwen 2.5' in MODEL_SELECTION_NOTES['primary']
        assert MODEL_SELECTION_NOTES['actual_model_size_mb'] == 1000


class TestInferenceResult:
    """Test InferenceResult dataclass."""

    def test_default_values(self):
        """Verify default InferenceResult is successful with empty text."""
        result = InferenceResult()
        assert result.success is True
        assert result.text == ''
        assert result.latency_ms == 0.0
        assert result.adapter_used == 'none'

    def test_error_result(self):
        """Verify error result construction."""
        result = InferenceResult(success=False, error='model not loaded')
        assert result.success is False
        assert result.error == 'model not loaded'


class TestHealthStats:
    """Test HealthStats dataclass."""

    def test_initial_state(self):
        """Verify initial health stats are zeroed."""
        stats = HealthStats()
        assert stats.model_loaded is False
        assert stats.total_queries == 0
        assert stats.errors == 0
        assert stats.avg_latency_ms == 0.0


class TestModelConfigDataclass:
    """Test ModelConfig dataclass defaults."""

    def test_qwen25_defaults(self):
        """Verify Qwen 2.5 tuned defaults in ModelConfig."""
        config = ModelConfig()
        assert config.temperature == 0.7
        assert config.top_p == 0.9
        assert config.top_k == 50
        assert config.min_p == 0.0
        assert config.n_ctx == 1024
        assert config.n_threads == 2  # 2 = reserve 2 cores for SLAM/Nav2 on RPi
        assert config.n_threads_batch == 0  # 0 = same as n_threads
        assert config.n_batch == 512
        assert config.flash_attn is False


class TestInferenceEngine:
    """Test InferenceEngine without a model loaded."""

    def test_query_without_model(self):
        """Verify query fails gracefully when no model is loaded."""
        engine = InferenceEngine()
        result = engine.query('Hello')
        assert result.success is False
        assert 'not loaded' in result.error.lower()

    def test_classify_query_conversational(self):
        """Verify conversational query classification."""
        engine = InferenceEngine()
        engine.set_tool_keywords(['escort', 'carry my', 'flight status'])
        assert engine.classify_query('Where is Gate B12?') == 'conversational'

    def test_classify_query_tool_use(self):
        """Verify tool-use query classification."""
        engine = InferenceEngine()
        engine.set_tool_keywords(['escort', 'carry my', 'flight status'])
        assert engine.classify_query('Can you escort me to Gate B12?') == 'tool_use'

    def test_get_health_empty(self):
        """Verify health dict structure when no model loaded."""
        engine = InferenceEngine()
        health = engine.get_health()
        assert health['model_loaded'] is False
        assert 'rss_mb' in health
        assert 'total_queries' in health
        assert 'errors' in health

    def test_parse_tool_call_valid(self):
        """Verify tool call parsing from model output."""
        engine = InferenceEngine()
        text = (
            'Let me help. <tool_call>'
            '{"name": "escort", "arguments": {"gate": "B12"}}'
            '</tool_call>'
        )
        result = engine.parse_tool_call(text)
        assert result is not None
        assert result['name'] == 'escort'
        assert result['arguments']['gate'] == 'B12'

    def test_parse_tool_call_none(self):
        """Verify no tool call returns None."""
        engine = InferenceEngine()
        result = engine.parse_tool_call('Gate B12 is to the left.')
        assert result is None


class TestPromptManager:
    """Test prompt template management."""

    def test_fallback_prompts(self):
        """Verify fallback prompts exist."""
        assert 'default' in FALLBACK_PROMPTS
        assert 'tool_use' in FALLBACK_PROMPTS
        assert 'Virtue' in FALLBACK_PROMPTS['default']

    def test_default_manager(self):
        """Verify PromptManager uses fallbacks when no YAML loaded."""
        pm = PromptManager()
        prompt = pm.get('default')
        assert 'Virtue' in prompt

    def test_get_unknown_key(self):
        """Verify unknown key falls back to default."""
        pm = PromptManager()
        prompt = pm.get('nonexistent_key')
        assert 'Virtue' in prompt

    def test_get_for_adapter_tool(self):
        """Verify tool-use adapter gets tool prompt."""
        pm = PromptManager()
        prompt = pm.get_for_adapter('tool_use')
        assert 'tool' in prompt.lower()

    def test_get_for_adapter_conversational(self):
        """Verify conversational adapter gets default prompt."""
        pm = PromptManager()
        prompt = pm.get_for_adapter('conversational')
        assert 'Virtue' in prompt

    def test_available_keys(self):
        """Verify available keys returns a sorted list."""
        pm = PromptManager()
        keys = pm.available_keys
        assert isinstance(keys, list)
        assert 'default' in keys

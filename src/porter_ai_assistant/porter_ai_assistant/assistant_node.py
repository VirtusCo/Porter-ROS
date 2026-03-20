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
"""ROS 2 service node for Porter AI Assistant.

Provides query processing backed by llama-cpp-python inference on GGUF models
with modular LoRA adapter hot-swapping. Handles model loading, query routing
(conversational vs tool-use), health monitoring, and response publishing.

Services:
    ~/query (std_srvs/Trigger): Process last received query (or test query).
    ~/get_status (std_srvs/Trigger): Get model health / status.

Topics (subscribe):
    /porter/ai_query (std_msgs/String): Incoming queries from GUI or other nodes.

Topics (publish):
    /porter/ai_response (std_msgs/String): JSON responses for GUI display.
    /diagnostics (diagnostic_msgs/DiagnosticArray): Health diagnostics.

Parameters:
    See config/assistant_params.yaml for full list.
"""

import json
import traceback

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from porter_ai_assistant.config import (
    DEFAULT_FLASH_ATTN,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_P,
    DEFAULT_MODEL_FILENAME,
    DEFAULT_N_BATCH,
    DEFAULT_N_CTX,
    DEFAULT_N_GPU_LAYERS,
    DEFAULT_N_THREADS,
    DEFAULT_N_THREADS_BATCH,
    DEFAULT_REPEAT_PENALTY,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
    HEALTH_CHECK_INTERVAL_SEC,
    LATENCY_ERROR_MS,
    LATENCY_WARN_MS,
    MAX_RSS_MB,
    MODELS_DIR,
)
from porter_ai_assistant.inference_engine import InferenceEngine, ModelConfig
from porter_ai_assistant.prompt_templates import PromptManager
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


class AssistantNode(Node):
    """ROS 2 node for the Porter AI Assistant.

    Wraps the InferenceEngine with ROS 2 services, topics, and parameter
    management. Loads GGUF model on startup, provides query service,
    publishes responses and diagnostics.
    """

    def __init__(self):
        """Initialize the assistant node with parameters and services."""
        super().__init__('porter_ai_assistant')

        # ── Declare Parameters ───────────────────────────────────────────────
        # Base GGUF model + LoRA directory (see CLAUDE.md lesson #36:
        # never merge QLoRA into base — use runtime LoRA adapter loading)
        self.declare_parameter('model_path',
                               f'models/gguf/{DEFAULT_MODEL_FILENAME}')
        self.declare_parameter('lora_dir', 'models/gguf')
        self.declare_parameter('default_adapter', 'conversational')

        self.declare_parameter('max_tokens', DEFAULT_MAX_TOKENS)
        self.declare_parameter('temperature', DEFAULT_TEMPERATURE)
        self.declare_parameter('top_p', DEFAULT_TOP_P)
        self.declare_parameter('top_k', DEFAULT_TOP_K)
        self.declare_parameter('min_p', DEFAULT_MIN_P)
        self.declare_parameter('repeat_penalty', DEFAULT_REPEAT_PENALTY)

        self.declare_parameter('n_ctx', DEFAULT_N_CTX)
        self.declare_parameter('n_batch', DEFAULT_N_BATCH)
        self.declare_parameter('n_threads', DEFAULT_N_THREADS)
        self.declare_parameter('n_threads_batch', DEFAULT_N_THREADS_BATCH)
        self.declare_parameter('n_gpu_layers', DEFAULT_N_GPU_LAYERS)
        self.declare_parameter('flash_attn', DEFAULT_FLASH_ATTN)
        self.declare_parameter('use_mmap', True)
        self.declare_parameter('use_mlock', False)

        self.declare_parameter('default_system_prompt', 'default')
        self.declare_parameter('system_prompts_file', 'data/system_prompts.yaml')
        self.declare_parameter('tool_keywords', [
            'take me', 'escort', 'carry my', 'weigh',
            'flight status', 'flight number',
            'directions to', 'navigate',
            'find nearest', 'where is the nearest',
            'call assistance', 'wheelchair',
        ])

        self.declare_parameter('service_timeout_sec', 5.0)
        self.declare_parameter('warmup_on_start', True)
        self.declare_parameter('log_queries', False)

        self.declare_parameter('health_check_interval_sec',
                               HEALTH_CHECK_INTERVAL_SEC)
        self.declare_parameter('max_memory_mb', float(MAX_RSS_MB))
        self.declare_parameter('max_latency_warn_ms', LATENCY_WARN_MS)
        self.declare_parameter('max_latency_error_ms', LATENCY_ERROR_MS)

        # ── Build Engine Config ──────────────────────────────────────────────
        model_path = self.get_parameter(
            'model_path').get_parameter_value().string_value
        if not model_path.startswith('/'):
            model_path = str(MODELS_DIR.parent / model_path)

        lora_dir = self.get_parameter(
            'lora_dir').get_parameter_value().string_value
        if not lora_dir.startswith('/'):
            lora_dir = str(MODELS_DIR.parent / lora_dir)

        config = ModelConfig(
            model_path=model_path,
            lora_dir=lora_dir,
            n_ctx=self.get_parameter('n_ctx').get_parameter_value().integer_value,
            n_batch=self.get_parameter(
                'n_batch').get_parameter_value().integer_value,
            n_threads=self.get_parameter(
                'n_threads').get_parameter_value().integer_value,
            n_threads_batch=self.get_parameter(
                'n_threads_batch').get_parameter_value().integer_value,
            n_gpu_layers=self.get_parameter(
                'n_gpu_layers').get_parameter_value().integer_value,
            flash_attn=self.get_parameter(
                'flash_attn').get_parameter_value().bool_value,
            use_mmap=self.get_parameter(
                'use_mmap').get_parameter_value().bool_value,
            use_mlock=self.get_parameter(
                'use_mlock').get_parameter_value().bool_value,
            max_tokens=self.get_parameter(
                'max_tokens').get_parameter_value().integer_value,
            temperature=self.get_parameter(
                'temperature').get_parameter_value().double_value,
            top_p=self.get_parameter(
                'top_p').get_parameter_value().double_value,
            top_k=self.get_parameter(
                'top_k').get_parameter_value().integer_value,
            min_p=self.get_parameter(
                'min_p').get_parameter_value().double_value,
            repeat_penalty=self.get_parameter(
                'repeat_penalty').get_parameter_value().double_value,
        )

        # ── Initialize Engine ────────────────────────────────────────────────
        self.engine = InferenceEngine(config)

        # Load system prompts
        prompts_file = self.get_parameter(
            'system_prompts_file').get_parameter_value().string_value
        if not prompts_file.startswith('/'):
            prompts_file = str(MODELS_DIR.parent / prompts_file)
        self.prompt_manager = PromptManager(prompts_file)

        # Set tool keywords for query classification
        tool_kw = self.get_parameter(
            'tool_keywords').get_parameter_value().string_array_value
        self.engine.set_tool_keywords(tool_kw)

        # ── Publishers ───────────────────────────────────────────────────────
        self.response_pub = self.create_publisher(
            String, '/porter/ai_response', 10
        )
        self.diag_pub = self.create_publisher(
            DiagnosticArray, '/diagnostics', 10
        )

        # ── Subscribers ──────────────────────────────────────────────────────
        self._pending_query = None
        self.query_sub = self.create_subscription(
            String, '/porter/ai_query', self._on_query_received, 10
        )

        # ── Services ─────────────────────────────────────────────────────────
        self.query_srv = self.create_service(
            Trigger, '~/query', self.handle_query
        )
        self.status_srv = self.create_service(
            Trigger, '~/get_status', self.handle_get_status
        )

        # ── Health Timer ─────────────────────────────────────────────────────
        health_interval = self.get_parameter(
            'health_check_interval_sec').get_parameter_value().double_value
        self.health_timer = self.create_timer(
            health_interval, self.publish_diagnostics
        )

        # ── Model Loading ────────────────────────────────────────────────────
        self._model_loaded = False
        self.get_logger().info(
            'Porter AI Assistant node started — loading model...'
        )
        self._load_model_deferred()

    def _load_model_deferred(self):
        """Load the model (called at startup)."""
        try:
            default_adapter = self.get_parameter(
                'default_adapter').get_parameter_value().string_value
            success = self.engine.load_model(
                lora_adapter=default_adapter
            )
            self._model_loaded = success
            if success:
                self.get_logger().info(
                    'Model loaded: %s (RSS: %.0f MB)',
                    self.engine.health.model_name,
                    self.engine.health.rss_mb,
                )
                warmup = self.get_parameter(
                    'warmup_on_start').get_parameter_value().bool_value
                if warmup:
                    self._warmup()
            else:
                self.get_logger().error('Failed to load model')
        except Exception as e:
            self.get_logger().error('Model load exception: %s', str(e))
            self._model_loaded = False

    def _warmup(self):
        """Run a dummy inference to warm caches."""
        self.get_logger().info('Warming up model...')
        result = self.engine.query('Hello', adapter='conversational')
        if result.success:
            self.get_logger().info(
                'Warmup complete (%.0f ms)', result.latency_ms
            )
        else:
            self.get_logger().warn('Warmup failed: %s', result.error)

    def _on_query_received(self, msg):
        """Handle incoming query from /porter/ai_query topic.

        Processes the query immediately and publishes response to
        /porter/ai_response. This is the primary query interface.
        """
        query_text = msg.data.strip()
        if not query_text:
            return

        if not self._model_loaded:
            self.get_logger().warn(
                'Query received but model not loaded: %s', query_text[:50]
            )
            return

        self.get_logger().info("Query: '%s'", query_text[:80])
        try:
            result = self.engine.query(
                query_text,
                system_prompt_key=self.get_parameter(
                    'default_system_prompt'
                ).get_parameter_value().string_value,
            )
            if result.success:
                resp_msg = String()
                resp_msg.data = json.dumps({
                    'query': query_text,
                    'response': result.text,
                    'latency_ms': round(result.latency_ms, 1),
                    'adapter': result.adapter_used,
                })
                self.response_pub.publish(resp_msg)
                self.get_logger().info(
                    'Response (%.0f ms, %s): %s',
                    result.latency_ms,
                    result.adapter_used,
                    result.text[:80],
                )
            else:
                self.get_logger().error('Query failed: %s', result.error)
        except Exception as e:
            self.get_logger().error('Query error: %s', e)

        # Store as pending for service call retrieval
        self._pending_query = query_text

    def handle_query(self, request, response):
        """Handle ~/query service call.

        Processes the last query received on /porter/ai_query topic.
        If no query is pending, uses a test query. In production,
        replace with a custom AiQuery.srv that carries the query text.
        """
        if not self._model_loaded:
            response.success = False
            response.message = 'Model not loaded'
            return response

        query_text = self._pending_query or 'Where is Gate B12?'
        self._pending_query = None

        try:
            result = self.engine.query(
                query_text,
                system_prompt_key=self.get_parameter(
                    'default_system_prompt'
                ).get_parameter_value().string_value,
            )
            response.success = result.success
            response.message = result.text if result.success else result.error

            # Publish to topic for GUI
            if result.success:
                msg = String()
                msg.data = json.dumps({
                    'query': query_text,
                    'response': result.text,
                    'latency_ms': round(result.latency_ms, 1),
                    'adapter': result.adapter_used,
                })
                self.response_pub.publish(msg)

            log_queries = self.get_parameter(
                'log_queries').get_parameter_value().bool_value
            if log_queries:
                self.get_logger().info(
                    "Query: '%s' → %s (%.0f ms, %s)",
                    query_text, result.text[:80],
                    result.latency_ms, result.adapter_used,
                )

        except Exception as e:
            response.success = False
            response.message = f'Inference error: {e}'
            self.get_logger().error(
                'Query handler error: %s\n%s', e, traceback.format_exc()
            )

        return response

    def handle_get_status(self, request, response):
        """Handle ~/get_status service call — returns health JSON."""
        health = self.engine.get_health()
        response.success = health.get('model_loaded', False)
        response.message = json.dumps(health, indent=2)
        return response

    def publish_diagnostics(self):
        """Publish health diagnostics periodically."""
        health = self.engine.get_health()

        status = DiagnosticStatus()
        status.name = 'porter_ai_assistant'
        status.hardware_id = 'ai_model'

        if not health['model_loaded']:
            status.level = DiagnosticStatus.ERROR
            status.message = 'Model not loaded'
        elif health['avg_latency_ms'] > self.get_parameter(
                'max_latency_error_ms').get_parameter_value().double_value:
            status.level = DiagnosticStatus.ERROR
            status.message = f"High latency: {health['avg_latency_ms']:.0f} ms"
        elif health['avg_latency_ms'] > self.get_parameter(
                'max_latency_warn_ms').get_parameter_value().double_value:
            status.level = DiagnosticStatus.WARN
            status.message = f"Elevated latency: {health['avg_latency_ms']:.0f} ms"
        elif health['rss_mb'] > self.get_parameter(
                'max_memory_mb').get_parameter_value().double_value:
            status.level = DiagnosticStatus.WARN
            status.message = f"High memory: {health['rss_mb']:.0f} MB"
        else:
            status.level = DiagnosticStatus.OK
            status.message = 'OK'

        status.values = [
            KeyValue(key='model_name', value=str(health['model_name'])),
            KeyValue(key='rss_mb', value=str(health['rss_mb'])),
            KeyValue(key='total_queries', value=str(health['total_queries'])),
            KeyValue(key='avg_latency_ms', value=str(health['avg_latency_ms'])),
            KeyValue(key='p95_latency_ms', value=str(health['p95_latency_ms'])),
            KeyValue(key='errors', value=str(health['errors'])),
            KeyValue(key='active_adapter', value=str(health['active_adapter'])),
        ]

        diag_msg = DiagnosticArray()
        diag_msg.header.stamp = self.get_clock().now().to_msg()
        diag_msg.status.append(status)
        self.diag_pub.publish(diag_msg)


def main(args=None):
    """Entry point for the assistant node."""
    rclpy.init(args=args)
    node = AssistantNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.engine.unload_model()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

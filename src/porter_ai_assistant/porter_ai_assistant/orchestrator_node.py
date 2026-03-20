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
"""ROS 2 node wrapping the Virtue AI conversation orchestrator.

This is the production-ready node for GUI integration. It replaces the
simpler assistant_node by adding:
- Tool execution loop (model calls tools, results fed back)
- Conversation memory (sliding window per session)
- Session management (create, expire, clear)
- Full orchestration statistics

Topics (subscribe):
    /porter/ai_query (std_msgs/String): JSON with 'query' and optional
        'session_id', 'context' fields.

Topics (publish):
    /porter/ai_response (std_msgs/String): JSON response for GUI display.
    /diagnostics (diagnostic_msgs/DiagnosticArray): Health diagnostics.

Services:
    ~/query (std_srvs/Trigger): Process last received query.
    ~/get_status (std_srvs/Trigger): Orchestrator health and stats.
    ~/clear_session (std_srvs/Trigger): Clear default session history.
"""

import json
import traceback

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue

from porter_ai_assistant.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_P,
    DEFAULT_MODEL_FILENAME,
    DEFAULT_N_BATCH,
    DEFAULT_N_CTX,
    DEFAULT_N_GPU_LAYERS,
    DEFAULT_N_THREADS,
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
from porter_ai_assistant.orchestrator import ConversationOrchestrator
from porter_ai_assistant.prompt_templates import PromptManager
from porter_ai_assistant.tool_executor import create_stub_tools, ToolExecutor

import rclpy
from rclpy.node import Node

from std_msgs.msg import String

from std_srvs.srv import Trigger


class OrchestratorNode(Node):
    """ROS 2 node for the Virtue AI orchestrator.

    Wraps ConversationOrchestrator with ROS 2 interfaces.
    Manages the full query lifecycle: classify, infer, execute tools,
    respond, with conversation memory.
    """

    def __init__(self):
        """Initialize the orchestrator node."""
        super().__init__('virtue_orchestrator')

        # ── Parameters ───────────────────────────────────────────────────────
        # Model parameters (same as assistant_node)
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
        self.declare_parameter('n_gpu_layers', DEFAULT_N_GPU_LAYERS)
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

        # Orchestrator-specific parameters
        self.declare_parameter('memory_size', 10)
        self.declare_parameter('session_timeout_sec', 300.0)
        self.declare_parameter('log_queries', False)
        self.declare_parameter('warmup_on_start', True)

        # Health parameters
        self.declare_parameter('health_check_interval_sec',
                               HEALTH_CHECK_INTERVAL_SEC)
        self.declare_parameter('max_memory_mb', float(MAX_RSS_MB))
        self.declare_parameter('max_latency_warn_ms', LATENCY_WARN_MS)
        self.declare_parameter('max_latency_error_ms', LATENCY_ERROR_MS)

        # ── Build Engine ─────────────────────────────────────────────────────
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
            n_ctx=self.get_parameter(
                'n_ctx').get_parameter_value().integer_value,
            n_batch=self.get_parameter(
                'n_batch').get_parameter_value().integer_value,
            n_threads=self.get_parameter(
                'n_threads').get_parameter_value().integer_value,
            n_gpu_layers=self.get_parameter(
                'n_gpu_layers').get_parameter_value().integer_value,
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

        self.engine = InferenceEngine(config)

        # Load system prompts
        prompts_file = self.get_parameter(
            'system_prompts_file').get_parameter_value().string_value
        if not prompts_file.startswith('/'):
            prompts_file = str(MODELS_DIR.parent / prompts_file)
        self.prompt_manager = PromptManager(prompts_file)

        # Set tool keywords
        tool_kw = self.get_parameter(
            'tool_keywords').get_parameter_value().string_array_value
        self.engine.set_tool_keywords(tool_kw)

        # ── Build Tool Executor ──────────────────────────────────────────────
        self.tool_executor = ToolExecutor()
        stub_tools = create_stub_tools()
        for name, fn in stub_tools.items():
            self.tool_executor.register(name, fn)
        self.get_logger().info(
            'Registered %d tools: %s',
            len(stub_tools), ', '.join(sorted(stub_tools.keys())),
        )

        # ── Build Orchestrator ───────────────────────────────────────────────
        memory_size = self.get_parameter(
            'memory_size').get_parameter_value().integer_value
        session_timeout = self.get_parameter(
            'session_timeout_sec').get_parameter_value().double_value

        self.orchestrator = ConversationOrchestrator(
            engine=self.engine,
            tools=self.tool_executor,
            memory_size=memory_size,
            session_timeout_sec=session_timeout,
        )

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
        self.clear_srv = self.create_service(
            Trigger, '~/clear_session', self.handle_clear_session
        )

        # ── Health Timer ─────────────────────────────────────────────────────
        health_interval = self.get_parameter(
            'health_check_interval_sec').get_parameter_value().double_value
        self.health_timer = self.create_timer(
            health_interval, self.publish_diagnostics
        )

        # ── Session cleanup timer (every 60s) ────────────────────────────────
        self.cleanup_timer = self.create_timer(
            60.0, self._cleanup_sessions
        )

        # ── Model Loading ────────────────────────────────────────────────────
        self._model_loaded = False
        self.get_logger().info(
            'Virtue Orchestrator node started — loading model...'
        )
        self._load_model()

    def _load_model(self):
        """Load model and optionally run warmup."""
        try:
            default_adapter = self.get_parameter(
                'default_adapter').get_parameter_value().string_value
            success = self.engine.load_model(lora_adapter=default_adapter)
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
                    result = self.engine.query(
                        'Hello', adapter='conversational',
                    )
                    if result.success:
                        self.get_logger().info(
                            'Warmup done (%.0f ms)', result.latency_ms,
                        )
            else:
                self.get_logger().error('Failed to load model')
        except Exception as e:
            self.get_logger().error('Model load exception: %s', str(e))
            self._model_loaded = False

    def _on_query_received(self, msg):
        """Handle query from /porter/ai_query topic.

        Expects JSON: {"query": "...", "session_id": "...", "context": {...}}
        Falls back to plain text if JSON parsing fails.
        """
        raw = msg.data.strip()
        if not raw:
            return

        if not self._model_loaded:
            self.get_logger().warn(
                'Query received but model not loaded: %s', raw[:50],
            )
            return

        # Parse input — JSON preferred, plain text fallback
        query_text = raw
        session_id = None
        context = None

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                query_text = parsed.get('query', raw)
                session_id = parsed.get('session_id')
                context = parsed.get('context')
        except (json.JSONDecodeError, TypeError):
            pass  # Plain text query

        self.get_logger().info(
            "Query [%s]: '%s'",
            session_id or 'default', query_text[:80],
        )

        # Process through orchestrator
        try:
            result = self.orchestrator.process_query(
                user_query=query_text,
                session_id=session_id,
                context=context,
            )

            resp_msg = String()
            resp_data = {
                'query': query_text,
                'response': result.response,
                'session_id': result.session_id,
                'adapter': result.adapter_used,
                'latency_ms': round(result.total_latency_ms, 1),
                'success': result.success,
            }

            # Include tool info if tools were called
            if result.tool_calls:
                resp_data['tools_called'] = [
                    tc.get('name', '') for tc in result.tool_calls
                ]
                resp_data['tool_latency_ms'] = round(
                    result.tool_latency_ms, 1,
                )

            if result.error:
                resp_data['error'] = result.error

            resp_msg.data = json.dumps(resp_data)
            self.response_pub.publish(resp_msg)

            log_queries = self.get_parameter(
                'log_queries').get_parameter_value().bool_value
            if log_queries or result.tool_calls:
                self.get_logger().info(
                    'Response (%.0f ms, %s, tools=%d): %s',
                    result.total_latency_ms,
                    result.adapter_used,
                    len(result.tool_calls),
                    result.response[:80],
                )

        except Exception as e:
            self.get_logger().error(
                'Orchestrator error: %s\n%s', e, traceback.format_exc(),
            )

        self._pending_query = query_text

    def handle_query(self, request, response):
        """Handle ~/query service — process last received or test query."""
        if not self._model_loaded:
            response.success = False
            response.message = 'Model not loaded'
            return response

        query_text = self._pending_query or 'Where is Gate B12?'
        self._pending_query = None

        try:
            result = self.orchestrator.process_query(user_query=query_text)
            response.success = result.success
            response.message = result.response if result.success else result.error

            if result.success:
                resp_msg = String()
                resp_msg.data = json.dumps({
                    'query': query_text,
                    'response': result.response,
                    'session_id': result.session_id,
                    'adapter': result.adapter_used,
                    'latency_ms': round(result.total_latency_ms, 1),
                    'success': True,
                })
                self.response_pub.publish(resp_msg)

        except Exception as e:
            response.success = False
            response.message = f'Orchestrator error: {e}'
            self.get_logger().error(
                'Query handler error: %s\n%s', e, traceback.format_exc(),
            )

        return response

    def handle_get_status(self, request, response):
        """Handle ~/get_status — return orchestrator stats JSON."""
        stats = self.orchestrator.stats
        response.success = self._model_loaded
        response.message = json.dumps(stats, indent=2, default=str)
        return response

    def handle_clear_session(self, request, response):
        """Handle ~/clear_session — clear default session history."""
        cleared = self.orchestrator.clear_session()
        response.success = cleared
        response.message = 'Session cleared' if cleared else 'No session to clear'
        return response

    def _cleanup_sessions(self):
        """Periodic cleanup of expired sessions."""
        removed = self.orchestrator.cleanup_expired_sessions()
        if removed > 0:
            self.get_logger().info('Cleaned up %d expired sessions', removed)

    def publish_diagnostics(self):
        """Publish health diagnostics to /diagnostics."""
        health = self.engine.get_health()
        orch_stats = self.orchestrator.stats

        status = DiagnosticStatus()
        status.name = 'virtue_orchestrator'
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
            status.message = (
                f"Elevated latency: {health['avg_latency_ms']:.0f} ms"
            )
        elif health['rss_mb'] > self.get_parameter(
                'max_memory_mb').get_parameter_value().double_value:
            status.level = DiagnosticStatus.WARN
            status.message = f"High memory: {health['rss_mb']:.0f} MB"
        else:
            status.level = DiagnosticStatus.OK
            status.message = 'OK'

        status.values = [
            KeyValue(key='model_name',
                     value=str(health['model_name'])),
            KeyValue(key='rss_mb',
                     value=f"{health['rss_mb']:.1f}"),
            KeyValue(key='total_queries',
                     value=str(orch_stats['total_queries'])),
            KeyValue(key='total_errors',
                     value=str(orch_stats['total_errors'])),
            KeyValue(key='active_sessions',
                     value=str(orch_stats['active_sessions'])),
            KeyValue(key='avg_latency_ms',
                     value=f"{health['avg_latency_ms']:.1f}"),
            KeyValue(key='p95_latency_ms',
                     value=f"{health['p95_latency_ms']:.1f}"),
            KeyValue(key='active_adapter',
                     value=str(health['active_adapter'])),
        ]

        diag_msg = DiagnosticArray()
        diag_msg.header.stamp = self.get_clock().now().to_msg()
        diag_msg.status.append(status)
        self.diag_pub.publish(diag_msg)


def main(args=None):
    """Entry point for the orchestrator node."""
    rclpy.init(args=args)
    node = OrchestratorNode()
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

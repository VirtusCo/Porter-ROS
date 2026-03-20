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
"""Standalone HTTP AI server for the Porter GUI.

Simple HTTP JSON API wrapping the InferenceEngine. Allows the Flutter GUI
to query Virtue (the AI assistant) without requiring ROS 2 or rosbridge.

Endpoints:
    POST /api/chat    — Send a query, get AI response
    GET  /api/health  — Get model health stats
    GET  /api/status  — Check if server is alive

Usage:
    # From porter_robot/ root, with venv active:
    source .venv-finetune/bin/activate
    python src/porter_ai_assistant/scripts/ai_server.py

    # Or with custom port/model:
    python src/porter_ai_assistant/scripts/ai_server.py --port 8085 \
        --model models/gguf/qwen2.5-1.5b-instruct-q4_k_m.gguf
"""

import argparse
import json
import logging
import re
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Add parent package to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = SCRIPT_DIR.parent
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from porter_ai_assistant.inference_engine import InferenceEngine, ModelConfig
from porter_ai_assistant.orchestrator import ConversationOrchestrator
from porter_ai_assistant.rag_retriever import KnowledgeBaseRetriever
from porter_ai_assistant.tool_executor import ToolExecutor, create_stub_tools
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
    MODELS_DIR,
    DATA_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('ai_server')

# Global engine + orchestrator (single-user touchscreen, one instance is fine)
_engine: InferenceEngine = None
_orchestrator: ConversationOrchestrator = None
_engine_lock = threading.Lock()

# Tool-call friendly names for GUI display
_TOOL_DISPLAY_NAMES = {
    'get_flight_status': 'Checking flight status for {flight_number}...',
    'get_directions': 'Getting directions to {destination}...',
    'find_nearest': 'Finding the nearest {facility_type}...',
    'get_gate_info': 'Looking up gate {gate_id} information...',
    'weigh_luggage': 'Activating luggage scale...',
    'call_assistance': 'Requesting {assistance_type} assistance...',
    'escort_passenger': 'Setting navigation to {destination}...',
    'show_map': 'Displaying map of {area}...',
    'check_wait_time': 'Checking wait time at {queue_type}...',
    'set_reminder': 'Setting reminder for flight {flight_number}...',
    'get_airline_counter': 'Finding counter for {airline}...',
    'get_transport_options': 'Looking up transport to {destination}...',
    'translate_text': 'Translating to {target_language}...',
    'report_incident': 'Reporting {incident_type} incident...',
}

_TOOL_CALL_RE = re.compile(
    r'<tool_call>\s*(\{.*?\})\s*</tool_call>', re.DOTALL
)


def _humanize_tool_response(raw_text: str) -> str:
    """Convert <tool_call> JSON into user-friendly text for the GUI.

    If the response contains a tool call, extract the tool name and arguments,
    then format a natural-language message. If no tool call is found, return
    the raw text unchanged.
    """
    match = _TOOL_CALL_RE.search(raw_text)
    if not match:
        return raw_text

    try:
        call = json.loads(match.group(1))
        name = call.get('name', '')
        args = call.get('arguments', {})

        template = _TOOL_DISPLAY_NAMES.get(name)
        if template:
            try:
                return template.format(**args)
            except KeyError:
                # Template has placeholders the args don't fill
                pass

        # Fallback: describe the tool call generically
        arg_str = ', '.join(f'{k}={v}' for k, v in args.items())
        return f'Using {name.replace("_", " ")}({arg_str})...'

    except (json.JSONDecodeError, AttributeError):
        return raw_text


class AiRequestHandler(BaseHTTPRequestHandler):
    """Handle HTTP requests for the AI server."""

    def do_OPTIONS(self):
        """Handle CORS preflight (for browser testing, not needed for native)."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/api/health':
            self._handle_health()
        elif self.path == '/api/status':
            self._handle_status()
        else:
            self._send_json(404, {'error': 'Not found'})

    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/api/chat':
            self._handle_chat()
        elif self.path == '/api/chat/stream':
            self._handle_chat_stream()
        else:
            self._send_json(404, {'error': 'Not found'})

    def _handle_chat(self):
        """Process a chat query via orchestrator with tool execution."""
        global _engine, _orchestrator

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                # Try reading anyway in case of chunked encoding
                body = self.rfile.read1(4096) if hasattr(self.rfile, 'read1') \
                    else b''
                if not body:
                    self._send_json(400, {'error': 'Empty request body'})
                    return
            else:
                body = self.rfile.read(content_length)

            data = json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_json(400, {'error': f'Invalid JSON: {e}'})
            return

        query = data.get('query', '').strip()
        if not query:
            self._send_json(400, {'error': 'Missing "query" field'})
            return

        # Extract session id for conversation continuity
        session_id = data.get('session_id', 'gui_default')

        if _engine is None or not _engine.health.model_loaded:
            self._send_json(503, {'error': 'Model not loaded'})
            return

        # Run through orchestrator (handles tool execution + followup)
        with _engine_lock:
            orch_result = _orchestrator.process_query(
                user_query=query,
                session_id=session_id,
            )

        if orch_result.success:
            response_data = {
                'response': orch_result.response,
                'query': query,
                'latency_ms': round(orch_result.total_latency_ms, 1),
                'adapter': orch_result.adapter_used,
                'tokens': 0,
            }
            # Include tool execution info if tools were called
            if orch_result.tool_calls:
                response_data['tool_calls'] = orch_result.tool_calls
                response_data['tool_latency_ms'] = round(
                    orch_result.tool_latency_ms, 1,
                )
            self._send_json(200, response_data)
        else:
            self._send_json(500, {
                'error': orch_result.error,
                'query': query,
            })

    def _handle_health(self):
        """Return model health stats."""
        global _engine
        if _engine is None:
            self._send_json(503, {'error': 'Engine not initialized'})
            return
        health = _engine.get_health()
        self._send_json(200, health)

    def _handle_chat_stream(self):
        """Stream chat response via Server-Sent Events.

        Event types sent to client:
            event: adapter    — {"adapter": "tool_use"}
            event: tool_call  — {"tool_call": {...}}
            event: tool_result— {"tool_name": ..., "data": {...}}
            event: token      — {"token": "word"}
            event: done       — {"latency_ms": ..., "tool_calls": [...]}
            event: error      — {"error": "..."}
        """
        global _engine, _orchestrator

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                body = self.rfile.read1(4096) if hasattr(self.rfile, 'read1') \
                    else b''
                if not body:
                    self._send_json(400, {'error': 'Empty request body'})
                    return
            else:
                body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_json(400, {'error': f'Invalid JSON: {e}'})
            return

        query = data.get('query', '').strip()
        if not query:
            self._send_json(400, {'error': 'Missing "query" field'})
            return

        session_id = data.get('session_id', 'gui_default')

        if _engine is None or not _engine.health.model_loaded:
            self._send_json(503, {'error': 'Model not loaded'})
            return

        # Send SSE headers
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self._send_cors_headers()
        self.end_headers()

        try:
            with _engine_lock:
                for event in _orchestrator.process_query_stream(
                    user_query=query,
                    session_id=session_id,
                ):
                    event_type = event.get('event', 'unknown')
                    payload = json.dumps(event, default=str)
                    sse_line = f'event: {event_type}\ndata: {payload}\n\n'
                    self.wfile.write(sse_line.encode('utf-8'))
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            logger.info('Client disconnected during streaming')
        except Exception as e:
            logger.error('Streaming error: %s', e)
            try:
                err = json.dumps({'event': 'error', 'error': str(e)})
                self.wfile.write(f'event: error\ndata: {err}\n\n'.encode())
                self.wfile.flush()
            except Exception:
                pass

    def _handle_status(self):
        """Return alive check status."""
        global _engine
        loaded = _engine is not None and _engine.health.model_loaded
        self._send_json(200, {
            'status': 'ready' if loaded else 'loading',
            'model_loaded': loaded,
        })

    def _send_json(self, status_code, data):
        """Send a JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def _send_cors_headers(self):
        """Send CORS headers (for browser testing)."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, format, *args):
        """Override to use Python logging instead of stderr."""
        logger.info(format, *args)


def load_engine(model_path: str, lora_dir: str, adapter: str = 'conversational'):
    """Load the inference engine with model and set up orchestrator."""
    global _engine, _orchestrator

    config = ModelConfig(
        model_path=model_path,
        lora_dir=lora_dir,
        n_ctx=DEFAULT_N_CTX,
        n_batch=DEFAULT_N_BATCH,
        n_threads=DEFAULT_N_THREADS,
        n_threads_batch=DEFAULT_N_THREADS_BATCH,
        n_gpu_layers=DEFAULT_N_GPU_LAYERS,
        flash_attn=DEFAULT_FLASH_ATTN,
        use_mmap=True,
        use_mlock=False,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=DEFAULT_TEMPERATURE,
        top_p=DEFAULT_TOP_P,
        top_k=DEFAULT_TOP_K,
        min_p=DEFAULT_MIN_P,
        repeat_penalty=DEFAULT_REPEAT_PENALTY,
    )

    _engine = InferenceEngine(config)

    # Load system prompts
    prompts_path = str(DATA_DIR / 'system_prompts.yaml')
    _engine.load_system_prompts(prompts_path)

    # Load tool schemas for tool-use system prompt injection
    schemas_path = str(DATA_DIR / 'tool_schemas.json')
    _engine.load_tool_schemas(schemas_path)

    # Set tool keywords
    _engine.set_tool_keywords([
        # Exact substring matches (case-insensitive)
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
        # Regex patterns (prefix with 'r:') for flexible word order
        'r:status.*flight', 'r:flight.*status',
        'r:where.*gate', 'r:gate.*where',
        'r:find.*(?:coffee|food|restaurant|shop|lounge|atm)',
        'r:(?:book|reserve|get).*(?:wheelchair|assistance|cart)',
        'r:how.*(?:long|far|much)',
        'r:(?:my|the)\\s+flight',
    ])

    # Load model
    logger.info('Loading model: %s', model_path)
    success = _engine.load_model(lora_adapter=adapter)
    if success:
        logger.info(
            'Model loaded (RSS: %.0f MB). Running warmup...',
            _engine.health.rss_mb,
        )
        # Warmup inference
        result = _engine.query('Hello', adapter='conversational')
        if result.success:
            logger.info('Warmup complete (%.0f ms)', result.latency_ms)
        else:
            logger.warning('Warmup failed: %s', result.error)
        # Create tool executor with stub tools
        tool_executor = ToolExecutor()
        for name, func in create_stub_tools().items():
            tool_executor.register(name, func)
        logger.info(
            'Tool executor ready (%d tools registered)',
            len(tool_executor.list_tools()),
        )

        # Create orchestrator wrapping engine + tools + RAG
        retriever = KnowledgeBaseRetriever()
        if retriever.documents:
            logger.info(
                'RAG retriever ready (%d documents indexed)',
                len(retriever.documents),
            )
        else:
            logger.warning('RAG retriever has no documents — responses '
                           'will lack knowledge base context')
            retriever = None
        _orchestrator = ConversationOrchestrator(
            engine=_engine,
            tools=tool_executor,
            retriever=retriever,
        )
        logger.info('Orchestrator initialized with tool execution pipeline')
    else:
        logger.error('Failed to load model!')

    return success


def _find_merged_model(gguf_dir: Path, adapter: str) -> Path | None:
    """Find a merged fine-tuned GGUF for the given adapter name.

    Scan for files matching ``porter-<adapter>-*-Q*_K_*.gguf``.
    Returns the largest matching file (highest quantization quality).

    Args:
        gguf_dir: Directory containing GGUF files.
        adapter: Adapter name (e.g. 'conversational', 'tool_use').

    Returns:
        Path to merged GGUF, or None if not found.
    """
    if not gguf_dir.is_dir():
        return None
    prefix = f'porter-{adapter}-'
    candidates = [
        f for f in gguf_dir.glob(f'{prefix}*Q*_K_*.gguf')
        if '-lora-' not in f.name
    ]
    if not candidates:
        return None
    # Prefer largest file (best quantization)
    return max(candidates, key=lambda p: p.stat().st_size)


def main():
    """Entry point for the AI HTTP server."""
    parser = argparse.ArgumentParser(
        description='Porter AI Assistant HTTP Server',
    )
    parser.add_argument(
        '--port', type=int, default=8085,
        help='HTTP server port (default: 8085)',
    )
    parser.add_argument(
        '--host', type=str, default='0.0.0.0',
        help='Bind address (default: 0.0.0.0)',
    )
    parser.add_argument(
        '--model', type=str, default=None,
        help='Path to GGUF model file',
    )
    parser.add_argument(
        '--lora-dir', type=str, default=None,
        help='Path to LoRA adapter directory',
    )
    parser.add_argument(
        '--adapter', type=str, default='conversational',
        help='Default LoRA adapter (default: conversational)',
    )
    args = parser.parse_args()

    # Resolve model path — prefer merged fine-tuned GGUF over base model
    gguf_dir = MODELS_DIR / 'gguf'
    model_path = args.model
    if model_path is None:
        # Auto-detect merged fine-tuned model for the requested adapter
        merged = _find_merged_model(gguf_dir, args.adapter)
        if merged:
            model_path = str(merged)
            logger.info(
                'Auto-detected merged %s model: %s',
                args.adapter,
                merged.name,
            )
        else:
            model_path = str(gguf_dir / DEFAULT_MODEL_FILENAME)
            logger.info('Using base model: %s', DEFAULT_MODEL_FILENAME)
    if not Path(model_path).exists():
        logger.error('Model not found: %s', model_path)
        sys.exit(1)

    # Resolve LoRA directory
    lora_dir = args.lora_dir
    if lora_dir is None:
        lora_dir = str(MODELS_DIR / 'gguf')

    # Load model
    if not load_engine(model_path, lora_dir, args.adapter):
        logger.error('Failed to start — model load failed')
        sys.exit(1)

    # Start HTTP server (threaded to handle concurrent requests during SSE)
    server = ThreadingHTTPServer((args.host, args.port), AiRequestHandler)
    server.daemon_threads = True
    logger.info('AI server listening on http://%s:%d', args.host, args.port)
    logger.info('  POST /api/chat        — send query')
    logger.info('  POST /api/chat/stream — SSE streaming query')
    logger.info('  GET  /api/health      — model health')
    logger.info('  GET  /api/status      — alive check')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
    finally:
        server.server_close()
        if _engine:
            _engine.unload_model()


if __name__ == '__main__':
    main()

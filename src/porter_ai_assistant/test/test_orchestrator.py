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
"""Unit tests for tool executor and conversation orchestrator."""

import time
from unittest.mock import MagicMock

from porter_ai_assistant.inference_engine import InferenceResult
from porter_ai_assistant.orchestrator import (
    ConversationOrchestrator,
    ConversationTurn,
    OrchestratorResult,
    Session,
)
from porter_ai_assistant.tool_executor import (
    create_stub_tools,
    ToolExecutor,
    ToolResult,
)


# ── ToolResult Tests ────────────────────────────────────────────────────────

class TestToolResult:
    """Test ToolResult dataclass defaults."""

    def test_default_success(self):
        """Verify default ToolResult is successful."""
        result = ToolResult()
        assert result.success is True
        assert result.data == {}
        assert result.error == ''
        assert result.tool_name == ''

    def test_error_result(self):
        """Verify error ToolResult construction."""
        result = ToolResult(success=False, error='not found', tool_name='test')
        assert result.success is False
        assert result.error == 'not found'
        assert result.tool_name == 'test'


# ── ToolExecutor Tests ──────────────────────────────────────────────────────

class TestToolExecutor:
    """Test ToolExecutor registration and execution."""

    def test_register_and_has_tool(self):
        """Verify tool registration and lookup."""
        executor = ToolExecutor()
        executor.register('test_tool', lambda args: {'ok': True})
        assert executor.has_tool('test_tool') is True
        assert executor.has_tool('nonexistent') is False

    def test_list_tools(self):
        """Verify tool listing returns registered tools."""
        executor = ToolExecutor()
        executor.register('alpha', lambda args: {})
        executor.register('beta', lambda args: {})
        tools = executor.list_tools()
        assert 'alpha' in tools
        assert 'beta' in tools

    def test_execute_success(self):
        """Verify successful tool execution."""
        executor = ToolExecutor()
        executor.register('greet', lambda args: {
            'greeting': f"Hello {args.get('name', 'World')}",
        })
        result = executor.execute('greet', {'name': 'Alice'})
        assert result.success is True
        assert result.data['greeting'] == 'Hello Alice'
        assert result.tool_name == 'greet'
        assert result.latency_ms >= 0

    def test_execute_unknown_tool(self):
        """Verify unknown tool returns error result."""
        executor = ToolExecutor()
        result = executor.execute('nonexistent', {})
        assert result.success is False
        assert 'not found' in result.error.lower() or 'unknown' in result.error.lower()

    def test_execute_with_exception(self):
        """Verify tool exception is caught and returned as error."""
        executor = ToolExecutor()

        def raise_error(args):
            raise ValueError('boom')

        executor.register('bad_tool', raise_error)
        result = executor.execute('bad_tool', {})
        assert result.success is False
        assert 'boom' in result.error

    def test_unregister(self):
        """Verify tool unregistration."""
        executor = ToolExecutor()
        executor.register('temp', lambda args: {})
        assert executor.has_tool('temp') is True
        removed = executor.unregister('temp')
        assert removed is True
        assert executor.has_tool('temp') is False

    def test_unregister_nonexistent(self):
        """Verify unregistering unknown tool returns False."""
        executor = ToolExecutor()
        assert executor.unregister('ghost') is False

    def test_stats_tracking(self):
        """Verify execution statistics tracking."""
        executor = ToolExecutor()
        executor.register('counter', lambda args: {'count': 1})
        executor.execute('counter', {})
        executor.execute('counter', {})
        stats = executor.stats
        assert stats['total_calls'] == 2
        assert stats['total_errors'] == 0
        assert stats['registered_tools'] == 1

    def test_stats_with_errors(self):
        """Verify error counting in stats."""
        executor = ToolExecutor()
        executor.execute('missing', {})
        executor.execute('missing', {})
        stats = executor.stats
        assert stats['total_errors'] == 2


# ── Stub Tools Tests ────────────────────────────────────────────────────────

class TestStubTools:
    """Test that create_stub_tools provides all 14 tools."""

    def test_all_tools_registered(self):
        """Verify all 14 expected tools are created."""
        tools = create_stub_tools()
        expected = [
            'get_directions', 'get_flight_status', 'find_nearest',
            'weigh_luggage', 'get_gate_info', 'call_assistance',
            'escort_passenger', 'show_map', 'check_wait_time',
            'set_reminder', 'get_airline_counter',
            'get_transport_options', 'translate_text',
            'report_incident',
        ]
        for name in expected:
            assert name in tools, f'Missing tool: {name}'
        assert len(tools) == 14

    def test_stub_get_directions(self):
        """Verify get_directions stub produces expected output."""
        tools = create_stub_tools()
        result = tools['get_directions']({'destination': 'Gate B12'})
        assert 'destination' in result
        assert result['destination'] == 'Gate B12'

    def test_stub_get_flight_status(self):
        """Verify get_flight_status stub returns flight data."""
        tools = create_stub_tools()
        result = tools['get_flight_status']({'flight_number': 'AA100'})
        assert 'flight_number' in result
        assert result['flight_number'] == 'AA100'

    def test_stub_find_nearest(self):
        """Verify find_nearest stub returns location data."""
        tools = create_stub_tools()
        result = tools['find_nearest']({'facility_type': 'restroom'})
        assert 'facility_type' in result

    def test_stub_executor_integration(self):
        """Verify stubs work through ToolExecutor."""
        executor = ToolExecutor()
        stubs = create_stub_tools()
        for name, fn in stubs.items():
            executor.register(name, fn)
        result = executor.execute(
            'get_flight_status', {'flight_number': 'BA456'},
        )
        assert result.success is True
        assert result.data['flight_number'] == 'BA456'


# ── Session Tests ────────────────────────────────────────────────────────────

class TestSession:
    """Test conversation session management."""

    def test_new_session(self):
        """Verify fresh session has empty history."""
        session = Session(session_id='test-1')
        assert session.session_id == 'test-1'
        assert len(session.history) == 0
        assert session.total_queries == 0

    def test_add_turn(self):
        """Verify conversation turns are recorded."""
        session = Session(session_id='test-2')
        turn = ConversationTurn(role='user', content='Hello')
        session.add_turn(turn)
        assert len(session.history) == 1
        assert session.total_queries == 1

    def test_add_assistant_turn(self):
        """Verify assistant turns don't increment query count."""
        session = Session(session_id='test-3')
        turn = ConversationTurn(role='assistant', content='Hi!')
        session.add_turn(turn)
        assert len(session.history) == 1
        assert session.total_queries == 0

    def test_memory_limit(self):
        """Verify history respects maxlen."""
        session = Session(session_id='test-4')
        # Default maxlen is 10
        for i in range(15):
            session.add_turn(
                ConversationTurn(role='user', content=f'msg-{i}'),
            )
        assert len(session.history) == 10
        assert session.history[0].content == 'msg-5'


# ── ConversationTurn Tests ──────────────────────────────────────────────────

class TestConversationTurn:
    """Test ConversationTurn dataclass."""

    def test_default_values(self):
        """Verify default turn has no tool data."""
        turn = ConversationTurn(role='user', content='test')
        assert turn.tool_call is None
        assert turn.tool_result is None
        assert turn.adapter_used == ''

    def test_with_tool_data(self):
        """Verify turn with tool call metadata."""
        turn = ConversationTurn(
            role='assistant',
            content='Let me check.',
            tool_call={'name': 'get_flight_status', 'arguments': {}},
            adapter_used='tool_use',
        )
        assert turn.tool_call['name'] == 'get_flight_status'
        assert turn.adapter_used == 'tool_use'


# ── OrchestratorResult Tests ────────────────────────────────────────────────

class TestOrchestratorResult:
    """Test OrchestratorResult dataclass."""

    def test_default_success(self):
        """Verify default result is successful and empty."""
        result = OrchestratorResult()
        assert result.success is True
        assert result.response == ''
        assert result.tool_calls == []
        assert result.tool_results == []

    def test_error_result(self):
        """Verify error result construction."""
        result = OrchestratorResult(success=False, error='model down')
        assert result.success is False
        assert result.error == 'model down'


# ── ConversationOrchestrator Tests ──────────────────────────────────────────

class TestConversationOrchestrator:
    """Test ConversationOrchestrator logic with mock engine."""

    def _make_engine_mock(self):
        """Create a mock InferenceEngine."""
        engine = MagicMock()
        engine.query.return_value = InferenceResult(
            success=True,
            text='Gate B12 is to the right.',
            latency_ms=100.0,
            adapter_used='conversational',
        )
        engine.parse_tool_call.return_value = None
        engine.get_health.return_value = {
            'model_loaded': True,
            'rss_mb': 350.0,
            'total_queries': 5,
            'errors': 0,
            'avg_latency_ms': 100.0,
            'p95_latency_ms': 150.0,
            'active_adapter': 'conversational',
        }
        return engine

    def _make_tools(self):
        """Create a ToolExecutor with stub tools."""
        executor = ToolExecutor()
        stubs = create_stub_tools()
        for name, fn in stubs.items():
            executor.register(name, fn)
        return executor

    def test_simple_query(self):
        """Verify simple conversational query flows through."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        result = orch.process_query('Where is Gate B12?')
        assert result.success is True
        assert result.response == 'Gate B12 is to the right.'
        assert result.adapter_used == 'conversational'
        assert len(result.tool_calls) == 0

    def test_session_creation(self):
        """Verify sessions are created on first query."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        result = orch.process_query('Hello', session_id='s1')
        assert result.session_id == 's1'
        assert orch.stats['active_sessions'] == 1

    def test_session_reuse(self):
        """Verify same session_id reuses existing session."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        orch.process_query('Hello', session_id='s1')
        orch.process_query('Where is Gate B12?', session_id='s1')
        assert orch.stats['active_sessions'] == 1
        assert orch.stats['total_queries'] == 2

    def test_multiple_sessions(self):
        """Verify different session_ids create separate sessions."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        orch.process_query('Hello', session_id='s1')
        orch.process_query('Hi', session_id='s2')
        assert orch.stats['active_sessions'] == 2

    def test_tool_execution_flow(self):
        """Verify tool call → execute → re-infer flow."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        # First call returns tool_call
        engine.query.side_effect = [
            InferenceResult(
                success=True,
                text='<tool_call>{"name": "get_flight_status", '
                     '"arguments": {"flight_number": "AA100"}}</tool_call>',
                latency_ms=80.0,
                adapter_used='tool_use',
            ),
            InferenceResult(
                success=True,
                text='Flight AA100 is on time, departing from Gate B12.',
                latency_ms=90.0,
                adapter_used='conversational',
            ),
        ]

        engine.parse_tool_call.side_effect = [
            {'name': 'get_flight_status', 'arguments': {'flight_number': 'AA100'}},
            None,  # No tool call in the follow-up response
        ]

        result = orch.process_query('What is the status of AA100?')
        assert result.success is True
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]['name'] == 'get_flight_status'
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is True

    def test_context_injection(self):
        """Verify context dict is passed through to session."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        result = orch.process_query(
            'Where am I?',
            context={'terminal': 'T1', 'location': 'Gate B area'},
        )
        assert result.success is True
        # Verify context was included in engine call
        call_args = engine.query.call_args
        assert 'terminal' in call_args.kwargs.get('context', '')

    def test_session_clear(self):
        """Verify session clearing removes history."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        orch.process_query('Hello')
        assert orch.clear_session() is True
        session = orch.get_or_create_session()
        assert len(session.history) == 0

    def test_session_remove(self):
        """Verify session removal deletes session."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        orch.process_query('Hello', session_id='remove-me')
        assert orch.remove_session('remove-me') is True
        assert orch.stats['active_sessions'] == 0

    def test_session_expiry(self):
        """Verify expired sessions are cleaned up."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(
            engine, tools, session_timeout_sec=0.1,
        )

        orch.process_query('Hello', session_id='expire-me')
        time.sleep(0.15)
        removed = orch.cleanup_expired_sessions()
        assert removed == 1
        assert orch.stats['active_sessions'] == 0

    def test_engine_error_handling(self):
        """Verify graceful handling of engine errors."""
        engine = self._make_engine_mock()
        engine.query.return_value = InferenceResult(
            success=False, error='model crashed',
        )
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        result = orch.process_query('Hello')
        assert result.success is False
        assert 'model crashed' in result.error

    def test_stats_structure(self):
        """Verify stats dict has expected keys."""
        engine = self._make_engine_mock()
        tools = self._make_tools()
        orch = ConversationOrchestrator(engine, tools)

        stats = orch.stats
        assert 'total_queries' in stats
        assert 'total_errors' in stats
        assert 'active_sessions' in stats
        assert 'tool_stats' in stats
        assert 'engine_health' in stats

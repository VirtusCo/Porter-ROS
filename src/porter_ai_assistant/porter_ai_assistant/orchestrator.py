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
"""Conversation orchestrator for Virtue AI assistant.

Lightweight orchestrator that manages the full query lifecycle:
1. Receive user query from GUI (topic or service)
2. Classify query type (conversational vs tool_use)
3. Run inference via InferenceEngine with appropriate adapter
4. Parse tool calls from model output
5. Execute tools via ToolExecutor
6. Feed tool results back into conversation for final response
7. Maintain conversation memory (sliding window)
8. Publish response to GUI

This replaces a LangChain dependency with ~300 lines of focused code,
zero extra dependencies, and full control over the query pipeline.
"""

from collections import deque
from dataclasses import dataclass, field
import json
import logging
import time
from typing import Any, Dict, Generator, List, Optional

from porter_ai_assistant.inference_engine import InferenceEngine
from porter_ai_assistant.rag_retriever import KnowledgeBaseRetriever
from porter_ai_assistant.tool_executor import ToolExecutor, ToolResult

logger = logging.getLogger(__name__)

# Maximum number of conversation turns to retain in memory
DEFAULT_MEMORY_SIZE = 10

# Maximum tool execution rounds per query (prevent infinite loops)
MAX_TOOL_ROUNDS = 3


@dataclass
class ConversationTurn:
    """Single turn in a conversation."""

    role: str  # 'user' or 'assistant'
    content: str
    timestamp: float = 0.0
    tool_call: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    adapter_used: str = ''
    latency_ms: float = 0.0


@dataclass
class Session:
    """Conversation session for one passenger interaction.

    Each session tracks conversation history, passenger context,
    and session-level metadata.
    """

    session_id: str = ''
    history: deque = field(default_factory=lambda: deque(maxlen=DEFAULT_MEMORY_SIZE))
    context: Dict[str, str] = field(default_factory=dict)
    created_at: float = 0.0
    last_active: float = 0.0
    total_queries: int = 0

    def add_turn(self, turn: ConversationTurn) -> None:
        """Append a conversation turn to history.

        Args:
            turn: ConversationTurn to add.
        """
        self.history.append(turn)
        self.last_active = time.time()
        if turn.role == 'user':
            self.total_queries += 1


@dataclass
class OrchestratorResult:
    """Full result from processing a user query."""

    response: str = ''
    session_id: str = ''
    adapter_used: str = ''
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    total_latency_ms: float = 0.0
    inference_latency_ms: float = 0.0
    tool_latency_ms: float = 0.0
    success: bool = True
    error: str = ''


class ConversationOrchestrator:
    """Orchestrates Virtue AI query lifecycle.

    Manages the full pipeline from user query to final response,
    including adapter routing, tool execution, conversation memory,
    and multi-session support.

    Architecture:
        GUI --(topic)--> Orchestrator --> InferenceEngine
                                     --> ToolExecutor
                                     --> ConversationMemory
             <--(topic)-- Orchestrator <-- final response

    Attributes:
        engine: InferenceEngine instance for model inference.
        tools: ToolExecutor instance for tool execution.
        sessions: Dict of active conversation sessions.
    """

    def __init__(
        self,
        engine: InferenceEngine,
        tools: ToolExecutor,
        retriever: Optional[KnowledgeBaseRetriever] = None,
        memory_size: int = DEFAULT_MEMORY_SIZE,
        session_timeout_sec: float = 300.0,
    ):
        """Initialise the orchestrator.

        Args:
            engine: InferenceEngine with loaded model.
            tools: ToolExecutor with registered tools.
            retriever: Optional RAG retriever for knowledge base context.
            memory_size: Max conversation turns per session.
            session_timeout_sec: Session expiry after inactivity.
        """
        self.engine = engine
        self.tools = tools
        self.retriever = retriever
        self._memory_size = memory_size
        self._session_timeout = session_timeout_sec
        self._sessions: Dict[str, Session] = {}
        self._default_session_id = 'default'
        self._total_queries = 0
        self._total_errors = 0

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
    ) -> Session:
        """Retrieve existing session or create a new one.

        Args:
            session_id: Session identifier. Uses default if None.

        Returns:
            Active Session instance.
        """
        sid = session_id or self._default_session_id

        if sid in self._sessions:
            session = self._sessions[sid]
            # Check for timeout
            if (
                self._session_timeout > 0
                and time.time() - session.last_active > self._session_timeout
            ):
                logger.info(
                    "Session '%s' expired (%.0fs inactive), creating new",
                    sid, time.time() - session.last_active,
                )
                session = self._create_session(sid)
            return session

        return self._create_session(sid)

    def _create_session(self, session_id: str) -> Session:
        """Create a new conversation session.

        Args:
            session_id: Unique session identifier.

        Returns:
            New Session instance.
        """
        session = Session(
            session_id=session_id,
            history=deque(maxlen=self._memory_size),
            created_at=time.time(),
            last_active=time.time(),
        )
        self._sessions[session_id] = session
        logger.info("Created session: '%s'", session_id)
        return session

    def clear_session(self, session_id: Optional[str] = None) -> bool:
        """Clear a session's conversation history.

        Args:
            session_id: Session to clear. Uses default if None.

        Returns:
            True if session was found and cleared.
        """
        sid = session_id or self._default_session_id
        if sid in self._sessions:
            self._sessions[sid].history.clear()
            logger.info("Cleared session: '%s'", sid)
            return True
        return False

    def remove_session(self, session_id: str) -> bool:
        """Remove a session entirely.

        Args:
            session_id: Session to remove.

        Returns:
            True if session was found and removed.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions.

        Returns:
            Number of sessions removed.
        """
        if self._session_timeout <= 0:
            return 0

        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_active > self._session_timeout
        ]
        for sid in expired:
            del self._sessions[sid]

        if expired:
            logger.info('Cleaned up %d expired sessions', len(expired))
        return len(expired)

    def process_query(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, str]] = None,
        force_adapter: Optional[str] = None,
    ) -> OrchestratorResult:
        """Process a user query through the full pipeline.

        Pipeline:
        1. Get/create session
        2. Build context from conversation history
        3. Run inference (auto-routes adapter)
        4. If tool call detected: execute tool, feed result back
        5. Store conversation turn
        6. Return final response

        Args:
            user_query: Passenger's question text.
            session_id: Session identifier for conversation continuity.
            context: Additional context dict (location, flight, etc.).
            force_adapter: Override adapter selection.

        Returns:
            OrchestratorResult with response and metadata.
        """
        t_start = time.monotonic()
        result = OrchestratorResult()
        self._total_queries += 1

        # Step 1: Get or create session
        session = self.get_or_create_session(session_id)
        result.session_id = session.session_id

        # Merge context
        if context:
            session.context.update(context)

        # Step 2: Build conversation context + RAG context
        context_str = self._build_context_string(session, user_query)

        # Step 3: Run inference
        inference_result = self.engine.query(
            user_query=user_query,
            context=context_str,
            adapter=force_adapter,
        )

        result.inference_latency_ms = inference_result.latency_ms
        result.adapter_used = inference_result.adapter_used

        if not inference_result.success:
            result.success = False
            result.error = inference_result.error
            result.total_latency_ms = (time.monotonic() - t_start) * 1000
            self._total_errors += 1
            return result

        # Step 4: Check for tool calls and execute
        response_text = inference_result.text
        tool_rounds = 0

        while tool_rounds < MAX_TOOL_ROUNDS:
            tool_call = self.engine.parse_tool_call(response_text)
            if tool_call is None:
                break

            tool_rounds += 1
            tool_name = tool_call.get('name', '')
            tool_args = tool_call.get('arguments', {})

            result.tool_calls.append(tool_call)
            logger.info(
                'Tool call #%d: %s(%s)', tool_rounds, tool_name,
                json.dumps(tool_args, default=str),
            )

            # Execute tool
            tool_result = self.tools.execute(tool_name, tool_args)
            result.tool_results.append(tool_result)
            result.tool_latency_ms += tool_result.latency_ms

            if not tool_result.success:
                logger.warning(
                    "Tool '%s' failed: %s", tool_name, tool_result.error,
                )
                # Feed error back to model for graceful handling
                tool_response = json.dumps({
                    'error': tool_result.error,
                    'tool': tool_name,
                })
            else:
                tool_response = json.dumps(tool_result.data, default=str)

            # Feed tool result back for final response
            followup_query = (
                f'Tool {tool_name} returned: {tool_response}\n'
                f'Please provide a helpful response to the passenger '
                f'based on this information.'
            )

            inference_result = self.engine.query(
                user_query=followup_query,
                context=context_str,
                adapter='conversational',
            )

            result.inference_latency_ms += inference_result.latency_ms

            if not inference_result.success:
                # Fallback: format tool result directly
                response_text = self._format_tool_result_fallback(
                    tool_name, tool_result,
                )
                break

            response_text = inference_result.text

        # Step 5: Store conversation turn
        user_turn = ConversationTurn(
            role='user',
            content=user_query,
            timestamp=time.time(),
        )
        session.add_turn(user_turn)

        assistant_turn = ConversationTurn(
            role='assistant',
            content=response_text,
            timestamp=time.time(),
            tool_call=result.tool_calls[-1] if result.tool_calls else None,
            tool_result=(
                result.tool_results[-1].data if result.tool_results else None
            ),
            adapter_used=result.adapter_used,
            latency_ms=result.inference_latency_ms,
        )
        session.add_turn(assistant_turn)

        # Step 6: Build final result
        result.response = response_text
        result.success = True
        result.total_latency_ms = (time.monotonic() - t_start) * 1000

        return result

    def process_query_stream(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, str]] = None,
        force_adapter: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Process a user query, yielding SSE events as tokens arrive.

        Event types yielded (each is a dict):
            {'event': 'adapter', 'adapter': str}
            {'event': 'tool_call', 'tool_call': dict}
            {'event': 'tool_result', 'tool_name': str, 'data': dict}
            {'event': 'token', 'token': str}
            {'event': 'done', 'latency_ms': float, 'tool_calls': list}
            {'event': 'error', 'error': str}
        """
        t_start = time.monotonic()
        self._total_queries += 1

        session = self.get_or_create_session(session_id)
        if context:
            session.context.update(context)
        context_str = self._build_context_string(session, user_query)

        # --- Step 1: First inference (may produce tool call or direct answer)
        # Tool-use adapter detects tool calls; we must collect the FULL
        # first response before deciding if it contains a tool call.
        first_result = self.engine.query(
            user_query=user_query,
            context=context_str,
            adapter=force_adapter,
        )

        adapter_used = first_result.adapter_used
        yield {'event': 'adapter', 'adapter': adapter_used}

        if not first_result.success:
            self._total_errors += 1
            yield {'event': 'error', 'error': first_result.error}
            return

        # --- Step 2: Check for tool call
        response_text = first_result.text
        tool_call = self.engine.parse_tool_call(response_text)
        tool_calls_list: List[Dict[str, Any]] = []
        total_tool_latency = 0.0

        if tool_call is not None:
            tool_name = tool_call.get('name', '')
            tool_args = tool_call.get('arguments', {})
            tool_calls_list.append(tool_call)

            yield {'event': 'tool_call', 'tool_call': tool_call}

            # Execute tool
            tool_result = self.tools.execute(tool_name, tool_args)
            total_tool_latency += tool_result.latency_ms

            if tool_result.success:
                yield {
                    'event': 'tool_result',
                    'tool_name': tool_name,
                    'data': tool_result.data,
                }
            else:
                yield {
                    'event': 'tool_result',
                    'tool_name': tool_name,
                    'data': {'error': tool_result.error},
                }

            # --- Step 3: Stream the followup response token by token
            tool_response = json.dumps(
                tool_result.data if tool_result.success
                else {'error': tool_result.error, 'tool': tool_name},
                default=str,
            )
            followup_query = (
                f'Tool {tool_name} returned: {tool_response}\n'
                f'Please provide a helpful response to the passenger '
                f'based on this information.'
            )

            full_tokens = []
            gen = self.engine.query_stream(
                user_query=followup_query,
                context=context_str,
                adapter='conversational',
            )
            try:
                while True:
                    token = next(gen)
                    full_tokens.append(token)
                    yield {'event': 'token', 'token': token}
            except StopIteration as e:
                stream_result = e.value
            response_text = ''.join(full_tokens)

        else:
            # --- No tool call: stream the first response
            # Re-do as streaming (first call was non-streaming for tool check).
            # For conversational queries this adds only ~50ms overhead.
            gen = self.engine.query_stream(
                user_query=user_query,
                context=context_str,
                adapter=force_adapter,
            )
            full_tokens = []
            try:
                while True:
                    token = next(gen)
                    full_tokens.append(token)
                    yield {'event': 'token', 'token': token}
            except StopIteration as e:
                stream_result = e.value
            response_text = ''.join(full_tokens)

        # --- Step 4: Store conversation turn
        user_turn = ConversationTurn(
            role='user',
            content=user_query,
            timestamp=time.time(),
        )
        session.add_turn(user_turn)

        assistant_turn = ConversationTurn(
            role='assistant',
            content=response_text,
            timestamp=time.time(),
            tool_call=tool_calls_list[-1] if tool_calls_list else None,
            adapter_used=adapter_used,
        )
        session.add_turn(assistant_turn)

        total_latency = (time.monotonic() - t_start) * 1000
        yield {
            'event': 'done',
            'latency_ms': round(total_latency, 1),
            'tool_calls': tool_calls_list,
            'tool_latency_ms': round(total_tool_latency, 1),
        }

    def _build_context_string(
        self,
        session: Session,
        user_query: str = '',
    ) -> str:
        """Build context string from session history, metadata, and RAG.

        Retrieves relevant knowledge base chunks for the user query and
        combines them with conversation history and session context.

        Args:
            session: Current conversation session.
            user_query: Current user query for RAG retrieval.

        Returns:
            Context string for inference engine.
        """
        parts = []

        # RAG: Retrieve relevant knowledge base context
        if self.retriever and user_query:
            rag_context = self.retriever.build_context(user_query)
            if rag_context:
                parts.append(rag_context)

        # Add session context (location, flight, etc.)
        if session.context:
            ctx_items = [f'{k}: {v}' for k, v in session.context.items()]
            parts.append('Current context: ' + ', '.join(ctx_items))

        # Add recent conversation history (last few turns)
        recent = list(session.history)[-4:]  # Last 2 exchanges
        if recent:
            history_lines = []
            for turn in recent:
                prefix = 'Passenger' if turn.role == 'user' else 'Virtue'
                history_lines.append(f'{prefix}: {turn.content}')
            parts.append(
                'Recent conversation:\n' + '\n'.join(history_lines)
            )

        return '\n\n'.join(parts) if parts else ''

    def _format_tool_result_fallback(
        self,
        tool_name: str,
        tool_result: ToolResult,
    ) -> str:
        """Format tool result as a readable response when model fails.

        Args:
            tool_name: Name of the tool that was called.
            tool_result: Result from tool execution.

        Returns:
            Human-readable string from tool data.
        """
        if not tool_result.success:
            return (
                'I tried to look that up for you, but encountered an error: '
                f'{tool_result.error}. Please try again or ask an airport staff '
                'member for assistance.'
            )

        data = tool_result.data
        lines = ['Here is what I found:']
        for key, value in data.items():
            readable_key = key.replace('_', ' ').title()
            if isinstance(value, list):
                lines.append(f'  {readable_key}:')
                for item in value:
                    if isinstance(item, dict):
                        item_str = ', '.join(
                            f'{k}: {v}' for k, v in item.items()
                        )
                        lines.append(f'    - {item_str}')
                    else:
                        lines.append(f'    - {item}')
            else:
                lines.append(f'  {readable_key}: {value}')

        return '\n'.join(lines)

    @property
    def stats(self) -> Dict[str, Any]:
        """Orchestrator statistics.

        Returns:
            Dict with query counts, session counts, tool stats.
        """
        return {
            'total_queries': self._total_queries,
            'total_errors': self._total_errors,
            'active_sessions': len(self._sessions),
            'tool_stats': self.tools.stats,
            'rag_stats': self.retriever.stats if self.retriever else {},
            'engine_health': self.engine.get_health(),
        }

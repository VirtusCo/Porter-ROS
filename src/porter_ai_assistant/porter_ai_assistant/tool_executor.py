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
"""Tool executor for Virtue AI assistant.

Provides a registry of callable tools that the AI model can invoke via
<tool_call> tags. Each tool maps to either a ROS 2 service call, a local
function, or a stub returning mock data for testing.

Tools are registered by name and executed with JSON arguments. Results
are returned as dicts that get formatted back into the conversation.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result from executing a tool."""

    success: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ''
    latency_ms: float = 0.0
    tool_name: str = ''


class ToolExecutor:
    """Registry and executor for AI-invocable tools.

    Tools are registered as callables that accept a dict of arguments
    and return a dict of results. The executor handles error catching,
    timing, and logging.

    Example:
        executor = ToolExecutor()
        executor.register('get_directions', my_directions_func)
        result = executor.execute('get_directions', {'destination': 'Gate B12'})
    """

    def __init__(self):
        """Initialise empty tool registry."""
        self._tools: Dict[str, Callable] = {}
        self._tool_descriptions: Dict[str, str] = {}
        self._total_calls = 0
        self._total_errors = 0

    def register(
        self,
        name: str,
        func: Callable[[Dict[str, Any]], Dict[str, Any]],
        description: str = '',
    ) -> None:
        """Register a tool by name.

        Args:
            name: Tool identifier matching training data names.
            func: Callable accepting args dict, returning result dict.
            description: Human-readable tool description.
        """
        self._tools[name] = func
        self._tool_descriptions[name] = description
        logger.info("Registered tool: '%s'", name)

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry.

        Args:
            name: Tool identifier to remove.

        Returns:
            True if tool was found and removed.
        """
        if name in self._tools:
            del self._tools[name]
            self._tool_descriptions.pop(name, None)
            return True
        return False

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered.

        Args:
            name: Tool identifier.

        Returns:
            True if tool exists in registry.
        """
        return name in self._tools

    def list_tools(self) -> Dict[str, str]:
        """List all registered tools with descriptions.

        Returns:
            Dict mapping tool names to descriptions.
        """
        return dict(self._tool_descriptions)

    def execute(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Execute a registered tool with the given arguments.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Dict of arguments to pass to the tool.

        Returns:
            ToolResult with success status, data, and timing.
        """
        result = ToolResult(tool_name=tool_name)
        self._total_calls += 1

        if tool_name not in self._tools:
            result.success = False
            result.error = f"Unknown tool: '{tool_name}'"
            self._total_errors += 1
            logger.warning("Tool not found: '%s'", tool_name)
            return result

        args = arguments or {}
        t_start = time.monotonic()

        try:
            data = self._tools[tool_name](args)
            result.data = data if isinstance(data, dict) else {'result': str(data)}
            result.success = True
        except Exception as e:
            result.success = False
            result.error = f'{type(e).__name__}: {e}'
            self._total_errors += 1
            logger.error("Tool '%s' failed: %s", tool_name, e)

        result.latency_ms = (time.monotonic() - t_start) * 1000
        return result

    @property
    def stats(self) -> Dict[str, Any]:
        """Return execution statistics summary.

        Returns:
            Dict with total_calls, total_errors, registered_tools count.
        """
        return {
            'total_calls': self._total_calls,
            'total_errors': self._total_errors,
            'registered_tools': len(self._tools),
        }


def create_stub_tools() -> Dict[str, Callable]:
    """Create stub tool implementations for testing.

    Returns mock data for all 14 Porter tools. These stubs are used
    during development and testing before real ROS 2 service
    integrations are connected.

    Returns:
        Dict mapping tool names to stub callables.
    """
    def get_directions(args: Dict) -> Dict:
        """Return mock walking directions."""
        dest = args.get('destination', 'unknown')
        return {
            'destination': dest,
            'distance_m': 150,
            'walk_time_min': 3,
            'directions': f'Head straight, turn left at the corridor to reach {dest}.',
            'accessible_route': True,
        }

    def get_flight_status(args: Dict) -> Dict:
        """Return mock flight status."""
        flight = args.get('flight_number', 'AI 101')
        return {
            'flight_number': flight,
            'status': 'On Time',
            'gate': 'B12',
            'departure_time': '14:30',
            'boarding_time': '14:00',
            'terminal': 'T2',
        }

    def find_nearest(args: Dict) -> Dict:
        """Return mock nearest facility."""
        facility = args.get('facility_type', 'restroom')
        return {
            'facility_type': facility,
            'name': f'Nearest {facility}',
            'distance_m': 50,
            'walk_time_min': 1,
            'floor': 'Ground',
            'direction': 'Turn right, 50 metres ahead.',
        }

    def weigh_luggage(args: Dict) -> Dict:
        """Return mock luggage weight."""
        return {
            'weight_kg': 18.5,
            'status': 'Within limit',
            'airline_limit_kg': 23,
            'remaining_kg': 4.5,
        }

    def get_gate_info(args: Dict) -> Dict:
        """Return mock gate information."""
        gate = args.get('gate_number', 'B12')
        return {
            'gate': gate,
            'terminal': 'T2',
            'status': 'Boarding',
            'distance_m': 200,
            'walk_time_min': 5,
        }

    def call_assistance(args: Dict) -> Dict:
        """Return mock assistance request confirmation."""
        atype = args.get('assistance_type', 'wheelchair')
        return {
            'assistance_type': atype,
            'request_id': 'REQ-2026-0042',
            'eta_min': 3,
            'status': 'Dispatched',
        }

    def escort_passenger(args: Dict) -> Dict:
        """Return mock escort confirmation."""
        dest = args.get('destination', 'Gate B12')
        return {
            'destination': dest,
            'route_planned': True,
            'estimated_time_min': 5,
            'bags_carried': args.get('num_bags', 1),
        }

    def show_map(args: Dict) -> Dict:
        """Return mock map display confirmation."""
        location = args.get('location', 'current area')
        return {
            'map_displayed': True,
            'highlighted_location': location,
            'zoom_level': 'area',
        }

    def check_wait_time(args: Dict) -> Dict:
        """Return mock queue wait time."""
        queue = args.get('queue_type', 'security')
        return {
            'queue_type': queue,
            'estimated_wait_min': 12,
            'queue_length': 45,
            'fastest_lane': 'Lane 3',
        }

    def set_reminder(args: Dict) -> Dict:
        """Return mock reminder confirmation."""
        return {
            'reminder_set': True,
            'event': args.get('event', 'boarding'),
            'time': args.get('time', '14:00'),
            'notification_type': 'screen_and_audio',
        }

    def get_airline_counter(args: Dict) -> Dict:
        """Return mock airline counter location."""
        airline = args.get('airline', 'Air India')
        return {
            'airline': airline,
            'counter': 'Row F, Counter 12-15',
            'terminal': 'T2',
            'floor': 'Departures',
            'distance_m': 100,
        }

    def get_transport_options(args: Dict) -> Dict:
        """Return mock transport options."""
        dest = args.get('destination', 'city centre')
        return {
            'destination': dest,
            'options': [
                {'type': 'Metro', 'cost': '₹60', 'time_min': 25},
                {'type': 'Taxi', 'cost': '₹400-500', 'time_min': 35},
                {'type': 'Bus', 'cost': '₹40', 'time_min': 45},
            ],
        }

    def translate_text(args: Dict) -> Dict:
        """Return mock translation."""
        text = args.get('text', '')
        lang = args.get('target_language', 'Hindi')
        return {
            'original': text,
            'translated': f'[{lang} translation of: {text}]',
            'target_language': lang,
        }

    def report_incident(args: Dict) -> Dict:
        """Return mock incident report confirmation."""
        itype = args.get('incident_type', 'general')
        return {
            'incident_type': itype,
            'report_id': 'INC-2026-0015',
            'status': 'Reported',
            'response_team': 'Airport Security',
            'eta_min': 5,
        }

    return {
        'get_directions': get_directions,
        'get_flight_status': get_flight_status,
        'find_nearest': find_nearest,
        'weigh_luggage': weigh_luggage,
        'get_gate_info': get_gate_info,
        'call_assistance': call_assistance,
        'escort_passenger': escort_passenger,
        'show_map': show_map,
        'check_wait_time': check_wait_time,
        'set_reminder': set_reminder,
        'get_airline_counter': get_airline_counter,
        'get_transport_options': get_transport_options,
        'translate_text': translate_text,
        'report_incident': report_incident,
    }

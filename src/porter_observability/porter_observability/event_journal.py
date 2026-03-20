"""Event journal node for the Virtus Observability Stack.

Subscribes to /orchestrator/state and /diagnostics to track significant
robot events.  Maintains a 60-second rolling buffer; on ERROR or RECOVERY
state the buffer is frozen and dumped to an incident file for post-mortem
analysis.

Event types written:
  - fsm_transition   : state machine transitions
  - diagnostic_warn  : WARN-level diagnostic messages
  - diagnostic_error : ERROR/STALE diagnostic messages
  - sensor_fault     : sensor-related diagnostic failures
"""

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from rclpy.node import Node
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from std_msgs.msg import String


# Diagnostic status level mapping
_DIAG_LEVEL_NAMES = {
    DiagnosticStatus.OK: 'OK',
    DiagnosticStatus.WARN: 'WARN',
    DiagnosticStatus.ERROR: 'ERROR',
    DiagnosticStatus.STALE: 'STALE',
}

# FSM states that trigger an incident freeze
_INCIDENT_TRIGGER_STATES = {'ERROR', 'RECOVERY', 'error', 'recovery'}

# Sensor-related keywords in diagnostic names/messages
_SENSOR_KEYWORDS = (
    'sensor', 'tof', 'ultrasonic', 'microwave', 'lidar', 'imu',
    'temperature', 'humidity',
)


class EventJournal(Node):
    """Track robot events and freeze rolling buffer on incidents."""

    def __init__(self):
        super().__init__('event_journal')

        # Parameters
        self.declare_parameter('robot_id', 'porter-001')
        self.declare_parameter('events_dir', '/opt/virtus/events')
        self.declare_parameter('incidents_dir', '/opt/virtus/incidents')
        self.declare_parameter('buffer_seconds', 60)
        self.declare_parameter('buffer_max_events', 600)

        self._robot_id = self.get_parameter('robot_id').value
        self._events_dir = Path(self.get_parameter('events_dir').value)
        self._incidents_dir = Path(self.get_parameter('incidents_dir').value)
        buffer_max = self.get_parameter('buffer_max_events').value

        self._events_dir.mkdir(parents=True, exist_ok=True)
        self._incidents_dir.mkdir(parents=True, exist_ok=True)

        # Rolling buffer (60s worth of events, capped at maxlen)
        self._buffer: deque = deque(maxlen=buffer_max)

        # Track current FSM state to detect transitions
        self._current_state: str = 'UNKNOWN'

        # Journal file handle
        self._journal_file = None
        self._journal_path = self._events_dir / 'journal.jsonl'
        self._journal_file = open(self._journal_path, 'a', encoding='utf-8')

        # Subscriptions
        self.create_subscription(
            String, '/orchestrator/state', self._on_state, 10
        )
        self.create_subscription(
            DiagnosticArray, '/diagnostics', self._on_diagnostics, 10
        )

        self.get_logger().info(
            f'Event journal started: robot_id={self._robot_id}, '
            f'events_dir={self._events_dir}, '
            f'incidents_dir={self._incidents_dir}'
        )

    # ------------------------------------------------------------------
    # FSM state subscription
    # ------------------------------------------------------------------

    def _on_state(self, msg: String):
        """Handle FSM state changes from /orchestrator/state."""
        new_state = msg.data.strip().upper()
        if new_state == self._current_state:
            return

        old_state = self._current_state
        self._current_state = new_state

        event = self._make_event(
            event_type='fsm_transition',
            details={
                'from_state': old_state,
                'to_state': new_state,
            },
        )
        self._record_event(event)

        # Freeze buffer on incident-triggering states
        if new_state in _INCIDENT_TRIGGER_STATES:
            self._freeze_incident(trigger_event=event)

    # ------------------------------------------------------------------
    # Diagnostics subscription
    # ------------------------------------------------------------------

    def _on_diagnostics(self, msg: DiagnosticArray):
        """Handle /diagnostics messages."""
        for status in msg.status:
            level = status.level
            level_name = _DIAG_LEVEL_NAMES.get(level, 'UNKNOWN')

            # Determine event type
            is_sensor = any(
                kw in (status.name or '').lower() or
                kw in (status.message or '').lower()
                for kw in _SENSOR_KEYWORDS
            )

            if level == DiagnosticStatus.OK:
                continue  # Only record non-OK diagnostics
            elif is_sensor and level in (
                DiagnosticStatus.ERROR, DiagnosticStatus.STALE
            ):
                event_type = 'sensor_fault'
            elif level == DiagnosticStatus.WARN:
                event_type = 'diagnostic_warn'
            else:
                event_type = 'diagnostic_error'

            # Build key-value pairs dict
            kv_pairs = {}
            for kv in status.values:
                kv_pairs[kv.key] = kv.value

            event = self._make_event(
                event_type=event_type,
                details={
                    'name': status.name,
                    'message': status.message,
                    'level': level_name,
                    'hardware_id': status.hardware_id,
                    'values': kv_pairs if kv_pairs else None,
                },
            )
            self._record_event(event)

    # ------------------------------------------------------------------
    # Event construction and recording
    # ------------------------------------------------------------------

    def _make_event(self, event_type: str, details: dict) -> dict:
        """Create a timestamped event record."""
        return {
            'ts': datetime.now(timezone.utc).isoformat(),
            'robot_id': self._robot_id,
            'event_type': event_type,
            'current_state': self._current_state,
            'details': {k: v for k, v in details.items() if v is not None},
        }

    def _record_event(self, event: dict):
        """Add event to rolling buffer and append to journal file."""
        self._buffer.append(event)

        try:
            line = json.dumps(event, default=str)
            self._journal_file.write(line + '\n')
            self._journal_file.flush()
        except OSError as exc:
            self.get_logger().error(f'Failed to write event: {exc}')

    # ------------------------------------------------------------------
    # Incident freeze
    # ------------------------------------------------------------------

    def _freeze_incident(self, trigger_event: dict):
        """Dump the rolling buffer to an incident file for post-mortem."""
        now = datetime.now(timezone.utc)
        filename = now.strftime('%Y%m%dT%H%M%S') + '.json'
        filepath = self._incidents_dir / filename

        incident = {
            'incident_ts': now.isoformat(),
            'robot_id': self._robot_id,
            'trigger': trigger_event,
            'buffer_size': len(self._buffer),
            'events': list(self._buffer),
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(incident, f, indent=2, default=str)
            self.get_logger().warn(
                f'Incident frozen: {filepath} '
                f'({len(self._buffer)} events in buffer)'
            )
        except OSError as exc:
            self.get_logger().error(f'Failed to freeze incident: {exc}')

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def destroy_node(self):
        """Close open file handles on shutdown."""
        if self._journal_file is not None:
            self._journal_file.close()
        super().destroy_node()


def main(args=None):
    """Entry point for event_journal node."""
    rclpy.init(args=args)
    node = EventJournal()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

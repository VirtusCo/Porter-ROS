"""Log bridge node for the Virtus Observability Stack.

Subscribes to /rosout, enriches log messages with structured fields via
regex pattern extraction, and writes JSONL to rotating daily log files.

Privacy filter: messages from /ai_assistant/response and /ai_assistant/query
topics are silently dropped to avoid persisting passenger conversations.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import Log

from porter_observability.patterns import extract_patterns

# ROS 2 Log severity level names
_SEVERITY_NAMES = {
    Log.DEBUG: 'DEBUG',
    Log.INFO: 'INFO',
    Log.WARN: 'WARN',
    Log.ERROR: 'ERROR',
    Log.FATAL: 'FATAL',
}

# Topic prefixes whose messages are never persisted (privacy)
_PRIVACY_FILTER_PREFIXES = (
    '/ai_assistant/response',
    '/ai_assistant/query',
)


class LogBridge(Node):
    """Subscribe to /rosout and write structured JSONL log files."""

    def __init__(self):
        super().__init__('log_bridge')

        # Parameters
        self.declare_parameter('robot_id', 'porter-001')
        self.declare_parameter('log_dir', '/opt/virtus/logs')
        self.declare_parameter('retention_days', 30)

        self._robot_id = self.get_parameter('robot_id').value
        self._log_dir = Path(self.get_parameter('log_dir').value)
        self._retention_days = self.get_parameter('retention_days').value

        # Ensure output directory exists
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # Current log file handle and date tracking for rotation
        self._current_date: str = ''
        self._log_file = None

        # Subscribe to /rosout
        self.create_subscription(Log, '/rosout', self._on_log, 100)

        # Periodic retention cleanup (once per hour)
        self.create_timer(3600.0, self._cleanup_old_logs)

        self.get_logger().info(
            f'Log bridge started: robot_id={self._robot_id}, '
            f'log_dir={self._log_dir}'
        )

    # ------------------------------------------------------------------
    # /rosout callback
    # ------------------------------------------------------------------

    def _on_log(self, msg: Log):
        """Process an incoming /rosout message."""
        # Privacy filter: drop AI assistant traffic
        node_name = msg.name or ''
        if any(node_name.startswith(p) or node_name.endswith(p.split('/')[-1])
               for p in _PRIVACY_FILTER_PREFIXES):
            return
        if any(prefix in (msg.msg or '') for prefix in _PRIVACY_FILTER_PREFIXES):
            return

        now = datetime.now(timezone.utc)
        record = self._build_record(msg, now)

        # Write to daily JSONL
        self._ensure_log_file(now)
        try:
            line = json.dumps(record, default=str)
            self._log_file.write(line + '\n')
            self._log_file.flush()
        except OSError as exc:
            self.get_logger().error(f'Failed to write log: {exc}')

    def _build_record(self, msg: Log, now: datetime) -> dict:
        """Build a structured log record from a ROS Log message."""
        message_text = msg.msg or ''
        record = {
            'ts': now.isoformat(),
            'robot_id': self._robot_id,
            'severity': _SEVERITY_NAMES.get(msg.level, 'UNKNOWN'),
            'node': msg.name or '',
            'function': msg.function or '',
            'file': msg.file or '',
            'line': msg.line,
            'message': message_text,
        }

        # Structured field extraction
        extracted = extract_patterns(message_text)
        if extracted:
            record['extracted'] = extracted

        return record

    # ------------------------------------------------------------------
    # Daily log rotation
    # ------------------------------------------------------------------

    def _ensure_log_file(self, now: datetime):
        """Open or rotate the daily log file."""
        date_str = now.strftime('%Y-%m-%d')
        if date_str != self._current_date:
            if self._log_file is not None:
                self._log_file.close()
            filepath = self._log_dir / f'{date_str}.jsonl'
            self._log_file = open(filepath, 'a', encoding='utf-8')
            self._current_date = date_str
            self.get_logger().info(f'Rotated log file to {filepath}')

    # ------------------------------------------------------------------
    # Retention cleanup
    # ------------------------------------------------------------------

    def _cleanup_old_logs(self):
        """Remove log files older than retention_days."""
        if self._retention_days <= 0:
            return
        cutoff = datetime.now(timezone.utc)
        removed = 0
        for logfile in self._log_dir.glob('*.jsonl'):
            try:
                file_date_str = logfile.stem  # e.g. "2026-03-20"
                file_date = datetime.strptime(file_date_str, '%Y-%m-%d').replace(
                    tzinfo=timezone.utc
                )
                age_days = (cutoff - file_date).days
                if age_days > self._retention_days:
                    logfile.unlink()
                    removed += 1
            except (ValueError, OSError):
                continue
        if removed:
            self.get_logger().info(f'Cleaned up {removed} old log file(s)')

    def destroy_node(self):
        """Close open file handles on shutdown."""
        if self._log_file is not None:
            self._log_file.close()
        super().destroy_node()


def main(args=None):
    """Entry point for log_bridge node."""
    rclpy.init(args=args)
    node = LogBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

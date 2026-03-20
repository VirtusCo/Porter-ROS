"""Metrics emitter node for the Virtus Observability Stack.

Collects system-level metrics (CPU, RAM, disk, temperature) via psutil
and subscribes to hardware telemetry topics.  Publishes a consolidated
JSON payload on /observability/metrics at 1 Hz and writes JSONL to
rotating daily files.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

# Attempt to import virtus_msgs for hardware telemetry; fall back to
# std_msgs.String decoding if the custom message package is unavailable.
try:
    from virtus_msgs.msg import HardwareStatus  # type: ignore[import]
    _HAS_VIRTUS_MSGS = True
except ImportError:
    _HAS_VIRTUS_MSGS = False


class MetricsEmitter(Node):
    """Collect and publish system + hardware metrics at 1 Hz."""

    def __init__(self):
        super().__init__('metrics_emitter')

        # Parameters
        self.declare_parameter('robot_id', 'porter-001')
        self.declare_parameter('metrics_dir', '/opt/virtus/metrics')
        self.declare_parameter('retention_days', 30)
        self.declare_parameter('publish_rate_hz', 1.0)

        self._robot_id = self.get_parameter('robot_id').value
        self._metrics_dir = Path(self.get_parameter('metrics_dir').value)
        self._retention_days = self.get_parameter('retention_days').value
        publish_rate = self.get_parameter('publish_rate_hz').value

        self._metrics_dir.mkdir(parents=True, exist_ok=True)

        # Latest hardware telemetry cache
        self._hw_status: dict = {}

        # File rotation state
        self._current_date: str = ''
        self._metrics_file = None

        # Publisher
        self._pub = self.create_publisher(String, '/observability/metrics', 10)

        # Hardware topic subscriptions
        if _HAS_VIRTUS_MSGS:
            self.create_subscription(
                HardwareStatus,
                '/hardware/status',
                self._on_hw_status_virtus,
                10,
            )
            self.get_logger().info('Using virtus_msgs.HardwareStatus')
        else:
            self.create_subscription(
                String,
                '/hardware/status',
                self._on_hw_status_string,
                10,
            )
            self.get_logger().info(
                'virtus_msgs not available; falling back to std_msgs/String'
            )

        # Battery topic (std_msgs/String JSON fallback always)
        self.create_subscription(
            String, '/hardware/battery', self._on_battery, 10
        )

        # Motor current topic
        self.create_subscription(
            String, '/hardware/motor_current', self._on_motor_current, 10
        )

        # 1 Hz timer
        period = 1.0 / max(publish_rate, 0.01)
        self.create_timer(period, self._emit_metrics)

        # Hourly retention cleanup
        self.create_timer(3600.0, self._cleanup_old_files)

        self.get_logger().info(
            f'Metrics emitter started: robot_id={self._robot_id}, '
            f'metrics_dir={self._metrics_dir}'
        )

    # ------------------------------------------------------------------
    # Hardware topic callbacks
    # ------------------------------------------------------------------

    def _on_hw_status_virtus(self, msg):
        """Handle virtus_msgs/HardwareStatus."""
        try:
            self._hw_status['battery_pct'] = msg.battery_percentage
            self._hw_status['battery_voltage'] = msg.battery_voltage
            self._hw_status['motor_left_current'] = msg.motor_left_current
            self._hw_status['motor_right_current'] = msg.motor_right_current
            self._hw_status['hw_ts'] = datetime.now(timezone.utc).isoformat()
        except AttributeError as exc:
            self.get_logger().warn(f'HardwareStatus field error: {exc}')

    def _on_hw_status_string(self, msg: String):
        """Handle hardware status as JSON-encoded std_msgs/String."""
        try:
            data = json.loads(msg.data)
            self._hw_status.update(data)
            self._hw_status['hw_ts'] = datetime.now(timezone.utc).isoformat()
        except (json.JSONDecodeError, TypeError) as exc:
            self.get_logger().warn(f'Failed to parse hardware status: {exc}')

    def _on_battery(self, msg: String):
        """Handle battery level updates."""
        try:
            data = json.loads(msg.data)
            self._hw_status['battery_pct'] = data.get('percentage')
            self._hw_status['battery_voltage'] = data.get('voltage')
        except (json.JSONDecodeError, TypeError):
            pass

    def _on_motor_current(self, msg: String):
        """Handle motor current updates."""
        try:
            data = json.loads(msg.data)
            self._hw_status['motor_left_current'] = data.get('left')
            self._hw_status['motor_right_current'] = data.get('right')
        except (json.JSONDecodeError, TypeError):
            pass

    # ------------------------------------------------------------------
    # Periodic metrics emission
    # ------------------------------------------------------------------

    def _emit_metrics(self):
        """Collect system metrics, merge with hardware data, publish + persist."""
        now = datetime.now(timezone.utc)

        # System metrics via psutil
        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        sys_metrics = {
            'cpu_percent': cpu_percent,
            'ram_used_mb': round(mem.used / (1024 * 1024), 1),
            'ram_total_mb': round(mem.total / (1024 * 1024), 1),
            'ram_percent': mem.percent,
            'disk_used_gb': round(disk.used / (1024 ** 3), 2),
            'disk_total_gb': round(disk.total / (1024 ** 3), 2),
            'disk_percent': disk.percent,
        }

        # CPU temperature (Linux thermal zone)
        temps = psutil.sensors_temperatures() if hasattr(psutil, 'sensors_temperatures') else {}
        if temps:
            for name, entries in temps.items():
                if entries:
                    sys_metrics['cpu_temp_c'] = entries[0].current
                    break

        # Build full metrics record
        record = {
            'ts': now.isoformat(),
            'robot_id': self._robot_id,
            'system': sys_metrics,
            'hardware': dict(self._hw_status) if self._hw_status else None,
        }

        # Publish
        out_msg = String()
        out_msg.data = json.dumps(record, default=str)
        self._pub.publish(out_msg)

        # Persist to JSONL
        self._write_record(record, now)

    # ------------------------------------------------------------------
    # File I/O with daily rotation
    # ------------------------------------------------------------------

    def _write_record(self, record: dict, now: datetime):
        """Append a metrics record to the daily JSONL file."""
        date_str = now.strftime('%Y-%m-%d')
        if date_str != self._current_date:
            if self._metrics_file is not None:
                self._metrics_file.close()
            filepath = self._metrics_dir / f'{date_str}.jsonl'
            self._metrics_file = open(filepath, 'a', encoding='utf-8')
            self._current_date = date_str

        try:
            self._metrics_file.write(json.dumps(record, default=str) + '\n')
            self._metrics_file.flush()
        except OSError as exc:
            self.get_logger().error(f'Failed to write metrics: {exc}')

    # ------------------------------------------------------------------
    # Retention cleanup
    # ------------------------------------------------------------------

    def _cleanup_old_files(self):
        """Remove metrics files older than retention_days."""
        if self._retention_days <= 0:
            return
        cutoff = datetime.now(timezone.utc)
        removed = 0
        for f in self._metrics_dir.glob('*.jsonl'):
            try:
                file_date = datetime.strptime(f.stem, '%Y-%m-%d').replace(
                    tzinfo=timezone.utc
                )
                if (cutoff - file_date).days > self._retention_days:
                    f.unlink()
                    removed += 1
            except (ValueError, OSError):
                continue
        if removed:
            self.get_logger().info(f'Cleaned up {removed} old metrics file(s)')

    def destroy_node(self):
        """Close open file handles on shutdown."""
        if self._metrics_file is not None:
            self._metrics_file.close()
        super().destroy_node()


def main(args=None):
    """Entry point for metrics_emitter node."""
    rclpy.init(args=args)
    node = MetricsEmitter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

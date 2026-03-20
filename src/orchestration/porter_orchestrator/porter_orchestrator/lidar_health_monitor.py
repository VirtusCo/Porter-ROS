"""LIDAR Health Monitor — subscribes to /diagnostics and publishes health level.

Translates raw ``diagnostic_msgs/DiagnosticArray`` messages from the
``ydlidar_node`` into a simple health level string and monitors scan
topic liveness. Publishes a health summary that the ``PorterStateMachine``
uses for state transitions.

The monitor also tracks ``/scan`` topic heartbeat — if no scan messages
arrive within a configurable timeout, the health level is escalated
regardless of what ``/diagnostics`` reports.

Copyright 2026 VirtusCo. All rights reserved. Proprietary and confidential.
"""

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from std_srvs.srv import Trigger


class LidarHealthMonitor(Node):
    """ROS 2 node that monitors LIDAR health and publishes status summaries.

    Subscribes to ``/diagnostics`` from ``ydlidar_node`` and ``/scan`` for
    heartbeat. Publishes a simple health level to ``/porter/health_status``
    for the state machine to consume.

    Subscriptions:
        ``/diagnostics`` (DiagnosticArray) — from ydlidar_node.
        ``/scan`` (LaserScan) — heartbeat (just checks liveness, not data).

    Publishers:
        ``/porter/health_status`` (String) — OK, WARN, ERROR, or STALE.

    Services:
        ``~/get_health_details`` (Trigger) — returns detailed health info.
    """

    def __init__(self):
        """Initialise the health monitor with configuration and subscriptions."""
        super().__init__('lidar_health_monitor')

        # --- Parameters ---
        self.declare_parameter('monitor_rate_hz', 2.0)
        self.declare_parameter('scan_timeout_sec', 3.0)
        self.declare_parameter('diag_timeout_sec', 5.0)
        self.declare_parameter('driver_diag_name', 'ydlidar_driver: LIDAR')
        self.declare_parameter('warn_consecutive_limit', 5)
        self.declare_parameter('error_escalation_sec', 10.0)

        rate_hz = self.get_parameter('monitor_rate_hz').value
        self.scan_timeout_ = self.get_parameter('scan_timeout_sec').value
        self.diag_timeout_ = self.get_parameter('diag_timeout_sec').value
        self.driver_diag_name_ = self.get_parameter('driver_diag_name').value
        self.warn_limit_ = self.get_parameter('warn_consecutive_limit').value
        self.error_escalation_ = self.get_parameter('error_escalation_sec').value

        # --- Internal state ---
        self.last_scan_time_ = None
        self.last_diag_time_ = None
        self.last_diag_level_ = DiagnosticStatus.STALE
        self.last_diag_message_ = 'No diagnostics received yet'
        self.consecutive_warns_ = 0
        self.scan_count_ = 0
        self.diag_count_ = 0
        self.diag_values_ = {}
        self.start_time_ = self.get_clock().now()

        # --- Publisher ---
        self.health_pub_ = self.create_publisher(
            String, '/porter/health_status', 10)

        # --- Subscriptions ---
        self.diag_sub_ = self.create_subscription(
            DiagnosticArray, '/diagnostics',
            self._diagnostics_callback, 10)

        # Match the ydlidar_driver's /scan QoS: RELIABLE + KEEP_LAST
        scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=5)
        self.scan_sub_ = self.create_subscription(
            LaserScan, '/scan', self._scan_heartbeat_callback, scan_qos)

        # --- Services ---
        self.details_srv_ = self.create_service(
            Trigger, '~/get_health_details', self._get_details_callback)

        # --- Timer ---
        period = 1.0 / rate_hz
        self.monitor_timer_ = self.create_timer(period, self._monitor_tick)

        self.get_logger().info(
            f'LIDAR Health Monitor started (rate={rate_hz} Hz, '
            f'scan_timeout={self.scan_timeout_}s, '
            f'diag_timeout={self.diag_timeout_}s)')

    # -----------------------------------------------------------------
    # Callbacks
    # -----------------------------------------------------------------

    def _diagnostics_callback(self, msg):
        """Process incoming diagnostics from ydlidar_node.

        Extracts the status entry matching the configured driver name
        and updates internal tracking.

        Args:
            msg: DiagnosticArray message from the driver.
        """
        for status in msg.status:
            if status.name == self.driver_diag_name_:
                self.last_diag_time_ = self.get_clock().now()
                self.last_diag_level_ = status.level
                self.last_diag_message_ = status.message
                self.diag_count_ += 1

                # Store key-value pairs for detail reporting
                self.diag_values_ = {
                    kv.key: kv.value for kv in status.values
                }

                if status.level == DiagnosticStatus.WARN:
                    self.consecutive_warns_ += 1
                else:
                    self.consecutive_warns_ = 0

                level_name = {
                    0: 'OK', 1: 'WARN', 2: 'ERROR', 3: 'STALE'
                }.get(status.level, f'UNKNOWN({status.level})')
                self.get_logger().debug(
                    f'Diagnostics received: level={level_name} '
                    f'msg="{status.message}" '
                    f'(diag #{self.diag_count_})')
                break
        else:
            # No matching status entry found
            names = [s.name for s in msg.status]
            self.get_logger().debug(
                f'Diagnostics received but no match for '
                f'"{self.driver_diag_name_}" in {names}')

    def _scan_heartbeat_callback(self, msg):
        """Track last /scan message time as a liveness indicator.

        Args:
            msg: LaserScan message (contents not inspected).
        """
        self.last_scan_time_ = self.get_clock().now()
        self.scan_count_ += 1

    # -----------------------------------------------------------------
    # Monitor logic
    # -----------------------------------------------------------------

    def _monitor_tick(self):
        """Periodic health evaluation — compute and publish health level."""
        now = self.get_clock().now()
        uptime = (now - self.start_time_).nanoseconds / 1e9
        health_level = self._evaluate_health(now)

        msg = String()
        msg.data = health_level
        self.health_pub_.publish(msg)

        # Log at INFO for first 10s of life, then DEBUG
        log_fn = (
            self.get_logger().info if uptime < 10.0
            else self.get_logger().debug)

        diag_level_name = {
            0: 'OK', 1: 'WARN', 2: 'ERROR', 3: 'STALE'
        }.get(self.last_diag_level_, f'?({self.last_diag_level_})')

        log_fn(
            f'Health: {health_level} '
            f'(diag_level={diag_level_name}, '
            f'diag_msg="{self.last_diag_message_}", '
            f'diags={self.diag_count_}, scans={self.scan_count_}, '
            f'uptime={uptime:.1f}s)')

    def _evaluate_health(self, now):
        """Compute the overall health level from diagnostics and heartbeat.

        Priority (highest to lowest):
            1. No diagnostics ever received → STALE
            2. Diagnostics timeout → STALE
            3. Scan heartbeat timeout → ERROR
            4. Diagnostics ERROR level → ERROR
            5. Consecutive warnings exceed limit → ERROR
            6. Diagnostics WARN level → WARN
            7. Otherwise → OK

        Args:
            now: Current ROS clock time.

        Returns:
            Health level string: OK, WARN, ERROR, or STALE.
        """
        # No diagnostics ever received
        if self.last_diag_time_ is None:
            return 'STALE'

        diag_age = (now - self.last_diag_time_).nanoseconds / 1e9

        # Diagnostics timed out
        if diag_age > self.diag_timeout_:
            self.get_logger().warn(
                f'Diagnostics stale ({diag_age:.1f}s > {self.diag_timeout_}s)')
            return 'STALE'

        # Scan heartbeat check
        if self.last_scan_time_ is not None:
            scan_age = (now - self.last_scan_time_).nanoseconds / 1e9
            if scan_age > self.scan_timeout_:
                self.get_logger().warn(
                    f'Scan data stale ({scan_age:.1f}s > '
                    f'{self.scan_timeout_}s)')
                return 'ERROR'

        # Map diagnostic level
        if self.last_diag_level_ == DiagnosticStatus.ERROR:
            return 'ERROR'
        if self.last_diag_level_ == DiagnosticStatus.STALE:
            return 'STALE'

        # Escalate persistent warnings
        if self.last_diag_level_ == DiagnosticStatus.WARN:
            if self.consecutive_warns_ >= self.warn_limit_:
                self.get_logger().warn(
                    f'Consecutive warnings ({self.consecutive_warns_}) '
                    f'>= limit ({self.warn_limit_}) — escalating to ERROR')
                return 'ERROR'
            return 'WARN'

        return 'OK'

    # -----------------------------------------------------------------
    # Service callback
    # -----------------------------------------------------------------

    def _get_details_callback(self, request, response):
        """Return detailed health information via service.

        Args:
            request: Trigger request (empty).
            response: Trigger response with detailed health string.

        Returns:
            Populated response.
        """
        now = self.get_clock().now()
        health = self._evaluate_health(now)

        scan_age_str = 'never'
        if self.last_scan_time_ is not None:
            scan_age = (now - self.last_scan_time_).nanoseconds / 1e9
            scan_age_str = f'{scan_age:.1f}s ago'

        diag_age_str = 'never'
        if self.last_diag_time_ is not None:
            diag_age = (now - self.last_diag_time_).nanoseconds / 1e9
            diag_age_str = f'{diag_age:.1f}s ago'

        details = (
            f'health={health} '
            f'diag_level={self.last_diag_level_} '
            f'diag_msg="{self.last_diag_message_}" '
            f'last_scan={scan_age_str} '
            f'last_diag={diag_age_str} '
            f'scan_count={self.scan_count_} '
            f'diag_count={self.diag_count_} '
            f'consecutive_warns={self.consecutive_warns_}')

        # Append key diagnostics values
        for key in ('actual_freq_hz', 'consecutive_failures', 'reconnect_count'):
            if key in self.diag_values_:
                details += f' {key}={self.diag_values_[key]}'

        response.success = (health == 'OK')
        response.message = details
        return response


def main(args=None):
    """Entry point for the lidar_health_monitor node."""
    rclpy.init(args=args)
    node = LidarHealthMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

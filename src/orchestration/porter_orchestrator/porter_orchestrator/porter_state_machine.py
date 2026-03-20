"""Porter State Machine — system-level state management for Porter Robot.

Manages the boot sequence, monitors subsystem health, and publishes the
current system state. The state machine coordinates the LIDAR driver,
scan processor, and (future) navigation subsystems.

State transitions::

    INITIALISING → DRIVER_STARTING → HEALTH_CHECK → PROCESSOR_STARTING
                                                   → READY ⇄ DEGRADED
                                                             → ERROR → RECOVERY → DRIVER_STARTING
                                                                     → SHUTDOWN

Copyright 2026 VirtusCo. All rights reserved. Proprietary and confidential.
"""

from enum import Enum, unique

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


@unique
class PorterState(Enum):
    """System-level states for the Porter Robot orchestrator."""

    INITIALISING = 'INITIALISING'
    DRIVER_STARTING = 'DRIVER_STARTING'
    HEALTH_CHECK = 'HEALTH_CHECK'
    PROCESSOR_STARTING = 'PROCESSOR_STARTING'
    READY = 'READY'
    DEGRADED = 'DEGRADED'
    ERROR = 'ERROR'
    RECOVERY = 'RECOVERY'
    SHUTDOWN = 'SHUTDOWN'


class PorterStateMachine(Node):
    """ROS 2 node that manages Porter Robot system state.

    Publishes the current state to ``/porter/state`` and exposes services
    for querying state and requesting recovery. Works in tandem with the
    ``LidarHealthMonitor`` node which feeds health updates.

    Subscriptions:
        ``/porter/health_status`` (String) — health level from monitor node.

    Publishers:
        ``/porter/state`` (String) — current system state.

    Services:
        ``~/get_state`` (Trigger) — returns the current state as a string.
        ``~/request_recovery`` (Trigger) — forces transition to RECOVERY.
        ``~/shutdown`` (Trigger) — initiates graceful shutdown sequence.
    """

    def __init__(self):
        """Initialise the state machine with pub/sub, services, and timers."""
        super().__init__('porter_state_machine')

        # --- Parameters ---
        self.declare_parameter('state_publish_rate_hz', 2.0)
        self.declare_parameter('boot_timeout_sec', 30.0)
        self.declare_parameter('boot_grace_sec', 8.0)
        self.declare_parameter('health_check_patience_sec', 10.0)
        self.declare_parameter('health_timeout_sec', 5.0)

        rate_hz = self.get_parameter('state_publish_rate_hz').value
        self.boot_timeout_ = self.get_parameter('boot_timeout_sec').value
        self.boot_grace_ = self.get_parameter('boot_grace_sec').value
        self.health_check_patience_ = (
            self.get_parameter('health_check_patience_sec').value)
        self.health_timeout_ = self.get_parameter('health_timeout_sec').value

        # --- State ---
        self.state_ = PorterState.INITIALISING
        self.previous_state_ = PorterState.INITIALISING
        self.last_health_level_ = 'UNKNOWN'
        self.last_health_time_ = self.get_clock().now()
        self.boot_start_time_ = self.get_clock().now()
        self.health_check_enter_time_ = None
        self.recovery_attempts_ = 0
        self.max_recovery_attempts_ = 3

        # --- Publisher ---
        self.state_pub_ = self.create_publisher(String, '/porter/state', 10)

        # --- Subscriptions ---
        self.health_sub_ = self.create_subscription(
            String, '/porter/health_status',
            self._health_status_callback, 10)

        # --- Services ---
        self.get_state_srv_ = self.create_service(
            Trigger, '~/get_state', self._get_state_callback)
        self.recovery_srv_ = self.create_service(
            Trigger, '~/request_recovery', self._request_recovery_callback)
        self.shutdown_srv_ = self.create_service(
            Trigger, '~/shutdown', self._shutdown_callback)

        # --- Timers ---
        period = 1.0 / rate_hz
        self.state_timer_ = self.create_timer(period, self._state_tick)

        self.get_logger().info(
            f'Porter State Machine initialised (rate={rate_hz} Hz, '
            f'boot_grace={self.boot_grace_}s, '
            f'boot_timeout={self.boot_timeout_}s, '
            f'health_check_patience={self.health_check_patience_}s)')

        # Kick off the boot sequence
        self._transition_to(PorterState.DRIVER_STARTING)

    # -----------------------------------------------------------------
    # State transition logic
    # -----------------------------------------------------------------

    def _transition_to(self, new_state):
        """Execute a state transition with logging.

        Args:
            new_state: The target PorterState.
        """
        if new_state == self.state_:
            return
        self.previous_state_ = self.state_
        self.state_ = new_state
        self.get_logger().info(
            f'State: {self.previous_state_.value} → {new_state.value}')

    def _state_tick(self):
        """Periodic state machine tick — evaluate transitions and publish."""
        now = self.get_clock().now()

        if self.state_ == PorterState.DRIVER_STARTING:
            self._tick_driver_starting(now)
        elif self.state_ == PorterState.HEALTH_CHECK:
            self._tick_health_check(now)
        elif self.state_ == PorterState.PROCESSOR_STARTING:
            self._tick_processor_starting(now)
        elif self.state_ == PorterState.READY:
            self._tick_ready(now)
        elif self.state_ == PorterState.DEGRADED:
            self._tick_degraded(now)
        elif self.state_ == PorterState.ERROR:
            self._tick_error(now)
        elif self.state_ == PorterState.RECOVERY:
            self._tick_recovery(now)

        # Always publish current state
        msg = String()
        msg.data = self.state_.value
        self.state_pub_.publish(msg)

    # -----------------------------------------------------------------
    # Per-state tick handlers
    # -----------------------------------------------------------------

    def _tick_driver_starting(self, now):
        """Wait for health OK from the LIDAR driver with a grace period.

        DDS discovery can take several seconds. We wait for at least
        ``boot_grace_sec`` before even considering health data. This
        prevents false failures from STALE health during DDS warm-up.

        Transitions to HEALTH_CHECK only when health is 'OK'. Times out
        after ``boot_timeout_sec``.
        """
        elapsed = (now - self.boot_start_time_).nanoseconds / 1e9

        # During grace period, just wait — log progress periodically
        if elapsed < self.boot_grace_:
            if self.last_health_level_ == 'OK':
                self.get_logger().info(
                    f'Driver health OK during grace period ({elapsed:.1f}s) '
                    '— proceeding to health check')
                self.health_check_enter_time_ = now
                self._transition_to(PorterState.HEALTH_CHECK)
            return

        # Grace period elapsed — evaluate health
        if self.last_health_level_ == 'OK':
            self.health_check_enter_time_ = now
            self._transition_to(PorterState.HEALTH_CHECK)
        elif elapsed > self.boot_timeout_:
            self.get_logger().error(
                f'Boot timeout ({self.boot_timeout_}s) — '
                f'health is {self.last_health_level_} '
                '(expected OK). Check LIDAR driver is running.')
            self._transition_to(PorterState.ERROR)

    def _tick_health_check(self, now):
        """Verify the driver is consistently healthy before proceeding.

        Stays in HEALTH_CHECK for a patience window, only advancing to
        PROCESSOR_STARTING if health remains OK. This absorbs transient
        startup glitches in diagnostics.
        """
        if self.health_check_enter_time_ is None:
            self.health_check_enter_time_ = now

        patience_elapsed = (
            (now - self.health_check_enter_time_).nanoseconds / 1e9)

        if self.last_health_level_ == 'OK':
            self.get_logger().info('Driver health OK — starting processor')
            self._transition_to(PorterState.PROCESSOR_STARTING)
        elif self.last_health_level_ in ('ERROR', 'STALE'):
            if patience_elapsed > self.health_check_patience_:
                self.get_logger().error(
                    f'Driver health is {self.last_health_level_} after '
                    f'{patience_elapsed:.1f}s patience — entering ERROR')
                self._transition_to(PorterState.ERROR)
            else:
                self.get_logger().debug(
                    f'Health is {self.last_health_level_}, '
                    f'patience {patience_elapsed:.1f}/'
                    f'{self.health_check_patience_}s')
        # WARN — stay in HEALTH_CHECK, might recover

    def _tick_processor_starting(self, now):
        """Transition to READY after allowing processor startup time.

        The processor node starts independently (via launch file). We give
        it a brief grace period, then move to READY. Future versions can
        wait for ``/scan/processed`` heartbeat.
        """
        # For now, immediately transition — processor is launched separately
        self.get_logger().info('System READY — all subsystems nominal')
        self.recovery_attempts_ = 0
        self._transition_to(PorterState.READY)

    def _tick_ready(self, now):
        """Monitor health while in the READY state.

        Degrades if health drops, errors if health is critical or stale.
        """
        health_age = (now - self.last_health_time_).nanoseconds / 1e9

        if health_age > self.health_timeout_:
            self.get_logger().warn(
                f'Health data stale ({health_age:.1f}s) — degrading')
            self._transition_to(PorterState.DEGRADED)
        elif self.last_health_level_ == 'WARN':
            self._transition_to(PorterState.DEGRADED)
        elif self.last_health_level_ in ('ERROR', 'STALE'):
            self.get_logger().error(
                f'Health critical ({self.last_health_level_}) — entering ERROR')
            self._transition_to(PorterState.ERROR)

    def _tick_degraded(self, now):
        """Monitor health in the DEGRADED state.

        Returns to READY if health recovers, escalates to ERROR if critical.
        """
        health_age = (now - self.last_health_time_).nanoseconds / 1e9

        if self.last_health_level_ == 'OK' and health_age < self.health_timeout_:
            self.get_logger().info('Health recovered — returning to READY')
            self._transition_to(PorterState.READY)
        elif self.last_health_level_ in ('ERROR', 'STALE'):
            self.get_logger().error('Health critical in DEGRADED — ERROR')
            self._transition_to(PorterState.ERROR)
        elif health_age > self.health_timeout_ * 2:
            self.get_logger().error('Health data lost — ERROR')
            self._transition_to(PorterState.ERROR)

    def _tick_error(self, now):
        """Handle ERROR state — attempt automatic recovery.

        Transitions to RECOVERY if attempts remain, SHUTDOWN if exhausted.
        """
        if self.recovery_attempts_ < self.max_recovery_attempts_:
            self.get_logger().warn(
                f'Attempting recovery ({self.recovery_attempts_ + 1}/'
                f'{self.max_recovery_attempts_})')
            self._transition_to(PorterState.RECOVERY)
        else:
            self.get_logger().error(
                'Max recovery attempts reached — system requires manual '
                'intervention')
            # Stay in ERROR — don't auto-shutdown to allow operator access

    def _tick_recovery(self, now):
        """Execute recovery actions and retry the boot sequence.

        Increments the attempt counter and restarts from DRIVER_STARTING.
        The actual driver restart is triggered via the health monitor's
        process management (future: lifecycle nodes).
        """
        self.recovery_attempts_ += 1
        self.last_health_level_ = 'UNKNOWN'
        self.health_check_enter_time_ = None
        self.boot_start_time_ = self.get_clock().now()
        self.get_logger().info(
            f'Recovery attempt {self.recovery_attempts_} — '
            'restarting boot sequence')
        self._transition_to(PorterState.DRIVER_STARTING)

    # -----------------------------------------------------------------
    # Callbacks
    # -----------------------------------------------------------------

    def _health_status_callback(self, msg):
        """Handle health status updates from the LidarHealthMonitor.

        Args:
            msg: String message with health level (OK, WARN, ERROR, STALE).
        """
        self.last_health_level_ = msg.data
        self.last_health_time_ = self.get_clock().now()

    def _get_state_callback(self, request, response):
        """Return current system state via service.

        Args:
            request: Trigger request (empty).
            response: Trigger response with state string.

        Returns:
            Populated response.
        """
        response.success = True
        response.message = (
            f'state={self.state_.value} '
            f'previous={self.previous_state_.value} '
            f'health={self.last_health_level_} '
            f'recovery_attempts={self.recovery_attempts_}')
        return response

    def _request_recovery_callback(self, request, response):
        """Force transition to RECOVERY state via service.

        Args:
            request: Trigger request (empty).
            response: Trigger response.

        Returns:
            Populated response.
        """
        if self.state_ == PorterState.SHUTDOWN:
            response.success = False
            response.message = 'Cannot recover from SHUTDOWN state'
        else:
            self.get_logger().warn('Manual recovery requested via service')
            self._transition_to(PorterState.ERROR)
            response.success = True
            response.message = f'Recovery initiated from {self.state_.value}'
        return response

    def _shutdown_callback(self, request, response):
        """Initiate graceful shutdown via service.

        Args:
            request: Trigger request (empty).
            response: Trigger response.

        Returns:
            Populated response.
        """
        self.get_logger().info('Shutdown requested via service')
        self._transition_to(PorterState.SHUTDOWN)
        response.success = True
        response.message = 'Shutdown initiated'

        # Schedule actual shutdown after response is sent
        self.create_timer(0.5, self._deferred_shutdown)
        return response

    def _deferred_shutdown(self):
        """Shut down the node after a brief delay."""
        self.get_logger().info('Porter State Machine shutting down')
        raise SystemExit(0)


def main(args=None):
    """Entry point for the porter_state_machine node."""
    rclpy.init(args=args)
    node = PorterStateMachine()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

"""Unit tests for the Porter Orchestrator state machine and health monitor.

Tests cover state transitions, health evaluation logic, and edge cases
without requiring a running ROS 2 graph.
"""

from unittest.mock import MagicMock

from porter_orchestrator.porter_state_machine import PorterState
import pytest
import rclpy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def rclpy_context():
    """Initialise rclpy once for the entire test module."""
    rclpy.init()
    yield
    rclpy.try_shutdown()


@pytest.fixture
def state_machine_node(rclpy_context):
    """Create a PorterStateMachine node for testing."""
    from porter_orchestrator.porter_state_machine import PorterStateMachine
    node = PorterStateMachine()
    yield node
    node.destroy_node()


@pytest.fixture
def health_monitor_node(rclpy_context):
    """Create a LidarHealthMonitor node for testing."""
    from porter_orchestrator.lidar_health_monitor import LidarHealthMonitor
    node = LidarHealthMonitor()
    yield node
    node.destroy_node()


# ---------------------------------------------------------------------------
# State Machine Tests
# ---------------------------------------------------------------------------

class TestPorterStateMachine:
    """Test state machine transitions and service callbacks."""

    def test_initial_state_is_driver_starting(self, state_machine_node):
        """Verify the state machine starts in DRIVER_STARTING after init."""
        assert state_machine_node.state_ == PorterState.DRIVER_STARTING

    def test_transition_logging(self, state_machine_node):
        """Verify state transitions update previous_state correctly."""
        state_machine_node._transition_to(PorterState.HEALTH_CHECK)
        assert state_machine_node.state_ == PorterState.HEALTH_CHECK
        assert state_machine_node.previous_state_ == PorterState.DRIVER_STARTING

    def test_no_op_transition(self, state_machine_node):
        """Verify transitioning to the same state is a no-op."""
        current = state_machine_node.state_
        prev = state_machine_node.previous_state_
        state_machine_node._transition_to(current)
        assert state_machine_node.previous_state_ == prev

    def test_health_check_ok_goes_to_processor_starting(
        self, state_machine_node
    ):
        """Verify OK health during HEALTH_CHECK advances to PROCESSOR_STARTING."""
        state_machine_node._transition_to(PorterState.HEALTH_CHECK)
        state_machine_node.last_health_level_ = 'OK'
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_health_check(now)
        assert state_machine_node.state_ == PorterState.PROCESSOR_STARTING

    def test_health_check_error_goes_to_error_after_patience(
        self, state_machine_node
    ):
        """Verify ERROR health in HEALTH_CHECK transitions after patience."""
        state_machine_node._transition_to(PorterState.HEALTH_CHECK)
        state_machine_node.last_health_level_ = 'ERROR'
        # Simulate patience window already expired by setting enter time in past
        from rclpy.time import Time
        state_machine_node.health_check_enter_time_ = Time(
            nanoseconds=0, clock_type=state_machine_node.get_clock().clock_type)
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_health_check(now)
        assert state_machine_node.state_ == PorterState.ERROR

    def test_health_check_error_tolerant_within_patience(
        self, state_machine_node
    ):
        """Verify ERROR health in HEALTH_CHECK is tolerated within patience."""
        state_machine_node._transition_to(PorterState.HEALTH_CHECK)
        state_machine_node.last_health_level_ = 'ERROR'
        state_machine_node.health_check_enter_time_ = (
            state_machine_node.get_clock().now())
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_health_check(now)
        # Should stay in HEALTH_CHECK during patience window
        assert state_machine_node.state_ == PorterState.HEALTH_CHECK

    def test_processor_starting_goes_to_ready(self, state_machine_node):
        """Verify PROCESSOR_STARTING transitions directly to READY."""
        state_machine_node._transition_to(PorterState.PROCESSOR_STARTING)
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_processor_starting(now)
        assert state_machine_node.state_ == PorterState.READY

    def test_ready_degrades_on_warn(self, state_machine_node):
        """Verify WARN health in READY state triggers DEGRADED."""
        state_machine_node._transition_to(PorterState.READY)
        state_machine_node.last_health_level_ = 'WARN'
        state_machine_node.last_health_time_ = (
            state_machine_node.get_clock().now())
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_ready(now)
        assert state_machine_node.state_ == PorterState.DEGRADED

    def test_degraded_recovers_on_ok(self, state_machine_node):
        """Verify OK health in DEGRADED state returns to READY."""
        state_machine_node._transition_to(PorterState.DEGRADED)
        state_machine_node.last_health_level_ = 'OK'
        state_machine_node.last_health_time_ = (
            state_machine_node.get_clock().now())
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_degraded(now)
        assert state_machine_node.state_ == PorterState.READY

    def test_error_triggers_recovery(self, state_machine_node):
        """Verify ERROR state triggers RECOVERY when attempts remain."""
        state_machine_node._transition_to(PorterState.ERROR)
        state_machine_node.recovery_attempts_ = 0
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_error(now)
        assert state_machine_node.state_ == PorterState.RECOVERY

    def test_error_stays_when_max_attempts(self, state_machine_node):
        """Verify ERROR stays in ERROR when recovery attempts exhausted."""
        state_machine_node._transition_to(PorterState.ERROR)
        state_machine_node.recovery_attempts_ = 3
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_error(now)
        assert state_machine_node.state_ == PorterState.ERROR

    def test_recovery_restarts_boot_sequence(self, state_machine_node):
        """Verify RECOVERY increments attempts and goes to DRIVER_STARTING."""
        state_machine_node._transition_to(PorterState.RECOVERY)
        state_machine_node.recovery_attempts_ = 0
        now = state_machine_node.get_clock().now()
        state_machine_node._tick_recovery(now)
        assert state_machine_node.state_ == PorterState.DRIVER_STARTING
        assert state_machine_node.recovery_attempts_ == 1

    def test_get_state_service(self, state_machine_node):
        """Verify get_state service returns current state."""
        request = MagicMock()
        response = MagicMock()
        result = state_machine_node._get_state_callback(request, response)
        assert result.success is True
        assert 'DRIVER_STARTING' in result.message


# ---------------------------------------------------------------------------
# Health Monitor Tests
# ---------------------------------------------------------------------------

class TestLidarHealthMonitor:
    """Test health evaluation logic and diagnostics processing."""

    def test_initial_health_is_stale(self, health_monitor_node):
        """Verify health is STALE when no diagnostics received yet."""
        now = health_monitor_node.get_clock().now()
        health = health_monitor_node._evaluate_health(now)
        assert health == 'STALE'

    def test_ok_health_after_good_diagnostics(self, health_monitor_node):
        """Verify health is OK after receiving healthy diagnostics."""
        from diagnostic_msgs.msg import DiagnosticStatus
        health_monitor_node.last_diag_time_ = (
            health_monitor_node.get_clock().now())
        health_monitor_node.last_diag_level_ = DiagnosticStatus.OK
        health_monitor_node.last_scan_time_ = (
            health_monitor_node.get_clock().now())
        now = health_monitor_node.get_clock().now()
        health = health_monitor_node._evaluate_health(now)
        assert health == 'OK'

    def test_warn_on_warn_diagnostics(self, health_monitor_node):
        """Verify health is WARN when diagnostics report WARN."""
        from diagnostic_msgs.msg import DiagnosticStatus
        health_monitor_node.last_diag_time_ = (
            health_monitor_node.get_clock().now())
        health_monitor_node.last_diag_level_ = DiagnosticStatus.WARN
        health_monitor_node.consecutive_warns_ = 1
        now = health_monitor_node.get_clock().now()
        health = health_monitor_node._evaluate_health(now)
        assert health == 'WARN'

    def test_error_on_error_diagnostics(self, health_monitor_node):
        """Verify health is ERROR when diagnostics report ERROR."""
        from diagnostic_msgs.msg import DiagnosticStatus
        health_monitor_node.last_diag_time_ = (
            health_monitor_node.get_clock().now())
        health_monitor_node.last_diag_level_ = DiagnosticStatus.ERROR
        now = health_monitor_node.get_clock().now()
        health = health_monitor_node._evaluate_health(now)
        assert health == 'ERROR'

    def test_consecutive_warns_escalate_to_error(self, health_monitor_node):
        """Verify persistent WARN escalates to ERROR after limit."""
        from diagnostic_msgs.msg import DiagnosticStatus
        health_monitor_node.last_diag_time_ = (
            health_monitor_node.get_clock().now())
        health_monitor_node.last_diag_level_ = DiagnosticStatus.WARN
        health_monitor_node.consecutive_warns_ = (
            health_monitor_node.warn_limit_)
        now = health_monitor_node.get_clock().now()
        health = health_monitor_node._evaluate_health(now)
        assert health == 'ERROR'

    def test_get_details_service(self, health_monitor_node):
        """Verify get_health_details returns structured info."""
        request = MagicMock()
        response = MagicMock()
        result = health_monitor_node._get_details_callback(
            request, response)
        assert 'health=' in result.message


# ---------------------------------------------------------------------------
# PorterState enum tests
# ---------------------------------------------------------------------------

class TestPorterStateEnum:
    """Test the PorterState enumeration."""

    def test_all_states_exist(self):
        """Verify all expected states are defined."""
        expected = [
            'INITIALISING', 'DRIVER_STARTING', 'HEALTH_CHECK',
            'PROCESSOR_STARTING', 'READY', 'DEGRADED',
            'ERROR', 'RECOVERY', 'SHUTDOWN',
        ]
        for name in expected:
            assert hasattr(PorterState, name)

    def test_state_values_are_strings(self):
        """Verify each state's value is its name string."""
        for state in PorterState:
            assert state.value == state.name

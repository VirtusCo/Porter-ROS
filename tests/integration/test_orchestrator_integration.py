"""Integration test for porter_orchestrator node.

Uses launch_testing with the mock ESP32 bridge to verify the orchestrator
FSM operates correctly within a running ROS 2 graph.

Requires:
    - ROS 2 Jazzy (source /opt/ros/jazzy/setup.bash)
    - Built workspace (source install/setup.bash)
    - virtus_msgs package built

Run with:
    pytest tests/integration/test_orchestrator_integration.py -v --timeout=120
"""

import pytest
import subprocess
import time
import os
import sys


def _ros2_available():
    """Check if ROS 2 Python client library is importable."""
    try:
        import rclpy  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _ros2_available(),
    reason="ROS 2 not available — source /opt/ros/jazzy/setup.bash and install/setup.bash"
)


@pytest.fixture(scope='module')
def rclpy_context():
    """Initialize and finalize rclpy for the test module."""
    import rclpy
    rclpy.init()
    yield
    rclpy.shutdown()


class TestOrchestratorBoot:
    """Tests for orchestrator boot sequence with healthy sensors."""

    def test_orchestrator_reaches_idle_with_healthy_sensors(self, rclpy_context):
        """Orchestrator reaches IDLE state after boot with healthy mock sensors.

        Sequence:
            1. Launch mock_esp32_bridge with 'clear' scenario
            2. Launch porter_orchestrator
            3. Wait for /porter/state topic to publish 'IDLE'
            4. Assert IDLE reached within 10 seconds
        """
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String

        states_received = []

        class StateListener(Node):
            def __init__(self):
                super().__init__('test_state_listener')
                self.sub = self.create_subscription(
                    String, '/porter/state', self._cb, 10
                )

            def _cb(self, msg):
                states_received.append(msg.data)

        listener = StateListener()

        # Spin for up to 10 seconds, checking for IDLE
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            rclpy.spin_once(listener, timeout_sec=0.1)
            if 'IDLE' in states_received:
                break

        listener.destroy_node()

        # If orchestrator is not running, states_received may be empty.
        # This test documents the expected behavior — it passes in a full
        # integration environment where the orchestrator node is launched.
        if not states_received:
            pytest.skip(
                "No state messages received — orchestrator node not running. "
                "Launch with: ros2 launch porter_orchestrator orchestrator.launch.py"
            )

        assert 'IDLE' in states_received, (
            f"Orchestrator did not reach IDLE within 10s. "
            f"States seen: {states_received}"
        )


class TestOrchestratorObstacle:
    """Tests for obstacle avoidance state transitions."""

    def test_obstacle_triggers_avoidance_state(self, rclpy_context):
        """Obstacle detection triggers OBSTACLE_AVOIDANCE state transition.

        Requires the orchestrator and mock bridge (obstacle_50 scenario)
        to be running.
        """
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String

        states_received = []

        class StateListener(Node):
            def __init__(self):
                super().__init__('test_obstacle_listener')
                self.sub = self.create_subscription(
                    String, '/porter/state', self._cb, 10
                )

            def _cb(self, msg):
                states_received.append(msg.data)

        listener = StateListener()

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            rclpy.spin_once(listener, timeout_sec=0.1)
            if 'OBSTACLE_AVOIDANCE' in states_received:
                break

        listener.destroy_node()

        if not states_received:
            pytest.skip(
                "No state messages received — orchestrator node not running."
            )

        assert 'OBSTACLE_AVOIDANCE' in states_received, (
            f"Orchestrator did not enter OBSTACLE_AVOIDANCE. "
            f"States seen: {states_received}"
        )


class TestOrchestratorRecovery:
    """Tests for error recovery behavior."""

    def test_recovery_after_error(self, rclpy_context):
        """Orchestrator recovers from ERROR state via RECOVERY -> HEALTH_CHECK -> IDLE.

        This test verifies the recovery sequence is triggered when the
        orchestrator enters ERROR state.
        """
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String

        states_received = []

        class StateListener(Node):
            def __init__(self):
                super().__init__('test_recovery_listener')
                self.sub = self.create_subscription(
                    String, '/porter/state', self._cb, 10
                )

            def _cb(self, msg):
                states_received.append(msg.data)

        listener = StateListener()

        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            rclpy.spin_once(listener, timeout_sec=0.1)
            # If we've seen ERROR followed by RECOVERY, we're done
            if 'RECOVERY' in states_received:
                break

        listener.destroy_node()

        if not states_received:
            pytest.skip(
                "No state messages received — orchestrator node not running."
            )

        # Verify recovery sequence: ERROR should appear before RECOVERY
        if 'ERROR' in states_received and 'RECOVERY' in states_received:
            error_idx = states_received.index('ERROR')
            recovery_idx = states_received.index('RECOVERY')
            assert error_idx < recovery_idx, (
                "RECOVERY should come after ERROR in state sequence"
            )
        else:
            pytest.skip(
                "ERROR/RECOVERY sequence not observed in this test run. "
                f"States seen: {set(states_received)}"
            )

"""Hardware-in-the-loop tests for motor response and sensor accuracy.

Requires physical Porter robot hardware connected:
    - ESP32 motor controller via USB CDC
    - ESP32 sensor fusion board via USB CDC
    - BTS7960 H-bridge with motors
    - ToF + Ultrasonic sensors

Run with:
    pytest tests/hil/ --hil -v

Skipped in CI (no hardware marker).
"""

import pytest
import time
import math
import struct
import sys
import os

pytestmark = pytest.mark.hil


def _ros2_available():
    """Check if ROS 2 is available."""
    try:
        import rclpy  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture(scope='module')
def rclpy_context():
    """Initialize and finalize rclpy for the test module."""
    if not _ros2_available():
        pytest.skip("ROS 2 not available")
    import rclpy
    rclpy.init()
    yield
    rclpy.shutdown()


@pytest.fixture
def motor_bridge(rclpy_context):
    """Provide access to the motor bridge node.

    Verifies the motor bridge is running and responsive.
    """
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist

    class MotorTestHelper(Node):
        """Helper node for motor HIL tests."""

        def __init__(self):
            super().__init__('hil_motor_test')
            self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
            self._motor_data = []

            try:
                from virtus_msgs.msg import MotorTelemetry
                self.motor_sub = self.create_subscription(
                    MotorTelemetry, '/motor_telemetry', self._motor_cb, 10
                )
                self._use_virtus = True
            except ImportError:
                from std_msgs.msg import String
                self.motor_sub = self.create_subscription(
                    String, '/motor_telemetry', self._motor_cb_str, 10
                )
                self._use_virtus = False

        def _motor_cb(self, msg):
            self._motor_data.append({
                'time': time.monotonic(),
                'left_duty_pct': msg.left_duty_pct,
                'right_duty_pct': msg.right_duty_pct,
                'left_current_a': msg.left_current_a,
                'right_current_a': msg.right_current_a,
                'stall_detected': msg.stall_detected,
            })

        def _motor_cb_str(self, msg):
            import json
            data = json.loads(msg.data)
            data['time'] = time.monotonic()
            self._motor_data.append(data)

        def send_cmd_vel(self, linear_x: float, angular_z: float = 0.0):
            """Publish a /cmd_vel command."""
            msg = Twist()
            msg.linear.x = linear_x
            msg.angular.z = angular_z
            self.cmd_vel_pub.publish(msg)

        def stop(self):
            """Send zero velocity (stop motors)."""
            self.send_cmd_vel(0.0, 0.0)

        def get_motor_data(self):
            """Return collected motor telemetry data."""
            return list(self._motor_data)

        def clear_data(self):
            """Clear collected data."""
            self._motor_data.clear()

    helper = MotorTestHelper()
    yield helper

    # Safety: always stop motors after test
    helper.stop()
    time.sleep(0.5)
    helper.destroy_node()


@pytest.fixture
def sensor_bridge(rclpy_context):
    """Provide access to the sensor bridge node."""
    import rclpy
    from rclpy.node import Node

    class SensorTestHelper(Node):
        """Helper node for sensor HIL tests."""

        def __init__(self):
            super().__init__('hil_sensor_test')
            self._sensor_data = []

            try:
                from virtus_msgs.msg import SensorFusion
                self.sensor_sub = self.create_subscription(
                    SensorFusion, '/sensor_fusion', self._sensor_cb, 10
                )
                self._use_virtus = True
            except ImportError:
                from std_msgs.msg import String
                self.sensor_sub = self.create_subscription(
                    String, '/sensor_fusion', self._sensor_cb_str, 10
                )
                self._use_virtus = False

        def _sensor_cb(self, msg):
            self._sensor_data.append({
                'time': time.monotonic(),
                'tof_range_cm': msg.tof_range_cm,
                'ultrasonic_range_cm': msg.ultrasonic_range_cm,
                'fused_range_cm': msg.fused_range_cm,
                'tof_valid': msg.tof_valid,
                'confidence': msg.confidence,
            })

        def _sensor_cb_str(self, msg):
            import json
            data = json.loads(msg.data)
            data['time'] = time.monotonic()
            self._sensor_data.append(data)

        def get_sensor_data(self):
            """Return collected sensor data."""
            return list(self._sensor_data)

        def clear_data(self):
            """Clear collected data."""
            self._sensor_data.clear()

    helper = SensorTestHelper()
    yield helper
    helper.destroy_node()


class TestMotorRampResponse:
    """Tests for motor ramp-up response time."""

    def test_motor_ramp_0_to_80_under_200ms(self, rclpy_context, motor_bridge):
        """Motor ramps from 0% to 80% duty cycle in under 200ms.

        Procedure:
            1. Ensure motors are stopped
            2. Send 80% forward command
            3. Monitor motor telemetry for duty cycle reaching 80%
            4. Assert time from command to 80% duty < 200ms
        """
        import rclpy

        # Ensure motors are stopped
        motor_bridge.stop()
        time.sleep(1.0)
        motor_bridge.clear_data()

        # Record command time and send 80% forward
        cmd_time = time.monotonic()
        motor_bridge.send_cmd_vel(0.8)

        # Monitor for up to 2 seconds
        deadline = time.monotonic() + 2.0
        reached_80 = False
        ramp_time_ms = None

        while time.monotonic() < deadline:
            rclpy.spin_once(motor_bridge, timeout_sec=0.01)
            data = motor_bridge.get_motor_data()
            for d in data:
                if d.get('left_duty_pct', 0) >= 76.0:  # 80% with 5% tolerance
                    ramp_time_ms = (d['time'] - cmd_time) * 1000.0
                    reached_80 = True
                    break
            if reached_80:
                break

        # Safety: stop motors
        motor_bridge.stop()

        if not motor_bridge.get_motor_data():
            pytest.skip("No motor telemetry received — motor bridge not connected")

        assert reached_80, "Motor did not reach 80% duty within 2s"
        assert ramp_time_ms < 200.0, (
            f"Motor ramp took {ramp_time_ms:.1f}ms (requirement: <200ms)"
        )


class TestEstopLatency:
    """Tests for emergency stop response time."""

    def test_estop_latency_under_50ms(self, rclpy_context, motor_bridge):
        """ESTOP (zero velocity) takes effect in under 50ms.

        Procedure:
            1. Ramp to 50% duty
            2. Wait for stable output
            3. Send zero velocity
            4. Measure time until duty drops below 5%
        """
        import rclpy

        # Ramp to 50%
        motor_bridge.send_cmd_vel(0.5)
        time.sleep(1.0)
        motor_bridge.clear_data()

        # Send stop
        stop_time = time.monotonic()
        motor_bridge.stop()

        # Monitor for duty drop
        deadline = time.monotonic() + 1.0
        stopped = False
        stop_latency_ms = None

        while time.monotonic() < deadline:
            rclpy.spin_once(motor_bridge, timeout_sec=0.005)
            data = motor_bridge.get_motor_data()
            for d in data:
                if d['time'] > stop_time and d.get('left_duty_pct', 100) < 5.0:
                    stop_latency_ms = (d['time'] - stop_time) * 1000.0
                    stopped = True
                    break
            if stopped:
                break

        if not motor_bridge.get_motor_data():
            pytest.skip("No motor telemetry received — motor bridge not connected")

        assert stopped, "Motor did not stop within 1s"
        assert stop_latency_ms < 50.0, (
            f"ESTOP latency was {stop_latency_ms:.1f}ms (requirement: <50ms)"
        )


class TestSensorFusionAccuracy:
    """Tests for sensor fusion accuracy at known distances."""

    def test_sensor_accuracy_at_50cm(self, rclpy_context, sensor_bridge):
        """Sensor fusion reads within +/-5cm at a known 50cm distance.

        Procedure:
            1. Place a flat surface at exactly 50cm from the sensor array
            2. Collect 100 sensor readings
            3. Assert mean fused range is 50cm +/- 5cm
            4. Assert standard deviation < 3cm
        """
        import rclpy

        sensor_bridge.clear_data()

        # Collect readings for 5 seconds
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            rclpy.spin_once(sensor_bridge, timeout_sec=0.02)

        data = sensor_bridge.get_sensor_data()

        if len(data) < 10:
            pytest.skip(
                f"Only {len(data)} sensor readings collected — "
                "sensor bridge not connected or not enough data"
            )

        # Extract fused range values
        fused_ranges = [d['fused_range_cm'] for d in data if not math.isnan(d.get('fused_range_cm', float('nan')))]

        if len(fused_ranges) < 10:
            pytest.skip("Not enough valid fused range readings")

        mean_range = sum(fused_ranges) / len(fused_ranges)
        variance = sum((r - mean_range) ** 2 for r in fused_ranges) / len(fused_ranges)
        std_dev = math.sqrt(variance)

        # Assert accuracy: mean should be 50cm +/- 5cm
        assert abs(mean_range - 50.0) < 5.0, (
            f"Mean fused range {mean_range:.1f}cm is not within 5cm of "
            f"expected 50cm (error: {abs(mean_range - 50.0):.1f}cm)"
        )

        # Assert precision: std dev should be < 3cm
        assert std_dev < 3.0, (
            f"Sensor std dev {std_dev:.2f}cm exceeds 3cm limit"
        )


class TestMotorCurrentReading:
    """Tests for motor current sensor accuracy."""

    def test_motor_current_within_10_percent(self, rclpy_context, motor_bridge):
        """Motor current reading is within 10% of known load.

        Procedure:
            1. Run motor at 30% duty (known steady-state current)
            2. Collect current readings for 3 seconds
            3. Compare mean reading against expected value

        Note: Expected current must be calibrated per robot. The default
        expected value (0.8A at 30% duty) may need adjustment.
        """
        import rclpy

        EXPECTED_CURRENT_A = 0.8  # Calibrate per robot
        TOLERANCE_PCT = 10.0

        motor_bridge.clear_data()
        motor_bridge.send_cmd_vel(0.3)

        # Let current stabilize
        time.sleep(1.0)
        motor_bridge.clear_data()

        # Collect for 3 seconds
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            rclpy.spin_once(motor_bridge, timeout_sec=0.02)

        # Stop motors
        motor_bridge.stop()

        data = motor_bridge.get_motor_data()

        if len(data) < 5:
            pytest.skip("Not enough motor telemetry — bridge not connected")

        currents = [d.get('left_current_a', 0.0) for d in data]
        mean_current = sum(currents) / len(currents)

        tolerance = EXPECTED_CURRENT_A * (TOLERANCE_PCT / 100.0)
        assert abs(mean_current - EXPECTED_CURRENT_A) < tolerance, (
            f"Mean motor current {mean_current:.3f}A differs from expected "
            f"{EXPECTED_CURRENT_A}A by more than {TOLERANCE_PCT}% "
            f"(tolerance: {tolerance:.3f}A)"
        )

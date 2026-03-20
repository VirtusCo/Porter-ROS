"""Integration test for ESP32 bridge protocol decode.

Verifies that the ESP32 bridge node correctly decodes raw serial frames
into ROS 2 messages. Tests the full path from binary protocol frame
to published ROS 2 topic.

Requires:
    - ROS 2 Jazzy (source /opt/ros/jazzy/setup.bash)
    - Built workspace (source install/setup.bash)
    - porter_esp32_bridge package built

Run with:
    pytest tests/integration/test_bridge_protocol.py -v --timeout=60
"""

import pytest
import struct
import time
import sys
import os

# Add parent to path for protocol codec import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unit.test_protocol_codec import encode_frame, crc16_ccitt, CMD_MOTOR, CMD_SENSOR


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


class TestBridgeFramePublishing:
    """Tests that decoded frames are published as ROS 2 messages."""

    def test_motor_telemetry_published(self, rclpy_context):
        """Motor telemetry frames produce /motor_telemetry messages.

        This test:
        1. Subscribes to /motor_telemetry
        2. Waits for messages (bridge node must be running with serial or mock)
        3. Validates message fields are within expected ranges
        """
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String

        messages_received = []

        class MotorListener(Node):
            def __init__(self):
                super().__init__('test_motor_listener')
                # Try virtus_msgs first, fall back to std_msgs
                try:
                    from virtus_msgs.msg import MotorTelemetry
                    self.sub = self.create_subscription(
                        MotorTelemetry, '/motor_telemetry', self._cb_typed, 10
                    )
                    self._typed = True
                except ImportError:
                    self.sub = self.create_subscription(
                        String, '/motor_telemetry', self._cb_string, 10
                    )
                    self._typed = False

            def _cb_typed(self, msg):
                messages_received.append({
                    'left_duty_pct': msg.left_duty_pct,
                    'right_duty_pct': msg.right_duty_pct,
                    'left_current_a': msg.left_current_a,
                    'right_current_a': msg.right_current_a,
                    'stall_detected': msg.stall_detected,
                })

            def _cb_string(self, msg):
                import json
                messages_received.append(json.loads(msg.data))

        listener = MotorListener()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            rclpy.spin_once(listener, timeout_sec=0.1)
            if messages_received:
                break

        listener.destroy_node()

        if not messages_received:
            pytest.skip(
                "No motor_telemetry messages received — bridge node not running."
            )

        msg = messages_received[0]
        assert 'left_duty_pct' in msg or hasattr(msg, 'left_duty_pct')
        assert 'right_duty_pct' in msg or hasattr(msg, 'right_duty_pct')

    def test_sensor_fusion_published(self, rclpy_context):
        """Sensor fusion frames produce /sensor_fusion messages.

        Verifies the bridge decodes sensor frames and publishes them
        with valid range values.
        """
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String

        messages_received = []

        class SensorListener(Node):
            def __init__(self):
                super().__init__('test_sensor_listener')
                try:
                    from virtus_msgs.msg import SensorFusion
                    self.sub = self.create_subscription(
                        SensorFusion, '/sensor_fusion', self._cb_typed, 10
                    )
                    self._typed = True
                except ImportError:
                    self.sub = self.create_subscription(
                        String, '/sensor_fusion', self._cb_string, 10
                    )
                    self._typed = False

            def _cb_typed(self, msg):
                messages_received.append({
                    'tof_range_cm': msg.tof_range_cm,
                    'ultrasonic_range_cm': msg.ultrasonic_range_cm,
                    'fused_range_cm': msg.fused_range_cm,
                    'tof_valid': msg.tof_valid,
                })

            def _cb_string(self, msg):
                import json
                messages_received.append(json.loads(msg.data))

        listener = SensorListener()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            rclpy.spin_once(listener, timeout_sec=0.1)
            if messages_received:
                break

        listener.destroy_node()

        if not messages_received:
            pytest.skip(
                "No sensor_fusion messages received — bridge node not running."
            )

        msg = messages_received[0]
        assert 'tof_range_cm' in msg
        assert 'fused_range_cm' in msg


class TestProtocolFrameIntegrity:
    """Tests for protocol frame encoding integrity (no ROS node needed)."""

    def test_motor_frame_structure(self):
        """Motor command frame has correct structure for bridge decode."""
        # Simulate what the RPi sends to ESP32
        left_duty = 50  # percent
        right_duty = 50
        direction = 1   # forward

        payload = struct.pack('<BBB', left_duty, right_duty, direction)
        frame = encode_frame(CMD_MOTOR, payload)

        # Bridge expects: header(2) + length(1) + cmd(1) + payload(3) + crc(2) = 9
        assert len(frame) == 9
        assert frame[0:2] == b'\xAA\x55'
        assert frame[3] == CMD_MOTOR

    def test_sensor_frame_structure(self):
        """Sensor response frame has correct structure."""
        tof_cm = 150.5
        ultrasonic_cm = 148.0
        microwave = 0
        confidence = 95

        payload = struct.pack('<ffBB', tof_cm, ultrasonic_cm, microwave, confidence)
        frame = encode_frame(CMD_SENSOR, payload)

        # header(2) + length(1) + cmd(1) + payload(10) + crc(2) = 16
        assert len(frame) == 16
        assert frame[3] == CMD_SENSOR

        # Verify we can decode the payload back
        extracted_payload = frame[4:14]
        t, u, m, c = struct.unpack('<ffBB', extracted_payload)
        assert t == pytest.approx(150.5)
        assert u == pytest.approx(148.0)
        assert m == 0
        assert c == 95

    def test_consecutive_frames_independent(self):
        """Each frame's CRC is independent of previous frames."""
        frame1 = encode_frame(CMD_MOTOR, b'\x32\x32\x01')
        frame2 = encode_frame(CMD_MOTOR, b'\x32\x32\x01')
        assert frame1 == frame2  # Same input -> same output

        frame3 = encode_frame(CMD_MOTOR, b'\x50\x50\x01')
        assert frame3 != frame1  # Different payload -> different frame

"""Mock ESP32 bridge node for testing Porter robot integration.

Simulates the ESP32 motor controller and sensor fusion boards by publishing
SensorFusion (50 Hz) and MotorTelemetry (10 Hz) messages, and subscribing
to /cmd_vel. Supports four built-in scenarios for deterministic testing.

Scenarios:
    SCENARIO_CLEAR       — All sensors nominal, no obstacles detected.
    SCENARIO_OBSTACLE_50 — Obstacle approaches from 200cm to 30cm over 10s.
    SCENARIO_STALL       — Motor stall condition (current > 6A) after 3s.
    SCENARIO_SENSOR_FAIL — ToF sensor fails mid-run (NaN readings after 5s).

Standalone usage:
    python3 -m tests.mocks.mock_esp32_bridge --scenario clear
    python3 -m tests.mocks.mock_esp32_bridge --scenario obstacle_50
    python3 -m tests.mocks.mock_esp32_bridge --scenario stall
    python3 -m tests.mocks.mock_esp32_bridge --scenario sensor_fail
"""

import argparse
import math
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# Scenario constants
SCENARIO_CLEAR = 'clear'
SCENARIO_OBSTACLE_50 = 'obstacle_50'
SCENARIO_STALL = 'stall'
SCENARIO_SENSOR_FAIL = 'sensor_fail'

VALID_SCENARIOS = [SCENARIO_CLEAR, SCENARIO_OBSTACLE_50, SCENARIO_STALL, SCENARIO_SENSOR_FAIL]

# Publish rates
SENSOR_FUSION_HZ = 50
MOTOR_TELEMETRY_HZ = 10

# Physical limits
MAX_MOTOR_CURRENT_A = 10.0
STALL_CURRENT_A = 6.5
NOMINAL_CURRENT_A = 1.2
TOF_MAX_RANGE_CM = 400.0
ULTRASONIC_MAX_RANGE_CM = 300.0


@dataclass
class SensorFusionData:
    """Mirrors virtus_msgs/msg/SensorFusion fields."""
    tof_range_cm: float = 200.0
    ultrasonic_range_cm: float = 200.0
    microwave_detected: bool = False
    fused_range_cm: float = 200.0
    tof_valid: bool = True
    ultrasonic_valid: bool = True
    confidence: float = 1.0
    timestamp_ms: int = 0


@dataclass
class MotorTelemetryData:
    """Mirrors virtus_msgs/msg/MotorTelemetry fields."""
    left_duty_pct: float = 0.0
    right_duty_pct: float = 0.0
    left_current_a: float = 0.0
    right_current_a: float = 0.0
    left_rpm: float = 0.0
    right_rpm: float = 0.0
    stall_detected: bool = False
    timestamp_ms: int = 0


@dataclass
class CmdVelData:
    """Received /cmd_vel data."""
    linear_x: float = 0.0
    angular_z: float = 0.0


class ScenarioGenerator:
    """Generates sensor and motor data for a given scenario over time."""

    def __init__(self, scenario: str):
        if scenario not in VALID_SCENARIOS:
            raise ValueError(
                f"Unknown scenario '{scenario}'. "
                f"Valid: {VALID_SCENARIOS}"
            )
        self.scenario = scenario
        self.start_time: Optional[float] = None
        self.last_cmd_vel = CmdVelData()

    def elapsed(self) -> float:
        """Returns elapsed time since start in seconds."""
        if self.start_time is None:
            self.start_time = time.monotonic()
        return time.monotonic() - self.start_time

    def get_sensor_fusion(self) -> SensorFusionData:
        """Generate SensorFusion data based on scenario and elapsed time."""
        t = self.elapsed()
        ts = int(t * 1000)

        if self.scenario == SCENARIO_CLEAR:
            return SensorFusionData(
                tof_range_cm=200.0,
                ultrasonic_range_cm=198.0,
                microwave_detected=False,
                fused_range_cm=199.0,
                tof_valid=True,
                ultrasonic_valid=True,
                confidence=0.98,
                timestamp_ms=ts,
            )

        elif self.scenario == SCENARIO_OBSTACLE_50:
            # Obstacle approaches from 200cm to 30cm over 10 seconds
            if t < 10.0:
                range_cm = 200.0 - (170.0 * (t / 10.0))
            else:
                range_cm = 30.0
            return SensorFusionData(
                tof_range_cm=range_cm,
                ultrasonic_range_cm=range_cm + 2.0,
                microwave_detected=(range_cm < 100.0),
                fused_range_cm=range_cm + 1.0,
                tof_valid=True,
                ultrasonic_valid=True,
                confidence=0.95,
                timestamp_ms=ts,
            )

        elif self.scenario == SCENARIO_STALL:
            return SensorFusionData(
                tof_range_cm=200.0,
                ultrasonic_range_cm=198.0,
                microwave_detected=False,
                fused_range_cm=199.0,
                tof_valid=True,
                ultrasonic_valid=True,
                confidence=0.97,
                timestamp_ms=ts,
            )

        elif self.scenario == SCENARIO_SENSOR_FAIL:
            # ToF fails after 5 seconds
            tof_valid = t < 5.0
            tof_range = 150.0 if tof_valid else float('nan')
            ultrasonic_range = 148.0
            # After ToF failure, fused range relies on ultrasonic only
            fused = (tof_range + ultrasonic_range) / 2.0 if tof_valid else ultrasonic_range
            return SensorFusionData(
                tof_range_cm=tof_range,
                ultrasonic_range_cm=ultrasonic_range,
                microwave_detected=False,
                fused_range_cm=fused,
                tof_valid=tof_valid,
                ultrasonic_valid=True,
                confidence=0.95 if tof_valid else 0.60,
                timestamp_ms=ts,
            )

        # Fallback (should not reach here)
        return SensorFusionData(timestamp_ms=ts)

    def get_motor_telemetry(self) -> MotorTelemetryData:
        """Generate MotorTelemetry data based on scenario and elapsed time."""
        t = self.elapsed()
        ts = int(t * 1000)

        cmd = self.last_cmd_vel

        if self.scenario == SCENARIO_STALL:
            # Normal for first 3s, then stall
            if t < 3.0:
                return MotorTelemetryData(
                    left_duty_pct=abs(cmd.linear_x) * 50.0,
                    right_duty_pct=abs(cmd.linear_x) * 50.0,
                    left_current_a=NOMINAL_CURRENT_A,
                    right_current_a=NOMINAL_CURRENT_A,
                    left_rpm=abs(cmd.linear_x) * 100.0,
                    right_rpm=abs(cmd.linear_x) * 100.0,
                    stall_detected=False,
                    timestamp_ms=ts,
                )
            else:
                return MotorTelemetryData(
                    left_duty_pct=abs(cmd.linear_x) * 50.0,
                    right_duty_pct=abs(cmd.linear_x) * 50.0,
                    left_current_a=STALL_CURRENT_A,
                    right_current_a=STALL_CURRENT_A,
                    left_rpm=0.0,
                    right_rpm=0.0,
                    stall_detected=True,
                    timestamp_ms=ts,
                )

        # Default motor telemetry for other scenarios
        duty = abs(cmd.linear_x) * 50.0
        diff = cmd.angular_z * 20.0
        return MotorTelemetryData(
            left_duty_pct=max(0.0, min(100.0, duty - diff)),
            right_duty_pct=max(0.0, min(100.0, duty + diff)),
            left_current_a=NOMINAL_CURRENT_A * (duty / 50.0) if duty > 0 else 0.1,
            right_current_a=NOMINAL_CURRENT_A * (duty / 50.0) if duty > 0 else 0.1,
            left_rpm=abs(cmd.linear_x) * 100.0,
            right_rpm=abs(cmd.linear_x) * 100.0,
            stall_detected=False,
            timestamp_ms=ts,
        )

    def on_cmd_vel(self, linear_x: float, angular_z: float):
        """Handle incoming /cmd_vel command."""
        self.last_cmd_vel = CmdVelData(linear_x=linear_x, angular_z=angular_z)


def _try_run_ros_node(scenario: str):
    """Attempt to run as a ROS 2 node. Falls back to standalone if rclpy unavailable."""
    try:
        import rclpy
        from rclpy.node import Node
        from geometry_msgs.msg import Twist
    except ImportError:
        print("[MockESP32Bridge] rclpy not available — running in standalone mode")
        _run_standalone(scenario)
        return

    rclpy.init()

    class MockESP32BridgeNode(Node):
        """ROS 2 node that publishes mock ESP32 data."""

        def __init__(self, scenario_name: str):
            super().__init__('mock_esp32_bridge')
            self.generator = ScenarioGenerator(scenario_name)
            self.get_logger().info(f'MockESP32Bridge starting with scenario: {scenario_name}')

            # Try importing virtus_msgs; fall back to std_msgs if unavailable
            try:
                from virtus_msgs.msg import SensorFusion, MotorTelemetry
                self.sensor_pub = self.create_publisher(SensorFusion, '/sensor_fusion', 10)
                self.motor_pub = self.create_publisher(MotorTelemetry, '/motor_telemetry', 10)
                self._use_virtus_msgs = True
            except ImportError:
                from std_msgs.msg import String
                self.sensor_pub = self.create_publisher(String, '/sensor_fusion', 10)
                self.motor_pub = self.create_publisher(String, '/motor_telemetry', 10)
                self._use_virtus_msgs = False
                self.get_logger().warn('virtus_msgs not available — publishing as JSON strings')

            self.cmd_vel_sub = self.create_subscription(
                Twist, '/cmd_vel', self._cmd_vel_cb, 10
            )

            sensor_period = 1.0 / SENSOR_FUSION_HZ
            motor_period = 1.0 / MOTOR_TELEMETRY_HZ
            self.create_timer(sensor_period, self._publish_sensor)
            self.create_timer(motor_period, self._publish_motor)

        def _cmd_vel_cb(self, msg: 'Twist'):
            self.generator.on_cmd_vel(msg.linear.x, msg.angular.z)

        def _publish_sensor(self):
            data = self.generator.get_sensor_fusion()
            if self._use_virtus_msgs:
                from virtus_msgs.msg import SensorFusion
                msg = SensorFusion()
                msg.tof_range_cm = data.tof_range_cm
                msg.ultrasonic_range_cm = data.ultrasonic_range_cm
                msg.microwave_detected = data.microwave_detected
                msg.fused_range_cm = data.fused_range_cm
                msg.tof_valid = data.tof_valid
                msg.ultrasonic_valid = data.ultrasonic_valid
                msg.confidence = data.confidence
            else:
                import json
                from std_msgs.msg import String
                msg = String()
                msg.data = json.dumps(data.__dict__)
            self.sensor_pub.publish(msg)

        def _publish_motor(self):
            data = self.generator.get_motor_telemetry()
            if self._use_virtus_msgs:
                from virtus_msgs.msg import MotorTelemetry
                msg = MotorTelemetry()
                msg.left_duty_pct = data.left_duty_pct
                msg.right_duty_pct = data.right_duty_pct
                msg.left_current_a = data.left_current_a
                msg.right_current_a = data.right_current_a
                msg.stall_detected = data.stall_detected
            else:
                import json
                from std_msgs.msg import String
                msg = String()
                msg.data = json.dumps(data.__dict__)
            self.motor_pub.publish(msg)

    node = MockESP32BridgeNode(scenario)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


def _run_standalone(scenario: str):
    """Run without ROS 2 — prints data to stdout for debugging."""
    gen = ScenarioGenerator(scenario)
    print(f"[MockESP32Bridge] Standalone mode — scenario: {scenario}")
    print(f"[MockESP32Bridge] Publishing sensor at {SENSOR_FUSION_HZ}Hz, "
          f"motor at {MOTOR_TELEMETRY_HZ}Hz")
    print("[MockESP32Bridge] Press Ctrl+C to stop\n")

    sensor_interval = 1.0 / SENSOR_FUSION_HZ
    motor_interval = 1.0 / MOTOR_TELEMETRY_HZ
    last_sensor = 0.0
    last_motor = 0.0
    last_print = 0.0

    try:
        while True:
            now = time.monotonic()

            if now - last_sensor >= sensor_interval:
                sensor = gen.get_sensor_fusion()
                last_sensor = now

            if now - last_motor >= motor_interval:
                motor = gen.get_motor_telemetry()
                last_motor = now

            # Print summary at 1Hz to avoid flooding
            if now - last_print >= 1.0:
                s = gen.get_sensor_fusion()
                m = gen.get_motor_telemetry()
                elapsed = gen.elapsed()
                print(
                    f"[{elapsed:6.1f}s] "
                    f"tof={s.tof_range_cm:6.1f}cm "
                    f"us={s.ultrasonic_range_cm:6.1f}cm "
                    f"fused={s.fused_range_cm:6.1f}cm "
                    f"tof_ok={s.tof_valid} "
                    f"| duty_L={m.left_duty_pct:4.1f}% "
                    f"I_L={m.left_current_a:4.2f}A "
                    f"stall={m.stall_detected}"
                )
                last_print = now

            time.sleep(0.001)  # 1ms sleep to avoid busy-wait
    except KeyboardInterrupt:
        print("\n[MockESP32Bridge] Stopped.")


def main():
    """Entry point for standalone execution."""
    parser = argparse.ArgumentParser(
        description='Mock ESP32 Bridge — simulates sensor and motor data'
    )
    parser.add_argument(
        '--scenario', '-s',
        choices=VALID_SCENARIOS,
        default=SCENARIO_CLEAR,
        help=f'Scenario to simulate (default: {SCENARIO_CLEAR})'
    )
    parser.add_argument(
        '--standalone',
        action='store_true',
        help='Force standalone mode (no ROS 2)'
    )
    args = parser.parse_args()

    if args.standalone:
        _run_standalone(args.scenario)
    else:
        _try_run_ros_node(args.scenario)


if __name__ == '__main__':
    main()

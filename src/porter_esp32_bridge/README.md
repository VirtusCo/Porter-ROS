# Porter ESP32 Bridge

ROS 2 Jazzy bridge nodes for communicating with ESP32 microcontrollers over USB serial using the Porter binary protocol.

## Nodes

### `esp32_motor_bridge`

Bridges ROS 2 `/cmd_vel` (Twist) to ESP32 #1 motor controller.

- **Subscribes:** `/cmd_vel` (`geometry_msgs/Twist`)
- **Publishes:** `/motor_status` (`std_msgs/String`), `/diagnostics`
- Converts `(linear.x, angular.z)` → differential drive `(left_speed, right_speed)`
- Sends periodic heartbeat to ESP32; ESP32 stops motors if heartbeat lost
- Watchdog: stops motors if no `/cmd_vel` for `cmd_vel_timeout` seconds

### `esp32_sensor_bridge`

Bridges ESP32 #2 fused sensor data to ROS 2.

- **Publishes:** `/environment` (`sensor_msgs/Range`), `/sensor_status` (`std_msgs/String`), `/diagnostics`
- Receives fused obstacle distance (ToF + Ultrasonic + Microwave Kalman filter)
- Polls ESP32 for per-sensor health status

## Parameters

See `config/esp32_bridge_params.yaml` for all parameters with descriptions.

## Protocol

Uses the Porter binary protocol (`esp32_firmware/common/`):
- Wire format: `[0xAA 0x55][Length][Command][Payload...][CRC16]`
- CRC16-CCITT (poly 0x1021, init 0xFFFF)
- Shared C library linked into both the ESP32 firmware and this ROS 2 package

## Launch

```bash
ros2 launch porter_esp32_bridge esp32_bridge_launch.py
ros2 launch porter_esp32_bridge esp32_bridge_launch.py motor_port:=/dev/ttyUSB0 sensor_port:=/dev/ttyUSB1
```

## Prerequisites

- ESP32 devices connected via USB serial
- udev rules installed for stable device names (see `esp32_firmware/udev/`)

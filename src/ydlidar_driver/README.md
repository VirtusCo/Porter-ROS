# YDLIDAR Driver — Porter Robot

Production-grade ROS 2 Jazzy driver for YDLIDAR sensors. Designed for the
[Porter Robot](https://github.com/austin207/Porter-ROS) autonomous luggage
carrier by [VirtusCo](https://virtusco.in).

## Features

- **Model-agnostic** — supports X4 Pro, S2 Pro, G4, G2, Tmini, TG series,
  and more. Change LIDAR model via YAML config only — zero code changes.
- **Production-grade health monitoring** — sliding-window diagnostics on
  `/diagnostics` with scan frequency, invalid point ratio, and failure tracking.
- **Auto-reconnect** — exponential backoff retry on init failure, automatic
  reconnection on sustained scan failures.
- **Sensor Data QoS** — uses `rclcpp::SensorDataQoS()` for `/scan` publisher,
  compatible with Nav2 and slam_toolbox out of the box.
- **Clean shutdown** — graceful stop of scan motor and serial disconnect.

## Supported Hardware

| Model | Type | Baudrate | Tested |
|-------|------|----------|--------|
| **YDLIDAR X4 Pro 360°** | Triangle | 128000 | ✅ Primary target |
| YDLIDAR S2 Pro | Triangle | 115200 | Config only |
| YDLIDAR G4 | Triangle | 230400 | Config only |
| YDLIDAR X2/X2L | Triangle | 115200 | Config only |
| YDLIDAR TG series | ToF | 512000 | Config only |

## Prerequisites

- **ROS 2 Jazzy** (Ubuntu 24.04)
- **YDLidar SDK** installed system-wide:

```bash
cd YDLidar-SDK
mkdir -p build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

## Quick Start

### Build

```bash
cd porter_robot
source /opt/ros/jazzy/setup.bash
colcon build --packages-select ydlidar_driver --symlink-install
source install/setup.bash
```

### Run

```bash
# With default config (X4 Pro on /dev/ttyUSB0)
ros2 launch ydlidar_driver ydlidar_launch.py

# Override port
ros2 launch ydlidar_driver ydlidar_launch.py port:=/dev/ttyUSB1

# Direct run with parameter overrides
ros2 run ydlidar_driver ydlidar_node --ros-args \
  -p port:=/dev/ttyUSB0 \
  -p baudrate:=128000 \
  -p frame_id:=laser_frame
```

### Verify

```bash
ros2 topic echo /scan             # View scan data
ros2 topic hz /scan               # Check scan rate
ros2 topic echo /diagnostics      # View health status
ros2 param dump /ydlidar_node     # Dump all parameters
```

## Parameters

See [config/ydlidar_params.yaml](config/ydlidar_params.yaml) for full
documentation. Key parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `port` | string | `/dev/ttyUSB0` | Serial device path |
| `baudrate` | int | `128000` | Serial baudrate |
| `frame_id` | string | `laser_frame` | TF frame ID |
| `frequency` | double | `10.0` | Target scan frequency (Hz) |
| `angle_min` | double | `-180.0` | Minimum scan angle (degrees) |
| `angle_max` | double | `180.0` | Maximum scan angle (degrees) |
| `min_range` | double | `0.01` | Minimum valid range (metres) |
| `max_range` | double | `12.0` | Maximum valid range (metres) |
| `lidar_type` | int | `1` | 0=ToF, 1=Triangle, 3=GS |
| `auto_reconnect` | bool | `true` | Auto-reconnect on failure |

## Topics

| Topic | Type | QoS | Description |
|-------|------|-----|-------------|
| `/scan` | `sensor_msgs/LaserScan` | SensorData | 360° laser scan |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | Default | Health status (1 Hz) |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   ydlidar_node                           │
│                                                          │
│  ┌──────────────┐   ┌───────────────┐                   │
│  │  SdkAdapter   │   │ HealthMonitor │                   │
│  │               │   │               │                   │
│  │ • initialize()│   │ • record_scan │ ──► /diagnostics  │
│  │ • start_scan()│   │ • record_fail │                   │
│  │ • read_scan() │   │ • get_health  │                   │
│  │ • disconnect()│   │ • should_     │                   │
│  │               │   │   reconnect   │                   │
│  └──────┬───────┘   └───────────────┘                   │
│         │                                                │
│         ▼                                                │
│  ┌──────────────┐                                        │
│  │  CYdLidar    │  (YDLidar SDK)                         │
│  │  (SDK)       │                                        │
│  └──────┬───────┘                                        │
│         │                                                │
│         ▼ serial                                         │
│    /dev/ttyUSB0  ──────────────────────► /scan           │
└─────────────────────────────────────────────────────────┘
```

## Changing LIDAR Model

To switch from X4 Pro to another model, edit
`config/ydlidar_params.yaml`:

```yaml
# Example: Switch to YDLIDAR G4
ydlidar_node:
  ros__parameters:
    baudrate: 230400
    lidar_type: 1        # Still TYPE_TRIANGLE
    intensity: true      # G4 supports intensity
    max_range: 16.0      # G4 range is 16m
    samp_rate: 9         # G4 sample rate
```

No recompilation needed — just change the YAML and relaunch.

## Known Issues

| Issue | Detail | Mitigation |
|-------|--------|------------|
| Missing baseplate info | Some units don't report baseplate reliably | Treated as non-fatal |
| SDK health code `ffffffff` | Occurs with some firmware versions | 3-retry with exponential backoff |
| DTR motor control | Some OS/USB adapters don't support DTR | Set `support_motor_dtr_ctrl: false` |

## License

Apache License 2.0 — see [LICENSE](../../LICENSE).

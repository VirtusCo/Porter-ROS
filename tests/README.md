# Virtus Test Infrastructure (VTI)

Three-layer test framework for the Porter robot ROS 2 stack.

## Three-Layer Architecture

| Layer | What | Runtime | Trigger |
|-------|------|---------|---------|
| Unit | Pure Python/C logic tests | ~90s | Every push |
| Integration | ROS 2 nodes with mock bridge | ~3min | Every push |
| System | Gazebo headless full stack | ~10min | PR to main |

## Directory Structure

```
tests/
├── conftest.py              # Shared pytest fixtures
├── unit/                    # Pure Python tests (no ROS 2 needed)
│   ├── test_fsm_transitions.py     # 14-transition FSM validation
│   ├── test_protocol_codec.py      # CRC16 + frame encode/decode
│   ├── test_kalman_filter.py       # Sensor fusion Kalman filter
│   └── test_lidar_filters.py       # LIDAR pipeline filters
├── integration/             # ROS 2 node tests with mock hardware
│   ├── test_orchestrator_integration.py  # FSM with mock bridge
│   ├── test_bridge_protocol.py           # Protocol decode to topics
│   └── test_bag_replay.py               # Bag replay test runner
├── system/                  # Full-stack Gazebo simulation tests
│   └── test_navigation_scenarios.py      # Nav2 + Gazebo headless
├── hil/                     # Hardware-in-the-loop (physical robot)
│   ├── conftest.py                  # --hil flag configuration
│   └── test_motor_response.py       # Motor/sensor hardware tests
├── mocks/                   # Mock nodes for testing
│   ├── __init__.py
│   └── mock_esp32_bridge.py         # 4-scenario mock ESP32 bridge
├── scenarios/               # Reusable test scenario definitions
│   └── __init__.py                  # TestScenario + 4 standard scenarios
└── bags/                    # Test bag files (.mcap)
    └── .gitkeep
```

## Running Tests

```bash
# Unit tests (no ROS 2 needed)
pytest tests/unit/ -v

# Integration tests (needs colcon build)
source /opt/ros/jazzy/setup.bash && source install/setup.bash
pytest tests/integration/ -v

# System tests (needs Gazebo)
pytest tests/system/ -v --timeout=120

# Hardware-in-the-loop (needs physical robot)
pytest tests/hil/ --hil -v

# All tests with coverage
pytest tests/ -v --cov=src/ --cov-report=html
```

## Mock ESP32 Bridge

The mock bridge simulates ESP32 sensor and motor boards for testing without hardware.

```bash
# Run as ROS 2 node (if rclpy available)
python3 -m tests.mocks.mock_esp32_bridge --scenario clear

# Run standalone (no ROS 2 needed, prints to stdout)
python3 -m tests.mocks.mock_esp32_bridge --scenario obstacle_50 --standalone
```

### Available Scenarios

| Scenario | Description |
|----------|-------------|
| `clear` | All sensors nominal, no obstacles |
| `obstacle_50` | Obstacle approaches from 200cm to 30cm over 10s |
| `stall` | Motor stall (>6A current) after 3s |
| `sensor_fail` | ToF sensor fails after 5s, ultrasonic continues |

## Test Scenarios

See `tests/scenarios/__init__.py` for reusable test scenario definitions used across
integration and system tests. Four standard scenarios are defined:

- **nominal_idle** — Robot in IDLE with healthy sensors
- **obstacle_recovery** — Obstacle approach, avoidance, resume
- **sensor_degradation** — ToF failure with ultrasonic fallback
- **motor_stall** — Motor stall detection and safe stop

## HIL Tests

Hardware-in-the-loop tests require the physical Porter robot. They are skipped
by default in CI and local runs. Pass `--hil` to pytest to enable them:

```bash
pytest tests/hil/ --hil -v
```

HIL tests verify:
- Motor ramp response time (<200ms from 0 to 80%)
- ESTOP latency (<50ms)
- Sensor fusion accuracy at known distances (50cm +/-5cm)
- Motor current reading accuracy (within 10% of calibrated value)

## CI Integration

The test suite runs in GitHub Actions via `.github/workflows/test.yml`:

1. **Unit tests** run on every push (ubuntu-latest, Python 3.12)
2. **Firmware Ztests** run on every push (Zephyr CI container)
3. **Integration tests** run after unit tests pass (ros:jazzy container)
4. **System tests** run only on PRs to main (osrf/ros:jazzy-desktop)

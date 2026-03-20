# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Porter Robot is an autonomous luggage-carrying robot for airports, built by VirtusCo. It navigates airport terminals using LIDAR, carries passenger luggage, and provides an on-device AI assistant ("Virtue") for passenger interaction. Everything runs locally on a Raspberry Pi 5 with no cloud dependency.

**Repo**: `github.com/austin207/porter-ros` | **Branches**: `prototype` (active development), `main` (stable) | **License**: Apache 2.0 (ydlidar_driver), Proprietary (everything else)

## Repository Structure

```
porter-ros/
├── src/                          # ROS 2 packages
│   ├── ydlidar_driver/           # C++17 — LIDAR driver, /scan + /diagnostics
│   ├── porter_lidar_processor/   # Python — 6-stage scan filter pipeline
│   ├── porter_orchestrator/      # Python — 9-state FSM + health monitor
│   ├── porter_esp32_bridge/      # C++17 — Motor + sensor serial bridges
│   ├── porter_ai_assistant/      # Python — Qwen 2.5 1.5B GGUF + LoRA, 14 tools, RAG
│   ├── porter_gui/               # Dart/Flutter — Touchscreen UI with SSE streaming
│   └── virtus_msgs/              # VDL — Custom message/service definitions
├── esp32_firmware/               # Zephyr RTOS firmware
│   ├── common/                   # Shared binary protocol (CRC16-CCITT, parser, HAL)
│   ├── motor_controller/         # SMF state machine, PWM, watchdog, differential drive
│   ├── sensor_fusion/            # Kalman filter, cross-validation, fallback logic
│   └── tests/                    # 178 Ztest cases on native_sim
├── tests/                        # Python unit/integration tests (no ROS 2 needed)
├── docker/                       # Docker compose + Dockerfiles
├── config/                       # ROS 2 parameter YAML files
├── launch/                       # ROS 2 launch files
└── skills/                       # Reference files: 16 ROS 2 + 12 Zephyr
```

## Build & Test Commands

### Docker Workflow (Primary)

```bash
# Build and start dev container (run from repo root, NOT from docker/)
docker compose -f docker/docker-compose.dev.yml build
docker compose -f docker/docker-compose.dev.yml up -d
docker exec -it porter_dev bash

# Inside container — full build
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --cmake-args -Wno-dev
source install/setup.bash

# Run all tests
colcon test --event-handlers console_direct+
colcon test-result --verbose

# Build/test a single package
colcon build --packages-select ydlidar_driver --symlink-install
colcon test --packages-select ydlidar_driver

# Clean rebuild
rm -rf build/ install/ log/
colcon build --cmake-clean-cache --symlink-install
```

### Unit Tests (No ROS 2 Needed)

```bash
pip install pytest pytest-cov
cd tests && pytest unit/ -v --tb=short
```

### ESP32 Firmware (Zephyr RTOS)

```bash
# Unit tests (native_sim, no hardware)
cd esp32_firmware && twister -T tests/ -p native_sim

# Cross-compile
west build -b esp32_devkitc_wroom esp32_firmware/motor_controller -d build/motor -- -DBOARD_ROOT=.
west build -b esp32_devkitc_wroom esp32_firmware/sensor_fusion -d build/sensor -- -DBOARD_ROOT=.
```

### Flutter GUI

```bash
cd src/porter_gui
flutter analyze
flutter test
flutter build linux --release
```

## Hardware Architecture

```
Raspberry Pi 5 (Master) — ROS 2 Jazzy, Nav2, Virtue AI, Touchscreen
├── YDLIDAR X4 Pro 360° (USB serial, 128000 baud)
├── ESP32 #1 (USB CDC) — Motor controller, BTS7960 H-bridge, differential drive
└── ESP32 #2 (USB CDC) — Sensor fusion: ToF + Ultrasonic + Microwave (Kalman)
```

## ROS 2 Topic Flow

```
YDLIDAR → ydlidar_driver → /scan → porter_lidar_processor → /scan/processed → Nav2
                            └→ /diagnostics → lidar_health_monitor → /porter/health_status → state_machine
Nav2 → /cmd_vel → esp32_motor_bridge → Serial → ESP32 #1
ESP32 #2 → Serial → esp32_sensor_bridge → /environment → Nav2
GUI → /porter/ai_query → porter_ai_assistant → /porter/ai_response → GUI
```

## ROS 2 Packages

| Package | Lang | Build Type | Purpose |
|---------|------|------------|---------|
| `ydlidar_driver` | C++17 | ament_cmake | LIDAR driver, publishes `/scan` + `/diagnostics` |
| `porter_lidar_processor` | Python | ament_python | 6-stage scan filter pipeline |
| `porter_orchestrator` | Python | ament_python | 9-state FSM + health monitor |
| `porter_esp32_bridge` | C++17 | ament_cmake | Motor + sensor serial bridges |
| `porter_ai_assistant` | Python | ament_python | Qwen 2.5 1.5B GGUF + LoRA inference, 14 tools, RAG |
| `porter_gui` | Dart | Flutter | Touchscreen UI with SSE streaming |
| `virtus_msgs` | IDL | ament_cmake | Custom message/service definitions (VDL) |

## AI Assistant ("Virtue")

- **Model**: Qwen 2.5 1.5B Instruct, Q4_K_M GGUF (~1 GB)
- **LoRA adapters**: conversational + tool-use, swapped at runtime (never merged at 4-bit)
- **Runtime**: llama-cpp-python, CPU-only, `n_threads=2` (reserves 2 cores for SLAM/Nav2)
- **RAG**: TF-IDF over 41 airport knowledge base docs (<1ms retrieval)
- **14 tools**: directions, flight status, find nearest, escort, map, assistance, etc.
- **Latency**: P50 ~1.4s, P95 ~1.8s on RPi 5

## ESP32 Wire Protocol

Binary format: `[0xAA 0x55][Length][Command][Payload...][CRC16-CCITT]`

## Critical Rules

### Docker
- **Always run docker compose from repo root**, never from `docker/` -- the build context is `..`
- Use `network_mode: host` for all services (DDS discovery)
- AI service: `cpus: 2.0`, `mem_limit: 2g`, `nice -n 10` to avoid starving SLAM/Nav2

### ROS 2 Jazzy
- All parameters must be typed: `declare_parameter<T>("name", default)` -- untyped fails on Jazzy
- Use `rclcpp::SensorDataQoS().reliable()` for `/scan` (matches RViz2 RELIABLE subscription)
- Never use `print()` in ROS nodes -- use `self.get_logger()` / `RCLCPP_INFO()`
- Never hard-code paths in launch files -- use `get_package_share_directory()`
- Always use `--symlink-install` for dev builds
- Source `install/setup.bash` after every build
- rosdep: `--skip-keys="ament_python"`
- CI shell must be `bash` (not `sh`) -- `ros:jazzy` container defaults to dash

### ESP32 / Zephyr
- Zephyr version pinned at **v4.0.0** -- SMF handlers return `void` (not `enum smf_state_result`)
- Board name: `esp32_devkitc_wroom` (flat name for 4.0.0)
- `COLCON_IGNORE` marker in `esp32_firmware/` prevents colcon from trying to build Zephyr code
- Never mix Zephyr venv and ROS 2 builds in the same shell session

### AI Assistant
- System prompts at inference must be **character-for-character identical** to training data
- `n_threads=2` on RPi (never auto-detect) -- leaves 2 cores for SLAM/Nav2
- `n_ctx=1024` (not 2048) -- saves ~28 MB, sufficient for airport Q&A
- Never merge LoRA on 4-bit model (`merge_and_unload()` degrades weights) -- use runtime loading
- Always call `engine.load_tool_schemas(path)` before first inference

### LIDAR
- `singleChannel: true` for X4/X4 Pro/X2/S2/S4 -- wrong setting causes all commands to timeout
- `health_expected_freq` must match actual scan delivery rate (e.g., 4.0 Hz for S2PRO)
- Never send extra SDK serial commands between `initialize()` and `turnOn()`

## Code Style

- **C++**: C++17, `ament_cpplint`/`ament_uncrustify`, `RCLCPP_*` logging, `//`-style copyright headers
- **Python**: PEP 8/257, max 99 chars, `ament_flake8`/`ament_pep257`, module + class docstrings required
- **Dart/Flutter**: standard Flutter lints

## Git Conventions

- Conventional commits: `<type>(<scope>): <description>`
- Types: `feat`, `fix`, `docs`, `test`, `build`, `ci`, `perf`, `refactor`, `chore`
- Scopes: `ydlidar-driver`, `lidar-processor`, `orchestrator`, `esp32-firmware`, `ai-assistant`, `docker`, `gui`
- Model files tracked via Git LFS (`.gguf`, `.safetensors`, `.pt`, `.onnx`)

## CI/CD

- `ci.yml`: Unit tests, ROS 2 build+test, ESP32 Ztest, Docker build, lint
- All CI jobs use `shell: bash`
- ROS 2 jobs run in `ros:jazzy` container

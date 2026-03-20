# Porter Robot

**Autonomous luggage-carrying robot for airports** — built by [VirtusCo](https://virtusco.in).

Porter Robot autonomously navigates terminals, carries passenger luggage, and avoids obstacles using LIDAR, ToF, ultrasonic, and microwave sensors. An on-device AI assistant (**Virtue**) answers passenger questions, provides directions, checks flight status, and calls for assistance — all running locally on a Raspberry Pi.

Built on ROS 2 Jazzy with a custom YDLIDAR driver, scan processing pipeline, ESP32 motor/sensor firmware (Zephyr RTOS), fine-tuned Gemma 3 270M GGUF model, and a lightweight conversation orchestrator with tool execution.

> **Status:** Phases 1, 3, 4, and 4.5 complete — LIDAR subsystem, ESP32 firmware + bridge, system orchestration, AI assistant with conversation orchestrator.
> Hardware tested with YDLIDAR X4 Pro (S2PRO). 324 tests across all packages.

---

## Quick Start (Docker)

Docker is the primary workflow. Works on any PC with Docker installed — no ROS 2 or SDK setup needed.

```bash
# Clone
git clone https://github.com/austin207/Porter-ROS.git
cd Porter-ROS/porter_robot

# Build (downloads ROS 2 Jazzy image + builds YDLidar SDK + compiles workspace)
docker compose -f docker/docker-compose.dev.yml build

# Start development container
docker compose -f docker/docker-compose.dev.yml up -d
docker exec -it porter_dev bash

# Inside container — ROS 2 is already sourced
colcon test --event-handlers console_direct+    # Run tests
ros2 launch ydlidar_driver ydlidar_launch.py    # Launch driver (needs LIDAR)
```

### Hardware Testing (with LIDAR plugged in)

```bash
# Start with device passthrough
docker compose -f docker/docker-compose.dev.yml --profile hardware up -d
docker exec -it porter_robot_hw bash

# Run driver
ros2 launch ydlidar_driver ydlidar_launch.py port:=/dev/ttyUSB0

# In another terminal
ros2 topic echo /scan           # View scan data
ros2 topic hz /scan             # Check frequency
ros2 topic echo /diagnostics    # Health status
```

### AI Assistant

```bash
# Launch simple assistant (inference only)
ros2 launch porter_ai_assistant assistant_launch.py

# Launch full orchestrator (tool execution + conversation memory, for GUI)
ros2 launch porter_ai_assistant assistant_launch.py use_orchestrator:=true

# Query via topic
ros2 topic pub /porter/ai_query std_msgs/String "data: 'Where is Gate B12?'" --once

# Read response
ros2 topic echo /porter/ai_response
```

### RViz2 Visualization

```bash
# On a machine with display (X11)
xhost +local:docker
docker compose -f docker/docker-compose.dev.yml --profile viz up
```

---

## System Architecture

### Hardware

```
┌──────────────────────────────────────────────────────────────┐
│                    Porter Robot Hardware                     │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │              Raspberry Pi 5 (Master)                │     │
│  │  • ROS 2 Jazzy + Nav2                               │     │
│  │  • YDLIDAR X4 Pro (serial, /dev/ttyUSB0)            │     │
│  │  • Virtue AI (Gemma 3 270M GGUF, 351 MB RSS)        │     │
│  │  • Touchscreen display                              │     │
│  │  • Docker deployment                                │     │
│  └──────┬──────────────────────┬───────────────────────┘     │
│         │ USB CDC Serial       │ USB CDC Serial              │
│  ┌──────▼──────────┐    ┌──────▼──────────┐                  │
│  │  ESP32 #1       │    │  ESP32 #2       │                  │
│  │  Motor Control  │    │  Sensor Fusion  │                  │
│  │  • 2× BTS7960   │    │  • ToF VL53L0x  │                  │
│  │  • Diff drive   │    │  • Ultrasonic   │                  │
│  │  • SMF states   │    │  • Microwave    │                  │
│  │  • Zephyr RTOS  │    │  • Kalman fuse  │                  │
│  └─────────────────┘    │  • Zephyr RTOS  │                  │
│                         └─────────────────┘                  │
└──────────────────────────────────────────────────────────────┘
```

### Software Stack

```
┌──────────────────────────────────────────────────────────────┐
│          Virtue AI Orchestrator                              │  Tool exec + memory
├──────────────────────────────────────────────────────────────┤
│          Virtue AI Assistant                                 │  Gemma 3 270M GGUF + LoRA
├──────────────────────────────────────────────────────────────┤
│          Porter Orchestrator                                 │  9-state FSM, health monitor
├──────────────────────────────────────────────────────────────┤
│          Porter LIDAR Processor                              │  Filtering, smoothing, ROI
├────────────┬────────────────┬────────────────────────────────┤
│ YDLIDAR    │ ESP32 Motor    │ ESP32 Sensor                   │  C++ drivers
│ Driver     │ Bridge         │ Bridge                         │
├────────────┴────────────────┴────────────────────────────────┤
│          Docker + Entrypoint                                 │  Container management
├──────────────────────────────────────────────────────────────┤
│          ROS 2 Jazzy / Ubuntu 24.04 Noble                    │  OS + middleware
└──────────────────────────────────────────────────────────────┘
```

### TF Tree

```
map ──► odom ──► base_link ──► laser_frame
 │        │         │
 │        │         └── (static: URDF)
 │        └── (odometry source: EKF / wheel odom)
 └── (SLAM / localisation)
```

### Topic Flow

```
YDLIDAR ──serial──► ydlidar_driver ──/scan──► porter_lidar_processor ──/scan/processed──► Nav2
                         │
                         └──/diagnostics──► lidar_health_monitor ──/porter/health_status──► state_machine
                                                                                              │
                                                                                     /porter/state

ESP32 #1 ◄──serial──► esp32_motor_bridge ◄──/cmd_vel──► Nav2
                            │
                            └──► /motor_status

ESP32 #2 ──serial──► esp32_sensor_bridge ──/environment──► Nav2
                            │
                            └──► /diagnostics

GUI ──/porter/ai_query──► virtue_orchestrator ──/porter/ai_response──► GUI
                               │
                               └── InferenceEngine + ToolExecutor (14 tools)
```

---

## Packages

### ROS 2 Packages (src/)

| Package | Language | Description |
|---------|----------|-------------|
| [`ydlidar_driver`](src/ydlidar_driver/) | C++17 | Custom YDLIDAR ROS 2 Jazzy driver. Publishes `/scan` + `/diagnostics`. Model-agnostic via YAML config. |
| [`porter_lidar_processor`](src/porter_lidar_processor/) | Python | Scan pipeline: range clamp → outlier reject → median → smoothing → ROI → downsample. Publishes `/scan/processed`. |
| [`porter_orchestrator`](src/orchestration/porter_orchestrator/) | Python | 9-state system FSM + health monitor. Boot sequence, auto-recovery, health evaluation. |
| [`porter_esp32_bridge`](src/porter_esp32_bridge/) | C++17 | Serial bridge to ESP32 motor controller + sensor fusion. `/cmd_vel` ↔ binary protocol. |
| [`porter_ai_assistant`](src/porter_ai_assistant/) | Python | On-device AI assistant (Gemma 3 270M GGUF + LoRA). Conversation orchestrator with 14-tool execution. |

### ESP32 Firmware (esp32_firmware/)

| Directory | Description |
|-----------|-------------|
| [`common/`](esp32_firmware/common/) | Shared protocol (CRC16-CCITT, binary parser/encoder, transport abstraction) |
| [`motor_controller/`](esp32_firmware/motor_controller/) | Zephyr RTOS: BTS7960 PWM, differential drive, SMF state machine, watchdog |
| [`sensor_fusion/`](esp32_firmware/sensor_fusion/) | Zephyr RTOS: ToF + Ultrasonic + Microwave, Kalman filter, cross-validation |
| [`tests/`](esp32_firmware/tests/) | Ztest: CRC16, protocol parser, transport (native_sim) |
| [`udev/`](esp32_firmware/udev/) | Stable device naming rules (`/dev/esp32_motors`, `/dev/esp32_sensors`) |

### Planned Packages

| Package | Description | Status |
|---------|-------------|--------|
| `nav2_config` | Navigation2 parameters | Phase 2 |
| `porter_robot_urdf` | URDF/Xacro robot model | Phase 2 |

---

## AI Assistant (Virtue)

On-device LLM for smart airport passenger assistance. Runs entirely on RPi 4/5 — no cloud required.

| Property | Value |
|----------|-------|
| Model | Google Gemma 3 270M IT (Q4_K_M GGUF, 241 MB) |
| LoRA Adapters | Conversational (7.3 MB) + Tool-use (7.3 MB) — swapped at runtime |
| Runtime | llama-cpp-python on CPU |
| Inference | Conversational: ~497 ms, Tool-use: ~250 ms |
| Memory | 351 MB RSS (model + runtime) |
| Training Data | 12K examples (7K conversational + 5K tool-use) |
| Tools | 14 (directions, flights, amenities, luggage, assistance, escort, maps, etc.) |
| AI Persona | **Virtue** (distinct from "Porter" robot product name) |

### Orchestrator Architecture

```
User Query ──► ConversationOrchestrator
                    │
                    ├── InferenceEngine.classify_query()
                    │       → 'conversational' or 'tool_use'
                    │
                    ├── InferenceEngine.query() with LoRA adapter
                    │       → model response (may contain <tool_call>)
                    │
                    ├── parse_tool_call() → ToolExecutor.execute()
                    │       → tool result (flight status, directions, etc.)
                    │
                    ├── Re-infer with tool result for final response
                    │
                    └── Session memory (sliding window, per-passenger)
```

---

## Configuration

### LIDAR Parameters ([ydlidar_params.yaml](src/ydlidar_driver/config/ydlidar_params.yaml))

| Parameter | Default | Description |
|-----------|---------|-------------|
| `port` | `/dev/ttyUSB0` | Serial device path |
| `baudrate` | `128000` | Baud rate (128000 for X4 Pro) |
| `frame_id` | `laser_frame` | TF frame for LaserScan header |
| `frequency` | `10.0` | Motor target frequency (Hz) |
| `angle_min` / `angle_max` | `-180.0` / `180.0` | Scan angle range (degrees) |
| `min_range` / `max_range` | `0.01` / `12.0` | Valid range (metres) |
| `singleChannel` | `true` | **Must match model** (see below) |
| `health_expected_freq` | `4.0` | Actual scan delivery rate for health (Hz) |

**Single-channel LIDARs** (one-way comms, `singleChannel: true`): X4, X4 Pro, X2, X2L, S2, S4/S2PRO, S4B

**Dual-channel LIDARs** (two-way comms, `singleChannel: false`): G4, G4 Pro, G6, G7, F4 Pro, TG series

> **Swap LIDAR model = change YAML config only.** No code changes needed.

### Orchestrator Parameters ([orchestrator_params.yaml](src/orchestration/porter_orchestrator/config/orchestrator_params.yaml))

| Parameter | Default | Description |
|-----------|---------|-------------|
| `boot_grace_sec` | `8.0` | DDS discovery grace period |
| `health_check_patience_sec` | `10.0` | Tolerate non-OK health window |
| `boot_timeout_sec` | `30.0` | Max wait for driver health |
| `warn_consecutive_limit` | `20` | WARNs before escalating to ERROR |

### AI Assistant Parameters ([assistant_params.yaml](src/porter_ai_assistant/config/assistant_params.yaml))

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_path` | `models/gguf/gemma-3-270m-it-Q4_K_M.gguf` | Base GGUF model |
| `default_adapter` | `conversational` | Default LoRA adapter |
| `max_tokens` | `256` | Max generation tokens |
| `temperature` | `1.0` | Sampling temperature |
| `n_ctx` | `768` | Context window |
| `memory_size` | `10` | Conversation turns per session |
| `session_timeout_sec` | `300.0` | Session expiry (seconds) |

---

## Docker Services

### Development (`docker-compose.dev.yml`)

| Service | Profile | Description |
|---------|---------|-------------|
| `porter_dev` | *(default)* | Dev shell with live code mount |
| `porter_robot` | `--profile hardware` | Full device access for LIDAR testing |
| `porter_viz` | `--profile viz` | RViz2 with X11 forwarding |

### Production (`docker-compose.prod.yml`)

| Service | Profile | Description |
|---------|---------|-------------|
| `porter_robot` | *(default)* | Multi-stage minimal image, `restart: unless-stopped` |
| `porter_test` | `--profile test` | CI test runner |

```bash
# Production build & deploy
docker compose -f docker/docker-compose.prod.yml build
docker compose -f docker/docker-compose.prod.yml up -d

# CI test run
docker compose -f docker/docker-compose.prod.yml --profile test up
```

---

## Native Build (Without Docker)

Requires Ubuntu 24.04 with ROS 2 Jazzy and YDLidar SDK installed.

```bash
# Prerequisites
sudo apt install ros-jazzy-desktop python3-colcon-common-extensions python3-numpy

# Install YDLidar SDK
git clone https://github.com/YDLIDAR/YDLidar-SDK.git
cd YDLidar-SDK && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc) && sudo make install
sudo ldconfig && cd ../..

# Build workspace
cd porter_robot
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --cmake-args -Wno-dev
source install/setup.bash

# Run LIDAR driver
ros2 launch ydlidar_driver ydlidar_launch.py

# Run AI assistant (with orchestrator)
ros2 launch porter_ai_assistant assistant_launch.py use_orchestrator:=true
```

---

## Testing

```bash
# All ROS 2 tests
colcon test --event-handlers console_direct+
colcon test-result --verbose

# Single package
colcon test --packages-select ydlidar_driver
colcon test --packages-select porter_ai_assistant

# ESP32 firmware tests (requires Zephyr toolchain)
cd esp32_firmware && twister -T tests/ -p native_sim
```

| Package | Tests | Description |
|---------|-------|-------------|
| `ydlidar_driver` | 9 | GTest (health monitor, scan conversion, config) + linters |
| `porter_lidar_processor` | 24 | 6 filter test classes + linters |
| `porter_orchestrator` | 23 | State machine + health monitor + linters |
| `porter_esp32_bridge` | — | C++ bridge (compile-tested, runtime needs hardware) |
| `porter_ai_assistant` | 55 | 20 inference/config + 35 orchestrator + linters |
| ESP32 firmware (Ztest) | 178 | CRC16, protocol parser, transport (native_sim) |

---

## Development

### Environment

| Field | Value |
|-------|-------|
| ROS 2 Distro | Jazzy Jalisco |
| ROS Domain ID | 11 |
| DDS / RMW | `rmw_fastrtps_cpp` |
| C++ Standard | C++17 |
| Python | 3.12 (system, managed by ROS 2) |
| ESP32 RTOS | Zephyr 4.0 |
| AI Runtime | llama-cpp-python 0.3.16 |

### Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, tested, deployable |
| `prototype` | Current development |
| `feat/*` | Feature branches |

### Commit Convention

```
<type>(<scope>): <short description>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`

### Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | AI engineer instructions (18 sections, 39 lessons learned) |
| `OBJECTIVES.md` | Project goals, timeline, hardware architecture |
| `COMPANY.md` | VirtusCo context, team, product vision |
| `CHANGES.md` | 30-entry change log with before/after code |
| `DevLogs/` | Session-by-session development logs |

---

## Project Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| **1 — LIDAR Subsystem** | Custom C++ driver + processing + orchestration | ✅ Complete |
| **3 — ESP32 Firmware** | Motor control + sensor fusion + ROS 2 bridge | ✅ Complete |
| **4 — System Orchestration** | Full bringup + health monitoring + recovery | ✅ Complete |
| **4.5 — AI Assistant** | Gemma 3 270M GGUF + LoRA + conversation orchestrator | ✅ Complete |
| **2 — Navigation** | Nav2, SLAM, AMCL, waypoint navigation | Planned |
| **5 — Display & UX** | Touchscreen UI for passengers | Planned |
| **6 — Cross-compilation** | Docker multi-arch (amd64 + arm64) | Planned |
| **7 — OTA & Security** | DDS security, MCUboot, encrypted comms | Planned |
| **8 — Simulation** | Gazebo Ignition + URDF | Planned |
| **9 — MVP Demo** | Autonomous luggage carrying demo | Target: ~10 weeks |

---

## License

- `ydlidar_driver` — Apache 2.0 (open-source)
- `porter_lidar_processor`, `porter_orchestrator`, `porter_ai_assistant`, `porter_esp32_bridge` — Proprietary (VirtusCo)
- ESP32 firmware (`esp32_firmware/`) — Proprietary (VirtusCo)

---

**VirtusCo** — [virtusco.in](https://virtusco.in) · [GitHub](https://github.com/austin207/Porter-ROS)

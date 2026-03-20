# CLAUDE.md — Porter Robot ROS 2 Jazzy Project Instructions

> **Single-source-of-truth for Claude Code (and any LLM coding agent) working on this repo.**
> Drop this file into the project root and Claude will follow it automatically.
> **Read `OBJECTIVES.md`** for project goals, hardware architecture, and timeline.
> **Read `COMPANY.md`** for company context, team, product vision, and Claude's role.
>
> Last updated: 09 Mar 2026 · VirtusCo — Engineer: Antony Austin
> Repo: `github.com/austin207/Porter-ROS` · Root: `porter_robot/`

---

## 1. Project Identity

| Field | Value |
|-------|-------|
| **Company** | VirtusCo ([virtusco.in](https://virtusco.in)) — autonomous airport porter robots |
| **Robot** | Porter Robot — autonomous luggage carrier for airports (scalable to cruise ships, hotels, restaurants) |
| **ROS 2 Distro** | Jazzy Jalisco (Ubuntu 24.04 Noble base) |
| **Build System** | `colcon` — `ament_cmake` for C++, `ament_python` / setuptools for Python |
| **Containerisation** | Docker multi-stage build + Docker Compose services; Docker on robot for deployment |
| **Target Platforms** | amd64 (dev PC), arm64 (RPi 5 — prototype, Jetson — future), possibly Latte Panda |
| **Primary LIDAR** | YDLIDAR X4 Pro 360° (prototype) — baudrate **128000**. Production model TBD. Driver must be model-agnostic. |
| **Master Compute** | Raspberry Pi 4 (current) / RPi 5 (upgrade target) — runs ROS 2 + Nav2 + display |
| **Slave Compute** | 2× ESP32 (Zephyr RTOS) — #1: motor control, #2: sensor fusion (ToF + Ultrasonic + Microwave) |
| **RPi ↔ ESP32 Comms** | USB CDC Serial (`/dev/ttyACM*`) — fast, reliable, simple |
| **DDS / RMW** | `rmw_fastrtps_cpp` |
| **ROS Domain** | `ROS_DOMAIN_ID=11` |

### Architecture Choice

**Option C — company-first production-grade driver, then upstream.**

* Performance-critical code (serial parsing, packet handling, publish loop) → **C++ (rclcpp, C++17)**.
* Orchestration, health checks, state machines, Nav2 integration → **Python (rclpy)**.
* The official `ydlidar_ros2` driver is **EOL and broken on Jazzy** (`Error, cannot retrieve Yd Lidar health code: ffffffff`). The ROS 2 variant is extremely old and has reached end-of-life.
* As a startup product, VirtusCo needs full control over this production-critical component — custom driver from scratch, not a fork/patch.
* The driver will be open-sourced later; the company wrapper (`porter_lidar_processor`) stays internal.

### Hardware Context (25 Feb investigation)

* LIDAR tested via SDK `tri_test`: S2PRO / YD-47 identified during investigation.
* **Prototype LIDAR**: YDLIDAR X4 Pro 360° — driver must be model-agnostic (swap model via YAML config only).
* SDK `tri_test` successfully connected, retrieved firmware, produced valid scan data.
* Working baudrate: **128000**.
* Some YDLIDAR devices don't return baseplate info reliably → driver must treat this as **non-fatal** if scan data arrives OK.

### Full Hardware Architecture

See `OBJECTIVES.md` §3 for complete hardware diagram. Summary:
* **RPi 5 (master)**: LIDAR direct serial, ROS 2, Nav2, display, orchestration
* **ESP32 #1 (motors)**: Zephyr RTOS, motor PWM, future encoders, lift mechanism
* **ESP32 #2 (sensors)**: Zephyr RTOS, ToF + Ultrasonic + Microwave → on-board sensor fusion → USB serial to RPi
* **RPi ↔ ESP32**: USB CDC Serial with binary protocol (`[HEADER][MSG_ID][LENGTH][PAYLOAD][CRC16]`)

### Using the Skills Knowledge Base

The `skills/` directory contains **comprehensive reference material** that Claude must consult as needed:

* **`skills/` (16 files)** — Full ROS 2 Jazzy documentation: concepts, tutorials, CLI, client libs, intermediate/advanced topics, how-to guides, distributions, code style, quality, developer guide, release process, glossary.
* **`skills/zephyr/` (12 files)** — Zephyr RTOS reference: kernel, device drivers, build system, USB CDC, ESP32 hardware, testing, code style, security.

**When to read skill files:**
- Before implementing any new ROS 2 feature — check relevant skill files for Jazzy-specific APIs, patterns, and pitfalls.
- Before writing Zephyr firmware — read the relevant `skills/zephyr/` files for correct APIs, Kconfig, devicetree overlays.
- When unsure about code style, naming, QoS, launch file patterns, or TF conventions — the skill files have the authoritative answers.
- When debugging build or runtime errors — skill files contain common pitfalls and solutions.

**Do not guess** when a skill file has the answer. Read it.

---

## 2. Repository Layout (actual, current)

```
porter_robot/                              ← REPO ROOT — all commands run from here
│
├── CLAUDE.md                              ← THIS FILE — read first
├── OBJECTIVES.md                          ← Project goals, timeline, hardware arch, phases
├── COMPANY.md                             ← VirtusCo context, team, product, Claude's role
├── README.md                              ← User-facing quick-start (TODO)
├── CHANGES.md                             ← Before/after change log (TODO)
│
├── skills/                                ← ROS 2 Jazzy knowledge base (16 skill files)
│   ├── ros2_developer_guide.md            ← Contributing, versioning, DCO, workflow
│   ├── ros2_quality_guide.md              ← Static/dynamic analysis, TSA, linters
│   ├── ros2_release_process.md            ← Release lifecycle, Rolling Ridley
│   ├── ros2_code_style.md                 ← C++/Python/CMake/Markdown conventions
│   ├── 01_installation.md                 ← Binary, source, Docker installs
│   ├── 02_concepts.md                     ← Nodes, topics, services, actions, QoS, tf2
│   ├── 03_tutorials_beginner_cli.md       ← ros2 CLI commands reference
│   ├── 04_tutorials_beginner_client_libs.md ← colcon, workspaces, pub/sub, services
│   ├── 05_tutorials_intermediate.md       ← rosdep, actions, composition, launch, tf2
│   ├── 06_tutorials_advanced.md           ← Discovery Server, tracing, security, Gazebo
│   ├── 07_tutorials_demos.md              ← QoS, lifecycle, intra-process, logging
│   ├── 08_how_to_guides.md                ← 32 how-to guides indexed
│   ├── 09_distributions.md                ← Distro list, LTS cadence, Jazzy specifics
│   ├── 10_ros2_project.md                 ← Features, roadmap, governance, platform EOL
│   ├── 11_tutorials_miscellaneous.md      ← RT kernel, Eclipse IDE, Kubernetes
│   └── 12_glossary_contact_citations.md   ← Terminology, community, REPs, citations
│   └── zephyr/                            ← Zephyr RTOS knowledge base (12 skill files)
│       ├── 01_getting_started.md          ← Installation, west, SDK, ESP32 setup
│       ├── 02_kernel_services.md          ← Threads, scheduling, sync, data passing, timers
│       ├── 03_device_driver_model.md      ← Devicetree, Kconfig, driver APIs
│       ├── 04_application_development.md  ← App structure, build system, flashing
│       ├── 05_build_system.md             ← CMake, Kconfig, Devicetree, sysbuild
│       ├── 06_os_services.md              ← Logging, Shell, SMF, zbus, watchdog, NVS
│       ├── 07_usb_cdc_connectivity.md     ← USB CDC ACM, UART API, RPi↔ESP32 comms
│       ├── 08_hardware_esp32.md           ← ESP32 board, GPIO, PWM, ADC, I2C
│       ├── 09_security_safety.md          ← Hardening, secure coding, motor safety
│       ├── 10_testing_samples.md          ← Ztest, twister, native_sim, samples
│       ├── 11_code_style.md               ← Naming, file structure, conventions
│       └── 12_glossary_reference.md       ← Glossary, quick reference, doc links
│
├── DevLogs/
│   └── 25_Feb_Logs.md                     ← Investigation: HW ID, architecture decision
│
├── docker/
│   ├── Dockerfile.dev                     ← osrf/ros:jazzy-desktop + colcon + rosdep
│   ├── Dockerfile.prod                    ← osrf/ros:jazzy-ros-base (minimal)
│   ├── docker-compose.dev.yml             ← Dev service: host net, live mounts, ROS_DOMAIN_ID=11
│   └── (docker-compose.prod.yml)          ← TODO
│
├── docs/                                  ← Driver Porting Guide, Contribution Guide (TODO)
│
├── esp32_firmware/                         ← Zephyr RTOS firmware for 2× ESP32
│   ├── README.md                          ← Overview, build commands, protocol docs
│   ├── motor_controller/                  ← ESP32 #1: BTS7960 H-bridge, encoder, PWM
│   │   ├── CMakeLists.txt
│   │   ├── prj.conf
│   │   ├── app.overlay
│   │   └── src/main.cpp
│   ├── sensor_fusion/                     ← ESP32 #2: ToF, ultrasonic, microwave
│   │   ├── CMakeLists.txt
│   │   ├── prj.conf
│   │   ├── app.overlay
│   │   └── src/main.cpp
│   └── common/                            ← Shared protocol lib (USB CDC binary protocol)
│       ├── include/protocol.h
│       ├── include/crc16.h
│       ├── src/protocol.cpp
│       └── src/crc16.cpp
│
└── src/                                   ← colcon workspace source root
    ├── ydlidar_driver/                    ← Open-source C++ driver (TO BUILD)
    │   ├── CMakeLists.txt
    │   ├── package.xml
    │   ├── src/
    │   │   ├── ydlidar_node.cpp
    │   │   └── sdk_adapter.cpp
    │   ├── include/ydlidar_driver/
    │   │   └── sdk_adapter.hpp
    │   ├── launch/
    │   │   └── ydlidar_launch.py
    │   ├── config/
    │   │   └── ydlidar_params.yaml
    │   ├── tests/
    │   └── README.md
    │
    ├── porter_lidar_processor/            ← Company internal Python processing (TO BUILD)
    │   ├── package.xml
    │   ├── setup.py / CMakeLists.txt
    │   ├── porter_lidar_processor/
    │   │   └── __init__.py
    │   ├── launch/
    │   ├── config/
    │   └── tests/
    │
    ├── orchestration/
    │   └── porter_orchestrator/           ← rclpy state machine & health monitor (TO BUILD)
    │       ├── porter_state_machine.py
    │       ├── lidar_health_monitor.py
    │       └── launch/
    │
    ├── nav/
    │   └── nav2_config/                   ← Navigation2 parameters (later)
    │
    ├── porter_ai_assistant/               ← AI assistant: Qwen 2.5 1.5B GGUF (Phase 4.5)
    │   ├── package.xml
    │   ├── setup.py
    │   ├── setup.cfg
    │   ├── porter_ai_assistant/
    │   │   ├── __init__.py
    │   │   ├── assistant_node.py           ← ROS 2 service node (query, status, diagnostics)
    │   │   ├── inference_engine.py         ← llama-cpp-python wrapper, LoRA, health
    │   │   ├── config.py                  ← Model paths, generation params, thresholds
    │   │   └── prompt_templates.py         ← System prompts, adapter routing
    │   ├── scripts/
    │   │   ├── finetune.py                ← QLoRA fine-tuning pipeline (SFTTrainer)
    │   │   ├── convert_to_gguf.py         ← LoRA merge + GGUF quantization
    │   │   ├── download_model.py          ← HuggingFace GGUF downloader
    │   │   ├── benchmark.py               ← Latency / accuracy benchmarks
    │   │   └── generate_dataset.py        ← Airport Q&A dataset generator
    │   ├── data/
    │   │   ├── conversational/             ← 7K train + 1.4K eval examples
    │   │   ├── tool_use/                  ← 3K train + 0.6K eval examples
    │   │   ├── combined/                  ← 10K train + 2K eval merged
    │   │   ├── system_prompts.yaml
    │   │   └── tool_schemas.json
    │   ├── models/                         ← .gitkeep (GGUF models via Git LFS)
    │   ├── launch/
    │   │   └── assistant_launch.py
    │   ├── config/
    │   │   └── assistant_params.yaml
    │   └── test/
    │       ├── test_assistant.py           ← 20 unit tests
    │       ├── test_flake8.py
    │       └── test_pep257.py
    │
    ├── simulation/
    │   ├── gazeebo/
    │   ├── ignition/
    │   └── porter_robot_urdf/
    │
    └── tools/                             ← Debug / utility scripts (later)
```

### Layout Rules

* **Never** move packages out of `src/`. Docker, `rosdep install --from-paths src`, and `colcon build` all require it.
* **Never** commit `build/`, `install/`, `log/` — must be in `.gitignore`.
* Keep launch files, configs (YAML), and URDF/Xacro inside their respective packages under `src/`.
* Shell scripts at the root must be `chmod +x` and use `#!/bin/bash` with `set -e`.
* Empty directories that must exist in git get a `.gitkeep` file.

---

## 3. Docker — Build & Run Rules

### 3.1 CRITICAL: Always run from repo root

```bash
cd /path/to/porter_robot                  # ← HERE, never porter_robot/docker/
docker compose -f docker/docker-compose.dev.yml up -d
docker exec -it porter_dev bash
```

**Why?** The build context in `docker-compose.dev.yml` is `context: ..` (repo root). Running from `docker/` breaks the context — `src/` won't be found and `rosdep install --from-paths src` fails with `given path 'src' does not exist`.

### 3.2 Current Docker Files

| File | Base Image | Purpose |
|------|-----------|---------|
| `docker/Dockerfile.dev` | `osrf/ros:jazzy-desktop` | Full dev: colcon, rosdep, build-essential, git |
| `docker/Dockerfile.prod` | `osrf/ros:jazzy-ros-base` | Minimal runtime: copies pre-built `install/` |
| `docker/docker-compose.dev.yml` | — | Service `porter_dev`: host net, mounts `src/` + `docs/` live, `ROS_DOMAIN_ID=11`, `rmw_fastrtps_cpp` |

### 3.3 Docker Compose Commands

```bash
docker compose -f docker/docker-compose.dev.yml build    # Build dev image
docker compose -f docker/docker-compose.dev.yml up -d    # Start dev container
docker compose -f docker/docker-compose.dev.yml down      # Stop and remove
docker exec -it porter_dev bash                            # Shell into container
```

### 3.4 Device Pass-Through (hardware testing)

When testing with real LIDAR, add to `docker-compose.dev.yml` under `porter_dev`:

```yaml
devices:
  - /dev/ttyUSB0:/dev/ttyUSB0
privileged: true        # Only for robot/hardware service
```

### 3.5 Dockerfile Conventions (for new / modified Dockerfiles)

1. **Multi-stage builds** (build stage → runtime stage) for production.
2. Use `--mount=type=cache` for `/var/cache/apt` and `/root/.cache/pip` to speed rebuilds.
3. Never install build-only deps (build-essential, cmake) in the runtime stage.
4. Copy `install/` from build stage — never `build/` or `log/`.
5. Copy `src/` into runtime only if launch files reference source-relative paths (config, URDF).
6. `WORKDIR /workspace` — all ROS 2 workspaces live here inside the container.
7. Support both `amd64` and `arm64` — avoid architecture-specific assumptions.
8. Set `ENV ROS_DOMAIN_ID=11` in the image; allow override at runtime via `-e`.

### 3.6 Entrypoint Pattern (for docker-entrypoint.sh when created)

```bash
#!/bin/bash
set -e
source /opt/ros/jazzy/setup.bash
[ -f /workspace/install/setup.bash ] && source /workspace/install/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-11}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
exec "$@"
```

### 3.7 Docker Compose Service Patterns

| Service | Purpose | `network_mode` | `privileged` | Volumes |
|---------|---------|----------------|-------------|---------|
| `porter_dev` | Development shell | `host` | `false` | `src/`, `docs/` live mounts |
| `porter_robot` | Full hardware stack | `host` | `true` | `/dev:/dev`, named volume for maps |
| `porter_ai` | AI assistant (resource-limited) | `host` | `false` | ai_models named volume |
| `porter_viz` | RViz on remote PC | `host` | `false` | X11 socket, Xauthority |
| `porter_sim` | Bag replay + stack | `host` | `false` | X11, `./datasets:/workspace/datasets:ro` |
| `porter_test` | CI test runner | `host` | `false` | — |

Rules:
- Always `network_mode: host` for DDS discovery across machines.
- Match `ROS_DOMAIN_ID=11` across all services and machines.
- X11 forwarding needs: `DISPLAY`, `QT_X11_NO_MITSHM=1`, `/tmp/.X11-unix`, `XAUTHORITY`.
- Use `restart: unless-stopped` only for the robot and AI services.
- Mount hardware devices (`/dev`) only in the robot service.
- AI service: `cpus: 2.0`, `mem_limit: 2g`, `PORTER_NICE=10` — prevents starving SLAM/Nav2 on 4-core RPi.

---

## 4. Build Commands

### 4.1 Docker Build (primary workflow)

```bash
# From porter_robot/ root
docker compose -f docker/docker-compose.dev.yml build
docker compose -f docker/docker-compose.dev.yml up -d
docker exec -it porter_dev bash

# Inside container
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --cmake-args -Wno-dev --parallel-workers $(nproc)
source install/setup.bash
```

### 4.2 Native Build (on host with Jazzy installed)

```bash
cd /path/to/porter_robot

# Clean build
unset AMENT_PREFIX_PATH && unset CMAKE_PREFIX_PATH
rm -rf build/ install/ log/
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --cmake-args -Wno-dev --parallel-workers $(nproc)
source install/setup.bash
```

### 4.3 Single-Package Rebuild

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon build --packages-select ydlidar_driver --symlink-install
```

### 4.4 Clean Rebuild (nuclear)

```bash
rm -rf build/ install/ log/
colcon build --cmake-clean-cache --symlink-install
```

---

## 5. Test & Verification Commands

### 5.1 Colcon Tests

```bash
# All tests
colcon test --event-handlers console_direct+
colcon test-result --verbose

# Single package
colcon test --packages-select ydlidar_driver
colcon test-result --verbose
```

### 5.2 Linting (must pass before any commit)

```bash
# Python (ament)
ament_flake8 src/porter_lidar_processor/
ament_pep257 src/porter_lidar_processor/

# C++ (ament)
ament_cpplint src/ydlidar_driver/src/ src/ydlidar_driver/include/
ament_cppcheck src/ydlidar_driver/src/
ament_uncrustify src/ydlidar_driver/src/ src/ydlidar_driver/include/

# Via colcon
colcon test --packages-select porter_lidar_processor --pytest-args -k "flake8 or pep257"
colcon test --packages-select ydlidar_driver --ctest-args -R "lint"
```

### 5.3 Hardware Test (with physical LIDAR)

```bash
# 1. Verify device with SDK first
cd /path/to/YDLidar-SDK/build
./tri_test          # Confirm baudrate 128000, scan output OK

# 2. Launch ROS2 driver
ros2 run ydlidar_driver ydlidar_node --ros-args -p port:=/dev/ttyUSB0 -p baudrate:=128000

# 3. Validate output
ros2 topic echo /scan
ros2 topic hz /scan
ros2 topic echo /diagnostics     # Health status
```

### 5.4 TF Tree Verification (runtime)

```bash
ros2 run tf2_tools view_frames               # Generates frames.pdf
ros2 topic echo /tf --once                   # Spot-check live transforms
ros2 run tf2_ros tf2_echo odom base_link     # Live TF lookup
```

---

## 6. ROS 2 Jazzy — Critical API Rules

These are **hard requirements** that cause compile failures if violated:

### 6.1 C++ Parameter Rules

| Rule | Correct Example | Wrong (will fail) |
|------|----------------|-------------------|
| Typed `declare_parameter<T>` with default | `node->declare_parameter<std::string>("port", "/dev/ttyUSB0");` | `node->declare_parameter("port");` |
| Typed `get_parameter` | `node->get_parameter("baudrate", baudrate);` | untyped overload |
| `SensorDataQoS` for sensor publishers | `create_publisher<LaserScan>("scan", rclcpp::SensorDataQoS());` | default QoS |
| C++17 standard | `set(CMAKE_CXX_STANDARD 17)` in CMakeLists.txt | C++14 or unset |

### 6.2 Common Jazzy Pitfalls

| Pitfall | Why it's bad | What to do instead |
|---------|-------------|-------------------|
| Untyped `declare_parameter("angle_max")` | Compile error on Jazzy | `declare_parameter<double>("angle_max", 180.0)` |
| Copy-pasting from old `ydlidar_ros2` driver | Uses deprecated Humble APIs | Write fresh Jazzy code |
| Missing baseplate info from device | Some S2PRO units don't report it | Treat as non-fatal if scan data valid |
| `print()` in ROS nodes | Bypasses ROS logging, invisible to `/rosout` | `self.get_logger().info()` / `RCLCPP_INFO()` |
| Hard-coded absolute paths in launch files | Breaks when installed to different prefix | `get_package_share_directory()` |
| Missing `--symlink-install` in dev builds | Python changes require full rebuild | Always use `--symlink-install` for dev |
| Not sourcing `install/setup.bash` | Nodes can't find each other | Source it in entrypoint and after every build |
| `network_mode: bridge` in docker-compose | DDS discovery fails across machines | Use `network_mode: host` |
| Forgetting `use_sim_time` in simulation | Nodes use wall clock, bag time ignored | Pass `use_sim_time:=true` in sim launch |
| Unbounded queue sizes | Memory grows in slow consumers | Use small queue depths (5–10) unless justified |
| Committing `build/`, `install/`, `log/` | Bloats repo, causes merge conflicts | Add to `.gitignore` |

---

## 7. Driver Parameters

Declare all of these in the C++ `ydlidar_node` with typed defaults:

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `port` | string | `"/dev/ttyUSB0"` | Serial device path |
| `baudrate` | int | `128000` | Confirmed working for S2PRO/YD-47 |
| `frame_id` | string | `"laser_frame"` | TF frame for LaserScan header |
| `samp_rate` | int | `5` | Sample rate (model dependent) |
| `frequency` | double | `10.0` | Scan frequency in Hz |
| `angle_min` | double | `-180.0` | Min scan angle in degrees |
| `angle_max` | double | `180.0` | Max scan angle in degrees |
| `min_range` | double | `0.01` | Min valid range in metres |
| `max_range` | double | `64.0` | Max valid range in metres |
| `ignore_array` | string | `""` | Comma-separated angle pairs e.g. `"-1,1,45,46"` |
| `resolution_fixed` | bool | `false` | Fixed angular resolution mode |
| `singleChannel` | bool | `false` | Single-channel communication mode |
| `auto_reconnect` | bool | `true` | Auto-reconnect on disconnect |
| `isToFLidar` | bool | `false` | Time-of-Flight LIDAR mode |
| `health_expected_freq` | double | `0.0` | Expected scan delivery rate for health monitor (0 = use `frequency`). S2PRO: set to `4.0`. |

**C++ declaration pattern:**

```cpp
node->declare_parameter<std::string>("port", "/dev/ttyUSB0");
node->declare_parameter<int>("baudrate", 128000);
node->declare_parameter<std::string>("frame_id", "laser_frame");
node->declare_parameter<double>("frequency", 10.0);
node->declare_parameter<double>("angle_min", -180.0);
node->declare_parameter<double>("angle_max", 180.0);
node->declare_parameter<double>("min_range", 0.01);
node->declare_parameter<double>("max_range", 64.0);
node->declare_parameter<std::string>("ignore_array", "");
node->declare_parameter<bool>("resolution_fixed", false);
node->declare_parameter<bool>("singleChannel", false);
node->declare_parameter<bool>("auto_reconnect", true);
node->declare_parameter<bool>("isToFLidar", false);
node->declare_parameter<int>("samp_rate", 5);
```

---

## 8. ROS 2 Package Conventions

### 8.1 Package Types for Porter

| Package | Build Type | Language | Purpose |
|---------|-----------|----------|---------|
| `ydlidar_driver` | `ament_cmake` | C++17 | LIDAR serial driver + LaserScan publisher |
| `porter_lidar_processor` | `ament_python` | Python | Scan filtering, smoothing, ROI cropping |
| `porter_orchestrator` | `ament_python` | Python | State machine, health monitoring, boot sequence |
| `nav2_config` | config-only | YAML | Navigation2 parameter files |
| `porter_robot_urdf` | `ament_cmake` | URDF/Xacro | Robot model and TF tree |

### 8.2 ament_cmake Package Structure (ydlidar_driver)

```
src/ydlidar_driver/
├── CMakeLists.txt
├── package.xml
├── include/ydlidar_driver/
│   └── *.hpp
├── src/
│   └── *.cpp
├── launch/
│   └── ydlidar_launch.py
├── config/
│   └── ydlidar_params.yaml
├── tests/
│   └── test_*.cpp
└── README.md
```

### 8.3 ament_python Package Structure (porter_lidar_processor)

```
src/porter_lidar_processor/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/porter_lidar_processor     # Empty marker (ament index)
├── porter_lidar_processor/
│   ├── __init__.py
│   └── processor_node.py
├── launch/
│   └── processor_launch.py
├── config/
│   └── processor_params.yaml
└── test/
    ├── test_flake8.py
    ├── test_pep257.py
    └── test_processor.py
```

### 8.4 Naming Conventions

| Element | Convention | Porter Examples |
|---------|-----------|----------------|
| Package names | `snake_case` | `ydlidar_driver`, `porter_lidar_processor` |
| Node names | `snake_case` | `ydlidar_node`, `lidar_processor`, `state_machine` |
| Topic names | `snake_case` with `/` | `/scan`, `/scan/processed`, `/diagnostics` |
| Frame IDs | `snake_case` | `laser_frame`, `base_link`, `odom` |
| Launch files | `<name>_launch.py` | `ydlidar_launch.py`, `porter_bringup_launch.py` |
| Config files | `<name>_params.yaml` | `ydlidar_params.yaml`, `nav2_config.yaml` |
| Parameter names | `snake_case` | `baudrate`, `min_range`, `auto_reconnect` |

### 8.5 Standard Frame IDs (REP-105)

| Frame | Meaning | Publisher |
|-------|---------|-----------|
| `map` | Global fixed frame | SLAM / localisation |
| `odom` | Continuous odometry frame | Odometry source (EKF, wheel odom) |
| `base_link` | Robot body centre | URDF (`robot_state_publisher`) |
| `base_footprint` | Ground projection of `base_link` | URDF (static joint) |
| `laser_frame` | LIDAR mount frame | URDF (static joint from `base_link`) |

### 8.6 TF Tree Rules

- Tree must be **fully connected**: `map → odom → base_link → laser_frame`.
- **One publisher per transform.** Never two nodes publishing the same TF.
- SLAM / localisation owns `map → odom`.
- Odometry source owns `odom → base_link`.
- `robot_state_publisher` owns all URDF joints (including `base_link → laser_frame`).
- Never publish `map → base_link` directly — it breaks the odom correction model.

### 8.7 Porter Topic Map

| Topic | Message Type | Publisher | Subscriber(s) |
|-------|-------------|-----------|---------------|
| `/scan` | `sensor_msgs/LaserScan` | `ydlidar_node` | `porter_lidar_processor`, Nav2 |
| `/scan/processed` | `sensor_msgs/LaserScan` | `porter_lidar_processor` | Nav2 (optional) |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | `ydlidar_node` | `lidar_health_monitor` |
| `/porter/state` | `std_msgs/String` | `porter_state_machine` | orchestration consumers |

---

## 9. Code Style & Quality

### 9.1 C++ (ydlidar_driver)

- Follow `ament_cpplint` and `ament_uncrustify` conventions.
- Use `RCLCPP_INFO/WARN/ERROR` macros — **never** `std::cout` for logging.
- Header guards: `#ifndef YDLIDAR_DRIVER__FILE_NAME_HPP_` / `#define` / `#endif`.
- No exceptions across threads — use error codes + logging.
- Use `std::shared_ptr` / `SharedPtr` where appropriate.
- Use `const &` for non-trivial parameters.
- C++17 features allowed (structured bindings, `std::optional`, `if constexpr`).

### 9.2 Python (porter_lidar_processor, porter_orchestrator)

- Follow **PEP 8** and **PEP 257** (enforced by `ament_flake8` + `ament_pep257`).
- Max line length: **99 characters** (ament default).
- Every source file must have a module-level docstring.
- Every class must have a class-level docstring explaining purpose and subscribers/publishers.
- Use `self.get_logger().info/warn/error()` — **never** bare `print()`.
- Use `rclpy.spin()` or `rclpy.spin_once()` — never busy-loop.
- Always call `rclpy.shutdown()` in `finally` blocks.

### 9.3 Launch Files (Python)

- Always use `launch_ros` actions (`Node`, `IncludeLaunchDescription`).
- Declare all tunable values as `DeclareLaunchArgument` with defaults.
- Use `LaunchConfiguration` to reference declared arguments.
- Always specify `output='screen'` explicitly.
- Never hard-code paths — use `get_package_share_directory()`.

### 9.4 YAML Config Files

- Use comments to document every non-obvious parameter.
- Group under node name with `ros__parameters:`.
- Include units: `# metres`, `# radians/sec`, `# Hz`.

```yaml
ydlidar_node:
  ros__parameters:
    port: "/dev/ttyUSB0"
    baudrate: 128000          # baud
    frame_id: "laser_frame"
    frequency: 10.0           # Hz
    angle_min: -180.0         # degrees
    angle_max: 180.0          # degrees
    min_range: 0.01           # metres
    max_range: 64.0           # metres
```

---

## 10. Implementation Tasks

Each task is atomic. Implement in order. Produce code + tests + docs for each.

### TASK 1 — `ydlidar_driver` C++ package skeleton

**Location:** `src/ydlidar_driver/`

**Files to create:**
- `src/ydlidar_driver/package.xml`
- `src/ydlidar_driver/CMakeLists.txt`
- `src/ydlidar_driver/src/ydlidar_node.cpp`
- `src/ydlidar_driver/include/ydlidar_driver/` (header stubs)
- `src/ydlidar_driver/launch/ydlidar_launch.py`
- `src/ydlidar_driver/config/ydlidar_params.yaml`
- `src/ydlidar_driver/README.md`

**Behaviour:**
- Read all typed parameters (see §7 table).
- Initialise serial device; attempt health read using SDK routines.
- Robust retries: 3 attempts with exponential backoff.
- On success → start scan loop publishing `sensor_msgs::msg::LaserScan` at configured frequency.
- Use `rclcpp::SensorDataQoS()` for the publisher.
- Graceful shutdown: stop scan, disconnect device.

**C++ constraints:**
- C++17. No exceptions across threads. Error codes + `RCLCPP_*` logging.
- `std::shared_ptr` where appropriate. Clear log messages for every init stage.

**CMakeLists.txt essentials:**
```cmake
cmake_minimum_required(VERSION 3.16)
project(ydlidar_driver)
set(CMAKE_CXX_STANDARD 17)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)

add_executable(ydlidar_node src/ydlidar_node.cpp src/sdk_adapter.cpp)
ament_target_dependencies(ydlidar_node rclcpp sensor_msgs std_msgs diagnostic_msgs)
target_include_directories(ydlidar_node PUBLIC include)

install(TARGETS ydlidar_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
```

**package.xml essentials:**
```xml
<package format="3">
  <name>ydlidar_driver</name>
  <version>0.1.0</version>
  <description>YDLIDAR ROS2 Jazzy driver for Porter Robot</description>
  <maintainer email="antony@example.com">Antony Austin</maintainer>
  <license>Apache-2.0</license>
  <buildtool_depend>ament_cmake</buildtool_depend>
  <depend>rclcpp</depend>
  <depend>sensor_msgs</depend>
  <depend>std_msgs</depend>
  <depend>diagnostic_msgs</depend>
  <test_depend>ament_lint_auto</test_depend>
  <test_depend>ament_lint_common</test_depend>
</package>
```

---

### TASK 2 — SDK adapter / packet parser

**Location:** `src/ydlidar_driver/src/sdk_adapter.cpp` + `src/ydlidar_driver/include/ydlidar_driver/sdk_adapter.hpp`

**Class API — `YdLidarAdapter`:**
```cpp
class YdLidarAdapter {
public:
  bool initialize(const std::string &port, int baudrate);
  bool getHealth(int &health_code);
  bool startScan();
  bool stopScan();
  bool readScan(std::vector<LaserPoint> &points);  // angle, range, intensity
  void disconnect();
};
```

**Rules:**
- Handle devices that return odd/missing baseplate info → non-fatal if scan data OK.
- Implement checksum validation and packet length checks.
- Log raw bytes when checksum fails.
- Wrap the YDLidar SDK `CYdLidar` class (or implement minimal serial parser).

---

### TASK 3 — LaserScan publishing

**In:** `src/ydlidar_driver/src/ydlidar_node.cpp`

- Convert SDK `angle, range, intensity` → `sensor_msgs::msg::LaserScan`.
- Compute `size = (angle_max - angle_min) / angle_increment + 1`.
- Fill `ranges[]` and `intensities[]` by index from angle and increment.
- Set `scan_time`, `time_increment` from SDK data or compute from frequency.
- Publish with `SensorDataQoS`.

---

### TASK 4 — Diagnostics & health monitoring (C++)

**Location:** `src/ydlidar_driver/src/` and `include/ydlidar_driver/`

- Publish health/status on `diagnostic_msgs::msg::DiagnosticArray` topic.
- `HealthMonitor` class: track last N scans, report missing scans, high error rate, too many invalid ranges.
- Expose ROS2 parameters for thresholds.

---

### TASK 5 — `porter_lidar_processor` (company layer, Python)

**Location:** `src/porter_lidar_processor/`

- Subscribe to `/scan` topic.
- Apply: smoothing, median filter, outlier rejection, downsampling, ROI cropping.
- Publish processed scan to `/scan/processed`.
- Expose ROS2 service to toggle filters and change parameters dynamically.
- Unit tests with pytest + ROS2 test harness.

---

### TASK 6 — Orchestration layer (rclpy)

**Location:** `src/orchestration/porter_orchestrator/`

**Files:**
- `porter_state_machine.py` — system state management
- `lidar_health_monitor.py` — subscribe to `/diagnostics`, trigger recovery
- `launch/` directory

**Behaviour:**
- Monitor `ydlidar_driver` status; restart or reconnect if health degrades.
- Expose service endpoints: restart driver, change baudrate.
- Boot sequence: bring up driver → verify health → bring up processing → publish `ready` state.

---

### TASK 7 — Docker dev environment improvements

**Location:** `docker/`

**Dockerfile.dev issues to fix:**
- COPY paths use `../src/*/package.xml` which doesn't glob correctly in Docker context.
- Should use relative paths from build context root: `COPY src/*/package.xml ./src/`.

**docker-compose.dev.yml improvements:**
- Add `devices` section for hardware testing (`/dev/ttyUSB0`).
- Add `docker-compose.prod.yml` for production.
- Add `docker-entrypoint.sh` for proper ROS 2 workspace sourcing.

---

### TASK 8 — Tests

| Test Type | Tool | Location |
|-----------|------|----------|
| Packet parser unit tests | GoogleTest (C++) | `src/ydlidar_driver/tests/` |
| Integration test (recorded data) | Feed saved `tri_test` output into parser | `src/ydlidar_driver/tests/` |
| ROS2 launch test | Launch in Docker, validate `/scan` topic | `src/ydlidar_driver/tests/` |
| Python processor tests | pytest + ROS2 test harness | `src/porter_lidar_processor/tests/` |
| Lint tests | ament_lint_auto | Per package |
| CI pipeline | GitHub Actions | `.github/workflows/` |

**CI must run:** `colcon build` → unit tests → `ament_cpplint` / `ament_flake8` → static analysis (optional).

---

### TASK 9 — Documentation

- `src/ydlidar_driver/README.md` — hardware, supported models, parameters, known issues.
- `docs/Driver_Porting_Guide.md` — how to adapt driver to other YDLidar models.
- `docs/Contribution_Guide.md` — code style, testing, PR process.
- `README.md` (repo root) — project overview, quick-start, architecture diagram.
- `CHANGES.md` (repo root) — before/after change log.

---

### TASK 10 — CRC16-CCITT implementation

**Location:** `esp32_firmware/common/src/crc16.cpp` + `esp32_firmware/common/include/crc16.h`

**Behaviour:**
- Implement CRC16-CCITT (polynomial `0x1021`, init `0xFFFF`).
- Must produce identical results on ESP32 (Zephyr) and RPi (Linux) — shared header.
- Used by protocol parser and encoder for packet integrity.

---

### TASK 11 — Protocol parser & encoder

**Location:** `esp32_firmware/common/src/protocol.cpp` + `esp32_firmware/common/include/protocol.h`

**Behaviour:**
- `protocol_parser_feed()` — byte-by-byte state machine: `HEADER1 → HEADER2 → LENGTH → COMMAND → PAYLOAD → CRC_LOW → CRC_HIGH → COMPLETE/ERROR`.
- `protocol_encode()` — builds packet: `[0xAA 0x55][Length][Command][Payload…][CRC16]`.
- CRC16 computed over `Length + Command + Payload` bytes.
- Reject packets with bad CRC (log and discard).
- Handle edge cases: oversized payload (>64 bytes), zero-length payload, back-to-back packets.

---

### TASK 12 — Transport abstraction layer (ESP-agnostic)

**Location:** `esp32_firmware/common/src/transport.cpp` + `esp32_firmware/common/include/transport.h`

**Behaviour:**
- Abstract `transport_init()`, `transport_read()`, `transport_write()` over two backends:
  - **UART backend** (`CONFIG_PORTER_TRANSPORT_UART=y`) — for ESP32-WROOM via CP2102/CH340 bridge.
  - **CDC ACM backend** (`CONFIG_PORTER_TRANSPORT_CDC_ACM=y`) — for ESP32-S2/S3 with native USB.
- Selected at build time via Kconfig, not runtime.
- The protocol layer calls transport functions and doesn't know which hardware is underneath.
- Firmware is ESP-agnostic: swap board variant = change Kconfig + overlay, not code.

---

### TASK 13 — Motor controller firmware (ESP32 #1)

**Location:** `esp32_firmware/motor_controller/src/`

**Subsystems:**
- **SMF state machine:** `IDLE → RUNNING → FAULT → ESTOP` (Zephyr State Machine Framework).
- **PWM motor driver:** BTS7960 dual H-bridge — `RPWM`/`LPWM` for direction, `EN` for enable. 2 motors (left/right).
- **Differential drive:** Convert `(linear_x, angular_z)` velocity commands → left/right wheel PWM duty cycles.
- **Speed ramping:** Enforce acceleration/deceleration limits — never instant full-speed.
- **Heartbeat watchdog:** No command from RPi in 500ms → stop motors immediately.
- **Task watchdog:** `CONFIG_TASK_WDT=y` — hardware watchdog fed in every thread loop.
- **Encoder stub:** Interface ready for future encoder feedback (not wired yet).
- **Lift mechanism:** Basic up/down control via GPIO.
- **zbus channels:** `motor_cmd_chan`, `motor_status_chan`, `safety_event_chan`.
- **Thread priorities:** safety(-1) > motor(0) > protocol(1) > reporting(5) > shell(14).

**Protocol commands handled:**
- `CMD_MOTOR_SET_SPEED (0x01)` — payload: `[left_speed:i16][right_speed:i16][flags:u8]`
- `CMD_MOTOR_STOP (0x02)` — emergency stop, no payload.
- `CMD_MOTOR_STATUS (0x03)` — request → respond with current state, speed, fault flags.
- `CMD_HEARTBEAT (0xF0)` — reset watchdog timer.

---

### TASK 14 — Sensor fusion firmware (ESP32 #2)

**Location:** `esp32_firmware/sensor_fusion/src/`

**Subsystems:**
- **SMF state machine:** `INIT → CALIBRATING → ACTIVE → DEGRADED → FAULT`.
- **ToF driver (I2C):** VL53L0x Time-of-Flight sensor on I2C0.
- **Ultrasonic driver (GPIO):** Trigger pulse + echo timing for distance measurement.
- **Microwave driver (ADC):** Analog presence/motion detection.
- **Kalman filter:** Fuse ToF + Ultrasonic + Microwave into unified obstacle estimate.
- **Cross-validation:** If ToF and Ultrasonic disagree by >30%, flag inconsistency.
- **Sensor timeout:** No response in 100ms → mark sensor as degraded.
- **Fallback:** Primary sensor fail → switch to secondary with warning.
- **zbus channels:** `sensor_data_chan`, `sensor_status_chan`, `safety_event_chan`.

**Protocol commands handled:**
- `CMD_SENSOR_FUSED (0x13)` — sends fused obstacle data to RPi periodically.
- `CMD_SENSOR_STATUS (0x14)` — request → respond with per-sensor health.
- `CMD_SENSOR_TOF/ULTRASONIC/MICROWAVE (0x10-0x12)` — individual sensor readings.

---

### TASK 15 — Ztest unit tests (CRC, protocol, transport)

**Location:** `esp32_firmware/tests/`

**Tests:**
- CRC16 known-vector tests (RFC-compliant test values).
- Protocol parser: valid packets, corrupted CRC, truncated, oversized, zero-length payload.
- Protocol encoder: round-trip encode → parse.
- Transport abstraction: mock read/write on `native_sim`.
- Run via `twister -T esp32_firmware/tests/` on `native_sim` target.

---

### TASK 16 — ROS 2 ESP32 bridge nodes

**Location:** `src/porter_esp32_bridge/`

**Package type:** `ament_cmake` (C++) or `ament_python` — C++ preferred for serial performance.

**Nodes:**
- **`esp32_motor_bridge`:**
  - Subscribes `/cmd_vel` (`geometry_msgs/Twist`).
  - Converts to binary protocol `CMD_MOTOR_SET_SPEED` packets.
  - Sends over serial to ESP32 #1.
  - Receives `CMD_MOTOR_STATUS` / `CMD_MOTOR_ENCODER` → publishes to `/motor_status`.
  - Sends periodic `CMD_HEARTBEAT`.
  - Parameters: `port` (default `/dev/esp32_motors`), `baudrate` (default `115200`).

- **`esp32_sensor_bridge`:**
  - Receives `CMD_SENSOR_FUSED` from ESP32 #2.
  - Publishes `/environment` (`sensor_msgs/Range` or custom message).
  - Sends config commands (thresholds, enable/disable sensors).
  - Publishes sensor health to `/diagnostics`.
  - Parameters: `port` (default `/dev/esp32_sensors`), `baudrate` (default `115200`).

**Shared:** Protocol encode/decode is shared C code from `esp32_firmware/common/` — linked into the ROS 2 package.

---

### TASK 17 — udev rules & device naming

**Location:** `esp32_firmware/udev/` + `docker/`

**Rules:**
- Stable symlinks: `/dev/esp32_motors` → `/dev/ttyUSB0` (or `ttyACM0`).
- Stable symlinks: `/dev/esp32_sensors` → `/dev/ttyUSB1` (or `ttyACM1`).
- Match by USB vendor/product ID + serial number.
- Install script to copy rules to `/etc/udev/rules.d/`.
- Docker device pass-through updated for new device names.

---

### TASK 18 — AI Assistant (`porter_ai_assistant`) — Phase 4.5

**Location:** `src/porter_ai_assistant/`

**Goal:** On-device LLM for smart airport passenger assistant running on RPi 4/5.

**Model:** Qwen 2.5 1.5B Instruct — fine-tuned with LoRA for airport domain.

**Package type:** `ament_python` (Python)

**Subtasks:**

| # | Subtask | Description |
|---|---------|-------------|
| 18a | Dataset curation | Collect/curate airport Q&A training data (gates, terminals, directions, flights, services, dining, accessibility, multilingual) |
| 18b | Model selection & baseline | Evaluate model candidates, run baseline benchmarks on RPi, measure latency/memory |
| 18c | LoRA fine-tune | Fine-tune with LoRA adapter on airport domain dataset |
| 18d | Quantization | Quantize model (INT4/INT8 GGUF) for RPi inference via llama.cpp or ONNX Runtime |
| 18e | ROS 2 service node | Build `porter_ai_assistant` ament_python package with service interface |
| 18f | Integration & benchmarks | Integrate with GUI pipeline, benchmark latency < 2s on RPi 4, accuracy on test set |

**Package structure:**
```
src/porter_ai_assistant/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/porter_ai_assistant
├── porter_ai_assistant/
│   ├── __init__.py
│   ├── assistant_node.py          ← ROS 2 service node
│   ├── inference_engine.py        ← Model loading + inference (llama.cpp / ONNX)
│   ├── prompt_templates.py        ← Airport-specific prompt engineering
│   └── config.py                  ← Model paths, generation params
├── models/                        ← Git LFS tracked (quantized GGUF/ONNX)
│   └── .gitkeep
├── data/
│   ├── airport_qa_train.jsonl     ← Training dataset
│   ├── airport_qa_eval.jsonl      ← Evaluation dataset
│   └── system_prompts.yaml        ← System prompt templates
├── scripts/
│   ├── finetune.py                ← LoRA fine-tuning script
│   ├── quantize.py                ← Model quantization script
│   ├── benchmark.py               ← Latency/accuracy benchmarks
│   └── convert_to_gguf.py         ← HF → GGUF conversion
├── launch/
│   └── assistant_launch.py
├── config/
│   └── assistant_params.yaml
└── test/
    ├── test_flake8.py
    ├── test_pep257.py
    └── test_assistant.py
```

**ROS 2 interfaces:**
- Service: `~/query` (custom `AiQuery.srv` — request: `string query`, `string context`; response: `string answer`, `float32 latency_ms`, `bool success`)
- Service: `~/get_status` (Trigger — model loaded, memory usage, avg latency)
- Topic: `/porter/ai_response` (String — for GUI display integration)
- Parameters: `model_path`, `max_tokens`, `temperature`, `top_p`, `system_prompt`, `device` (cpu/gpu)

**Constraints:**
- Must run on RPi 4 (4 GB RAM) — model + runtime < 2 GB RSS.
- Inference latency < 2 seconds per response.
- Use venv for AI/ML dependencies (NOT system Python — see §14.7).
- Model files stored via Git LFS (see §12.4).
- Multi-language support (English primary, expandable).

---

## 11. Documentation Standards

### 11.1 CHANGES.md (Change Log)

Every change must be a numbered section with:

```markdown
## N. Short Title

**File(s):** `path/to/file`

**Problem:** What was wrong and why it matters.

### Before
```<lang>
<exact code before the change>
```

### After
```<lang>
<exact code after the change>
```

**Why:** Technical rationale linking the fix to the problem.
```

Rules:
- One section per logical change — even if it touches multiple files.
- Show 5–15 lines of surrounding context in Before/After.
- Never delete old entries — append-only, chronological.
- Same commit for code change + CHANGES.md entry.

### 11.2 README.md Structure

```markdown
# Porter Robot

One-paragraph summary of the robot and its capabilities.

## Quick Start (Docker)
## System Architecture
  ### Hardware
  ### Software Stack
  ### TF Tree (ASCII)
  ### Topic Flow (ASCII)
## Native Build (Without Docker)
## Packages (table)
## Configuration Files (table)
## Development
## Testing
```

Docker instructions come **before** native build. All code blocks must be copy-pasteable.

### 11.3 DevLogs

Continue the pattern in `DevLogs/`. Each session gets a dated file:
- `DevLogs/25_Feb_Logs.md` — existing
- `DevLogs/28_Feb_Logs.md` — next session, etc.

---

## 12. Git & Commit Conventions

### 12.1 Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, tested, deployable |
| `prototype` | Current development (lidar company variant) |
| `simulation` | Simulation work (from prototype if needed) |
| `feat/ydlidar-driver` | Feature: C++ driver implementation |
| `feat/health-monitor` | Feature: diagnostics & health |
| `feat/lidar-processor` | Feature: Python processing layer |
| `ci/docker` | CI / Docker improvements |

### 12.2 Commit Messages (Conventional Commits)

```
<type>(<scope>): <short description>

<body — what and why, not how>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`
**Scopes:** `ydlidar-driver`, `lidar-processor`, `orchestrator`, `docker`, `launch`, `config`, `ci`

**Porter examples:**
```
feat(ydlidar-driver): add serial health check with 3-retry backoff
fix(ydlidar-driver): handle missing baseplate info as non-fatal
perf(lidar-processor): reduce median filter window for RPi 5
build(docker): fix COPY path for package.xml glob in Dockerfile.dev
docs: add 25 Feb devlog with hardware investigation results
test(ydlidar-driver): add GoogleTest for packet checksum validation
ci: add GitHub Actions workflow for colcon build + test
```

### 12.3 Rules

- Every commit must leave the workspace in a **buildable** state.
- Run `colcon test` before pushing.
- Update CHANGES.md in the same commit as the code change.
- Tag releases with semver: `v0.1.0`, `v0.2.0`, etc.

### 12.4 Git LFS (Large File Storage)

Git LFS is configured for AI/ML model files. The `.gitattributes` at repo root tracks:

| Extension | Use Case |
|-----------|----------|
| `.bin` | General model binaries, tokenizers |
| `.pt` / `.pth` | PyTorch checkpoints |
| `.onnx` | ONNX Runtime models |
| `.gguf` / `.ggml` | llama.cpp quantized models |
| `.safetensors` | HuggingFace safe format |
| `.h5` | Keras/TensorFlow |
| `.tflite` | TensorFlow Lite (RPi) |
| `.pkl` | Pickled objects/datasets |
| `.model` / `.weights` | Generic model files |
| `.npz` | NumPy arrays (embeddings) |

**Rules:**
- **Never** commit model files without Git LFS installed (`git lfs install`).
- Store models under `porter_robot/src/porter_ai_assistant/models/` (gitignored locally, LFS-tracked when pushed).
- Maximum file size on GitHub free LFS: **2 GB per file**, **1 GB storage** (upgrade if needed).
- Use `git lfs ls-files` to verify tracked files before pushing.
- Quantized models (GGUF/ONNX/TFLite) preferred over full-precision for RPi deployment.

```bash
# Verify LFS is active
git lfs install
git lfs ls-files

# Track a new extension
git lfs track "*.new_ext"
git add .gitattributes
```

### 12.5 Useful Git Commands

```bash
# Rename prototype → simulation (if needed)
git fetch origin prototype:simulation
git push origin simulation
git push origin --delete prototype

# Standard feature branch flow
git checkout -b feat/ydlidar-driver
# ... work ...
git push origin feat/ydlidar-driver
```

---

## 13. CI/CD Pipeline

### 13.1 GitHub Actions Workflow

```yaml
# .github/workflows/ros2-ci.yml
name: Porter ROS 2 CI
on: [push, pull_request]

jobs:
  build-and-test:
    runs-on: ubuntu-24.04
    container:
      image: ros:jazzy
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: |
          apt-get update
          rosdep update
          rosdep install --from-paths src --ignore-src -r -y

      - name: Build
        run: |
          source /opt/ros/jazzy/setup.bash
          colcon build --cmake-args -Wno-dev

      - name: Test
        run: |
          source /opt/ros/jazzy/setup.bash
          source install/setup.bash
          colcon test --event-handlers console_direct+
          colcon test-result --verbose

  docker-build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Build dev image
        run: docker compose -f docker/docker-compose.dev.yml build
```

### 13.2 Pre-Commit Hooks (recommended)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-xml
  - repo: https://github.com/PyCQA/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: ['--max-line-length=99']
```

---

## 14. Workflow Rules for Claude

### 14.1 When Making Changes

1. **Understand before editing.** Read relevant files, launch files, configs. Trace TF tree and topic flow.
2. **One logical change at a time.** Don't bundle unrelated fixes.
3. **Preserve existing patterns.** Match the code style, naming, and structure already in the project.
4. **Test after every change:**
   - C++: `colcon build --packages-select ydlidar_driver` must succeed.
   - Python: `colcon test --packages-select porter_lidar_processor` must pass.
   - Docker: `docker compose -f docker/docker-compose.dev.yml build` must succeed.
5. **Update documentation atomically:**
   - Code change → CHANGES.md entry (same commit).
   - New feature → README.md update.

### 14.2 When Creating New Packages

1. Follow package structure from §8.2 (C++) or §8.3 (Python).
2. Add standard lint test files (`test_flake8.py`, `test_pep257.py` for Python).
3. Register all nodes as entry points in `setup.py` (Python) or `CMakeLists.txt` (C++).
4. Ensure the package is discoverable by `rosdep` and `colcon`.

### 14.3 When Modifying Dockerfiles

1. Minimise layer count — combine related `RUN` commands.
2. Order layers by change frequency: base deps → system pkgs → source copy → build.
3. Update both dev and prod Dockerfiles if the change affects dependencies.
4. Test: `docker compose -f docker/docker-compose.dev.yml build` from repo root.

### 14.4 When Modifying Launch Files

1. Never hard-code paths — use `get_package_share_directory()`.
2. Every parameter override must trace to a config YAML or `DeclareLaunchArgument`.
3. Verify TF tree remains connected (§8.6).
4. Test with `ros2 launch <pkg> <launch>.py --show-args`.

### 14.5 When Fixing TF Issues

1. Draw the expected tree: `map → odom → base_link → laser_frame`.
2. Ensure exactly **one** publisher per transform.
3. Use standard frame IDs (§8.5).
4. Validate with `ros2 run tf2_tools view_frames`.

### 14.6 When Optimizing Performance

1. **Measure first** — `ros2 topic hz`, `htop`, `perf`.
2. Document baseline in CHANGES.md.
3. Change one parameter at a time, measure again.
4. Record before/after metrics.
5. Prefer parameter tuning over code changes.

### 14.7 Python Environment Rules

1. **ROS 2 Python packages** (rclpy nodes, ament_python packages): use the **system Python** managed by ROS 2 / colcon. Do **not** create a venv — colcon and rosdep manage dependencies.
2. **Non-ROS Python work** (AI/ML, data analysis, standalone scripts, pip-only libraries): **always use a venv.**

```bash
# Create venv (once)
python3 -m venv /home/antony-austin/Porter-ROS/porter_robot/.venv
source /home/antony-austin/Porter-ROS/porter_robot/.venv/bin/activate

# Install packages inside venv
pip install <package>

# Deactivate when done
deactivate
```

3. **Never run `pip install --break-system-packages`** — if you need pip, you need a venv.
4. Add `.venv/` to `.gitignore` (already there).
5. If a future AI/ML integration package is needed (e.g., PyTorch, TensorFlow, OpenCV custom builds), create the venv and document dependencies in a `requirements.txt`.

---

## 15. Known Issues & Gotchas

| Issue | Detail | Mitigation |
|-------|--------|------------|
| Jazzy typed params | `declare_parameter("name")` without type → compile error | Always `declare_parameter<T>("name", default)` |
| Health code `ffffffff` | Official ydlidar_ros2 driver fails to read health | Our driver: 3 retries + exponential backoff + robust error handling |
| Missing baseplate info | Some S2PRO/YD-47 units don't report baseplate reliably | Treat as non-fatal if scan data arrives OK |
| Docker context path | Building from `docker/` breaks `rosdep` | Always build from `porter_robot/` root |
| Dockerfile.dev COPY glob | `../src/*/package.xml` may not glob correctly | Fix to `src/*/package.xml` relative to context root |
| Empty git folders | Git ignores empty directories | Use `.gitkeep` files |
| Old ydlidar_ros2 code | Uses deprecated Humble APIs, won't compile on Jazzy | Write fresh driver code, do not copy-paste |
| CI `source: not found` | `ros:jazzy` container defaults to `sh` (dash), not `bash` | Always set `shell: bash` in GitHub Actions `defaults.run` when using ROS 2 containers |
| CI rosdep `ament_python` | `ament_python` is a build type, not a rosdep system key | Add `--skip-keys="ament_python"` to `rosdep install` |
| colcon discovers Zephyr firmware | `esp32_firmware/` has `CMakeLists.txt` with `find_package(Zephyr)` | Add `COLCON_IGNORE` marker to non-ROS directories containing CMakeLists.txt |
| `osrf/ros:jazzy-ros-base` 404 | Docker Hub doesn't have `osrf/` prefix for `-ros-base` images | Use `ros:jazzy-ros-base` (official library). Only `osrf/ros:jazzy-desktop` has `osrf/` prefix. |
| BuildKit apt cache lock | Multi-stage Dockerfile with shared `--mount=type=cache,target=/var/cache/apt` | Give each stage a unique `id`: `--mount=type=cache,id=apt-build,...` / `id=apt-runtime,...` |
| Zephyr SDK toolchain URL format | Filename is `toolchain_<platform>_<toolchain>.tar.xz`, not `toolchain_<toolchain>_<platform>` | Verify against GitHub Releases API. Pin exact filenames in CI workflows. |
| Toolchain tarball in SDK dir | `wget` inside SDK dir → cmake globs `.tar.xz` as toolchain → `CROSS_COMPILE` broken | Download to `/tmp`, extract with `-C ~/zephyr-sdk-VERSION/`, then `rm` the tarball |
| ESP32 board name vs Zephyr version | HWMv2 qualified names (`esp32_devkitc/esp32/procpu`) don't exist in Zephyr 4.0.0 | Zephyr 4.0.0: `esp32_devkitc_wroom`. Zephyr ≥4.1: `esp32_devkitc_wroom/esp32/procpu`. |
| SMF API varies by Zephyr version | `enum smf_state_result` / `SMF_EVENT_HANDLED` don't exist in Zephyr 4.0.0 | Zephyr 4.0.0: handlers return `void`. Zephyr ≥4.1: return `enum smf_state_result`. Pin version. |
| TRL 0.29.0 breaks `SFTConfig` / `SFTTrainer` API | `max_seq_length` → `max_length`, `tokenizer` → `processing_class` | Check `inspect.signature()` when upgrading TRL. They break backward compat without deprecation warnings. |
| Gemma 3 chat template rejects `tool` role | `TemplateError: Conversation roles must alternate user/assistant/...` | Merge `assistant→tool→assistant` into single assistant with `<tool_response>` XML tags. |
| CUDA OOM with 262K vocab model | Logits tensor `batch×seq×262144` dominates VRAM, not model weights | Enable gradient checkpointing + small batch (2–4) for large-vocab models. |
| `device_map="auto"` CPU offload on single GPU | Silently offloads layers to CPU → ~40% GPU utilization | Use `device_map={"": 0}` for single-GPU QLoRA. Reduce batch if OOM. |
| AI `n_threads=0` starves SLAM on RPi | llama.cpp auto-detect uses ALL 4 cores → SLAM/Nav2 get zero CPU during inference | Set `n_threads=2`, Docker `cpus: 2.0`, `PORTER_NICE=10`. Never auto-detect on 4-core RPi with nav stack running. |
| AI `n_ctx=2048` wastes RAM on RPi 4 | Airport Q&A rarely exceeds 800 tokens; 2048 wastes ~28 MB | Set `n_ctx=1024`. Increase only if RAG context + conversation exceeds 800 tokens. |
| `flash_attn` slower on x86 AVX512 | 17% slower in benchmarks (882ms vs 745ms) | Disabled by default. Test on ARM NEON (RPi 5) at deployment. |

### 15.1 Lessons Learned (bugs fixed during development)

These are mistakes made and fixed during driver development. **Never repeat them.**

| # | Mistake | Why It Broke | Correct Approach |
|---|---------|-------------|-----------------|
| 1 | Called `getDeviceInfo()` between `initialize()` and `turnOn()` | Extra serial command corrupted protocol state on single-channel LIDARs. `turnOn()` → "Failed to start scan mode -1" | **Never** send extra SDK serial commands between `initialize()` and `turnOn()`. The SDK already queries device info during `initialize()`. |
| 2 | No retry logic on `turnOn()` / `start_scan()` | Motor needs ~1s to spin up. First scan command can fail on cold start. | Always retry `turnOn()` with exponential backoff (1s → 2s → 4s). The SDK's internal single retry is not enough. |
| 3 | Called `rclcpp::shutdown()` directly inside ROS 2 node constructor | Destroys RCL context while node is still being constructed → `RCLError: failed to create guard condition: the given context is not valid` | **Never** call `rclcpp::shutdown()` from a constructor. Use a deferred wall timer (e.g. 100ms) to schedule shutdown after construction completes. |
| 4 | Set `singleChannel: false` for X4 Pro / S2PRO LIDAR | Single-channel devices use one-way comms. With `singleChannel=false`, the SDK sends commands and waits for response headers that **never come** → every command times out (health, device info, scan start). | **X4, X4 Pro, X2, X2L, S2, S4, S4B** are single-channel → `singleChannel: true`. **G4, G4 Pro, G6, G7, F4 Pro, TG series** are dual-channel → `singleChannel: false`. Always match this to the LIDAR model. When in doubt, `tri_test` asks "one-way communication?" — answer must match. |
| 5 | Used `rclcpp::SensorDataQoS()` (BEST_EFFORT) for `/scan` publisher | RViz2's LaserScan display subscribes with RELIABLE QoS → policy mismatch → no data shown, logs "incompatible QoS RELIABILITY_QOS_POLICY" | Use `rclcpp::SensorDataQoS().reliable()` — overrides to RELIABLE while keeping KEEP_LAST and small queue depth. Compatible with both RViz2 and Nav2. |
| 6 | Wrong import ordering in ament_python packages | `ament_flake8` uses `isort` with `force_sort_within_sections=true` — it sorts **all** imports (both `import X` and `from X import Y`) alphabetically by module name, ignoring the `import`/`from` keyword. `porter_lidar_processor` < `rclpy` < `sensor_msgs` < `std_srvs`. | Sort all imports strictly alphabetically by module name within each group (stdlib → third-party → local). `from porter_lidar_processor.filters import ...` comes **before** `import rclpy` because `p` < `r`. Never assume `import` statements precede `from` statements. |
| 7 | Used `"NaN"` as the first word of a docstring | `pep257 D403` requires the first word to be "properly capitalized" — `NaN` is not recognized as a capitalized word by the checker. | Start docstrings with a standard capitalized word (e.g. `"Verify NaN values..."` instead of `"NaN values..."`). D403 checks the literal first character is uppercase and the second is lowercase. Acronyms/abbreviations as the first word will fail. |
| 8 | Used Google-style `Returns:` section headers in docstrings | `pep257` checks D213 (summary at second line), D406 (section name newline), D407 (dashed underline), D413 (blank after last section) — these enforce numpy-style section formatting that conflicts with simple Google-style. | Add `D213,D406,D407,D413` to the pep257 ignore list in `test_pep257.py` when using Google-style docstrings: `main(argv=['--add-ignore', 'D100,D104,D213,D406,D407,D413'])`. Alternatively, switch to numpy-style with dashed underlines. |
| 9 | State machine transitioned immediately on first health status (including STALE) | DDS discovery takes 1–5+ seconds. Health monitor publishes STALE before discovering `/diagnostics` and `/scan` publishers. State machine saw STALE ≠ UNKNOWN → entered HEALTH_CHECK → saw STALE/ERROR → entered ERROR → recovery loop. All within ~2s, never giving DDS time to discover. | Add a **boot grace period** (`boot_grace_sec=8`) — state machine stays in DRIVER_STARTING and ignores non-OK health until grace elapses (or immediately advances if OK arrives early). Add **patience window** (`health_check_patience_sec=10`) in HEALTH_CHECK to tolerate STALE/WARN before declaring failure. Also match `/scan` subscription QoS to the publisher's RELIABLE + KEEP_LAST profile. |
| 10 | Health monitor used `frequency` (motor target) as expected scan rate | The `frequency: 10.0` parameter sets the motor target (10 Hz), but the S2PRO's actual scan delivery rate is ~3.85 Hz (5K sample rate ÷ 1300 points per revolution). The health freq check: 3.8 / 10.0 = 0.38 < `freq_error_ratio` (0.5) → permanent ERROR even though the LIDAR is operating normally. | Add a separate `health_expected_freq` parameter (default 0.0 = use `frequency`). Set `health_expected_freq: 4.0` in YAML for S2PRO to match the actual scan delivery rate. This decouples the motor speed target from the health monitor expectation. Never assume the SDK scan delivery rate equals the motor target frequency — single-channel LIDARs with high point counts per revolution will have lower delivery rates. |
| 11 | Invalid point warn threshold too low for indoor use (30%) | Indoor S2PRO scans naturally have ~33% invalid/out-of-range points (walls at varying distances, glass, open spaces). `health_invalid_warn_ratio: 0.3` triggered permanent WARN. 5 consecutive WARNs in the Python health monitor escalated to ERROR after just 2.5s. | Raised `health_invalid_warn_ratio` from 0.3 → **0.5** and `health_invalid_error_ratio` from 0.6 → **0.8**. Also raised `warn_consecutive_limit` from 5 → **20** (10s at 2 Hz) to prevent steady-state environmental WARNs from escalating. Indoor LIDARs commonly see 30–40% invalid points — that's normal operation, not a health concern. |
| 12 | GitHub Actions CI used default shell (`sh`) in `ros:jazzy` container | `ros:jazzy` image sets `sh` (dash) as default shell. `source` is a bash builtin — dash doesn't have it. Every step calling `source /opt/ros/jazzy/setup.bash` failed with exit code 127. | **Always** add `shell: bash` to `defaults.run` (or per-step) in GitHub Actions workflows that use ROS 2 container images. The ROS 2 setup scripts are bash scripts and require bash. |
| 13 | rosdep tried to resolve `ament_python` as a system package | `<buildtool_depend>ament_python</buildtool_depend>` in `package.xml` is a build type declaration, not a system dependency. rosdep has no key for it → error message (non-fatal with `-r`). | Add `--skip-keys="ament_python"` to `rosdep install`. This is standard for ament_python packages — the build type is already part of the ROS 2 installation. |
| 14 | colcon discovered ESP32 Zephyr firmware directory as a ROS 2 package | `esp32_firmware/motor_controller/CMakeLists.txt` calls `find_package(Zephyr)`. colcon auto-discovers any directory with `CMakeLists.txt` or `package.xml`. Zephyr SDK not in CI → CMake error → cascading build failure. | Add `COLCON_IGNORE` marker file to any directory under the workspace that contains CMakeLists.txt but is **not** a ROS 2 package (e.g. Zephyr firmware, third-party libs). |
| 15 | `CONFIG_ZTEST_NEW_API=y` in prj.conf | Zephyr 4.3.x made the new Ztest API the default. The Kconfig symbol no longer exists → build warning `Symbol ZTEST_NEW_API is not defined`. | **Remove** `CONFIG_ZTEST_NEW_API=y` from all Ztest `prj.conf` files when using Zephyr ≥ 4.1. The new API (`ZTEST_SUITE`, `ZTEST` macros) is always enabled. |
| 16 | `ZTEST_SUITE` called with 5 arguments | Zephyr 4.3.x `ZTEST_SUITE` macro requires exactly 6 args: `(name, predicate, setup, before, after, teardown)`. Missing the teardown arg → compile error. | Always use all 6 args: `ZTEST_SUITE(suite_name, NULL, NULL, NULL, NULL, NULL);`. Don't rely on old examples that omit teardown. |
| 17 | Duplicate `LOG_MODULE_REGISTER` in transport.c | Transport.c had `LOG_MODULE_REGISTER(transport, LOG_LEVEL_INF)` both in the shared Zephyr section (line 29) and inside the mock backend section (line 50). Both expand to the same linker symbol `log_const_transport` → redefinition error. | **One** `LOG_MODULE_REGISTER` per `.c` file, placed at file scope. Backend-specific sections share the same log module — never register the same module name twice. |
| 18 | Zephyr venv active during `colcon build` | CMake cached `~/zephyrproject/.venv/bin/python3` which lacks `catkin_pkg`, `ament_package`, etc. colcon build fails with `No module named 'catkin_pkg'`. Even after deactivating, CMake cache retains the wrong Python. | **Always** deactivate Zephyr venv before colcon: `deactivate 2>/dev/null`. If already polluted, **delete** `build/`, `install/`, `log/` to clear CMake cache. Never mix Zephyr and ROS 2 builds in the same shell session. |
| 19 | ESP32 `#pwm-cells` mismatch in devicetree overlay | Used `#pwm-cells = <2>` for LEDC PWM, but Zephyr's ESP32 LEDC binding requires `#pwm-cells = <3>` (channel, period, flags). Build error: `node has #pwm-cells = 2, expected 3`. | Always check the binding YAML (`dts/bindings/pwm/espressif,esp32-ledc.yaml`) for the correct `#pwm-cells` value. ESP32 LEDC uses 3 cells: channel, period (ns), flags. |
| 20 | SMF state handler return type varies by Zephyr version | Initially used `void` for SMF handlers → failed on local Zephyr 4.x which had `enum smf_state_result`. Fixed to return `SMF_STATE_HANDLED`. Then CI ran Zephyr 4.0.0 where `enum smf_state_result` / `SMF_EVENT_HANDLED` **don't exist yet** → `void` is correct for 4.0.0. | **Check the target Zephyr version.** Zephyr 4.0.0: SMF handlers return `void`. Zephyr ≥4.1: handlers return `enum smf_state_result`. Pin your `ZEPHYR_VERSION` in CI and match the API. Never assume the local dev version matches CI. |
| 21 | SMF state array forward declaration in C++ | C++ linkage mangling breaks SMF's `extern const struct smf_state states[]`. The `SMF_CREATE_STATE` macro expects C linkage for the state array. | Use `extern "C"` block around state arrays and handler declarations, or declare with `extern const struct smf_state xxx[];` forward declaration before use in C++ files. |
| 22 | ESP32 ADC node disabled by default in devicetree | ADC peripheral nodes in ESP32 devicetree are `status = "disabled"` by default. Overlay only set channel properties but didn't enable the ADC node → driver init fails silently. | Always add `status = "okay";` to ADC nodes in the app overlay. Check `esp32_devkitc.dts` for default status of all peripherals. |
| 23 | ament_copyright only recognizes `//` comment style for Apache 2.0 | Used `/* ... */` block comments for copyright headers in C++ files. `ament_copyright` test regex only matches `// Copyright` format → fails even with correct copyright text. | Use `//` line comments for copyright/license headers in C++ files: `// Copyright 2026 VirtusCo` followed by `//` Apache 2.0 boilerplate. Never use `/* */` blocks for copyright headers in ament packages. |
| 24 | `osrf/ros:jazzy-ros-base` Docker image doesn't exist | Dockerfile.prod used `osrf/ros:jazzy-ros-base` for the runtime stage. Image doesn't exist on Docker Hub — only `osrf/ros:jazzy-desktop` has the `osrf/` prefix. | Use `ros:jazzy-ros-base` (official library image, no `osrf/` prefix) for the minimal runtime base. Use `osrf/ros:jazzy-desktop` for dev. Always `docker manifest inspect` to verify image existence before committing. |
| 25 | BuildKit apt cache lock contention in multi-stage Dockerfile | Two stages sharing `--mount=type=cache,target=/var/cache/apt` without unique IDs. BuildKit runs stages in parallel → both `apt-get install` commands fight over `/var/cache/apt/archives/lock` → exit code 100. | Give each stage a unique cache `id`: `--mount=type=cache,id=apt-build,target=/var/cache/apt` (build stage) and `--mount=type=cache,id=apt-runtime,target=/var/cache/apt` (runtime stage). |
| 26 | Zephyr SDK toolchain filename format | Used `toolchain_xtensa-espressif_esp32_zephyr-TOOLCHAIN_linux-x86_64.tar.xz` — 404 on GitHub. The Zephyr SDK 0.17.0 naming convention puts the **platform before the toolchain**: `toolchain_linux-x86_64_xtensa-espressif_esp32_zephyr-elf.tar.xz`. Suffix is `zephyr-elf`, not `zephyr-TOOLCHAIN`. | Always verify download URLs against the GitHub Releases API: `curl -sL "https://api.github.com/repos/zephyrproject-rtos/sdk-ng/releases/tags/v0.17.0" \| jq '.assets[].name'`. Pin exact filenames in CI. |
| 27 | Toolchain tarball downloaded inside Zephyr SDK directory | `wget` ran after `cd ~/zephyr-sdk-0.17.0/`, downloading `.tar.xz` **into** the SDK dir. SDK's cmake globs `*xtensa-espressif_esp32*` and matched the tarball file as a toolchain path → `CROSS_COMPILE` pointed at `.tar.xz/bin/` → compiler not found. | Always download toolchain tarballs to `/tmp`, then `tar xf ... -C ~/zephyr-sdk-VERSION/`, then `rm` the tarball. Never `wget` inside the SDK directory. |
| 28 | ESP32 board name format depends on Zephyr version | Used `esp32_devkitc/esp32/procpu` (HWMv2 qualified format) — doesn't exist in Zephyr 4.0.0. Used `esp32_devkitc_wroom` — works but triggers deprecation warning in 4.0.0 (auto-changed to qualified form). | For Zephyr 4.0.0: use `esp32_devkitc_wroom` (flat name, gets auto-qualified with deprecation warning). For Zephyr ≥4.1: use `esp32_devkitc_wroom/esp32/procpu` (HWMv2 qualified). Match the board name to your pinned `ZEPHYR_VERSION`. |
| 29 | TRL `SFTConfig` API changed in v0.29.0 — `max_seq_length` removed | `SFTConfig.__init__() got an unexpected keyword argument 'max_seq_length'`. TRL 0.29.0 renamed the parameter. Old examples and tutorials all use `max_seq_length`. | Use `max_length` (not `max_seq_length`) in `SFTConfig` for TRL ≥0.29.0. Always check the actual API with `inspect.signature(SFTConfig)` when upgrading TRL — they break backwards compatibility frequently. |
| 30 | TRL `SFTTrainer` no longer accepts `tokenizer` kwarg | `SFTTrainer.__init__() got an unexpected keyword argument 'tokenizer'`. TRL 0.29.0 unified the interface. | Use `processing_class=tokenizer` instead of `tokenizer=tokenizer` in `SFTTrainer` for TRL ≥0.29.0. The old `tokenizer` parameter was removed without deprecation warning. |
| 31 | Gemma 3 chat template rejects `tool` role in conversations | Tool_use dataset had `system → user → assistant → tool → assistant` role sequence. Gemma 3's Jinja2 chat template enforces strict `user/assistant` alternation after system — `tool` role triggers `TemplateError: Conversation roles must alternate user/assistant/user/assistant/...` | Merge `assistant(tool_call) → tool(result) → assistant(response)` into a **single assistant message** with `<tool_response>` XML tags: `"<tool_call>\n{json}\n</tool_call>\n\n<tool_response>\n{result}\n</tool_response>\n\n{final_answer}"`. Always validate dataset role sequences against the target model's chat template before training. |
| 32 | CUDA OOM with 262K vocab model even at small batch size | Gemma 3 has a 262,144-token vocabulary. The logits tensor for cross-entropy loss is `batch × seq_len × vocab_size` — at batch=4, seq_len=512, that's **4 × 512 × 262144 × 2 bytes = 1 GB** in bf16, plus gradients. With batch=8 and no gradient checkpointing, it OOMs on 8 GB VRAM. | For large-vocab models (Gemma 3 262K, Llama 3 128K), **always enable gradient checkpointing** and use **small batch sizes** (2–4). The vocab size dominates VRAM usage at the loss computation step, not the model weights. Compensate with higher `gradient_accumulation_steps` to maintain effective batch size. |
| 33 | `device_map="auto"` silently offloads layers to CPU on single-GPU | `accelerate`'s `device_map="auto"` partitions across all available devices including CPU. On a single GPU, it may offload embedding/lm_head layers to CPU if VRAM is tight, causing slow CPU↔GPU transfers and ~40% GPU utilization. | Use `device_map={"": 0}` (force everything to GPU 0) for single-GPU QLoRA training. The 4-bit quantized model is small enough to fit entirely. If OOM occurs, reduce batch size rather than allowing CPU offloading — CPU offload makes training 3–5× slower. |
| 34 | Tool_use system prompt too long for `max_seq_length` | The full JSON tool schemas system prompt was **2491 tokens** but SFT training used `max_seq_length=512`. Every tool_use training example was truncated at 512 tokens — the model **never saw any user queries, `<tool_call>` tags, or assistant responses** during training. The "eval_loss=0.0001" was bogus (memorizing truncated prompt fragments). At inference, the model output garbage (repeating tool schemas or refusing). | **Always verify** that training `max_seq_length` exceeds the longest training example. For tool_use: create a **compact system prompt** (~350 tokens) listing tool signatures instead of full JSON schemas (~2500 tokens). The compact format `- tool_name(param1, param2?) - Description` preserves all necessary information while fitting within context. After fixing: tool_use went from 40% → **100%**. |
| 35 | DPO with fresh LoRA adapter produces zero gradients | `ref_model=None` + `peft_config` in TRL DPOTrainer creates a **new LoRA with B=0**. Policy model == reference model (both produce identical logprobs). DPO loss = log(sigmoid(0)) = 0.6931 (random). Gradients are exactly 0. LoRA weights never update. Trained for 339 steps with `loss=0.6931, logps/chosen=0, logps/rejected=0, grad_norm=0` across 4 different configurations. | Either (a) **load pre-trained SFT adapter** as the initial PeftModel (so policy ≠ reference from the start), or (b) use **full fine-tuning** without LoRA + explicit `ref_model=deepcopy(model)`. Never use DPO with a fresh zero-initialized LoRA and `ref_model=None`. |
| 36 | GRPO `merge_and_unload()` on 4-bit model degrades weights | `merge_and_unload()` on a 4-bit quantized model dequantizes weights (lossy), merges LoRA deltas, then the resulting bf16 weights lose quantization accuracy. Training a new LoRA on top of these degraded weights produces worse results than the original SFT adapter. | Never call `merge_and_unload()` on a 4-bit model and expect to train further on it. Either (a) merge in full precision (load model in bf16 first), or (b) train the new LoRA directly on top of the existing adapter chain. |
| 37 | Inference test used different tool names/format than training data | Test expected `get_flight_info`, `track_luggage`, `search_amenity` — none of these exist in training data (which uses `get_flight_status`, `weigh_luggage`, `find_nearest`). Test also used 5-tool simplified prompt vs 14-tool training prompt. Combined with putting system prompt in user message (vs proper system role). | **Always synchronize** inference test tool names, system prompts, and message formats with exact training data format. Create constants or load from shared config files rather than duplicating. |
| 38 | GGUF LoRA vocab assertion: tokenizer N+1 vs model N | `llama.cpp/convert_lora_to_gguf.py` asserts `tokenizer.vocab_size == model.vocab_size`. After QLoRA, the tokenizer may report 262,145 tokens (added pad token) vs model's 262,144. The assertion fires and conversion fails. | **Resize embeddings** before saving LoRA adapter: `model.resize_token_embeddings(len(tokenizer))`. Or use `--override-vocab-size` if the converter supports it. Always verify `tokenizer.vocab_size == model.config.vocab_size` before GGUF conversion. |
| 39 | AI persona name must be separate from robot product name | Renamed AI from "Porter" to "Virtue" — needed to update 16 files, 24K+ lines of training data. "Porter" still appears in hardware refs ("Porter's screen", "Porter robots"). The training data has both. | When naming an AI persona on a named product, keep them **distinct from day one**. Don't use the product name as the AI name — it creates thousands of ambiguous references. Training data, system prompts, user greetings, and self-identification all need consistent naming. |
| 40 | Flutter `GestureDetector` `onLongPress` requires competing `onTap` | Setting `onTap: null` when e-stop is engaged removes the tap recognizer from the gesture arena. Without a competing recognizer, Flutter's gesture disambiguator never triggers `onLongPress`. The long-press callback is silently never called — no errors, no logs. | **Always** provide `onTap: () {}` (no-op) alongside `onLongPress` in a `GestureDetector`. Setting `onTap: null` removes the tap recognizer entirely — the long press recognizer needs a competing tap to disambiguate against. This is a common Flutter pitfall with no compile-time or runtime warning. |
| 41 | Unused Flutter deps add 20+ transitive packages | `google_fonts` (unused — app uses system fonts) pulled 23 transitive packages. `cupertino_icons` was also unused (Material icons only). Together they added download time, build size, and dependency conflicts. | Audit `pubspec.yaml` regularly. Run `flutter pub deps` to see the full transitive tree. Remove any dep where no import exists in `lib/`. Even a single unused dep can pull dozens of transitive packages. |
| 42 | Flutter streaming rebuild rate directly controls CPU/memory | Initial streaming config (20ms/2chars) caused ~50 rebuilds/second per message. With 10+ messages visible, the widget tree rebuilt 500+ times/second — visible scroll jank on RPi. | Batch character reveals: 80ms interval, 8 chars per tick → ~12 rebuilds/second (75% reduction). Combine with `RepaintBoundary` around message bubbles, `AnimatedSize` for smooth growth, and capped message list (100 max) + smart auto-scroll (only when near bottom). |
| 43 | `ament_flake8` picks up auto-generated files in `build/` directory | After `colcon build`, `build/<pkg>/prefix_override/sitecustomize.py` is auto-generated with lines >99 chars (E501). `test_flake8.py` with `--exclude scripts` doesn't exclude `build/`. | Add `build` to the exclude list: `argv=['--exclude', 'scripts,build']`. Always exclude `build/`, `install/`, and `log/` directories in flake8 tests — they contain auto-generated code that doesn't follow project style rules. |
| 44 | `max_seq_length` truncation silently produces fake 100% accuracy | Tool_use training used `max_seq_length=512` but the full JSON-schema system prompt was ~2400 tokens. Every training example was truncated — the model **never saw any user queries, `<tool_call>` tags, or assistant responses**. eval_loss≈0.0 / 100% accuracy was bogus (memorizing truncated prompt fragments). At inference the model output conversational refusals instead of tool calls. | **Always verify** `max_seq_length` exceeds the longest training example. After fixing: compact prompt (~478 tokens) + `max_seq_length=1024` → tool_use went from 0% tool call generation → 98% accuracy. Lesson #34 warned about this exact scenario. |
| 45 | Tool-use inference needs tool schemas injected at server startup | `ai_server.py` never called `load_tool_schemas()` — `self._tool_schemas` was empty. The inference engine built a system prompt with zero tool definitions, so the model had no tool context and responded conversationally. | **Always** call `engine.load_tool_schemas(path)` at startup before loading the model. Without schemas, the compact tool prompt builder produces `system_prompt + "\n\nAvailable tools:\n"` with nothing after it — the model can't call tools it doesn't know about. |
| 46 | System prompt YAML must exactly match training data | The `tool_use:` prompt in `system_prompts.yaml` had extra "Guidelines" and formatting not present in training data. This distribution shift caused the model to ignore the tool-call format instruction and generate conversational refusals. | System prompts used at inference must be **character-for-character identical** to what was used during training. Copy the exact preamble from the training data generation script. Any additions (extra rules, guidelines, formatting) shift the prompt distribution and degrade tool-call compliance. |
| 47 | Compact tool prompt format: signature style, not full JSON | Full JSON schemas for 14 tools were ~2400 tokens (9106 chars). Compact format `- tool_name(param1, param2?) - Description` is ~478 tokens (1899 chars) — a 5× reduction. The model learns the calling convention equally well from either format but actually fits within training context. | Use `- name(required_param, optional_param?) - Short description` for tool prompts. Optional params get `?` suffix. This is human-readable, model-learnable, and fits dozens of tools in <500 tokens. Reserve full JSON schemas for runtime tool execution validation, not LLM prompting. |
| 48 | `_humanize_tool_response()` needed for GUI display | Raw `<tool_call>{"name":"get_flight_status","arguments":{"flight_number":"BA456"}}</tool_call>` is unusable in a passenger-facing GUI. Users expect natural language like "Checking flight status for BA456..." | Post-process tool call JSON at the server layer: extract tool name + args, format via template dict (`_TOOL_DISPLAY_NAMES`), and return the humanized string to the GUI. Keep the raw tool call for ROS 2 orchestrator consumption. |
| 49 | DPO with synthetic corruption data gives near-zero eval_loss | Synthetic preference pairs (strip_tags, ramble, wrong_json, echo) produce obviously-wrong rejections. DPO easily separates chosen/rejected → eval_loss=1e-6 to 1e-10. This doesn't mean the model is perfect — it means the preference task was trivially easy. Real human preferences would yield higher eval_loss but more meaningful alignment. | Use synthetic DPO for **format compliance** (tool tags, JSON structure, conciseness). Use human DPO for **quality alignment** (tone, accuracy, helpfulness). Near-zero eval_loss on synthetic data is expected and not a sign of overfitting — verify by benchmarking actual response quality against SFT baseline. |
| 50 | `precompute_ref_log_probs=True` essential for low-VRAM DPO | Without this flag, DPO keeps both policy and reference models in VRAM simultaneously. On 8 GB GPU with Qwen 2.5 1.5B in bf16, this OOMs. With `precompute_ref_log_probs=True`, TRL computes ref logprobs once (peak ~7.3 GB), saves to disk, then trains with only the policy model (~6.3 GB). | Always enable `precompute_ref_log_probs=True` and set `precompute_ref_batch_size=1` for DPO on <12 GB VRAM. The precompute pass takes extra time but prevents OOM. |
| 51 | Python `HTTPServer` blocks during SSE streaming | Single-threaded `HTTPServer` blocks all other requests while one client holds an SSE connection open. Health checks from Flutter hang, causing the GUI to show "server unavailable" even though inference is running fine. | Use `ThreadingHTTPServer` (from `http.server`) instead of `HTTPServer` for any server that handles SSE or long-lived connections. Each request gets its own thread. Alternatively, switch to an async framework (aiohttp, FastAPI) for production. |
| 52 | TF-IDF beats embeddings for small corpora on RPi | `sentence-transformers/all-MiniLM-L6-v2` adds ~80 MB model + ~200ms/query on RPi 4. For a 41-document airport knowledge base, TF-IDF with keyword boosting retrieves equally relevant results in <1ms with zero additional dependencies. | For small knowledge bases (<500 docs), TF-IDF + keyword boosting is sufficient and RPi-friendly. Reserve embedding models for >1000 docs or when semantic similarity matters more than keyword overlap. The crossover point depends on vocabulary diversity — airport FAQ content is keyword-rich and TF-IDF-friendly. |
| 53 | `n_threads=0` (auto-detect) starves SLAM on 4-core RPi | llama.cpp auto-detect uses ALL available cores. On RPi 4/5 (4 cores), inference grabs 100% CPU → SLAM/Nav2/LIDAR get zero CPU time → navigation halts during inference, potential collision risk. The 32-core dev machine masked this — 0 (auto) ≈ 16 threads still leaves plenty for other processes. | **Always set `n_threads=2`** on 4-core RPi to reserve 2 cores for safety-critical ROS 2 nodes (SLAM, Nav2, LIDAR). Only use `n_threads=0` (auto) when the AI runs standalone without navigation. Supplement with Docker `cpus: 2.0` hard cap and `nice -n 10` for defense-in-depth. |
| 54 | `n_batch=512` is 8× faster than `64` for prompt eval, `flash_attn` slower on x86 AVX512 | Benchmarked: `n_batch=64` → 780ms, `n_batch=512` → 745ms (identical RSS). `flash_attn=True` → 882ms (17% **slower** on x86 AVX512). `type_k=8/type_v=8` (q8_0 KV cache) crashes in llama-cpp-python 0.3.16. | Use `n_batch=512` (llama.cpp default) always. Keep `flash_attn=False` on x86 — may help on ARM NEON (RPi 5), needs testing on-device. KV cache quantization not yet supported in Python bindings — revisit when llama-cpp-python upgrades. |

---

## 16. References

| Resource | Link / Location |
|----------|----------------|
| **OBJECTIVES.md** | `OBJECTIVES.md` — Hardware arch, timeline, phases, technical decisions |
| **COMPANY.md** | `COMPANY.md` — VirtusCo context, founding team, product vision, market data, financials, competitors, Claude's engineering role |
| **Pitch Deck** | `VirtusCo Pitch Deck.pdf` (gitignored) — investor deck; key data extracted into `COMPANY.md` |
| **Skills (ROS 2 reference)** | `skills/` — 16 skill files covering full Jazzy docs, dev guide, code style, quality, release process |
| **Skills (Zephyr RTOS reference)** | `skills/zephyr/` — 12 skill files covering Zephyr kernel, devicetree, USB CDC ACM, ESP32, SMF, zbus |
| **ESP32 Firmware** | `esp32_firmware/` — Zephyr RTOS firmware for motor controller (ESP32 #1) and sensor fusion (ESP32 #2) with shared USB CDC protocol |
| Zephyr RTOS docs | https://docs.zephyrproject.org/latest/ |
| ESP32-DevKitC Board | https://docs.zephyrproject.org/latest/boards/espressif/esp32_devkitc/doc/index.html |
| 25 Feb DevLog | `DevLogs/25_Feb_Logs.md` — HW ID, architecture decision, Docker fix |
| 07 Mar DevLog | `DevLogs/07_Mar_Logs.md` — ydlidar_driver Tasks 1–4, RViz launch, 5 bugs fixed, hardware test pass |
| 10 Mar ESP32 DevLog | `DevLogs/10_Mar_ESP32_Logs.md` — Phase 3 Tasks 10–17, ESP32 firmware, bridge nodes, 247 total tests |
| 07 Mar CI/CD DevLog | `DevLogs/07_Mar_CICD_Logs.md` — CI/CD pipeline fixes: Docker image tags, Zephyr SDK URLs, board names, SMF API, apt cache locks |
| YDLidar SDK | Use `tri_test` for hardware verification. Baudrate `128000` confirmed. |
| ROS 2 Jazzy docs | https://docs.ros.org/en/jazzy/ |
| sensor_msgs/LaserScan | https://docs.ros.org/en/jazzy/p/sensor_msgs/interfaces/msg/LaserScan.html |
| REP-105 (Coordinate Frames) | https://www.ros.org/reps/rep-0105.html |
| Conventional Commits | https://www.conventionalcommits.org/ |
| 07 Mar AI DevLog | `DevLogs/07_Mar_AI_Logs.md` — Phase 4.5 Tasks 18a–18c, Gemma 3 270M (initial), 12K dataset, 22 tests |
| 08 Mar AI DevLog | `DevLogs/08_Mar_AI_Logs.md` — Phase 4.5 Tasks 18d–18f, GGUF quantization, benchmarks, Virtue rename |
| 08 Mar Model Switch DevLog | `DevLogs/08_Mar_Model_Switch_Logs.md` — Gemma 3 270M → Qwen 2.5 1.5B Instruct, 15 files updated |
| 08 Mar GUI/CI DevLog | `DevLogs/08_Mar_GUI_CICD_Logs.md` — Flutter perf optimization, CI/CD Flutter build, e-stop bug fix |
| 09 Mar Qwen Training DevLog | `DevLogs/09_Mar_Qwen_Training_Logs.md` — Qwen 2.5 1.5B LoRA training, GGUF conversion, benchmarks, 57 tests |
| 09 Mar Tool-Use Fix DevLog | `DevLogs/09_Mar_Tool_Use_Fix_Logs.md` — 3 root causes diagnosed, compact prompt retrain, GUI humanized responses |
| 09 Mar DPO Training DevLog | `DevLogs/09_Mar_DPO_Training_Logs.md` — DPO RL on both adapters, GGUF conversion, SFT vs DPO benchmark |
| 09 Mar SSE & RAG DevLog | `DevLogs/09_Mar_SSE_RAG_Logs.md` — Real-time SSE token streaming, RAG knowledge base retrieval (41 docs, TF-IDF), 30 RAG tests |
| 09 Mar CPU/SLAM DevLog | `DevLogs/09_Mar_CPU_SLAM_Optimization_Logs.md` — CPU inference benchmarks, SLAM coexistence: n_threads=2, n_ctx=1024, Docker resource caps, nice priority |
| Qwen 2.5 1.5B GGUF (Official) | `huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF` — Q4_K_M (~1.0 GB) primary model |
| Qwen 2.5 1.5B base | `huggingface.co/Qwen/Qwen2.5-1.5B-Instruct` — base model for fine-tuning |
| llama-cpp-python | `github.com/abetlen/llama-cpp-python` — GGUF inference runtime |
| GitHub Repo | `github.com/austin207/Porter-ROS` |

---

## 17. Quick Reference Card

```bash
# ─── Docker (from porter_robot/ root) ───────────────────
docker compose -f docker/docker-compose.dev.yml build     # Build dev image
docker compose -f docker/docker-compose.dev.yml up -d     # Start container
docker exec -it porter_dev bash                            # Shell in
docker compose -f docker/docker-compose.dev.yml down       # Stop

# ─── Build ───────────────────────────────────────────────
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --cmake-args -Wno-dev       # Full build
colcon build --packages-select ydlidar_driver              # Single pkg
source install/setup.bash                                   # Source overlay

# ─── Test ────────────────────────────────────────────────
colcon test --event-handlers console_direct+                # All tests
colcon test --packages-select ydlidar_driver                # Single pkg
colcon test-result --verbose                                # Results

# ─── Lint ────────────────────────────────────────────────
ament_cpplint src/ydlidar_driver/src/                      # C++ lint
ament_flake8 src/porter_lidar_processor/                   # Python lint

# ─── Run ─────────────────────────────────────────────────
ros2 run ydlidar_driver ydlidar_node --ros-args \
  -p port:=/dev/ttyUSB0 -p baudrate:=128000                # Driver
ros2 topic echo /scan                                       # Verify scan
ros2 topic hz /scan                                         # Check rate

# ─── Debug ───────────────────────────────────────────────
ros2 topic list                                             # Active topics
ros2 node list                                              # Active nodes
ros2 run tf2_tools view_frames                              # TF tree PDF
ros2 param dump /ydlidar_node                               # All params
```

---

## 18. Quick-Start for Claude Code

Issue these commands one at a time:

### Phase 1 — LIDAR Subsystem (Tasks 1–9) ✅ COMPLETE

1. **"IMPLEMENT TASK 1"** — Full `ydlidar_driver` C++ package skeleton. ✅
2. **"IMPLEMENT TASK 2"** — `YdLidarAdapter` SDK wrapper. ✅
3. **"IMPLEMENT TASK 3"** — LaserScan publishing. ✅
4. **"IMPLEMENT TASK 4"** — Diagnostics & health monitor. ✅
5. **"IMPLEMENT TASK 5"** — `porter_lidar_processor` Python package. ✅
6. **"IMPLEMENT TASK 6"** — Orchestration layer. ✅
7. **"IMPLEMENT TASK 7"** — Docker improvements. ✅
8. **"IMPLEMENT TASK 8"** — Tests & CI pipeline. ✅
9. **"IMPLEMENT TASK 9"** — Documentation. ✅

### Phase 3 — ESP32 Firmware & Bridge (Tasks 10–17) ✅ COMPLETE

10. **"IMPLEMENT TASK 10"** — CRC16-CCITT implementation (`esp32_firmware/common/`). ✅
11. **"IMPLEMENT TASK 11"** — Protocol parser & encoder (`esp32_firmware/common/`). ✅
12. **"IMPLEMENT TASK 12"** — Transport abstraction layer — UART vs CDC ACM via Kconfig. ✅
13. **"IMPLEMENT TASK 13"** — Motor controller firmware (SMF, PWM, differential drive, watchdogs). ✅
14. **"IMPLEMENT TASK 14"** — Sensor fusion firmware (ToF, Ultrasonic, Microwave, Kalman filter). ✅
15. **"IMPLEMENT TASK 15"** — Ztest unit tests (CRC, protocol, transport on `native_sim`). ✅
16. **"IMPLEMENT TASK 16"** — ROS 2 bridge nodes (`esp32_motor_bridge` + `esp32_sensor_bridge`). ✅
17. **"IMPLEMENT TASK 17"** — udev rules & stable device names. ✅

Or: **"IMPLEMENT TASKS 10-17"** to run ESP32 phase sequentially. ✅ ALL COMPLETE

### Phase 4.5 — AI Assistant (Task 18) ✅ COMPLETE

18a. **"IMPLEMENT TASK 18a"** — Dataset curation (airport Q&A training data). ✅
18b. **"IMPLEMENT TASK 18b"** — Model selection & baseline benchmarks. ✅
18c. **"IMPLEMENT TASK 18c"** — LoRA fine-tune on airport domain. ✅ Qwen: conv eval_loss=0.1365 (95.5% acc), tool_use eval_loss≈0 (100% acc)
18d. **"IMPLEMENT TASK 18d"** — GGUF quantization. ✅ Merged LoRA + Q4_K_M: 940 MB each (conv + tool_use)
18e. **"IMPLEMENT TASK 18e"** — ROS 2 service node with `/porter/ai_query` topic. ✅
18f. **"IMPLEMENT TASK 18f"** — Benchmarks. ✅ conv 1436ms/80% <2s, tool_use 1724ms/70% <2s, 1678 MB RSS, ~39 tok/s

**AI persona name: "Virtue"** (not "Porter" — Porter is the robot product name).
**Model: Qwen 2.5 1.5B Instruct** — QLoRA fine-tuned, merged GGUF. See DevLogs/09_Mar_Qwen_Training_Logs.md.

Or: **"IMPLEMENT TASK 18"** to run AI Assistant phase sequentially. ✅ ALL COMPLETE

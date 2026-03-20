# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Porter Robot is an autonomous luggage-carrying robot for airports, built by VirtusCo. It navigates terminals using LIDAR, carries luggage, and provides an on-device AI assistant ("Virtue") for passenger interaction — all running locally on a Raspberry Pi with no cloud dependency.

**Repo**: `github.com/austin207/Porter-ROS` | **Branch**: `prototype` (active development), `main` (stable) | **Version**: read from `porter_robot/VERSION`

## Repository Structure (Monorepo)

This is a monorepo with five major workspaces. Each has its own detailed `CLAUDE.md`:

- **`porter_robot/`** — ROS 2 Jazzy workspace (the robot software). See `porter_robot/CLAUDE.md` for 18 sections of detailed rules, 54 lessons learned, and task specifications.
- **`porter-vscode-extension/`** — TypeScript VS Code extension for firmware flashing and RPi deployment. See `porter-vscode-extension/CLAUDE.md` for extension architecture and commands.
- **`virtus-firmware-builder/`** — Visual node-based firmware development tool for ESP32/Zephyr. Drag-and-drop nodes → generates DTS overlay, prj.conf, C source. Scans Zephyr API headers to auto-generate nodes. See `virtus-firmware-builder/CLAUDE.md` and `USAGE_GUIDE.md`.
- **`virtus-ai-studio/`** — Complete MLOps workbench: train (YOLO/LLM/RL), benchmark, export (HEF/GGUF/ONNX), deploy to RPi+Hailo. See `virtus-ai-studio/CLAUDE.md`.
- **`virtus-ros2-studio/`** — Porter-specific ROS 2 dev environment: live topic monitor, node graph, 9-state FSM viewer, ESP32 CRC16 bridge debugger, n8n-style launch builder. See `virtus-ros2-studio/CLAUDE.md`.
- **`virtus-hardware-dashboard/`** — Live hardware telemetry: power rails, motor current, sensor readings, threshold alerts, power event log, schematic cross-reference. See `virtus-hardware-dashboard/CLAUDE.md`.
- **`virtus-simulation-manager/`** — Gazebo simulation: one-click launch profiles, URDF preview, Nav2 parameter editor (27 params), bag file manager, test scenario runner, world manager. See `virtus-simulation-manager/CLAUDE.md`.
- **`virtus-pcb-studio/`** — KiCad schematic viewer + visual PCB builder (14-component library), pinout sync checker, BOM with LCSC links, Git-based schematic diff, firmware impact analyzer. See `virtus-pcb-studio/CLAUDE.md`.
- **`virtusco-devtools-suite/`** — Master meta-extension: installs/manages all 7 sub-extensions, shared config, dependency checker, workspace bootstrapper, cross-extension event bus. See `virtusco-devtools-suite/CLAUDE.md`.
- **`.github/workflows/`** — CI/CD: `verify.yml` (9-job gate) and `build-release.yml` (6-job release pipeline).

## Build & Test Commands

### ROS 2 Workspace (primary — run from `porter_robot/`)

```bash
# Docker workflow (primary)
docker compose -f docker/docker-compose.dev.yml build
docker compose -f docker/docker-compose.dev.yml up -d
docker exec -it porter_dev bash

# Inside container — build
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --cmake-args -Wno-dev
source install/setup.bash

# Test all packages
colcon test --event-handlers console_direct+
colcon test-result --verbose

# Test single package
colcon test --packages-select ydlidar_driver
colcon test --packages-select porter_ai_assistant

# Build single package
colcon build --packages-select ydlidar_driver --symlink-install

# Clean rebuild
rm -rf build/ install/ log/
colcon build --cmake-clean-cache --symlink-install
```

### ESP32 Firmware (Zephyr RTOS — run from `porter_robot/`)

```bash
# Unit tests (native_sim, no hardware needed)
cd esp32_firmware && twister -T tests/ -p native_sim

# Cross-compile firmware
west build -b esp32_devkitc_wroom esp32_firmware/motor_controller -d build/motor -- -DBOARD_ROOT=.
west build -b esp32_devkitc_wroom esp32_firmware/sensor_fusion -d build/sensor -- -DBOARD_ROOT=.
```

### VS Code Extension (run from `porter-vscode-extension/`)

```bash
npm install
npm run compile     # Build TypeScript
npm run lint        # ESLint
npm run test        # Mocha tests
npx vsce package    # Package as .vsix
```

### Firmware Builder Extension (run from `virtus-firmware-builder/`)

```bash
npm install
npm run compile     # Build both extension host + webview bundles
npm run watch       # Watch mode for development
npm run lint        # ESLint
npm run package     # Package as .vsix
# Debug: F5 in VS Code to launch Extension Development Host
```

### Flutter GUI (run from `porter_robot/src/porter_gui/`)

```bash
flutter analyze
flutter test
flutter build linux --release
```

## Architecture Overview

### Hardware Stack

```
Raspberry Pi 5 (Master) — ROS 2 Jazzy, Nav2, Virtue AI, Touchscreen
├── YDLIDAR X4 Pro 360° (USB serial, 128000 baud)
├── ESP32 #1 (USB CDC) — Motor controller, BTS7960 H-bridge, differential drive
└── ESP32 #2 (USB CDC) — Sensor fusion: ToF + Ultrasonic + Microwave (Kalman)
```

### ROS 2 Topic Flow

```
YDLIDAR → ydlidar_driver →/scan→ porter_lidar_processor →/scan/processed→ Nav2
                            └→/diagnostics→ lidar_health_monitor →/porter/health_status→ state_machine
Nav2 →/cmd_vel→ esp32_motor_bridge → Serial → ESP32 #1
ESP32 #2 → Serial → esp32_sensor_bridge →/environment→ Nav2
GUI →/porter/ai_query→ porter_ai_assistant →/porter/ai_response→ GUI
```

### ROS 2 Packages (`porter_robot/src/`)

| Package | Lang | Build Type | Purpose |
|---------|------|------------|---------|
| `ydlidar_driver` | C++17 | ament_cmake | LIDAR driver, publishes `/scan` + `/diagnostics` |
| `porter_lidar_processor` | Python | ament_python | 6-stage scan filter pipeline |
| `porter_orchestrator` | Python | ament_python | 9-state FSM + health monitor |
| `porter_esp32_bridge` | C++17 | ament_cmake | Motor + sensor serial bridges |
| `porter_ai_assistant` | Python | ament_python | Qwen 2.5 1.5B GGUF + LoRA inference, 14 tools, RAG |
| `porter_gui` | Dart | Flutter | Touchscreen UI with SSE streaming |

### ESP32 Firmware (`porter_robot/esp32_firmware/`)

- **`common/`** — Shared binary protocol (CRC16-CCITT, parser, transport abstraction)
- **`motor_controller/`** — Zephyr RTOS: SMF state machine, PWM, watchdog, differential drive
- **`sensor_fusion/`** — Zephyr RTOS: Kalman filter fusion, cross-validation, fallback logic
- **`tests/`** — 178 Ztest cases on `native_sim`
- Wire format: `[0xAA 0x55][Length][Command][Payload...][CRC16-CCITT]`

### AI Assistant ("Virtue")

- **Model**: Qwen 2.5 1.5B Instruct, Q4_K_M GGUF (~1 GB)
- **LoRA adapters**: conversational + tool-use, swapped at runtime (never merged at 4-bit)
- **Runtime**: llama-cpp-python, CPU-only, `n_threads=2` (reserves 2 cores for SLAM/Nav2)
- **RAG**: TF-IDF over 41 airport knowledge base docs (<1ms retrieval)
- **14 tools**: directions, flight status, find nearest, escort, map, assistance, etc.
- **Latency**: P50 ~1.4s, P95 ~1.8s on RPi 5

## Critical Rules

### Docker
- **Always run docker compose from `porter_robot/`**, never from `docker/` — the build context is `..` (repo root).
- Use `network_mode: host` for all services (DDS discovery).
- AI service: `cpus: 2.0`, `mem_limit: 2g`, `nice -n 10` to avoid starving SLAM/Nav2.

### ROS 2 Jazzy
- All parameters must be typed: `declare_parameter<T>("name", default)` — untyped fails on Jazzy.
- Use `rclcpp::SensorDataQoS().reliable()` for `/scan` (matches RViz2 RELIABLE subscription).
- Never use `print()` in ROS nodes — use `self.get_logger()` / `RCLCPP_INFO()`.
- Never hard-code paths in launch files — use `get_package_share_directory()`.
- Always use `--symlink-install` for dev builds.
- Source `install/setup.bash` after every build.

### ESP32 / Zephyr
- Zephyr version pinned at **v4.0.0** — SMF handlers return `void` (not `enum smf_state_result`).
- Board name: `esp32_devkitc_wroom` (flat name for 4.0.0).
- `COLCON_IGNORE` marker in `esp32_firmware/` prevents colcon from trying to build Zephyr code.
- Never mix Zephyr venv and ROS 2 builds in the same shell session.

### AI Assistant
- System prompts at inference must be **character-for-character identical** to training data — any extra text breaks tool-use compliance.
- `n_threads=2` on RPi (never auto-detect) — leaves 2 cores for SLAM/Nav2.
- `n_ctx=1024` (not 2048) — saves ~28 MB, sufficient for airport Q&A.
- Never merge LoRA on 4-bit model (`merge_and_unload()` degrades weights) — use runtime loading.
- Always call `engine.load_tool_schemas(path)` before first inference.

### LIDAR
- `singleChannel: true` for X4/X4 Pro/X2/S2/S4 — wrong setting causes all commands to timeout.
- `health_expected_freq` must match actual scan delivery rate (e.g., 4.0 Hz for S2PRO), not motor target.
- Never send extra SDK serial commands between `initialize()` and `turnOn()`.

### Code Style
- **C++**: C++17, `ament_cpplint`/`ament_uncrustify`, `RCLCPP_*` logging, `//`-style copyright headers
- **Python**: PEP 8/257, max 99 chars, `ament_flake8`/`ament_pep257`, module + class docstrings required
- **TypeScript** (extension): strict mode, no `any`, `camelCase` files, `PascalCase` types

### Git
- Conventional commits: `<type>(<scope>): <description>`
- Types: `feat`, `fix`, `docs`, `test`, `build`, `ci`, `perf`, `refactor`, `chore`
- Scopes: `ydlidar-driver`, `lidar-processor`, `orchestrator`, `esp32-firmware`, `ai-assistant`, `docker`, `ext`, `gui`
- Model files tracked via Git LFS (`.gguf`, `.safetensors`, `.pt`, `.onnx`, etc.)

### CI/CD
- `verify.yml`: 9 jobs — ROS 2 build/test, linting, ESP32 Ztest, ESP32 cross-compile, Flutter, Docker, integration smoke
- `build-release.yml`: 6 jobs — Docker image, ESP32 .bin, Flutter bundle, VS Code .vsix → GitHub Release with SHA256SUMS
- CI shell must be `bash` (not `sh`) — `ros:jazzy` container defaults to dash
- rosdep: `--skip-keys="ament_python"`

## Extension Suite Status

| Extension | Status | Revisit Needed |
|-----------|--------|----------------|
| Porter DevTools | Done | No |
| Virtus Firmware Builder | Done | No |
| Virtus AI Studio | Done | No |
| Virtus ROS 2 Studio | Done | Yes — launch code generation, Browse buttons, live ROS 2 testing |
| Virtus Hardware Dashboard | Done | No |
| Virtus Simulation Manager | Done | No |
| Virtus PCB Studio | Done | Yes — builder drag-drop rendering, KiCad export, sync checker testing |
| VirtusCo DevTools Suite | Done | Yes — extension install commands, cross-extension events, workspace bootstrap |
| Virtus Fleet Monitor | Deferred | Post-deployment |

## Key Documentation

| File | Content |
|------|---------|
| `porter_robot/CLAUDE.md` | Detailed dev instructions, 54 lessons learned, all task specs |
| `porter_robot/OBJECTIVES.md` | Hardware architecture, timeline, project phases |
| `porter_robot/COMPANY.md` | VirtusCo context, team, product vision |
| `porter_robot/CHANGES.md` | Before/after change log |
| `porter_robot/DevLogs/` | Session-by-session development logs |
| `porter_robot/skills/` | 16 ROS 2 Jazzy + 12 Zephyr RTOS reference files |
| `porter-vscode-extension/CLAUDE.md` | Extension architecture, commands, settings |

## Licenses

- `ydlidar_driver` — Apache 2.0 (open-source, planned upstream contribution)
- All other packages — Proprietary (VirtusCo)

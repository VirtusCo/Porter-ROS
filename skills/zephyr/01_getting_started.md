# Zephyr RTOS — Getting Started & Installation — Skill File

> Source: https://docs.zephyrproject.org/latest/develop/getting_started/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

Zephyr is a scalable real-time operating system (RTOS) supporting multiple hardware architectures, optimized for resource-constrained devices, and built with safety and security in mind. Licensed under Apache 2.0.

### Key Features
- Multi-architecture: ARM (Cortex-M, Cortex-R, Cortex-A), RISC-V, Xtensa (ESP32), x86, ARC, MIPS, etc.
- **C++17 support** (`CONFIG_CPP=y`, `CONFIG_STD_CPP17=y`) — used by Porter firmware
- Configurable kernel services (threads, scheduling, synchronization, memory management)
- Devicetree-based hardware description
- Kconfig-based software configuration
- CMake-based build system with `west` meta-tool
- Built-in support for: BLE 5.0, USB, Networking, CAN, LoRa, Modbus
- Native simulation support (POSIX) for host-based testing
- Shell subsystem for interactive debugging
- NVS (Non-Volatile Storage)
- Comprehensive logging framework

---

## Host System Requirements (Ubuntu 24.04)

### 1. Install Dependencies

```bash
sudo apt update
sudo apt install --no-install-recommends \
    git cmake ninja-build gperf ccache dfu-util device-tree-compiler wget \
    python3-dev python3-pip python3-setuptools python3-tk python3-wheel \
    python3-venv xz-utils file make gcc gcc-multilib g++-multilib \
    libsdl2-dev libmagic1
```

### 2. Install West (Zephyr Meta-Tool)

```bash
# Always use a virtual environment for Zephyr Python tools
python3 -m venv ~/zephyrproject/.venv
source ~/zephyrproject/.venv/bin/activate
pip install west
```

### 3. Initialize Zephyr Workspace

```bash
west init ~/zephyrproject
cd ~/zephyrproject
west update
```

### 4. Export Zephyr CMake Package

```bash
west zephyr-export
```

### 5. Install Python Requirements

```bash
pip install -r ~/zephyrproject/zephyr/scripts/requirements.txt
```

### 6. Install Zephyr SDK

```bash
west sdk install
```

The SDK includes toolchains for all supported architectures (ARM, Xtensa/ESP32, RISC-V, x86, etc.).

---

## Verify Installation — Build & Flash Blinky

```bash
cd ~/zephyrproject/zephyr
west build -p always -b esp32_devkitc/esp32/procpu samples/basic/blinky
west flash
```

---

## West Command Reference

| Command | Description |
|---------|-------------|
| `west init` | Initialize a new Zephyr workspace |
| `west update` | Fetch/update all project repositories |
| `west build -b <board>` | Build for a specific board |
| `west build -p always` | Pristine build (clean rebuild) |
| `west flash` | Flash binary to connected board |
| `west debug` | Launch debugger |
| `west build -t menuconfig` | Interactive Kconfig editor |
| `west build -t guiconfig` | GUI Kconfig editor |
| `west build -t clean` | Clean build artifacts (keep .config) |
| `west build -t pristine` | Full clean (remove .config too) |
| `west zephyr-export` | Register Zephyr CMake package |
| `west sdk install` | Install Zephyr SDK toolchains |

---

## ESP32-Specific Setup

### Supported ESP32 Boards in Zephyr
- `esp32_devkitc/esp32/procpu` — ESP32-DevKitC (our target)
- `esp32_devkitc/esp32/appcpu` — ESP32 app CPU
- `esp32s2_devkitc` — ESP32-S2
- `esp32s3_devkitc` — ESP32-S3
- `esp32c3_devkitc` — ESP32-C3 (RISC-V)

### ESP32 Flash & Monitor

```bash
# Flash
west flash

# Monitor serial output (ESP-IDF monitor)
west espressif monitor
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ZEPHYR_BASE` | Path to Zephyr source tree (auto-set by `west`) |
| `BOARD` | Default board for builds |
| `CONF_FILE` | Override Kconfig fragment file |
| `DTC_OVERLAY_FILE` | Override devicetree overlay file |
| `EXTRA_CONF_FILE` | Additional Kconfig fragments |
| `EXTRA_DTC_OVERLAY_FILE` | Additional devicetree overlays |

---

## Python Environment Rule

> **CRITICAL**: Always use a Python virtual environment (`venv`) for Zephyr tools.
> Never `pip install --break-system-packages`.
> The Zephyr workspace venv is at `~/zephyrproject/.venv/`.

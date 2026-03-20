# Zephyr RTOS — Application Development — Skill File

> Source: https://docs.zephyrproject.org/latest/develop/application/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

Zephyr's build system is application-centric. The application controls the configuration and build process of both the application and Zephyr itself, compiling them into a single binary.

---

## 1. Application Types

| Type | Location | Description |
|------|----------|-------------|
| **Repository** | Inside `zephyr/` repo | Samples and tests |
| **Workspace** | Inside west workspace, outside `zephyr/` | Recommended for custom apps |
| **Freestanding** | Outside any workspace | Requires `ZEPHYR_BASE` set |

### Recommended: Workspace Application
```
zephyrproject/
├── .west/config
├── zephyr/
├── modules/
└── applications/
    └── porter_motor_controller/
        ├── CMakeLists.txt
        ├── prj.conf
        ├── app.overlay
        └── src/main.cpp
```

---

## 2. Application Files

| File | Purpose | Required? |
|------|---------|-----------|
| `CMakeLists.txt` | Build system entry point | ✓ |
| `prj.conf` | Kconfig configuration fragment | ✓ (can be empty) |
| `app.overlay` | Devicetree overlay | Optional |
| `VERSION` | Application version info | Optional |
| `src/main.cpp` | Application source code | ✓ |

### CMakeLists.txt Template

```cmake
cmake_minimum_required(VERSION 3.20.0)

# find_package MUST come before project()
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(my_app LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Add source files
target_sources(app PRIVATE
    src/main.cpp
    src/motor_driver.cpp
    src/protocol.cpp
)

# Add include directories
target_include_directories(app PRIVATE
    include/
)
```

### VERSION File Format
```
VERSION_MAJOR = 0
VERSION_MINOR = 1
PATCHLEVEL = 0
VERSION_TWEAK = 0
```

---

## 3. Build System Variables

| Variable | Description | How to Set |
|----------|-------------|------------|
| `BOARD` | Target board | `-DBOARD=esp32_devkitc/esp32/procpu` |
| `CONF_FILE` | Kconfig fragment file(s) | `-DCONF_FILE=prj.conf` |
| `EXTRA_CONF_FILE` | Additional Kconfig fragments | `-DEXTRA_CONF_FILE=debug.conf` |
| `DTC_OVERLAY_FILE` | Devicetree overlay file(s) | `-DDTC_OVERLAY_FILE=app.overlay` |
| `EXTRA_DTC_OVERLAY_FILE` | Additional DT overlays | `-DEXTRA_DTC_OVERLAY_FILE=debug.overlay` |
| `SHIELD` | Shield name | `-DSHIELD=my_shield` |
| `FILE_SUFFIX` | Config file suffix variant | `-DFILE_SUFFIX=debug` |

### Priority Order (highest first)
1. CMake cache (previous builds)
2. Command line `-D` flags
3. Environment variables
4. `set()` in CMakeLists.txt

---

## 4. Building Applications

### Using West (Recommended)

```bash
# Build for ESP32
west build -b esp32_devkitc/esp32/procpu

# Pristine build (clean + build)
west build -p always -b esp32_devkitc/esp32/procpu

# Build with extra config
west build -b esp32_devkitc/esp32/procpu -- -DEXTRA_CONF_FILE=debug.conf

# Build from different directory
west build -b esp32_devkitc/esp32/procpu path/to/app
```

### Using CMake Directly

```bash
cmake -Bbuild -GNinja -DBOARD=esp32_devkitc/esp32/procpu .
ninja -Cbuild
```

### Build Output

```
build/
├── build.ninja
├── CMakeCache.txt
└── zephyr/
    ├── .config          # Final merged configuration
    ├── zephyr.elf       # Combined application + kernel binary
    ├── zephyr.bin       # Raw binary
    └── zephyr.hex       # Intel HEX format
```

---

## 5. Running & Flashing

### Flash to Hardware

```bash
west flash
```

### Run in Emulator (QEMU)

```bash
# Build for QEMU
west build -b qemu_x86 samples/hello_world
west build -t run
# Ctrl+A, X to exit QEMU
```

### Run Native Simulation

```bash
west build -b native_sim samples/hello_world
./build/zephyr/zephyr.exe
```

---

## 6. Rebuilding

```bash
# Incremental rebuild (fast)
west build

# Clean build (keep .config)
west build -t clean

# Pristine build (remove everything including .config)
west build -t pristine
west build -p always -b <board>
```

---

## 7. Board-Specific Configuration

### File Naming Convention

```
my_app/
├── prj.conf                              # Default
├── boards/
│   ├── esp32_devkitc_esp32_procpu.conf   # ESP32-specific Kconfig
│   ├── esp32_devkitc_esp32_procpu.overlay # ESP32-specific DT overlay
│   └── native_sim.conf                    # Native sim config
```

Board-specific files are auto-detected by the build system based on board name.

---

## 8. File Suffix Variants

For multiple build variants of the same app:

```
my_app/
├── prj.conf              # Default config
├── prj_debug.conf        # Debug variant
├── boards/
│   └── esp32_devkitc_esp32_procpu_debug.overlay
```

Build with variant:
```bash
west build -b esp32_devkitc/esp32/procpu -- -DFILE_SUFFIX=debug
```

---

## 9. Custom Board Definitions

For custom hardware (future production board):

```
my_app/
├── boards/
│   └── virtusco/
│       └── porter_board/
│           ├── porter_board_defconfig
│           ├── porter_board.dts
│           ├── porter_board.yaml
│           ├── board.cmake
│           ├── Kconfig.porter_board
│           └── Kconfig.defconfig
```

Build with custom board root:
```bash
west build -b porter_board -- -DBOARD_ROOT=path/to/boards
```

---

## 10. Debugging

```bash
# Start GDB debug session
west debug

# Use OpenOCD
west debugserver
# Then connect GDB in another terminal
```

### ESP32 Debugging
- JTAG via ESP-PROG or similar adapter
- Or use `west espressif monitor` for serial debug output

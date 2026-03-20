# Zephyr RTOS — Claude Code Instructions

> This file provides Zephyr-specific rules for Claude Code when working on ESP32 firmware.
> Read alongside `Claude.md` (ROS 2 + project-wide rules) and `skills/zephyr/*.md` (full Zephyr reference).

---

## 1. Project Context

- **Hardware**: 2× ESP32-DevKitC running Zephyr RTOS
  - **ESP32 #1 — Motor Controller**: PWM (LEDC), GPIO (direction + enable), encoder interrupts, BTS7960 H-bridge driver
  - **ESP32 #2 — Sensor Fusion**: I2C (ToF VL53L0x), GPIO (ultrasonic trigger/echo), ADC (microwave analog), Kalman filter
- **Communication**: USB CDC ACM serial → appears as `/dev/ttyACM*` on RPi host
- **Protocol**: Custom binary protocol with 0xAA55 header, command ID, payload length, CRC16-CCITT
- **Build target**: `esp32_devkitc/esp32/procpu`
- **Zephyr workspace**: `~/zephyrproject/`

---

## 2. Build & Flash Rules

```bash
# Always use west (never raw cmake for application builds)
west build -p always -b esp32_devkitc/esp32/procpu esp32_firmware/motor_controller
west flash

# For sensor fusion
west build -p always -b esp32_devkitc/esp32/procpu esp32_firmware/sensor_fusion
west flash
```

### Rules
- Always use `-p always` for clean builds during development
- Never modify files under `~/zephyrproject/zephyr/` — only modify `esp32_firmware/`
- The `common/` directory is shared between both applications via `target_sources()` and `target_include_directories()` in CMakeLists.txt

---

## 3. Configuration Rules

### Kconfig (prj.conf)
- One `prj.conf` per application (`motor_controller/prj.conf`, `sensor_fusion/prj.conf`)
- Enable only what's needed — every `CONFIG_*=y` increases binary size and attack surface
- Use `west build -t menuconfig` to explore options — never guess Kconfig symbol names
- Board-specific overrides go in `boards/esp32_devkitc_esp32_procpu.conf`

### Devicetree (app.overlay)
- One `app.overlay` per application
- Hardware pin assignments MUST match the actual PCB wiring
- Use aliases for board-independent code (`DT_ALIAS()` in C++, `aliases {}` in DTS)
- Always set `status = "okay"` for peripherals you're using

---

## 4. Code Style Rules

### Headers
```c
/*
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */
```

### Language
- **C++17** — all firmware source files are `.cpp`
- Kconfig: `CONFIG_CPP=y`, `CONFIG_STD_CPP17=y`, `CONFIG_REQUIRES_FULL_LIBCPP=y`
- Zephyr kernel APIs are C — wrap with `extern "C"` in headers or use the existing guards
- Prefer C++ features: `constexpr`, `enum class`, `std::array`, namespaces, RAII
- Avoid exceptions (`CONFIG_EXCEPTIONS` is off by default) — use return codes
- Avoid dynamic allocation (`new`/`delete`) — use static objects and Zephyr memory pools

### Include Order
1. `<zephyr/kernel.h>` (always first)
2. Zephyr subsystem headers (`<zephyr/drivers/*.h>`, `<zephyr/logging/log.h>`)
3. Standard C++ / C headers (`<cstdint>`, `<cstring>`, `<array>`)
4. Application headers (`"protocol.h"`, `"crc16.h"`)

### Logging
- Every `.cpp` file: `LOG_MODULE_REGISTER(name, LOG_LEVEL_INF);`
- Use `LOG_ERR`, `LOG_WRN`, `LOG_INF`, `LOG_DBG` — never `printk` in application code
- Module names: `motor_ctrl`, `sensor_tof`, `sensor_us`, `usb_proto`, `safety`, `main`

### Error Handling
- Every API call → check return value
- Return negative errno on failure (`-EINVAL`, `-ENODEV`, `-EIO`)
- `device_is_ready()` check before any device use
- Never ignore errors silently — always `LOG_ERR` with context

---

## 5. Architecture Rules

### State Machine Framework (SMF)
- Use SMF for motor controller states: IDLE → RUNNING → FAULT → ESTOP
- Use SMF for sensor fusion states: INIT → CALIBRATING → ACTIVE → DEGRADED → FAULT
- `smf_ctx` MUST be the first member of the user object struct
- Call `smf_set_state()` only from entry or run handlers (never from exit)

### zbus
- Use zbus channels for inter-module communication within each application
- Channel examples: `motor_cmd_chan`, `motor_status_chan`, `sensor_data_chan`, `safety_event_chan`
- Listeners for real-time callbacks, Subscribers for thread-based processing

### Threading
- Static thread creation only (`K_THREAD_DEFINE()`)
- Priority scheme: safety(-1) > motor(0) > protocol(1) > sensor(2) > reporting(5) > shell(14)
- Name every thread: `k_thread_name_set()`

---

## 6. Safety Rules

### Motor Safety (ESP32 #1)
- **Heartbeat timeout**: If no command from RPi in 500ms → stop motors
- **Hardware watchdog**: `CONFIG_TASK_WDT=y` — feed in every thread loop
- **Speed ramping**: Never allow instant full-speed; enforce acceleration limits
- **Current sensing**: Monitor BTS7960 IS pins via ADC; fault if overcurrent

### Sensor Safety (ESP32 #2)
- **Cross-validation**: If ToF and ultrasonic disagree by >30%, flag inconsistency
- **Sensor timeout**: If a sensor doesn't respond in 100ms, mark as degraded
- **Fallback**: If primary sensor fails, switch to secondary with a warning

### Communication Safety
- **CRC16 on every packet** — reject if CRC mismatch (log and discard)
- **Sequence numbers** — detect dropped/duplicate packets
- **Unknown commands** — respond with NACK, don't execute

---

## 7. Testing Rules

- Write Ztest unit tests for all protocol/CRC functions
- Test on `native_sim` first, then `esp32_devkitc`
- Keep test files in `tests/` directory alongside each application
- Use twister for automated test runs

---

## 8. Python Environment Rule

> **CRITICAL**: Zephyr Python tools live in `~/zephyrproject/.venv/`.
> Always `source ~/zephyrproject/.venv/bin/activate` before using `west`.
> Never `pip install --break-system-packages`.

---

## 9. File Locations

| What | Where |
|------|-------|
| Motor firmware | `esp32_firmware/motor_controller/` |
| Sensor firmware | `esp32_firmware/sensor_fusion/` |
| Shared protocol | `esp32_firmware/common/` |
| Zephyr skills | `skills/zephyr/` (12 files) |
| ROS 2 skills | `skills/` (16 files) |
| Project rules | `Claude.md` |
| This file | `esp32_firmware/ZEPHYR_INSTRUCTIONS.md` |

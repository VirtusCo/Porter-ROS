# Zephyr RTOS — Security & Safety — Skill File

> Source: https://docs.zephyrproject.org/latest/security/index.html
> Source: https://docs.zephyrproject.org/latest/safety/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

Zephyr provides security features important for a production robot operating in airports. Security is relevant for firmware integrity, communication safety, and preventing unauthorized control.

---

## 1. Security Overview

### Security Architecture
- **Memory Protection**: Hardware MPU support for thread isolation
- **User Mode**: Unprivileged thread execution (if SoC supports it)
- **Stack Canaries**: Stack overflow detection (`CONFIG_STACK_CANARIES=y`)
- **Address Space Layout Randomization**: Limited support
- **Secure Boot**: Via MCUboot integration
- **Firmware Signing**: Verify firmware integrity before execution

---

## 2. Secure Coding Guidelines

### Memory Safety
```kconfig
# Enable stack canaries (detect stack smashing)
CONFIG_STACK_CANARIES=y

# Enable stack sentinel (additional stack check)
CONFIG_STACK_SENTINEL=y

# Thread stack overflow detection
CONFIG_THREAD_STACK_INFO=y

# Enable assertions (development)
CONFIG_ASSERT=y
```

### Input Validation
- **Always validate** data received over USB CDC ACM
- Check CRC16 before processing any protocol packet
- Validate command IDs against known values
- Bounds-check payload lengths
- Reject malformed packets silently (log and discard)

### Buffer Overflow Prevention
```c
/* BAD: No bounds checking */
memcpy(dest, src, len);

/* GOOD: Check bounds first */
if (len > sizeof(dest)) {
    LOG_ERR("Buffer overflow prevented: %d > %zu", len, sizeof(dest));
    return -EOVERFLOW;
}
memcpy(dest, src, len);
```

---

## 3. Hardening Tool

Zephyr provides a hardening tool to check Kconfig for security best practices:

```bash
west build -t hardenconfig
```

This compares your configuration against recommended security settings and reports deviations.

### Recommended Security Kconfig
```kconfig
# Stack protection
CONFIG_STACK_CANARIES=y
CONFIG_STACK_SENTINEL=y

# Heap/memory safety
CONFIG_SYS_HEAP_VALIDATE=y

# Fault handling
CONFIG_EXCEPTION_STACK_TRACE=y

# No code execution from SRAM (if supported)
CONFIG_HW_STACK_PROTECTION=y

# Disable unused features to reduce attack surface
CONFIG_SHELL=n          # Disable in production!
CONFIG_PRINTK=n         # Disable in production
```

---

## 4. Control Flow Integrity (CFI)

If the compiler and architecture support it:
```kconfig
CONFIG_CFI=y
```

Prevents code-reuse attacks by validating function call targets at runtime.

---

## 5. Vulnerability Reporting

- Zephyr has a defined vulnerability reporting process
- CVEs tracked and patched in LTS releases
- Subscribe to security advisories: https://lists.zephyrproject.org/g/security

---

## 6. Safety Considerations for Porter Robot

### Motor Safety
- **E-Stop**: Emergency stop must work independent of software state
- **Watchdog**: Use hardware watchdog + task watchdog
- **Timeout**: If no command received in N ms, stop motors
- **Current Limiting**: BTS7960 has built-in current sense — monitor it
- **Speed Ramping**: Don't allow instant full-speed commands (acceleration limits)

### Communication Safety
- **CRC16 on every packet**: Detect bit errors in USB communication
- **Sequence Numbers**: Detect dropped/duplicate packets (future)
- **Heartbeat**: RPi sends periodic heartbeat; ESP32 stops motors if missing
- **Command Timeout**: Auto-stop if no speed command for 500ms

### Sensor Safety (ESP32 #2)
- **Redundancy**: Multiple sensor types (ToF + Ultrasonic + Microwave)
- **Cross-validation**: Alert if sensors disagree significantly
- **Fallback**: If one sensor fails, switch to degraded mode with remaining sensors

### Firmware Safety
```c
/* Heartbeat watchdog pattern */
#define HEARTBEAT_TIMEOUT_MS 500

static int64_t last_heartbeat;

void on_heartbeat_received(void) {
    last_heartbeat = k_uptime_get();
}

void safety_check_thread(void) {
    while (1) {
        int64_t elapsed = k_uptime_get() - last_heartbeat;
        if (elapsed > HEARTBEAT_TIMEOUT_MS) {
            LOG_WRN("Heartbeat timeout! Stopping motors.");
            emergency_stop();
        }
        k_msleep(100);
    }
}
```

---

## 7. Production vs Development Configuration

### Development Build
```kconfig
# prj.conf (or prj_debug.conf)
CONFIG_LOG=y
CONFIG_LOG_DEFAULT_LEVEL=4       # DEBUG
CONFIG_SHELL=y
CONFIG_SHELL_BACKEND_SERIAL=y
CONFIG_ASSERT=y
CONFIG_STACK_CANARIES=y
CONFIG_THREAD_NAME=y
CONFIG_THREAD_MONITOR=y
```

### Production Build
```kconfig
# prj_release.conf
CONFIG_LOG=y
CONFIG_LOG_DEFAULT_LEVEL=2       # WARN only
CONFIG_SHELL=n                   # No shell in production
CONFIG_ASSERT=n                  # No assertions (handle errors gracefully)
CONFIG_STACK_CANARIES=y          # Keep for safety
CONFIG_HW_STACK_PROTECTION=y
CONFIG_THREAD_NAME=n             # Save memory
CONFIG_THREAD_MONITOR=n
CONFIG_BOOT_BANNER=n             # Don't print banner
CONFIG_PRINTK=n                  # Don't use printk
```

Build production variant:
```bash
west build -b esp32_devkitc/esp32/procpu -- -DFILE_SUFFIX=release
```

---

## 8. Secure Boot (MCUboot)

For OTA firmware updates (Phase 7 in OBJECTIVES.md):

```kconfig
CONFIG_BOOTLOADER_MCUBOOT=y
```

### MCUboot Flow
1. MCUboot boots first → verifies application signature
2. If valid → jumps to application
3. If invalid → stays in bootloader (can receive new firmware)
4. Supports A/B slot swapping for rollback safety

---

## 9. Security Standards

Zephyr targets compliance with:
- **IEC 62443** — Industrial communication security
- **PSA Certified** — Platform Security Architecture
- **NIST guidelines** — Cryptographic recommendations

### Relevant for Porter (Airport Environment)
- Physical security: robot enclosure tamper detection
- Communication integrity: CRC + signed packets
- Firmware integrity: MCUboot + signed images
- Operational safety: watchdog + heartbeat + E-stop

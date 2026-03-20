# Zephyr RTOS — Code Style & Best Practices — Skill File

> Source: https://docs.zephyrproject.org/latest/contribute/coding_guidelines/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

This file covers Zephyr coding conventions and best practices for the Porter robot ESP32 firmware development. **All Porter firmware is written in C++17.**

---

## 0. C++ in Zephyr — Key Rules

### Kconfig Required
```kconfig
CONFIG_CPP=y
CONFIG_STD_CPP17=y
CONFIG_REQUIRES_FULL_LIBCPP=y
```

### CMakeLists.txt
```cmake
project(my_app LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
```

### What to Use from C++
- `constexpr` for compile-time constants instead of `#define` for values
- `enum class` instead of plain `enum` for type safety
- `std::array` instead of raw C arrays where appropriate
- `namespace porter {}` for application code to avoid name collisions
- RAII patterns for resource management (e.g., scoped GPIO/mutex wrappers)
- `static_assert()` for compile-time validation
- Structured bindings (`auto [a, b] = ...`) where it improves readability

### What to Avoid
- **Exceptions** — disabled by default (`CONFIG_EXCEPTIONS=n`), use return codes
- **RTTI** — disabled by default (`CONFIG_RTTI=n`), no `dynamic_cast`
- **`new`/`delete`** — no dynamic heap allocation; use Zephyr memory slabs/pools
- **STL containers** (`std::vector`, `std::map`, etc.) — they use heap; use fixed-size alternatives
- **`std::string`** — uses heap; use `char[]` or `std::string_view` for non-owning refs
- **Virtual inheritance** — avoid deep hierarchies; prefer composition
- **Templates with heavy instantiation** — keep binary size in check

### Zephyr C APIs from C++
Zephyr kernel/driver APIs are C. Headers already have `extern "C"` guards. They work seamlessly from `.cpp` files. When writing your own headers shared with C:
```cpp
#ifdef __cplusplus
extern "C" {
#endif

/* C-linkage declarations here */

#ifdef __cplusplus
}
#endif
```

---

## 1. Zephyr Naming Conventions

### Functions
- Kernel APIs: `k_*` (e.g., `k_msleep`, `k_thread_create`)
- Driver APIs: `<subsystem>_*` (e.g., `gpio_pin_set_dt`, `uart_fifo_read`)
- Application functions: `<module>_<action>` (e.g., `motor_set_speed`, `protocol_parse`)

### Types
- Kernel types: `k_*` (e.g., `k_thread`, `k_sem`, `k_timer`)
- Devicetree types: `*_dt_spec` (e.g., `gpio_dt_spec`, `pwm_dt_spec`)
- Application types: `<module>_<type>_t` (e.g., `protocol_packet_t`, `motor_state_t`)

### Macros
- Kernel macros: `K_*` (e.g., `K_FOREVER`, `K_MSEC(100)`)
- Devicetree macros: `DT_*` (e.g., `DT_NODELABEL`, `DT_ALIAS`)
- Kconfig symbols: `CONFIG_*` (e.g., `CONFIG_GPIO`, `CONFIG_LOG`)
- Application macros: `PORTER_*` or `CMD_*` for protocol commands

### Reserved Prefixes (Do NOT Use)
- `z_` — internal Zephyr kernel functions
- `_` — reserved by C standard
- `k_` — kernel API
- `sys_` — Zephyr system utilities
- `arch_` — architecture-specific

---

## 2. File Organization

### Header Files
```c
/*
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef MODULE_NAME_H
#define MODULE_NAME_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Public API declarations */

#ifdef __cplusplus
}
#endif

#endif /* MODULE_NAME_H */
```

### Source Files
```c
/*
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

/* Module-specific includes */
#include "module_name.h"

LOG_MODULE_REGISTER(module_name, LOG_LEVEL_INF);

/* Private data */
static int internal_var;

/* Public functions */
int module_init(void) {
    /* ... */
}
```

### Include Order
1. Zephyr headers (`<zephyr/*.h>`)
2. Standard C++ / C headers (`<cstdint>`, `<cstring>`, `<array>`)
3. Application headers (`"protocol.h"`)

---

## 3. Error Handling

### Return Codes
- Use standard errno values: `-EINVAL`, `-ENODEV`, `-ENOMEM`, `-EIO`, `-EBUSY`
- 0 for success, negative for errors
- Check every API return value

```c
int ret = gpio_pin_configure_dt(&pin, GPIO_OUTPUT);
if (ret < 0) {
    LOG_ERR("GPIO configure failed: %d", ret);
    return ret;
}
```

### Device Readiness Check
```c
const struct device *dev = DEVICE_DT_GET(DT_NODELABEL(my_dev));
if (!device_is_ready(dev)) {
    LOG_ERR("Device %s not ready", dev->name);
    return -ENODEV;
}
```

---

## 4. Thread Design Guidelines

### Stack Sizing
- Start with `1024` for simple threads
- Use `4096` for threads with complex logic or deep call stacks
- Monitor with `CONFIG_THREAD_ANALYZER=y`
- Never allocate large buffers on thread stacks

### Priority Assignment
| Priority | Thread | Rationale |
|----------|--------|-----------|
| -1 (coop) | Safety watchdog | Must never be preempted |
| 0 | Motor control | Highest preemptive priority |
| 1 | Protocol handler | High priority for comms |
| 2 | Sensor reading | Regular operation |
| 5 | Status reporting | Low priority |
| 14 | Shell/debug | Lowest operational priority |

### Thread Pattern
```c
#define MOTOR_STACK_SIZE 2048
#define MOTOR_PRIORITY 0

void motor_thread(void *p1, void *p2, void *p3) {
    int ret;

    ret = motor_init();
    if (ret < 0) {
        LOG_ERR("Motor init failed: %d", ret);
        return;
    }

    while (1) {
        /* Main loop */
        motor_process();
        k_msleep(10);  /* 100Hz loop rate */
    }
}

K_THREAD_DEFINE(motor_tid, MOTOR_STACK_SIZE,
    motor_thread, NULL, NULL, NULL,
    MOTOR_PRIORITY, 0, 0);
```

---

## 5. Memory Best Practices

### Static Allocation Preferred
```c
/* GOOD: Static allocation — deterministic */
K_MSGQ_DEFINE(cmd_queue, sizeof(struct cmd_msg), 8, 4);
K_SEM_DEFINE(data_ready, 0, 1);
static uint8_t buffer[256];

/* AVOID: Dynamic allocation — non-deterministic */
void *ptr = k_malloc(256);  /* Use only when necessary */
```

### Use Memory Slabs for Fixed-Size Allocations
```c
K_MEM_SLAB_DEFINE(packet_slab, sizeof(protocol_packet_t), 8, 4);

void *pkt;
k_mem_slab_alloc(&packet_slab, &pkt, K_NO_WAIT);
/* use pkt */
k_mem_slab_free(&packet_slab, pkt);
```

---

## 6. ISR Best Practices

```c
/* ISR rules:
 * 1. Keep ISRs SHORT
 * 2. No blocking calls (no k_msleep, no K_FOREVER timeouts)
 * 3. Use K_NO_WAIT for any kernel API
 * 4. Signal threads via semaphore/event/workqueue
 * 5. No LOG_* in ISR (use LOG_* with _ISR suffix or just skip)
 */

void my_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins) {
    /* Quick: set a flag or give a semaphore */
    k_sem_give(&data_ready);
    /* Do NOT: k_msleep(1), LOG_INF(...), k_msgq_put(..., K_FOREVER) */
}
```

---

## 7. Devicetree Best Practices

- Use `DT_ALIAS` for board-independent references
- Use `DT_NODELABEL` for board-specific references
- Use `*_dt_spec` structures for compile-time device binding
- Always check `device_is_ready()` before use
- Put hardware-specific details in `.overlay` files, not in C++ code

---

## 8. Porter-Specific Conventions

### File Naming
```
motor_driver.cpp / motor_driver.h    — Motor control
sensor_tof.cpp / sensor_tof.h       — ToF sensor driver
sensor_ultrasonic.cpp                — Ultrasonic sensor
protocol.cpp / protocol.h           — USB CDC protocol
crc16.cpp / crc16.h                 — CRC implementation
safety.cpp / safety.h               — Safety monitors
```

### Module Registration
- Every `.cpp` file that uses logging: `LOG_MODULE_REGISTER(name, level);`
- Use descriptive module names: `motor_ctrl`, `sensor_tof`, `usb_protocol`, `safety`

### Comment Style
```c
/* Single-line comment */

/*
 * Multi-line comment block
 * describing complex logic.
 */

/** @brief Doxygen-style for public API */
```

### License Header (Every File)
```c
/*
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */
```

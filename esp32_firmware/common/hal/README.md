# Virtus Hardware Abstraction Layer (VHAL)

A lightweight, registry-based HAL for the Porter Robot ESP32 firmware.
VHAL provides a uniform interface for sensors, actuators, and communication
channels, decoupling application logic from hardware-specific driver code.

## Architecture

```
Application Code
       |
       v
  virtus_hal.h  (single public header)
       |
  +----+----+
  |         |
hal_core  hal_health
  |         |
  v         v
Driver Registry    Health Tracker
  |
  +---> Sensor Drivers     (vl53l0x, hcsr04, rcwl0516)
  +---> Actuator Drivers   (bts7960, relay)
  +---> Comm Drivers       (future)
```

### Key Design Decisions

- **Function pointer vtable** pattern for drivers (no C++ vtable, pure C99).
- **Static registry arrays** (no dynamic allocation) — SENSOR_MAX=8, ACTUATOR_MAX=8.
- **Zephyr-optional** — core code compiles on native_sim without Zephyr headers via `#ifdef CONFIG_LOG` guards.
- **ISR-safe emergency stop** — actuator e-stop uses raw GPIO writes, no logging in ISR path.
- **Health tracking** built into the read path (consecutive fail count + stale timeout).

## Directory Structure

```
hal/
├── include/
│   └── virtus_hal.h          # Single public header (all types + API)
├── src/
│   ├── hal_core.c            # Driver registry + dispatch
│   ├── hal_health.c          # Health monitoring (fail count, stale detection)
│   └── hal_error.c           # Error string mapping + fatal callback
├── drivers/
│   ├── sensors/
│   │   ├── vl53l0x_driver.c  # ToF distance sensor (I2C)
│   │   ├── hcsr04_driver.c   # Ultrasonic ranging (GPIO trigger/echo)
│   │   └── rcwl0516_driver.c # Microwave presence detection (GPIO)
│   └── actuators/
│       ├── bts7960_driver.c  # Dual H-bridge motor driver (PWM + GPIO)
│       └── relay_driver.c    # GPIO relay outputs (4 channels)
├── tests/
│   ├── CMakeLists.txt        # Ztest build config for native_sim
│   ├── prj.conf              # Ztest Kconfig
│   ├── test_hal_registry.c   # Registry dispatch + error tests
│   ├── test_hal_sensor_mock.c    # Mock sensor read + health tests
│   └── test_hal_actuator_mock.c  # Mock actuator set + estop tests
└── README.md                 # This file
```

## How to Add a New Driver

### 1. Sensor Driver

Create `drivers/sensors/my_sensor_driver.c`:

```c
#include "virtus_hal.h"
#include <errno.h>

static int my_init(void)       { /* hardware init */ return 0; }
static int my_deinit(void)     { return 0; }
static bool my_is_ready(void)  { return true; }

static int my_read(virtus_sensor_data_t *out)
{
    /* Read hardware, fill out->data.tof.mm (or appropriate union member) */
    out->valid = true;
    return 0;
}

static bool my_is_healthy(void)    { return true; }
static int my_diag(char *b, size_t l) { return snprintf(b, l, "ok"); }

const virtus_sensor_driver_t my_sensor_driver = {
    .init = my_init, .deinit = my_deinit, .is_ready = my_is_ready,
    .read = my_read, .is_healthy = my_is_healthy, .get_diagnostics = my_diag,
};
```

### 2. Register at startup

In your application `main()`:

```c
#include "virtus_hal.h"

extern const virtus_sensor_driver_t my_sensor_driver;

int main(void)
{
    virtus_sensor_register(SENSOR_TEMPERATURE, &my_sensor_driver);
    virtus_sensor_init_all();

    /* Read in your main loop */
    virtus_sensor_data_t data;
    virtus_sensor_read(SENSOR_TEMPERATURE, &data);
    return 0;
}
```

### 3. Actuator Driver

Same pattern — implement the `virtus_actuator_driver_t` vtable:

```c
const virtus_actuator_driver_t my_actuator_driver = {
    .init           = my_init,
    .deinit         = my_deinit,
    .set            = my_set,
    .get_state      = my_get_state,
    .emergency_stop = my_estop,   /* Must be ISR-safe! */
    .is_healthy     = my_healthy,
};
```

Register with `virtus_actuator_register(ACTUATOR_SPARE, &my_actuator_driver)`.

### 4. Add to tests

Add a mock version in `tests/` and include the source in `tests/CMakeLists.txt`.

## Running Tests

Tests use Zephyr's Ztest framework on the `native_sim` target (no hardware needed):

```bash
cd porter_robot/esp32_firmware
twister -T common/hal/tests/ -p native_sim
```

Or build manually:

```bash
west build -b native_sim common/hal/tests/ -d build/hal_tests
west build -t run -d build/hal_tests
```

## Health Monitoring

The health tracker (`hal_health.c`) automatically monitors sensor reads:

- **Consecutive failures**: 5+ failures in a row marks the sensor unhealthy.
- **Stale timeout**: No successful read in 500ms marks it unhealthy.
- Counters are reset on each successful read.
- Call `virtus_hal_health_reset(id)` to clear all counters.

## Error Handling

All HAL functions return standard errno values:

| Error | Meaning |
|-------|---------|
| 0 | Success |
| -EINVAL | Invalid argument (bad ID, NULL pointer) |
| -ENODEV | No driver registered for that slot |
| -ENOSYS | Driver exists but function not implemented |
| -EIO | Hardware I/O error |
| -ETIMEDOUT | Operation timed out |

Use `virtus_hal_error_to_string(err)` for human-readable error messages.

## License

Proprietary - VirtusCo

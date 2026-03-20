# Zephyr RTOS — Glossary & Quick Reference — Skill File

> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Glossary

| Term | Definition |
|------|-----------|
| **west** | Zephyr's meta-tool for building, flashing, managing repos |
| **Kconfig** | Linux-derived software configuration system (`CONFIG_*` symbols) |
| **Devicetree (DTS)** | Data structure describing hardware; compiled at build time |
| **DT overlay** | Application-specific devicetree modifications (`.overlay` files) |
| **prj.conf** | Application Kconfig fragment file |
| **CMakeLists.txt** | CMake build configuration entry point |
| **Zephyr SDK** | Toolchain bundle for all supported architectures |
| **RTOS** | Real-Time Operating System |
| **SMF** | State Machine Framework — Zephyr's built-in state machine |
| **zbus** | Zephyr Bus — publish/subscribe message passing system |
| **CDC ACM** | Communications Device Class / Abstract Control Model — USB virtual serial |
| **UDC** | USB Device Controller |
| **LEDC** | LED Controller — ESP32's PWM peripheral |
| **NVS** | Non-Volatile Storage — key-value flash storage |
| **MCUboot** | Secure bootloader supporting OTA and signed firmware |
| **twister** | Zephyr's automated test runner |
| **native_sim** | Host-based simulation board (runs Zephyr on Linux/macOS) |
| **Ztest** | Zephyr's unit testing framework |
| **VDED** | Virtual Distributed Event Dispatcher — zbus's notification engine |
| **HOP** | Highest Observer Priority — used in zbus priority boost |
| **SYS_INIT** | Macro for registering initialization functions at specific boot stages |
| **ISR** | Interrupt Service Routine |
| **MPU** | Memory Protection Unit |
| **DMA** | Direct Memory Access |
| **pinctrl** | Pin control subsystem — maps peripheral functions to physical pins |
| **defconfig** | Default Kconfig configuration for a board |

---

## Quick Reference — Build Commands

```bash
# Build
west build -p always -b esp32_devkitc/esp32/procpu

# Flash
west flash

# Monitor
west espressif monitor

# Clean
west build -t pristine

# Interactive config
west build -t menuconfig

# Check security
west build -t hardenconfig

# Memory report
west build -t rom_report
west build -t ram_report

# Run tests
./scripts/twister -p native_sim -T tests/
```

---

## Quick Reference — Kconfig Essentials

```kconfig
# Core
CONFIG_CPP=y
CONFIG_STD_CPP17=y
CONFIG_REQUIRES_FULL_LIBCPP=y
CONFIG_GPIO=y
CONFIG_PWM=y
CONFIG_I2C=y
CONFIG_ADC=y
CONFIG_UART_LINE_CTRL=y

# USB CDC ACM
CONFIG_USB_DEVICE_STACK=y
CONFIG_USBD_CDC_ACM_CLASS=y

# Frameworks
CONFIG_SMF=y
CONFIG_ZBUS=y
CONFIG_LOG=y
CONFIG_SHELL=y
CONFIG_TASK_WDT=y

# Testing
CONFIG_ZTEST=y
CONFIG_ZTEST_NEW_API=y

# Safety
CONFIG_STACK_CANARIES=y
CONFIG_THREAD_STACK_INFO=y
```

---

## Quick Reference — Common API Patterns

```cpp
/* Device access */
const struct device *dev = DEVICE_DT_GET(DT_NODELABEL(name));
if (!device_is_ready(dev)) { return -ENODEV; }

/* GPIO */
static const struct gpio_dt_spec pin = GPIO_DT_SPEC_GET(DT_ALIAS(name), gpios);
gpio_pin_configure_dt(&pin, GPIO_OUTPUT);
gpio_pin_set_dt(&pin, 1);

/* PWM */
static const struct pwm_dt_spec pwm = PWM_DT_SPEC_GET(DT_ALIAS(name));
pwm_set_dt(&pwm, PWM_USEC(period), PWM_USEC(pulse));

/* Logging */
LOG_MODULE_REGISTER(name, LOG_LEVEL_INF);
LOG_INF("Message: %d", value);

/* Semaphore */
K_SEM_DEFINE(sem, 0, 1);
k_sem_give(&sem);
k_sem_take(&sem, K_FOREVER);

/* Message Queue */
K_MSGQ_DEFINE(msgq, sizeof(struct msg), 10, 4);
k_msgq_put(&msgq, &msg, K_MSEC(100));
k_msgq_get(&msgq, &msg, K_FOREVER);

/* Timer */
K_TIMER_DEFINE(timer, handler, NULL);
k_timer_start(&timer, K_MSEC(100), K_MSEC(100));

/* SMF */
smf_set_initial(SMF_CTX(&obj), &states[INIT]);
ret = smf_run_state(SMF_CTX(&obj));

/* zbus */
zbus_chan_pub(&chan, &msg, K_MSEC(100));
zbus_chan_read(&chan, &msg, K_MSEC(100));
```

---

## Documentation References

| Resource | URL |
|----------|-----|
| Zephyr Docs | https://docs.zephyrproject.org/latest/ |
| Getting Started | https://docs.zephyrproject.org/latest/develop/getting_started/index.html |
| Application Dev | https://docs.zephyrproject.org/latest/develop/application/index.html |
| Kconfig Search | https://docs.zephyrproject.org/latest/kconfig.html |
| Devicetree Bindings | https://docs.zephyrproject.org/latest/build/dts/api/bindings.html |
| API Reference | https://docs.zephyrproject.org/latest/doxygen/html/index.html |
| ESP32-DevKitC Board | https://docs.zephyrproject.org/latest/boards/espressif/esp32_devkitc/doc/index.html |
| Samples | https://docs.zephyrproject.org/latest/samples/index.html |
| SMF Framework | https://docs.zephyrproject.org/latest/services/smf/index.html |
| zbus | https://docs.zephyrproject.org/latest/services/zbus/index.html |
| USB CDC ACM | https://docs.zephyrproject.org/latest/connectivity/usb/device_next/cdc_acm.html |
| Security | https://docs.zephyrproject.org/latest/security/index.html |
| West Tool | https://docs.zephyrproject.org/latest/develop/west/index.html |

---

## Skills File Index

| # | File | Topics |
|---|------|--------|
| 01 | `01_getting_started.md` | Installation, west, SDK, ESP32 setup |
| 02 | `02_kernel_services.md` | Threads, scheduling, sync, data passing, timers |
| 03 | `03_device_driver_model.md` | Devicetree, Kconfig, driver APIs, GPIO/PWM/UART/I2C |
| 04 | `04_application_development.md` | App structure, build system, flashing, debugging |
| 05 | `05_build_system.md` | CMake, Kconfig, Devicetree, sysbuild, signing |
| 06 | `06_os_services.md` | Logging, Shell, SMF, zbus, watchdog, NVS, CRC |
| 07 | `07_usb_cdc_connectivity.md` | USB CDC ACM setup, UART API, RPi communication |
| 08 | `08_hardware_esp32.md` | ESP32 board, GPIO, PWM, ADC, I2C, peripherals |
| 09 | `09_security_safety.md` | Hardening, secure coding, motor safety, MCUboot |
| 10 | `10_testing_samples.md` | Ztest, twister, native_sim, relevant samples |
| 11 | `11_code_style.md` | Naming, file structure, error handling, conventions |
| 12 | `12_glossary_reference.md` | This file — glossary, quick reference, links |

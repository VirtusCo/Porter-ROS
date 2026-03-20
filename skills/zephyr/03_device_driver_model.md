# Zephyr RTOS — Device Driver Model & Devicetree — Skill File

> Source: https://docs.zephyrproject.org/latest/kernel/drivers/index.html
> Source: https://docs.zephyrproject.org/latest/build/dts/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

Zephyr uses a **Devicetree + Kconfig** combination for hardware description and software configuration. The devicetree describes the hardware; Kconfig configures the software.

---

## 1. Devicetree (DTS)

### What is Devicetree?
- A data structure describing hardware (borrowed from Linux)
- `.dts` files: board-level devicetree sources
- `.dtsi` files: includable devicetree fragments (SoC-level)
- `.overlay` files: application-specific overrides
- Compiled at build time → generates C macros for code access

### Devicetree Hierarchy
```
Board DTS (e.g., esp32_devkitc.dts)
  └── SoC DTSI (e.g., esp32.dtsi)
       └── Architecture DTSI
            └── Application overlay (app.overlay)
```

### Application Overlay Example

```dts
/* app.overlay — enable and configure peripherals */

/* Enable I2C0 for ToF sensors */
&i2c0 {
    status = "okay";
    clock-frequency = <I2C_BITRATE_FAST>;

    vl53l0x@29 {
        compatible = "st,vl53l0x";
        reg = <0x29>;
    };
};

/* Enable PWM for motors */
&ledc0 {
    status = "okay";
    #pwm-cells = <2>;
};

/* USB CDC ACM */
&zephyr_udc0 {
    cdc_acm_uart0: cdc_acm_uart0 {
        compatible = "zephyr,cdc-acm-uart";
        label = "CDC_ACM_0";
    };
};
```

### Accessing Devicetree from C

```c
/* Get a node by alias */
#define MY_UART DT_ALIAS(protocol_uart)

/* Get a node by compatible */
#define TOF_SENSOR DT_NODELABEL(vl53l0x)

/* Get device pointer */
const struct device *uart = DEVICE_DT_GET(MY_UART);
if (!device_is_ready(uart)) {
    LOG_ERR("UART not ready");
}

/* Get property values */
#define PWM_PERIOD DT_PROP(DT_NODELABEL(motor_pwm), period)
```

### Chosen Nodes
```dts
/ {
    chosen {
        zephyr,console = &uart0;
        zephyr,shell-uart = &uart0;
        zephyr,sram = &sram0;
        zephyr,flash = &flash0;
    };
};
```

---

## 2. Kconfig Configuration

### What is Kconfig?
- Software configuration system (borrowed from Linux kernel)
- `prj.conf`: application Kconfig fragment
- `CONFIG_*` symbols control which features are compiled
- Interactive editors: `west build -t menuconfig` or `west build -t guiconfig`

### prj.conf Example

```kconfig
# Enable USB device stack
CONFIG_USB_DEVICE_STACK=y

# Enable CDC ACM class
CONFIG_USBD_CDC_ACM_CLASS=y

# Enable GPIO
CONFIG_GPIO=y

# Enable PWM
CONFIG_PWM=y

# Enable I2C
CONFIG_I2C=y

# Enable logging
CONFIG_LOG=y
CONFIG_LOG_DEFAULT_LEVEL=3
```

### Board-Specific Configuration

```
my_app/
├── prj.conf                          # Default config
├── boards/
│   ├── esp32_devkitc_esp32_procpu.conf  # ESP32-specific overrides
│   └── native_sim.conf                  # Native sim overrides
```

---

## 3. Device Driver API Pattern

### Getting a Device

```c
#include <zephyr/device.h>

/* From devicetree */
const struct device *dev = DEVICE_DT_GET(DT_NODELABEL(my_peripheral));

/* Check readiness */
if (!device_is_ready(dev)) {
    LOG_ERR("Device not ready");
    return -ENODEV;
}
```

### Common Driver APIs

| API Header | Peripherals |
|------------|-------------|
| `<zephyr/drivers/gpio.h>` | GPIO pins |
| `<zephyr/drivers/pwm.h>` | PWM output |
| `<zephyr/drivers/uart.h>` | UART serial |
| `<zephyr/drivers/i2c.h>` | I2C bus |
| `<zephyr/drivers/spi.h>` | SPI bus |
| `<zephyr/drivers/adc.h>` | Analog-to-digital |
| `<zephyr/drivers/sensor.h>` | Sensor abstraction |
| `<zephyr/drivers/counter.h>` | Hardware timers/counters |

### GPIO Example
```c
#include <zephyr/drivers/gpio.h>

#define LED_NODE DT_ALIAS(led0)
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED_NODE, gpios);

/* Configure and use */
gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
gpio_pin_set_dt(&led, 1);  /* ON */
gpio_pin_set_dt(&led, 0);  /* OFF */
gpio_pin_toggle_dt(&led);
```

### PWM Example
```c
#include <zephyr/drivers/pwm.h>

static const struct pwm_dt_spec motor_pwm = PWM_DT_SPEC_GET(DT_ALIAS(motor_pwm));

/* Set duty cycle (period in ns, pulse in ns) */
pwm_set_dt(&motor_pwm, PWM_USEC(1000), PWM_USEC(500));  /* 50% duty */
```

### UART Example (Interrupt-Driven)
```c
#include <zephyr/drivers/uart.h>

const struct device *uart = DEVICE_DT_GET(DT_NODELABEL(cdc_acm_uart0));

void uart_callback(const struct device *dev, void *user_data) {
    while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
        if (uart_irq_rx_ready(dev)) {
            uint8_t buf[64];
            int len = uart_fifo_read(dev, buf, sizeof(buf));
            /* process received data */
        }
    }
}

/* Setup */
uart_irq_callback_user_data_set(uart, uart_callback, NULL);
uart_irq_rx_enable(uart);
```

### I2C Example
```c
#include <zephyr/drivers/i2c.h>

#define I2C_DEV DT_NODELABEL(i2c0)
const struct device *i2c = DEVICE_DT_GET(I2C_DEV);

/* Write then read */
uint8_t tx_buf[] = {0x00};  /* register address */
uint8_t rx_buf[2];
i2c_write_read(i2c, 0x29, tx_buf, 1, rx_buf, 2);
```

---

## 4. Application Structure

```
my_zephyr_app/
├── CMakeLists.txt      # Build configuration
├── prj.conf            # Kconfig options
├── app.overlay         # Devicetree overlay
├── VERSION             # Version info (optional)
├── boards/             # Board-specific configs (optional)
│   └── esp32_devkitc_esp32_procpu.conf
└── src/
    └── main.c          # Application entry point
```

### Minimal CMakeLists.txt
```cmake
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(my_app)

target_sources(app PRIVATE src/main.c)
```

---

## 5. Device Initialization Order

Zephyr initializes devices in a defined order using `SYS_INIT()` and device init priorities:

1. `PRE_KERNEL_1` — earliest, before kernel starts
2. `PRE_KERNEL_2` — after PRE_KERNEL_1
3. `POST_KERNEL` — after kernel starts (most drivers)
4. `APPLICATION` — after all kernel/driver init

Use `DEVICE_DT_DEFINE()` with appropriate init level for custom drivers.

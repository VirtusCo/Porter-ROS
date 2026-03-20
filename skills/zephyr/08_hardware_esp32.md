# Zephyr RTOS — Hardware Support & ESP32 Specifics — Skill File

> Source: https://docs.zephyrproject.org/latest/hardware/index.html
> Source: https://docs.zephyrproject.org/latest/boards/espressif/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

Zephyr supports 600+ boards across multiple architectures. The ESP32 uses the **Xtensa** architecture and is supported via Espressif's HAL integration.

---

## 1. ESP32-DevKitC Board Support

### Board Identifier
```
esp32_devkitc/esp32/procpu     # Main CPU (PRO_CPU)
esp32_devkitc/esp32/appcpu     # App CPU (APP_CPU)
```

### Supported Espressif Boards in Zephyr
| Board | SoC | Architecture | Board ID |
|-------|-----|--------------|----------|
| ESP32-DevKitC | ESP32 | Xtensa LX6 (dual-core) | `esp32_devkitc/esp32/procpu` |
| ESP32-S2-DevKitC | ESP32-S2 | Xtensa LX7 (single-core) | `esp32s2_devkitc` |
| ESP32-S3-DevKitC | ESP32-S3 | Xtensa LX7 (dual-core) | `esp32s3_devkitc` |
| ESP32-C3-DevKitC | ESP32-C3 | RISC-V | `esp32c3_devkitc` |
| ESP32-C6-DevKitC | ESP32-C6 | RISC-V | `esp32c6_devkitc` |
| ESP-WROVER-KIT | ESP32 | Xtensa LX6 | `esp_wrover_kit` |

### ESP32 SoC Features
- Dual-core Xtensa LX6 @ 240 MHz
- 520 KB SRAM
- 4 MB Flash (external)
- WiFi 802.11 b/g/n
- Bluetooth 4.2 / BLE
- 34 GPIO pins
- 2× I2C, 3× SPI, 2× UART
- 2× I2S, 1× CAN
- 16× PWM (LEDC)
- 18× 12-bit ADC channels
- 2× 8-bit DAC channels
- Touch sensor support
- USB OTG (ESP32-S2/S3 only; ESP32 uses USB-UART bridge)

---

## 2. GPIO (General Purpose I/O)

### Configuration
```kconfig
CONFIG_GPIO=y
```

### Devicetree
```dts
/* ESP32 GPIO nodes are pre-defined in the SoC dtsi */
/* Use gpio0 for GPIO 0-31, gpio1 for GPIO 32-39 */

/ {
    motor_pins {
        compatible = "gpio-leds";
        motor_l_dir: motor_l_dir {
            gpios = <&gpio0 25 GPIO_ACTIVE_HIGH>;
            label = "Motor L Direction";
        };
        motor_r_dir: motor_r_dir {
            gpios = <&gpio0 26 GPIO_ACTIVE_HIGH>;
            label = "Motor R Direction";
        };
    };

    aliases {
        motor-l-dir = &motor_l_dir;
        motor-r-dir = &motor_r_dir;
    };
};
```

### Code
```c
#include <zephyr/drivers/gpio.h>

static const struct gpio_dt_spec motor_l_dir =
    GPIO_DT_SPEC_GET(DT_ALIAS(motor_l_dir), gpios);

/* Configure as output */
gpio_pin_configure_dt(&motor_l_dir, GPIO_OUTPUT_INACTIVE);

/* Set direction */
gpio_pin_set_dt(&motor_l_dir, 1);  /* Forward */
gpio_pin_set_dt(&motor_l_dir, 0);  /* Reverse */

/* GPIO interrupt (for encoder inputs) */
static struct gpio_callback encoder_cb;
void encoder_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins) {
    /* Handle encoder tick — ISR context! */
}
gpio_pin_configure_dt(&encoder_pin, GPIO_INPUT);
gpio_pin_interrupt_configure_dt(&encoder_pin, GPIO_INT_EDGE_BOTH);
gpio_init_callback(&encoder_cb, encoder_isr, BIT(encoder_pin.pin));
gpio_add_callback(encoder_pin.port, &encoder_cb);
```

---

## 3. PWM (Motor Speed Control)

### Configuration
```kconfig
CONFIG_PWM=y
```

### Devicetree (ESP32 LEDC PWM)
```dts
/* ESP32 uses the LEDC peripheral for PWM */
&ledc0 {
    status = "okay";
    pinctrl-0 = <&ledc0_default>;
    pinctrl-names = "default";
    #pwm-cells = <2>;
};

/* Define PWM channels in pin control */
&pinctrl {
    ledc0_default: ledc0_default {
        group1 {
            pinmux = <LEDC_CH0_GPIO18>,   /* Motor L PWM */
                     <LEDC_CH1_GPIO19>;    /* Motor R PWM */
            output-enable;
        };
    };
};

/ {
    aliases {
        pwm-motor-l = &ledc0;
        pwm-motor-r = &ledc0;
    };
};
```

### Code
```c
#include <zephyr/drivers/pwm.h>

static const struct pwm_dt_spec motor_l_pwm =
    PWM_DT_SPEC_GET(DT_ALIAS(pwm_motor_l));

/* Initialize */
if (!pwm_is_ready_dt(&motor_l_pwm)) {
    LOG_ERR("PWM not ready");
}

/* Set duty cycle (period_ns, pulse_ns) */
#define PWM_PERIOD_US 1000  /* 1kHz PWM frequency */

void set_motor_speed(const struct pwm_dt_spec *pwm, uint8_t duty_percent) {
    uint32_t pulse = PWM_USEC(PWM_PERIOD_US * duty_percent / 100);
    pwm_set_dt(pwm, PWM_USEC(PWM_PERIOD_US), pulse);
}

set_motor_speed(&motor_l_pwm, 75);  /* 75% duty */
```

---

## 4. ADC (Battery Monitoring)

### Configuration
```kconfig
CONFIG_ADC=y
```

### Code
```c
#include <zephyr/drivers/adc.h>

#define ADC_NODE DT_NODELABEL(adc0)
static const struct device *adc_dev = DEVICE_DT_GET(ADC_NODE);

static const struct adc_channel_cfg ch_cfg = {
    .gain = ADC_GAIN_1,
    .reference = ADC_REF_INTERNAL,
    .acquisition_time = ADC_ACQ_TIME_DEFAULT,
    .channel_id = 0,
};

int16_t buf;
struct adc_sequence seq = {
    .channels = BIT(0),
    .buffer = &buf,
    .buffer_size = sizeof(buf),
    .resolution = 12,
};

adc_channel_setup(adc_dev, &ch_cfg);
adc_read(adc_dev, &seq);

int voltage_mv = buf;  /* Convert based on reference voltage and gain */
```

---

## 5. I2C (Sensor Communication)

### Configuration
```kconfig
CONFIG_I2C=y
```

### Devicetree
```dts
&i2c0 {
    status = "okay";
    clock-frequency = <I2C_BITRATE_FAST>;  /* 400kHz */
    sda-gpios = <&gpio0 21 0>;
    scl-gpios = <&gpio0 22 0>;
};
```

### Code
```c
#include <zephyr/drivers/i2c.h>

const struct device *i2c_dev = DEVICE_DT_GET(DT_NODELABEL(i2c0));

/* Write-read pattern (common for sensors) */
uint8_t reg_addr = 0x00;
uint8_t data[2];
i2c_write_read(i2c_dev, 0x29, &reg_addr, 1, data, 2);

/* Burst read */
i2c_burst_read(i2c_dev, 0x29, 0x00, data, sizeof(data));
```

---

## 6. Peripherals & Pin Control

### ESP32 Pin Control (pinctrl)
```dts
#include <zephyr/dt-bindings/pinctrl/esp32-pinctrl.h>

&pinctrl {
    uart0_default: uart0_default {
        group1 {
            pinmux = <UART0_TX_GPIO1>;
            output-enable;
        };
        group2 {
            pinmux = <UART0_RX_GPIO3>;
            bias-pull-up;
        };
    };
};
```

---

## 7. Porting Guide (Custom Hardware)

For the production Porter board (future):

1. **Create board directory** under `boards/virtusco/porter_board/`
2. **Define DTS** with exact pin mappings for your PCB
3. **Create defconfig** with default Kconfig settings
4. **Add board.cmake** for flash/debug runner configuration
5. **Test with Zephyr samples** before application code

---

## 8. Emulators & Testing

### Native Simulation
```bash
# Build for native_sim (runs on host, no hardware needed)
west build -b native_sim my_app
./build/zephyr/zephyr.exe
```

### QEMU
```bash
# ESP32 not directly supported in QEMU
# Use native_sim for logic testing
# Use real hardware for peripheral testing
```

---

## 9. ESP32-Specific Notes

1. **USB**: ESP32 (original) does NOT have native USB — it uses a CP2102/CH340 USB-UART bridge. For native USB CDC ACM, you need **ESP32-S2** or **ESP32-S3**.
   - **IMPORTANT**: If using original ESP32, CDC ACM won't work natively. Consider ESP32-S2/S3, or use hardware UART over USB bridge.
   - Alternative: Use regular UART through the existing USB-UART bridge chip.

2. **Flash via UART**: `west flash` uses `esptool.py` which communicates via UART0.

3. **WiFi/BT**: Available but not needed for MVP (USB CDC is simpler and more reliable for wired communication).

4. **Dual Core**: PRO_CPU runs the Zephyr kernel. APP_CPU can be used for symmetric multiprocessing (SMP) if `CONFIG_SMP=y`.

5. **Power**: ESP32 deep sleep available via `CONFIG_PM=y` for battery optimization.

# Zephyr RTOS — USB CDC ACM & Connectivity — Skill File

> Source: https://docs.zephyrproject.org/latest/connectivity/usb/device_next/cdc_acm.html
> Source: https://docs.zephyrproject.org/latest/connectivity/usb/device_next/usb_device.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

The Porter robot uses **USB CDC ACM** (Abstract Control Model) for RPi ↔ ESP32 communication. CDC ACM emulates a serial port over USB — it appears as `/dev/ttyACM*` on the RPi host.

This is the **most critical connectivity feature** for the project.

---

## 1. USB CDC ACM Configuration

### Kconfig
```kconfig
# USB device stack (new API — do NOT use deprecated stack)
CONFIG_USB_DEVICE_STACK=y
CONFIG_USBD_CDC_ACM_CLASS=y
CONFIG_UART_LINE_CTRL=y               # DTR/RTS control signals

# Optional: auto-init CDC ACM at boot
# CONFIG_CDC_ACM_SERIAL_INITIALIZE_AT_BOOT=y
```

### Devicetree Overlay
```dts
/* Enable USB controller */
&usb0 {
    status = "okay";
};

/* Define CDC ACM UART instance */
&zephyr_udc0 {
    cdc_acm_uart0: cdc_acm_uart0 {
        compatible = "zephyr,cdc-acm-uart";
        label = "CDC_ACM_0";
    };
};

/* Optionally use as console */
/ {
    chosen {
        zephyr,console = &cdc_acm_uart0;
        /* OR keep console on hardware UART and use CDC for protocol */
    };
};
```

### Each CDC ACM instance requires 3 endpoints:
- 2× bulk endpoints (IN + OUT) for data
- 1× interrupt IN endpoint (MaxPacketSize = 16) for control

---

## 2. Using CDC ACM in Application

### Wait for DTR Signal

Before sending data, wait for the host to open the serial port:

```c
#include <zephyr/drivers/uart.h>
#include <zephyr/usb/usbd.h>

const struct device *cdc_dev = DEVICE_DT_GET(DT_NODELABEL(cdc_acm_uart0));

/* Wait for DTR (host opened the port) */
uint32_t dtr = 0;
while (!dtr) {
    uart_line_ctrl_get(cdc_dev, UART_LINE_CTRL_DTR, &dtr);
    k_msleep(100);
}

LOG_INF("CDC ACM: DTR set, host connected");
```

### Interrupt-Driven UART API (Recommended)

```c
static void cdc_irq_handler(const struct device *dev, void *user_data)
{
    while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
        if (uart_irq_rx_ready(dev)) {
            uint8_t buf[64];
            int len = uart_fifo_read(dev, buf, sizeof(buf));
            if (len > 0) {
                /* Feed bytes to protocol parser */
                for (int i = 0; i < len; i++) {
                    protocol_parser_feed(&parser, buf[i]);
                }
            }
        }

        if (uart_irq_tx_ready(dev)) {
            /* Send queued response data */
            int len = uart_fifo_fill(dev, tx_buf, tx_len);
            if (len >= tx_len) {
                uart_irq_tx_disable(dev);
            }
        }
    }
}

/* Setup */
uart_irq_callback_user_data_set(cdc_dev, cdc_irq_handler, NULL);
uart_irq_rx_enable(cdc_dev);
```

### Polling API (Simpler but Blocking)

```c
/* Send a byte (blocks if TX full and hw-flow-control enabled) */
uart_poll_out(cdc_dev, byte);

/* Receive a byte (non-blocking, returns -1 if no data) */
unsigned char c;
int ret = uart_poll_in(cdc_dev, &c);
```

---

## 3. Full USB Device Stack Setup

For cases where auto-init is not used:

```c
#include <zephyr/usb/usbd.h>

/* Instantiate USB device context */
USBD_DEVICE_DEFINE(my_usbd,
    DEVICE_DT_GET(DT_NODELABEL(zephyr_udc0)),
    0x2FE3,    /* VID — get your own or use Zephyr's for dev */
    0x0001);   /* PID */

/* String descriptors */
USBD_DESC_LANG_DEFINE(my_lang);
USBD_DESC_MANUFACTURER_DEFINE(my_mfr, "VirtusCo");
USBD_DESC_PRODUCT_DEFINE(my_product, "Porter Motor Controller");

/* Configuration */
USBD_CONFIGURATION_DEFINE(my_fs_config,
    USB_SCD_SELF_POWERED, 100 /* mA */);

/* Initialize */
int usb_init(void) {
    int err;

    err = usbd_add_descriptor(&my_usbd, &my_lang);
    err |= usbd_add_descriptor(&my_usbd, &my_mfr);
    err |= usbd_add_descriptor(&my_usbd, &my_product);
    err |= usbd_add_configuration(&my_usbd, USBD_SPEED_FS, &my_fs_config);
    err |= usbd_register_all_classes(&my_usbd, USBD_SPEED_FS, 1, NULL);

    if (err) {
        LOG_ERR("USB setup failed: %d", err);
        return err;
    }

    err = usbd_init(&my_usbd);
    if (err) {
        LOG_ERR("USB init failed: %d", err);
        return err;
    }

    err = usbd_enable(&my_usbd);
    if (err) {
        LOG_ERR("USB enable failed: %d", err);
        return err;
    }

    LOG_INF("USB CDC ACM initialized");
    return 0;
}
```

### USB Message Notifications

```c
static void usb_msg_cb(struct usbd_context *const ctx,
                        const struct usbd_msg *const msg)
{
    LOG_INF("USB: %s", usbd_msg_type_string(msg->type));

    if (msg->type == USBD_MSG_CONFIGURATION) {
        LOG_INF("USB configured: %d", msg->status);
    }
}

/* Register callback */
usbd_msg_register_cb(&my_usbd, usb_msg_cb);
```

---

## 4. CDC ACM as Console/Shell Backend

For development, CDC ACM can serve as the Zephyr shell/console:

```dts
/ {
    chosen {
        zephyr,console = &cdc_acm_uart0;
        zephyr,shell-uart = &cdc_acm_uart0;
    };
};
```

```kconfig
CONFIG_CDC_ACM_SERIAL_INITIALIZE_AT_BOOT=y
CONFIG_SHELL=y
CONFIG_SHELL_BACKEND_SERIAL=y
```

---

## 5. Other Connectivity (Reference)

### Bluetooth (Future — not MVP)
```kconfig
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
```

### CAN Bus (Not Used Currently)
```kconfig
CONFIG_CAN=y
```

### Networking (Not Used Currently)
```kconfig
CONFIG_NETWORKING=y
```

### Modbus (Potential Future for Industrial)
```kconfig
CONFIG_MODBUS=y
```

---

## 6. Important Notes for Porter

1. **Use the NEW USB device stack** (`device_next`), not the deprecated one
2. **Wait for DTR** before transmitting — the RPi side may not be ready
3. **Interrupt-driven API** is preferred over polling for the protocol handler
4. **CDC ACM appears as `/dev/ttyACM*`** on the RPi (Linux) side
5. The binary protocol (`protocol.h`) handles framing, so raw UART read/write is sufficient
6. Each ESP32 gets its own CDC ACM instance → two `/dev/ttyACM*` devices on the RPi
7. **Test with `minicom`** or `picocom` during development

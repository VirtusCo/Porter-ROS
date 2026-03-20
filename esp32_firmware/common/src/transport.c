/*
 * Porter Robot — Transport Abstraction Layer Implementation
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 *
 * Build-time backend selection:
 *   Zephyr + CONFIG_PORTER_TRANSPORT_UART    → Hardware UART (ESP32-WROOM)
 *   Zephyr + CONFIG_PORTER_TRANSPORT_CDC_ACM → USB CDC ACM  (ESP32-S2/S3)
 *   Non-Zephyr (host)                        → Mock with ring buffers (testing)
 */

#include "transport.h"

#ifdef __ZEPHYR__
/* ==========================================================================
 * Zephyr Implementation — Real hardware backends
 * ========================================================================== */

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#if defined(CONFIG_PORTER_TRANSPORT_CDC_ACM)
#include <zephyr/usb/usbd.h>
#endif

LOG_MODULE_REGISTER(transport, LOG_LEVEL_INF);

/* --- Build-time validation --- */
#if defined(CONFIG_PORTER_TRANSPORT_CDC_ACM) && defined(CONFIG_PORTER_TRANSPORT_UART)
#error "Select only one transport: CONFIG_PORTER_TRANSPORT_CDC_ACM or CONFIG_PORTER_TRANSPORT_UART"
#endif

#if !defined(CONFIG_PORTER_TRANSPORT_CDC_ACM) && !defined(CONFIG_PORTER_TRANSPORT_UART) && \
    !defined(CONFIG_PORTER_TRANSPORT_MOCK)
#error "Select a transport backend: CONFIG_PORTER_TRANSPORT_UART, CONFIG_PORTER_TRANSPORT_CDC_ACM, or CONFIG_PORTER_TRANSPORT_MOCK"
#endif

#if defined(CONFIG_PORTER_TRANSPORT_MOCK)
/* ==========================================================================
 * Mock Implementation — For Zephyr native_sim testing
 * ========================================================================== */

#include <string.h>

#define MOCK_BUF_SIZE 1024

static uint8_t mock_rx_buf[MOCK_BUF_SIZE];
static size_t  mock_rx_head = 0;
static size_t  mock_rx_tail = 0;

static uint8_t mock_tx_buf[MOCK_BUF_SIZE];
static size_t  mock_tx_len = 0;

static bool            mock_initialized = false;
static transport_rx_cb_t mock_rx_cb      = NULL;
static void             *mock_rx_ud      = NULL;

int transport_init(const transport_config_t *config)
{
    (void)config;
    mock_initialized = true;
    LOG_INF("Mock transport initialized");
    return TRANSPORT_OK;
}

bool transport_is_ready(void)
{
    return mock_initialized;
}

int transport_read(uint8_t *buf, size_t max_len)
{
    if (!mock_initialized) {
        return TRANSPORT_ERR_NOT_READY;
    }
    if (buf == NULL || max_len == 0) {
        return 0;
    }
    size_t count = 0;
    while (count < max_len && mock_rx_tail != mock_rx_head) {
        buf[count++] = mock_rx_buf[mock_rx_tail % MOCK_BUF_SIZE];
        mock_rx_tail++;
    }
    return (int)count;
}

int transport_write(const uint8_t *buf, size_t len)
{
    if (!mock_initialized) {
        return TRANSPORT_ERR_NOT_READY;
    }
    if (buf == NULL || len == 0) {
        return 0;
    }
    size_t space = MOCK_BUF_SIZE - mock_tx_len;
    size_t to_copy = (len < space) ? len : space;
    memcpy(mock_tx_buf + mock_tx_len, buf, to_copy);
    mock_tx_len += to_copy;
    return (int)to_copy;
}

int transport_set_rx_callback(transport_rx_cb_t cb, void *user_data)
{
    mock_rx_cb = cb;
    mock_rx_ud = user_data;
    return TRANSPORT_OK;
}

void transport_flush(void)
{
    mock_rx_head = 0;
    mock_rx_tail = 0;
}

void transport_deinit(void)
{
    mock_initialized = false;
    mock_rx_cb = NULL;
    mock_rx_ud = NULL;
}

const char *transport_backend_name(void)
{
    return "mock";
}

void transport_mock_inject_rx(const uint8_t *data, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        mock_rx_buf[mock_rx_head % MOCK_BUF_SIZE] = data[i];
        mock_rx_head++;
    }
    if (mock_rx_cb != NULL) {
        mock_rx_cb(data, len, mock_rx_ud);
    }
}

size_t transport_mock_get_tx(uint8_t *buf, size_t max_len)
{
    size_t to_copy = (mock_tx_len < max_len) ? mock_tx_len : max_len;
    memcpy(buf, mock_tx_buf, to_copy);
    if (to_copy < mock_tx_len) {
        memmove(mock_tx_buf, mock_tx_buf + to_copy, mock_tx_len - to_copy);
    }
    mock_tx_len -= to_copy;
    return to_copy;
}

void transport_mock_reset(void)
{
    mock_initialized = false;
    mock_rx_head = 0;
    mock_rx_tail = 0;
    mock_tx_len  = 0;
    mock_rx_cb   = NULL;
    mock_rx_ud   = NULL;
}

#else /* Real hardware backends: UART or CDC ACM */

/* --- Device from devicetree alias --- */
/*
 * Both backends use the same alias: "protocol-uart"
 * The overlay determines which device it points to:
 *   UART backend:    protocol-uart = &uart2;       (hardware UART)
 *   CDC ACM backend: protocol-uart = &cdc_acm_uart0; (USB virtual serial)
 */
#define PROTOCOL_UART_NODE DT_ALIAS(protocol_uart)

#if !DT_NODE_EXISTS(PROTOCOL_UART_NODE)
#error "Devicetree alias 'protocol-uart' not defined. Add it to your app.overlay."
#endif

static const struct device *uart_dev = DEVICE_DT_GET(PROTOCOL_UART_NODE);

/* --- Internal state --- */
static volatile bool transport_initialized = false;
static transport_rx_cb_t  rx_callback  = NULL;
static void              *rx_user_data = NULL;

/* --- UART IRQ handler (shared by both backends) --- */
static void uart_irq_handler(const struct device *dev, void *user_data)
{
    ARG_UNUSED(user_data);

    while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
        if (uart_irq_rx_ready(dev)) {
            uint8_t buf[64];
            int len = uart_fifo_read(dev, buf, sizeof(buf));
            if (len > 0 && rx_callback != NULL) {
                rx_callback(buf, (size_t)len, rx_user_data);
            }
        }
    }
}

/* --- API Implementation --- */

int transport_init(const transport_config_t *config)
{
    transport_config_t cfg;

    if (config != NULL) {
        cfg = *config;
    } else {
        transport_config_t defaults = TRANSPORT_CONFIG_DEFAULT;
        cfg = defaults;
    }

    /* Check device readiness */
    if (!device_is_ready(uart_dev)) {
        LOG_ERR("Transport device not ready");
        return TRANSPORT_ERR_INIT;
    }

#if defined(CONFIG_PORTER_TRANSPORT_UART)
    /*
     * UART backend — configure baudrate on hardware UART.
     * The external USB-UART bridge (CP2102/CH340) handles USB conversion.
     */
    {
        struct uart_config uart_cfg;
        int ret = uart_config_get(uart_dev, &uart_cfg);

        if (ret == 0) {
            uart_cfg.baudrate = cfg.baudrate;
            ret = uart_configure(uart_dev, &uart_cfg);
            if (ret != 0) {
                LOG_WRN("Failed to set baudrate %u (err %d), using default",
                        cfg.baudrate, ret);
            }
        } else {
            LOG_WRN("Failed to get UART config (err %d), using defaults", ret);
        }
    }

    transport_initialized = true;
    LOG_INF("Transport [UART] initialized, baudrate=%u", cfg.baudrate);

#elif defined(CONFIG_PORTER_TRANSPORT_CDC_ACM)
    /*
     * CDC ACM backend — wait for host to assert DTR.
     * DTR indicates the host has opened the serial port.
     * On RPi, this happens when the ROS 2 bridge node opens /dev/ttyACMx.
     */
    {
        uint32_t dtr = 0;
        int64_t  start = k_uptime_get();
        uint32_t timeout = cfg.init_timeout_ms;

        LOG_INF("Transport [CDC ACM] waiting for host DTR...");

        while (dtr == 0) {
            uart_line_ctrl_get(uart_dev, UART_LINE_CTRL_DTR, &dtr);

            if (timeout > 0 &&
                (uint32_t)(k_uptime_get() - start) > timeout) {
                LOG_WRN("DTR timeout after %u ms — host not connected", timeout);
                return TRANSPORT_ERR_TIMEOUT;
            }

            k_msleep(100);
        }
    }

    transport_initialized = true;
    LOG_INF("Transport [CDC ACM] initialized, host DTR asserted");
#endif

    return TRANSPORT_OK;
}

bool transport_is_ready(void)
{
    if (!transport_initialized) {
        return false;
    }

#if defined(CONFIG_PORTER_TRANSPORT_CDC_ACM)
    /* Re-check DTR — host may have disconnected */
    uint32_t dtr = 0;

    uart_line_ctrl_get(uart_dev, UART_LINE_CTRL_DTR, &dtr);
    if (dtr == 0) {
        LOG_WRN("Host DTR deasserted — disconnected");
        return false;
    }
#endif

    return true;
}

int transport_read(uint8_t *buf, size_t max_len)
{
    if (!transport_initialized) {
        return TRANSPORT_ERR_NOT_READY;
    }
    if (buf == NULL || max_len == 0) {
        return 0;
    }

    size_t count = 0;
    unsigned char c;

    while (count < max_len) {
        int ret = uart_poll_in(uart_dev, &c);
        if (ret != 0) {
            break;  /* No more data available */
        }
        buf[count++] = (uint8_t)c;
    }

    return (int)count;
}

int transport_write(const uint8_t *buf, size_t len)
{
    if (!transport_initialized) {
        return TRANSPORT_ERR_NOT_READY;
    }
    if (buf == NULL || len == 0) {
        return 0;
    }

    for (size_t i = 0; i < len; i++) {
        uart_poll_out(uart_dev, buf[i]);
    }

    return (int)len;
}

int transport_set_rx_callback(transport_rx_cb_t cb, void *user_data)
{
    if (!transport_initialized) {
        return TRANSPORT_ERR_NOT_READY;
    }

    rx_callback  = cb;
    rx_user_data = user_data;

    if (cb != NULL) {
        uart_irq_callback_user_data_set(uart_dev, uart_irq_handler, NULL);
        uart_irq_rx_enable(uart_dev);
        LOG_DBG("RX callback enabled (interrupt-driven)");
    } else {
        uart_irq_rx_disable(uart_dev);
        LOG_DBG("RX callback disabled (polling mode)");
    }

    return TRANSPORT_OK;
}

void transport_flush(void)
{
    if (!transport_initialized) {
        return;
    }

    /* Drain pending RX data */
    unsigned char c;
    while (uart_poll_in(uart_dev, &c) == 0) {
        /* discard */
    }
}

void transport_deinit(void)
{
    if (rx_callback != NULL) {
        uart_irq_rx_disable(uart_dev);
        rx_callback  = NULL;
        rx_user_data = NULL;
    }

    transport_initialized = false;
    LOG_INF("Transport deinitialized");
}

const char *transport_backend_name(void)
{
#if defined(CONFIG_PORTER_TRANSPORT_UART)
    return "uart";
#elif defined(CONFIG_PORTER_TRANSPORT_CDC_ACM)
    return "cdc_acm";
#else
    return "unknown";
#endif
}

#endif /* CONFIG_PORTER_TRANSPORT_MOCK (else: real hardware) */

#else
/* ==========================================================================
 * Host Mock Implementation — For unit testing without Zephyr
 * ========================================================================== */

#include <string.h>

/* Ring buffer sizes for mock */
#define MOCK_BUF_SIZE 1024

/* Mock RX buffer (simulates data arriving from host) */
static uint8_t mock_rx_buf[MOCK_BUF_SIZE];
static size_t  mock_rx_head = 0;  /* write index (inject) */
static size_t  mock_rx_tail = 0;  /* read index (transport_read) */

/* Mock TX buffer (captures data sent to host) */
static uint8_t mock_tx_buf[MOCK_BUF_SIZE];
static size_t  mock_tx_len = 0;

/* Mock state */
static bool            mock_initialized = false;
static transport_rx_cb_t mock_rx_cb      = NULL;
static void             *mock_rx_ud      = NULL;

int transport_init(const transport_config_t *config)
{
    (void)config;
    mock_initialized = true;
    return TRANSPORT_OK;
}

bool transport_is_ready(void)
{
    return mock_initialized;
}

int transport_read(uint8_t *buf, size_t max_len)
{
    if (!mock_initialized) {
        return TRANSPORT_ERR_NOT_READY;
    }
    if (buf == NULL || max_len == 0) {
        return 0;
    }

    size_t count = 0;

    while (count < max_len && mock_rx_tail != mock_rx_head) {
        buf[count++] = mock_rx_buf[mock_rx_tail % MOCK_BUF_SIZE];
        mock_rx_tail++;
    }

    return (int)count;
}

int transport_write(const uint8_t *buf, size_t len)
{
    if (!mock_initialized) {
        return TRANSPORT_ERR_NOT_READY;
    }
    if (buf == NULL || len == 0) {
        return 0;
    }

    /* Append to TX capture buffer */
    size_t space = MOCK_BUF_SIZE - mock_tx_len;
    size_t to_copy = (len < space) ? len : space;

    memcpy(mock_tx_buf + mock_tx_len, buf, to_copy);
    mock_tx_len += to_copy;

    return (int)to_copy;
}

int transport_set_rx_callback(transport_rx_cb_t cb, void *user_data)
{
    mock_rx_cb = cb;
    mock_rx_ud = user_data;
    return TRANSPORT_OK;
}

void transport_flush(void)
{
    mock_rx_head = 0;
    mock_rx_tail = 0;
}

void transport_deinit(void)
{
    mock_initialized = false;
    mock_rx_cb = NULL;
    mock_rx_ud = NULL;
}

const char *transport_backend_name(void)
{
    return "mock";
}

/* --- Mock Test Helpers --- */

void transport_mock_inject_rx(const uint8_t *data, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        mock_rx_buf[mock_rx_head % MOCK_BUF_SIZE] = data[i];
        mock_rx_head++;
    }

    /* If a callback is registered, invoke it (simulates IRQ-driven arrival) */
    if (mock_rx_cb != NULL) {
        mock_rx_cb(data, len, mock_rx_ud);
    }
}

size_t transport_mock_get_tx(uint8_t *buf, size_t max_len)
{
    size_t to_copy = (mock_tx_len < max_len) ? mock_tx_len : max_len;

    memcpy(buf, mock_tx_buf, to_copy);

    /* Shift remaining data forward */
    if (to_copy < mock_tx_len) {
        memmove(mock_tx_buf, mock_tx_buf + to_copy, mock_tx_len - to_copy);
    }
    mock_tx_len -= to_copy;

    return to_copy;
}

void transport_mock_reset(void)
{
    mock_initialized = false;
    mock_rx_head = 0;
    mock_rx_tail = 0;
    mock_tx_len  = 0;
    mock_rx_cb   = NULL;
    mock_rx_ud   = NULL;
}

#endif /* __ZEPHYR__ */

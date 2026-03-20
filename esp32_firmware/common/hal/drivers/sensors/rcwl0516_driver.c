/* Copyright 2026 VirtusCo
 *
 * VHAL Driver — RCWL-0516 Microwave presence/motion sensor
 * GPIO digital input — HIGH when motion detected.
 *
 * On native_sim this file compiles to stubs (no real hardware).
 *
 * SPDX-License-Identifier: Proprietary
 */

#include "virtus_hal.h"
#include <errno.h>

#ifdef CONFIG_GPIO
/* ========================================================================
 * Zephyr Hardware Implementation
 * ======================================================================== */

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(rcwl0516_drv, LOG_LEVEL_INF);

/* Devicetree alias for the microwave sensor pin.
 * Expected overlay:
 *   / { aliases { microwave-sensor = &mw_sensor; }; };
 */
#if DT_NODE_EXISTS(DT_ALIAS(microwave_sensor))
#define MW_NODE DT_ALIAS(microwave_sensor)
#else
#define MW_NODE DT_INVALID_NODE
#endif

/** GPIO spec from devicetree. */
static struct gpio_dt_spec s_pin;

/** Whether the driver is initialised. */
static bool s_initialised;

/** Health tracking. */
static uint32_t s_read_count;

/**
 * Initialise the RCWL-0516 sensor GPIO.
 * Configures the pin as input with pull-down (sensor outputs HIGH on detect).
 */
static int rcwl0516_init(void)
{
    int ret;

#if DT_NODE_IS_VALID(MW_NODE)
    s_pin = (struct gpio_dt_spec)GPIO_DT_SPEC_GET(MW_NODE, gpios);

    if (!gpio_is_ready_dt(&s_pin)) {
        LOG_ERR("RCWL-0516 GPIO not ready");
        return -EIO;
    }

    ret = gpio_pin_configure_dt(&s_pin, GPIO_INPUT | GPIO_PULL_DOWN);
    if (ret != 0) {
        LOG_ERR("Failed to configure RCWL-0516 pin: %d", ret);
        return ret;
    }

    s_initialised = true;
    s_read_count = 0;
    LOG_INF("RCWL-0516 initialised");
    return 0;
#else
    LOG_ERR("RCWL-0516: devicetree alias not defined");
    return -ENODEV;
#endif
}

/**
 * De-initialise the RCWL-0516.
 */
static int rcwl0516_deinit(void)
{
    s_initialised = false;
    s_read_count = 0;
    LOG_INF("RCWL-0516 de-initialised");
    return 0;
}

/**
 * Check if the driver is initialised.
 */
static bool rcwl0516_is_ready(void)
{
    return s_initialised;
}

/**
 * Read the digital presence detection state.
 * HIGH = motion detected, LOW = no motion.
 */
static int rcwl0516_read(virtus_sensor_data_t *out)
{
    int val;

    if (!s_initialised) {
        return -ENODEV;
    }

    val = gpio_pin_get_dt(&s_pin);
    if (val < 0) {
        return val;
    }

    out->data.microwave.detected = (val != 0);
    out->data.microwave.raw_adc = (uint16_t)(val ? 4095 : 0);
    out->valid = true;

    s_read_count++;
    return 0;
}

/**
 * Health check — the RCWL-0516 is a passive sensor.
 * Considered healthy as long as it has been read at least once.
 */
static bool rcwl0516_is_healthy(void)
{
    return s_initialised && (s_read_count > 0);
}

/**
 * Diagnostic string.
 */
static int rcwl0516_get_diagnostics(char *buf, size_t buf_len)
{
    int n;

    if (buf == NULL || buf_len == 0) {
        return 0;
    }

    n = snprintf(buf, buf_len,
                 "RCWL-0516: init=%d, reads=%u",
                 s_initialised, s_read_count);
    return (n > 0 && (size_t)n < buf_len) ? n : 0;
}

/** Exported driver instance. */
const virtus_sensor_driver_t rcwl0516_driver = {
    .init            = rcwl0516_init,
    .deinit          = rcwl0516_deinit,
    .is_ready        = rcwl0516_is_ready,
    .read            = rcwl0516_read,
    .is_healthy      = rcwl0516_is_healthy,
    .get_diagnostics = rcwl0516_get_diagnostics,
};

#else /* !CONFIG_GPIO — stub for native_sim builds */

static int stub_init(void)          { return -ENOTSUP; }
static int stub_deinit(void)        { return 0; }
static bool stub_is_ready(void)     { return false; }
static int stub_read(virtus_sensor_data_t *out) { (void)out; return -ENOTSUP; }
static bool stub_is_healthy(void)   { return false; }
static int stub_diag(char *buf, size_t len)
{
    if (buf && len > 0) {
        buf[0] = '\0';
    }
    return 0;
}

const virtus_sensor_driver_t rcwl0516_driver = {
    .init            = stub_init,
    .deinit          = stub_deinit,
    .is_ready        = stub_is_ready,
    .read            = stub_read,
    .is_healthy      = stub_is_healthy,
    .get_diagnostics = stub_diag,
};

#endif /* CONFIG_GPIO */

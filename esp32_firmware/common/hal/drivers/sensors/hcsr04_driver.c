/* Copyright 2026 VirtusCo
 *
 * VHAL Driver — HC-SR04 Ultrasonic ranging sensor
 * Trigger pulse + echo timing to measure distance in centimetres.
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
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(hcsr04_drv, LOG_LEVEL_INF);

/* Devicetree node aliases for trigger and echo pins.
 * Expected overlay:
 *   / { aliases { us-trigger = &us_trigger; us-echo = &us_echo; }; };
 */
#if DT_NODE_EXISTS(DT_ALIAS(us_trigger))
#define TRIGGER_NODE DT_ALIAS(us_trigger)
#else
#define TRIGGER_NODE DT_INVALID_NODE
#endif

#if DT_NODE_EXISTS(DT_ALIAS(us_echo))
#define ECHO_NODE DT_ALIAS(us_echo)
#else
#define ECHO_NODE DT_INVALID_NODE
#endif

/** GPIO specs from devicetree. */
static struct gpio_dt_spec s_trigger;
static struct gpio_dt_spec s_echo;

/** Health tracking counters. */
static uint32_t s_success_count;
static uint32_t s_fail_count;

/** Whether the driver has been successfully initialised. */
static bool s_initialised;

/** Speed of sound: ~343 m/s at 20C = 0.0343 cm/us.
 *  distance_cm = (echo_us / 2) * 0.0343
 *  Simplified: distance_cm = echo_us / 58 */
#define US_TO_CM_DIVISOR  58

/** Maximum echo wait time in microseconds (~4m range). */
#define ECHO_TIMEOUT_US   25000

/**
 * Initialise the HC-SR04 GPIO pins.
 */
static int hcsr04_init(void)
{
    int ret;

#if DT_NODE_IS_VALID(TRIGGER_NODE) && DT_NODE_IS_VALID(ECHO_NODE)
    s_trigger = (struct gpio_dt_spec)GPIO_DT_SPEC_GET(TRIGGER_NODE, gpios);
    s_echo    = (struct gpio_dt_spec)GPIO_DT_SPEC_GET(ECHO_NODE, gpios);

    if (!gpio_is_ready_dt(&s_trigger)) {
        LOG_ERR("Trigger GPIO not ready");
        return -EIO;
    }
    if (!gpio_is_ready_dt(&s_echo)) {
        LOG_ERR("Echo GPIO not ready");
        return -EIO;
    }

    ret = gpio_pin_configure_dt(&s_trigger, GPIO_OUTPUT_LOW);
    if (ret != 0) {
        LOG_ERR("Failed to configure trigger pin: %d", ret);
        return ret;
    }

    ret = gpio_pin_configure_dt(&s_echo, GPIO_INPUT);
    if (ret != 0) {
        LOG_ERR("Failed to configure echo pin: %d", ret);
        return ret;
    }

    s_success_count = 0;
    s_fail_count = 0;
    s_initialised = true;
    LOG_INF("HC-SR04 initialised");
    return 0;
#else
    LOG_ERR("HC-SR04: devicetree aliases not defined");
    return -ENODEV;
#endif
}

/**
 * De-initialise the HC-SR04.
 */
static int hcsr04_deinit(void)
{
    s_initialised = false;
    s_success_count = 0;
    s_fail_count = 0;
    LOG_INF("HC-SR04 de-initialised");
    return 0;
}

/**
 * Check if the driver is initialised.
 */
static bool hcsr04_is_ready(void)
{
    return s_initialised;
}

/**
 * Read distance by sending a 10us trigger pulse and timing the echo.
 */
static int hcsr04_read(virtus_sensor_data_t *out)
{
    uint32_t start_us;
    uint32_t elapsed_us;
    uint32_t timeout_count;

    if (!s_initialised) {
        return -ENODEV;
    }

    /* Send 10us trigger pulse */
    gpio_pin_set_dt(&s_trigger, 1);
    k_busy_wait(10);
    gpio_pin_set_dt(&s_trigger, 0);

    /* Wait for echo to go HIGH (start of return pulse) */
    timeout_count = 0;
    while (gpio_pin_get_dt(&s_echo) == 0) {
        k_busy_wait(1);
        timeout_count++;
        if (timeout_count > ECHO_TIMEOUT_US) {
            s_fail_count++;
            s_success_count = 0;
            return -ETIMEDOUT;
        }
    }

    start_us = k_cycle_get_32();

    /* Wait for echo to go LOW (end of return pulse) */
    timeout_count = 0;
    while (gpio_pin_get_dt(&s_echo) == 1) {
        k_busy_wait(1);
        timeout_count++;
        if (timeout_count > ECHO_TIMEOUT_US) {
            s_fail_count++;
            s_success_count = 0;
            return -ETIMEDOUT;
        }
    }

    elapsed_us = k_cyc_to_us_floor32(k_cycle_get_32() - start_us);

    /* Convert to centimetres */
    out->data.ultrasonic.cm = (uint16_t)(elapsed_us / US_TO_CM_DIVISOR);
    out->data.ultrasonic.confidence = 100;
    out->valid = true;

    s_success_count++;
    s_fail_count = 0;
    return 0;
}

/**
 * Health check: healthy if last N reads succeeded.
 */
static bool hcsr04_is_healthy(void)
{
    return s_initialised && (s_success_count > 0) && (s_fail_count < 5);
}

/**
 * Diagnostic string.
 */
static int hcsr04_get_diagnostics(char *buf, size_t buf_len)
{
    int n;

    if (buf == NULL || buf_len == 0) {
        return 0;
    }

    n = snprintf(buf, buf_len,
                 "HC-SR04: init=%d, ok=%u, fail=%u",
                 s_initialised, s_success_count, s_fail_count);
    return (n > 0 && (size_t)n < buf_len) ? n : 0;
}

/** Exported driver instance. */
const virtus_sensor_driver_t hcsr04_driver = {
    .init            = hcsr04_init,
    .deinit          = hcsr04_deinit,
    .is_ready        = hcsr04_is_ready,
    .read            = hcsr04_read,
    .is_healthy      = hcsr04_is_healthy,
    .get_diagnostics = hcsr04_get_diagnostics,
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

const virtus_sensor_driver_t hcsr04_driver = {
    .init            = stub_init,
    .deinit          = stub_deinit,
    .is_ready        = stub_is_ready,
    .read            = stub_read,
    .is_healthy      = stub_is_healthy,
    .get_diagnostics = stub_diag,
};

#endif /* CONFIG_GPIO */

/* Copyright 2026 VirtusCo
 *
 * VHAL Driver — VL53L0x Time-of-Flight sensor
 * Reads distance via Zephyr sensor API, publishes as tof.mm.
 *
 * On native_sim this file compiles to stubs (no real hardware).
 *
 * SPDX-License-Identifier: Proprietary
 */

#include "virtus_hal.h"
#include <errno.h>

#ifdef CONFIG_SENSOR
/* ========================================================================
 * Zephyr Hardware Implementation
 * ======================================================================== */

#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(vl53l0x_drv, LOG_LEVEL_INF);

/** Device reference from devicetree alias "tof-sensor". */
static const struct device *s_dev;

/** Consecutive successful read count for health check. */
static uint32_t s_success_count;

/** Consecutive failure count. */
static uint32_t s_fail_count;

/**
 * Initialise the VL53L0x sensor.
 * Gets the device binding from the devicetree alias.
 */
static int vl53l0x_init(void)
{
    s_dev = DEVICE_DT_GET_OR_NULL(DT_ALIAS(tof_sensor));
    if (s_dev == NULL) {
        LOG_ERR("tof-sensor alias not found in devicetree");
        return -ENODEV;
    }

    if (!device_is_ready(s_dev)) {
        LOG_ERR("VL53L0x device not ready");
        s_dev = NULL;
        return -EIO;
    }

    s_success_count = 0;
    s_fail_count = 0;
    LOG_INF("VL53L0x initialised");
    return 0;
}

/**
 * De-initialise the VL53L0x sensor.
 */
static int vl53l0x_deinit(void)
{
    s_dev = NULL;
    s_success_count = 0;
    s_fail_count = 0;
    LOG_INF("VL53L0x de-initialised");
    return 0;
}

/**
 * Check if the sensor device is bound and ready.
 */
static bool vl53l0x_is_ready(void)
{
    return (s_dev != NULL) && device_is_ready(s_dev);
}

/**
 * Read a distance sample from the VL53L0x.
 * Uses Zephyr sensor API: fetch + channel get.
 */
static int vl53l0x_read(virtus_sensor_data_t *out)
{
    struct sensor_value val;
    int ret;

    if (s_dev == NULL) {
        return -ENODEV;
    }

    ret = sensor_sample_fetch(s_dev);
    if (ret != 0) {
        s_fail_count++;
        s_success_count = 0;
        LOG_WRN("VL53L0x fetch failed: %d", ret);
        return ret;
    }

    ret = sensor_channel_get(s_dev, SENSOR_CHAN_DISTANCE, &val);
    if (ret != 0) {
        s_fail_count++;
        s_success_count = 0;
        LOG_WRN("VL53L0x channel get failed: %d", ret);
        return ret;
    }

    /* sensor_value is in metres (val1) + micro-metres (val2).
     * Convert to millimetres. */
    out->data.tof.mm = (uint16_t)(val.val1 * 1000 + val.val2 / 1000);
    out->data.tof.status = 0;
    out->valid = true;

    s_success_count++;
    s_fail_count = 0;
    return 0;
}

/**
 * Health check based on recent read success.
 */
static bool vl53l0x_is_healthy(void)
{
    return (s_dev != NULL) && (s_success_count > 0) && (s_fail_count < 5);
}

/**
 * Get diagnostic string.
 */
static int vl53l0x_get_diagnostics(char *buf, size_t buf_len)
{
    int n;

    if (buf == NULL || buf_len == 0) {
        return 0;
    }

    n = snprintf(buf, buf_len,
                 "VL53L0x: dev=%s, ok=%u, fail=%u",
                 (s_dev != NULL) ? "bound" : "NULL",
                 s_success_count, s_fail_count);
    return (n > 0 && (size_t)n < buf_len) ? n : 0;
}

/** Exported driver instance. */
const virtus_sensor_driver_t vl53l0x_driver = {
    .init            = vl53l0x_init,
    .deinit          = vl53l0x_deinit,
    .is_ready        = vl53l0x_is_ready,
    .read            = vl53l0x_read,
    .is_healthy      = vl53l0x_is_healthy,
    .get_diagnostics = vl53l0x_get_diagnostics,
};

#else /* !CONFIG_SENSOR — stub for native_sim builds */

/**
 * Stub driver for builds without Zephyr sensor subsystem.
 * All functions return error codes indicating no hardware.
 */

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

const virtus_sensor_driver_t vl53l0x_driver = {
    .init            = stub_init,
    .deinit          = stub_deinit,
    .is_ready        = stub_is_ready,
    .read            = stub_read,
    .is_healthy      = stub_is_healthy,
    .get_diagnostics = stub_diag,
};

#endif /* CONFIG_SENSOR */

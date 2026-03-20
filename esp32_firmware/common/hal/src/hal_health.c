/* Copyright 2026 VirtusCo
 *
 * VHAL Health Monitoring — Tracks sensor read success/failure rates
 * and determines healthy/unhealthy status based on configurable thresholds.
 *
 * SPDX-License-Identifier: Proprietary
 */

#include "virtus_hal.h"
#include <string.h>

/* --- Zephyr timing (optional) --- */
#ifdef CONFIG_LOG
#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
LOG_MODULE_DECLARE(virtus_hal, LOG_LEVEL_INF);
#define HAL_GET_TIME_US() (uint32_t)(k_uptime_get() * 1000U)
#else
#define HAL_GET_TIME_US() 0U
#endif

/* ========================================================================
 * Health Tracking Configuration
 * ======================================================================== */

/** Number of consecutive failures before marking a sensor unhealthy. */
#define UNHEALTHY_CONSECUTIVE_FAILS   5

/** Stale timeout in milliseconds — no successful read within this window
 *  marks the sensor as unhealthy. */
#define UNHEALTHY_STALE_MS            500

/* ========================================================================
 * Health State Storage
 * ======================================================================== */

/**
 * Per-sensor health tracking state.
 */
typedef struct {
    uint32_t read_count;           /**< Total read attempts */
    uint32_t fail_count;           /**< Total failed reads */
    uint32_t consecutive_fails;    /**< Current streak of failures */
    uint32_t last_success_us;      /**< Timestamp of last successful read */
} virtus_driver_health_t;

/** Health state for each sensor slot. */
static virtus_driver_health_t s_health[SENSOR_MAX];

/* ========================================================================
 * Health Tracking Functions
 * ======================================================================== */

/**
 * Record a successful sensor read.
 * Resets the consecutive failure counter and updates the last-success
 * timestamp.
 */
void virtus_hal_health_record_success(virtus_sensor_id_t id)
{
    if ((int)id < 0 || id >= SENSOR_MAX) {
        return;
    }

    s_health[id].read_count++;
    s_health[id].consecutive_fails = 0;
    s_health[id].last_success_us = HAL_GET_TIME_US();
}

/**
 * Record a failed sensor read.
 * Increments both the total and consecutive failure counters.
 */
void virtus_hal_health_record_failure(virtus_sensor_id_t id)
{
    if ((int)id < 0 || id >= SENSOR_MAX) {
        return;
    }

    s_health[id].read_count++;
    s_health[id].fail_count++;
    s_health[id].consecutive_fails++;
}

/**
 * Reset all health tracking counters for a sensor.
 */
void virtus_hal_health_reset(virtus_sensor_id_t id)
{
    if ((int)id < 0 || id >= SENSOR_MAX) {
        return;
    }

    memset(&s_health[id], 0, sizeof(virtus_driver_health_t));
}

/**
 * Check health by consecutive failure count and stale timeout.
 *
 * A sensor is considered unhealthy if:
 *   - It has had UNHEALTHY_CONSECUTIVE_FAILS or more failures in a row, OR
 *   - No successful read has occurred in UNHEALTHY_STALE_MS milliseconds
 *     (only checked when Zephyr timing is available).
 *
 * A sensor with zero total reads is considered unhealthy (never used).
 */
bool virtus_hal_health_is_healthy(virtus_sensor_id_t id)
{
    if ((int)id < 0 || id >= SENSOR_MAX) {
        return false;
    }

    /* Never read = not healthy */
    if (s_health[id].read_count == 0) {
        return false;
    }

    /* Too many consecutive failures */
    if (s_health[id].consecutive_fails >= UNHEALTHY_CONSECUTIVE_FAILS) {
        return false;
    }

#ifdef CONFIG_LOG
    /* Check for stale data (no success within timeout) */
    {
        uint32_t now_us = HAL_GET_TIME_US();
        uint32_t elapsed_ms;

        if (now_us >= s_health[id].last_success_us) {
            elapsed_ms = (now_us - s_health[id].last_success_us) / 1000U;
        } else {
            /* Timer wraparound */
            elapsed_ms = (0xFFFFFFFFU - s_health[id].last_success_us
                          + now_us) / 1000U;
        }

        if (elapsed_ms > UNHEALTHY_STALE_MS) {
            return false;
        }
    }
#endif

    return true;
}

/* Copyright 2026 VirtusCo
 *
 * VHAL Core — Driver registry and dispatch.
 * Manages registration, initialisation, and dispatch for all
 * sensor, actuator, and communication drivers.
 *
 * SPDX-License-Identifier: Proprietary
 */

#include "virtus_hal.h"
#include <errno.h>
#include <string.h>

/* --- Zephyr logging (optional — compiles without it for native_sim) --- */
#ifdef CONFIG_LOG
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(virtus_hal, LOG_LEVEL_INF);
#define HAL_LOG_INF(...) LOG_INF(__VA_ARGS__)
#define HAL_LOG_WRN(...) LOG_WRN(__VA_ARGS__)
#define HAL_LOG_ERR(...) LOG_ERR(__VA_ARGS__)
#else
#include <stdio.h>
#define HAL_LOG_INF(...) do { printf("[INF] "); printf(__VA_ARGS__); printf("\n"); } while (0)
#define HAL_LOG_WRN(...) do { printf("[WRN] "); printf(__VA_ARGS__); printf("\n"); } while (0)
#define HAL_LOG_ERR(...) do { printf("[ERR] "); printf(__VA_ARGS__); printf("\n"); } while (0)
#endif

/* ========================================================================
 * Static Driver Registries
 * ======================================================================== */

/** Registered sensor drivers, indexed by virtus_sensor_id_t. */
static const virtus_sensor_driver_t *s_sensors[SENSOR_MAX];

/** Registered actuator drivers, indexed by virtus_actuator_id_t. */
static const virtus_actuator_driver_t *s_actuators[ACTUATOR_MAX];

/** Registered communication drivers (up to 4 channels). */
#define VHAL_MAX_COMMS 4
static const virtus_comm_driver_t *s_comms[VHAL_MAX_COMMS];

/* ========================================================================
 * Sensor Name Table
 * ======================================================================== */

/** Human-readable sensor names, indexed by virtus_sensor_id_t. */
static const char *s_sensor_names[SENSOR_MAX] = {
    "ToF",
    "Ultrasonic",
    "Microwave",
    "Encoder-Left",
    "Encoder-Right",
    "LoadCell",
    "IMU",
    "Temperature"
};

/* ========================================================================
 * Actuator Name Table
 * ======================================================================== */

/** Human-readable actuator names, indexed by virtus_actuator_id_t. */
static const char *s_actuator_names[ACTUATOR_MAX] = {
    "Motor-Left",
    "Motor-Right",
    "Lift",
    "Relay-1",
    "Relay-2",
    "Relay-3",
    "Relay-4",
    "Spare"
};

/* ========================================================================
 * Sensor API Implementation
 * ======================================================================== */

/**
 * Register a sensor driver for the given slot.
 * Replaces any previously registered driver for that slot.
 */
int virtus_sensor_register(virtus_sensor_id_t id,
                           const virtus_sensor_driver_t *driver)
{
    if ((int)id < 0 || id >= SENSOR_MAX) {
        HAL_LOG_ERR("sensor register: invalid id %d", (int)id);
        return -EINVAL;
    }
    if (driver == NULL) {
        HAL_LOG_ERR("sensor register: NULL driver for id %d", (int)id);
        return -EINVAL;
    }

    if (s_sensors[id] != NULL) {
        HAL_LOG_WRN("sensor register: replacing driver for %s",
                     s_sensor_names[id]);
    }

    s_sensors[id] = driver;
    HAL_LOG_INF("sensor registered: %s (id=%d)", s_sensor_names[id], (int)id);
    return 0;
}

/**
 * Initialise all registered sensor drivers.
 * Calls init() on each registered driver in order. Returns the first
 * non-zero error code but continues initialising remaining drivers.
 */
int virtus_sensor_init_all(void)
{
    int first_err = 0;
    int i;

    HAL_LOG_INF("initialising all sensors...");

    for (i = 0; i < SENSOR_MAX; i++) {
        if (s_sensors[i] == NULL) {
            continue;
        }
        if (s_sensors[i]->init == NULL) {
            HAL_LOG_WRN("sensor %s: no init function", s_sensor_names[i]);
            continue;
        }

        int ret = s_sensors[i]->init();
        if (ret != 0) {
            HAL_LOG_ERR("sensor %s init failed: %d", s_sensor_names[i], ret);
            if (first_err == 0) {
                first_err = ret;
            }
        } else {
            HAL_LOG_INF("sensor %s initialised OK", s_sensor_names[i]);
        }
    }

    return first_err;
}

/**
 * Read from a sensor. Dispatches to the registered driver and tracks
 * health via the hal_health module.
 */
int virtus_sensor_read(virtus_sensor_id_t id, virtus_sensor_data_t *out)
{
    int ret;

    if ((int)id < 0 || id >= SENSOR_MAX) {
        return -EINVAL;
    }
    if (out == NULL) {
        return -EINVAL;
    }
    if (s_sensors[id] == NULL) {
        return -ENODEV;
    }
    if (s_sensors[id]->read == NULL) {
        return -ENOSYS;
    }

    ret = s_sensors[id]->read(out);
    if (ret == 0) {
        out->id = id;
        virtus_hal_health_record_success(id);
    } else {
        virtus_hal_health_record_failure(id);
    }

    return ret;
}

/**
 * Check if a sensor is healthy using the health tracking module.
 */
bool virtus_sensor_is_healthy(virtus_sensor_id_t id)
{
    if ((int)id < 0 || id >= SENSOR_MAX) {
        return false;
    }
    if (s_sensors[id] == NULL) {
        return false;
    }

    /* If the driver provides its own is_healthy, use it */
    if (s_sensors[id]->is_healthy != NULL) {
        return s_sensors[id]->is_healthy();
    }

    /* Fallback: not registered = not healthy */
    return false;
}

/**
 * Get the human-readable name for a sensor ID.
 */
const char *virtus_sensor_name(virtus_sensor_id_t id)
{
    if ((int)id < 0 || id >= SENSOR_MAX) {
        return "UNKNOWN";
    }
    return s_sensor_names[id];
}

/* ========================================================================
 * Actuator API Implementation
 * ======================================================================== */

/**
 * Register an actuator driver for the given slot.
 * Replaces any previously registered driver for that slot.
 */
int virtus_actuator_register(virtus_actuator_id_t id,
                             const virtus_actuator_driver_t *driver)
{
    if ((int)id < 0 || id >= ACTUATOR_MAX) {
        HAL_LOG_ERR("actuator register: invalid id %d", (int)id);
        return -EINVAL;
    }
    if (driver == NULL) {
        HAL_LOG_ERR("actuator register: NULL driver for id %d", (int)id);
        return -EINVAL;
    }

    if (s_actuators[id] != NULL) {
        HAL_LOG_WRN("actuator register: replacing driver for %s",
                     s_actuator_names[id]);
    }

    s_actuators[id] = driver;
    HAL_LOG_INF("actuator registered: %s (id=%d)",
                s_actuator_names[id], (int)id);
    return 0;
}

/**
 * Initialise all registered actuator drivers.
 * Returns the first non-zero error code but continues initialising
 * remaining drivers.
 */
int virtus_actuator_init_all(void)
{
    int first_err = 0;
    int i;

    HAL_LOG_INF("initialising all actuators...");

    for (i = 0; i < ACTUATOR_MAX; i++) {
        if (s_actuators[i] == NULL) {
            continue;
        }
        if (s_actuators[i]->init == NULL) {
            HAL_LOG_WRN("actuator %s: no init function",
                         s_actuator_names[i]);
            continue;
        }

        int ret = s_actuators[i]->init();
        if (ret != 0) {
            HAL_LOG_ERR("actuator %s init failed: %d",
                         s_actuator_names[i], ret);
            if (first_err == 0) {
                first_err = ret;
            }
        } else {
            HAL_LOG_INF("actuator %s initialised OK", s_actuator_names[i]);
        }
    }

    return first_err;
}

/**
 * Send a command to an actuator. Dispatches to the registered driver.
 */
int virtus_actuator_set(const virtus_actuator_cmd_t *cmd)
{
    virtus_actuator_id_t id;

    if (cmd == NULL) {
        return -EINVAL;
    }

    id = cmd->id;
    if ((int)id < 0 || id >= ACTUATOR_MAX) {
        return -EINVAL;
    }
    if (s_actuators[id] == NULL) {
        return -ENODEV;
    }
    if (s_actuators[id]->set == NULL) {
        return -ENOSYS;
    }

    return s_actuators[id]->set(cmd);
}

/**
 * Get the current state of an actuator.
 */
int virtus_actuator_get_state(virtus_actuator_id_t id,
                              virtus_actuator_state_t *out)
{
    if ((int)id < 0 || id >= ACTUATOR_MAX) {
        return -EINVAL;
    }
    if (out == NULL) {
        return -EINVAL;
    }
    if (s_actuators[id] == NULL) {
        return -ENODEV;
    }
    if (s_actuators[id]->get_state == NULL) {
        return -ENOSYS;
    }

    return s_actuators[id]->get_state(out);
}

/**
 * Emergency-stop ALL registered actuators.
 * Iterates every slot, calls emergency_stop on each registered driver.
 * Never fails silently — logs errors but always continues through all slots.
 * Returns the count of actuators that failed to stop (0 = all OK).
 */
int virtus_actuator_emergency_stop_all(void)
{
    int fail_count = 0;
    int i;

    HAL_LOG_WRN("EMERGENCY STOP ALL ACTUATORS");

    for (i = 0; i < ACTUATOR_MAX; i++) {
        if (s_actuators[i] == NULL) {
            continue;
        }
        if (s_actuators[i]->emergency_stop == NULL) {
            HAL_LOG_WRN("actuator %s: no emergency_stop function",
                         s_actuator_names[i]);
            fail_count++;
            continue;
        }

        int ret = s_actuators[i]->emergency_stop();
        if (ret != 0) {
            HAL_LOG_ERR("actuator %s emergency_stop FAILED: %d",
                         s_actuator_names[i], ret);
            fail_count++;
        } else {
            HAL_LOG_INF("actuator %s stopped", s_actuator_names[i]);
        }
    }

    if (fail_count > 0) {
        HAL_LOG_ERR("emergency stop: %d actuator(s) failed to stop",
                     fail_count);
    } else {
        HAL_LOG_INF("emergency stop: all actuators stopped successfully");
    }

    return fail_count;
}

/**
 * Check if an actuator is healthy.
 */
bool virtus_actuator_is_healthy(virtus_actuator_id_t id)
{
    if ((int)id < 0 || id >= ACTUATOR_MAX) {
        return false;
    }
    if (s_actuators[id] == NULL) {
        return false;
    }
    if (s_actuators[id]->is_healthy == NULL) {
        return false;
    }

    return s_actuators[id]->is_healthy();
}

/**
 * Get the human-readable name for an actuator ID.
 */
const char *virtus_actuator_name(virtus_actuator_id_t id)
{
    if ((int)id < 0 || id >= ACTUATOR_MAX) {
        return "UNKNOWN";
    }
    return s_actuator_names[id];
}

/* ========================================================================
 * Communication API Implementation
 * ======================================================================== */

/**
 * Register a communication driver for the given channel index.
 */
int virtus_comm_register(int index, const virtus_comm_driver_t *driver)
{
    if (index < 0 || index >= VHAL_MAX_COMMS) {
        HAL_LOG_ERR("comm register: invalid index %d", index);
        return -EINVAL;
    }
    if (driver == NULL) {
        HAL_LOG_ERR("comm register: NULL driver for index %d", index);
        return -EINVAL;
    }

    s_comms[index] = driver;
    HAL_LOG_INF("comm channel %d registered", index);
    return 0;
}

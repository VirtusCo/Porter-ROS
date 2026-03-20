/* Copyright 2026 VirtusCo
 *
 * Virtus Hardware Abstraction Layer (VHAL)
 * Unified driver registry for sensors, actuators, and communications.
 *
 * This is the single public header for VHAL. Include only this file.
 *
 * SPDX-License-Identifier: Proprietary
 */

#ifndef VIRTUS_HAL_H_
#define VIRTUS_HAL_H_

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ========================================================================
 * Sensor Types and Structures
 * ======================================================================== */

/**
 * Sensor identifier enum.
 * Each value maps to a slot in the internal driver registry.
 */
typedef enum {
    SENSOR_TOF          = 0,  /**< Time-of-Flight distance sensor (VL53L0x) */
    SENSOR_ULTRASONIC   = 1,  /**< Ultrasonic ranging sensor (HC-SR04) */
    SENSOR_MICROWAVE    = 2,  /**< Microwave presence/motion sensor (RCWL-0516) */
    SENSOR_ENCODER_LEFT = 3,  /**< Left wheel encoder */
    SENSOR_ENCODER_RIGHT = 4, /**< Right wheel encoder */
    SENSOR_LOADCELL     = 5,  /**< Load cell (luggage weight) */
    SENSOR_IMU          = 6,  /**< Inertial measurement unit */
    SENSOR_TEMPERATURE  = 7,  /**< Temperature sensor */
    SENSOR_MAX          = 8   /**< Total sensor slots (not a valid ID) */
} virtus_sensor_id_t;

/**
 * Sensor data container.
 * The active union member is determined by the sensor ID.
 */
typedef struct {
    virtus_sensor_id_t id;        /**< Which sensor produced this data */
    uint32_t           timestamp_us; /**< Microsecond timestamp of reading */
    bool               valid;     /**< True if data is trustworthy */

    union {
        struct {
            uint16_t mm;          /**< Distance in millimetres */
            uint8_t  status;      /**< Sensor-specific status byte */
        } tof;

        struct {
            uint16_t cm;          /**< Distance in centimetres */
            uint8_t  confidence;  /**< Measurement confidence 0-100 */
        } ultrasonic;

        struct {
            bool     detected;    /**< Motion/presence detected */
            uint16_t raw_adc;     /**< Raw ADC reading (0-4095) */
        } microwave;

        struct {
            int32_t  ticks;       /**< Accumulated encoder ticks */
            int16_t  velocity_dps; /**< Velocity in degrees per second */
        } encoder;

        struct {
            int32_t  grams;       /**< Weight in grams */
            bool     tared;       /**< True if zero-offset applied */
        } loadcell;
    } data;
} virtus_sensor_data_t;

/**
 * Sensor driver function pointer table.
 * Every sensor driver must implement these callbacks.
 */
typedef struct {
    /** Initialise the sensor hardware. Returns 0 on success, negative errno. */
    int  (*init)(void);

    /** De-initialise the sensor hardware. Returns 0 on success. */
    int  (*deinit)(void);

    /** Check if the sensor is ready to produce readings. */
    bool (*is_ready)(void);

    /** Read a single sample. Fills *out. Returns 0 on success, negative errno. */
    int  (*read)(virtus_sensor_data_t *out);

    /** Check if the sensor is in a healthy operating state. */
    bool (*is_healthy)(void);

    /**
     * Get diagnostic information as a human-readable string.
     * Writes up to buf_len bytes into buf. Returns bytes written.
     */
    int  (*get_diagnostics)(char *buf, size_t buf_len);
} virtus_sensor_driver_t;

/* ========================================================================
 * Actuator Types and Structures
 * ======================================================================== */

/**
 * Actuator identifier enum.
 * Each value maps to a slot in the internal driver registry.
 */
typedef enum {
    ACTUATOR_MOTOR_LEFT  = 0, /**< Left drive motor (BTS7960) */
    ACTUATOR_MOTOR_RIGHT = 1, /**< Right drive motor (BTS7960) */
    ACTUATOR_LIFT        = 2, /**< Luggage lift mechanism */
    ACTUATOR_RELAY_1     = 3, /**< Relay output 1 */
    ACTUATOR_RELAY_2     = 4, /**< Relay output 2 */
    ACTUATOR_RELAY_3     = 5, /**< Relay output 3 */
    ACTUATOR_RELAY_4     = 6, /**< Relay output 4 */
    ACTUATOR_SPARE       = 7, /**< Reserved for future use */
    ACTUATOR_MAX         = 8  /**< Total actuator slots (not a valid ID) */
} virtus_actuator_id_t;

/**
 * Actuator command container.
 * The active union member is determined by the actuator ID.
 */
typedef struct {
    virtus_actuator_id_t id;  /**< Target actuator */

    union {
        struct {
            int16_t  speed_pct;   /**< Speed percentage: -100 to +100 */
            uint8_t  flags;       /**< Bit 0: brake mode, Bit 1: coast mode */
        } motor;

        struct {
            int16_t  position_pct; /**< Lift position: 0 (down) to 100 (up) */
            uint8_t  speed;        /**< Lift speed: 0-255 */
        } lift;

        struct {
            bool     on;           /**< Relay state: true = energised */
        } relay;
    } cmd;
} virtus_actuator_cmd_t;

/**
 * Actuator state feedback container.
 * The active union member is determined by the actuator ID.
 */
typedef struct {
    virtus_actuator_id_t id;          /**< Which actuator */
    uint32_t             timestamp_us; /**< Microsecond timestamp */
    bool                 enabled;      /**< True if actuator is active */

    union {
        struct {
            int16_t  speed_pct;    /**< Current commanded speed */
            uint16_t current_ma;   /**< Measured motor current in mA */
            int8_t   temp_c;       /**< Estimated temperature in Celsius */
        } motor;

        struct {
            int16_t  position_pct; /**< Current lift position */
            bool     at_limit;     /**< True if at mechanical limit */
        } lift;

        struct {
            bool     on;           /**< Current relay state */
            uint32_t on_time_ms;   /**< Cumulative on-time in milliseconds */
        } relay;
    } state;
} virtus_actuator_state_t;

/**
 * Actuator driver function pointer table.
 * Every actuator driver must implement these callbacks.
 */
typedef struct {
    /** Initialise the actuator hardware. Returns 0 on success, negative errno. */
    int  (*init)(void);

    /** De-initialise the actuator hardware. Returns 0 on success. */
    int  (*deinit)(void);

    /** Apply a command to the actuator. Returns 0 on success, negative errno. */
    int  (*set)(const virtus_actuator_cmd_t *cmd);

    /** Read the current actuator state. Returns 0 on success, negative errno. */
    int  (*get_state)(virtus_actuator_state_t *out);

    /** Emergency stop — must be ISR-safe. Returns 0 on success. */
    int  (*emergency_stop)(void);

    /** Check if the actuator is in a healthy operating state. */
    bool (*is_healthy)(void);
} virtus_actuator_driver_t;

/* ========================================================================
 * Communication Driver
 * ======================================================================== */

/**
 * Communication channel driver function pointer table.
 */
typedef struct {
    /** Initialise the communication channel. Returns 0 on success. */
    int  (*init)(void);

    /** Send data. Returns number of bytes sent, or negative errno. */
    int  (*send)(const uint8_t *data, size_t len);

    /** Receive data. Returns number of bytes received, or negative errno. */
    int  (*recv)(uint8_t *buf, size_t max_len);

    /** Check if the channel is connected / ready. */
    bool (*is_connected)(void);
} virtus_comm_driver_t;

/* ========================================================================
 * HAL API — Sensor Functions
 * ======================================================================== */

/**
 * Register a sensor driver for the given sensor ID.
 *
 * @param id     Sensor slot to register into (must be < SENSOR_MAX).
 * @param driver Pointer to a const driver struct (must not be NULL).
 * @return 0 on success, -EINVAL if id or driver is invalid.
 */
int virtus_sensor_register(virtus_sensor_id_t id,
                           const virtus_sensor_driver_t *driver);

/**
 * Initialise all registered sensor drivers.
 *
 * @return 0 if all succeed, or the first non-zero error code encountered.
 */
int virtus_sensor_init_all(void);

/**
 * Read from a specific sensor. Dispatches to the registered driver.
 *
 * @param id  Sensor to read from.
 * @param out Pointer to data structure to fill.
 * @return 0 on success, -ENODEV if no driver registered, or driver error.
 */
int virtus_sensor_read(virtus_sensor_id_t id, virtus_sensor_data_t *out);

/**
 * Check if a sensor is healthy.
 *
 * @param id Sensor to check.
 * @return true if healthy, false otherwise.
 */
bool virtus_sensor_is_healthy(virtus_sensor_id_t id);

/**
 * Get the human-readable name for a sensor ID.
 *
 * @param id Sensor identifier.
 * @return Static string name, or "UNKNOWN" for invalid IDs.
 */
const char *virtus_sensor_name(virtus_sensor_id_t id);

/* ========================================================================
 * HAL API — Actuator Functions
 * ======================================================================== */

/**
 * Register an actuator driver for the given actuator ID.
 *
 * @param id     Actuator slot to register into (must be < ACTUATOR_MAX).
 * @param driver Pointer to a const driver struct (must not be NULL).
 * @return 0 on success, -EINVAL if id or driver is invalid.
 */
int virtus_actuator_register(virtus_actuator_id_t id,
                             const virtus_actuator_driver_t *driver);

/**
 * Initialise all registered actuator drivers.
 *
 * @return 0 if all succeed, or the first non-zero error code encountered.
 */
int virtus_actuator_init_all(void);

/**
 * Send a command to a specific actuator.
 *
 * @param cmd Pointer to command structure (cmd->id selects the actuator).
 * @return 0 on success, -ENODEV if no driver registered, or driver error.
 */
int virtus_actuator_set(const virtus_actuator_cmd_t *cmd);

/**
 * Get the current state of a specific actuator.
 *
 * @param id  Actuator to query.
 * @param out Pointer to state structure to fill.
 * @return 0 on success, -ENODEV if no driver registered, or driver error.
 */
int virtus_actuator_get_state(virtus_actuator_id_t id,
                              virtus_actuator_state_t *out);

/**
 * Emergency-stop ALL registered actuators.
 * Iterates every slot and calls emergency_stop on each registered driver.
 * Never fails silently — logs errors but continues to stop remaining actuators.
 *
 * @return 0 if all succeeded, or number of actuators that failed to stop.
 */
int virtus_actuator_emergency_stop_all(void);

/**
 * Check if an actuator is healthy.
 *
 * @param id Actuator to check.
 * @return true if healthy, false otherwise.
 */
bool virtus_actuator_is_healthy(virtus_actuator_id_t id);

/**
 * Get the human-readable name for an actuator ID.
 *
 * @param id Actuator identifier.
 * @return Static string name, or "UNKNOWN" for invalid IDs.
 */
const char *virtus_actuator_name(virtus_actuator_id_t id);

/* ========================================================================
 * HAL API — Communication Functions
 * ======================================================================== */

/**
 * Register a communication driver.
 *
 * @param index Comm channel index (0-3).
 * @param driver Pointer to a const driver struct.
 * @return 0 on success, -EINVAL if index or driver is invalid.
 */
int virtus_comm_register(int index, const virtus_comm_driver_t *driver);

/* ========================================================================
 * HAL API — Health Tracking (internal, exposed for testing)
 * ======================================================================== */

/**
 * Record a successful sensor read for health tracking.
 *
 * @param id Sensor that succeeded.
 */
void virtus_hal_health_record_success(virtus_sensor_id_t id);

/**
 * Record a failed sensor read for health tracking.
 *
 * @param id Sensor that failed.
 */
void virtus_hal_health_record_failure(virtus_sensor_id_t id);

/**
 * Reset health tracking counters for a sensor.
 *
 * @param id Sensor to reset.
 */
void virtus_hal_health_reset(virtus_sensor_id_t id);

/* ========================================================================
 * HAL API — Error Reporting
 * ======================================================================== */

/**
 * Convert an errno-style error code to a human-readable string.
 *
 * @param err Error code (negative values accepted, sign is stripped).
 * @return Static string describing the error.
 */
const char *virtus_hal_error_to_string(int err);

/**
 * Error callback function type for fatal errors.
 */
typedef void (*virtus_hal_error_cb_t)(int err, const char *msg);

/**
 * Register a callback for fatal HAL errors.
 *
 * @param cb Callback function (NULL to unregister).
 */
void virtus_hal_set_error_callback(virtus_hal_error_cb_t cb);

#ifdef __cplusplus
}
#endif

#endif /* VIRTUS_HAL_H_ */

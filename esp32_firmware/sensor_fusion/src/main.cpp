/*
 * Porter Robot — Sensor Fusion Firmware
 * ESP32 #2: ToF + Ultrasonic + Microwave sensor fusion via USB-UART bridge
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 *
 * Subsystems:
 *   - SMF state machine: INIT → CALIBRATING → ACTIVE → DEGRADED → FAULT
 *   - ToF driver (I2C): VL53L0x Time-of-Flight distance sensor
 *   - Ultrasonic driver (GPIO): HC-SR04 trigger/echo timing
 *   - Microwave driver (ADC): RCWL-0516 analog motion detector
 *   - Kalman filter: fuse ToF + Ultrasonic → distance estimate
 *   - Cross-validation: flag >30% disagreement between ToF and Ultrasonic
 *   - Sensor timeout: no response in 100ms → mark sensor degraded
 *   - Transport: protocol packets over UART/CDC ACM to RPi
 *   - Zbus channels: sensor_data, sensor_status, safety_event
 *   - Shell commands for development/debug
 *
 * Thread priorities: sensor_read(0) > protocol(1) > fusion(2) > reporting(5) > shell(14)
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/logging/log.h>
#include <zephyr/smf.h>
#include <zephyr/zbus/zbus.h>
#include <zephyr/shell/shell.h>
#include <zephyr/task_wdt/task_wdt.h>

#include <cstring>
#include <cstdlib>
#include <cmath>
#include <algorithm>

#include "protocol.h"
#include "transport.h"

LOG_MODULE_REGISTER(sensor_fusion, LOG_LEVEL_INF);

/* ========================================================================
 * Configuration Constants
 * ======================================================================== */

#define FIRMWARE_VERSION          "0.2.0"

/* Sensor timing */
#define SENSOR_READ_PERIOD_MS     50      /* 20 Hz sensor read rate */
#define FUSION_PERIOD_MS          50      /* 20 Hz fusion output rate */
#define REPORT_PERIOD_MS          100     /* 10 Hz report to RPi */
#define CALIBRATION_SAMPLES       20      /* samples to average during calibration */
#define SENSOR_TIMEOUT_MS         100     /* no reading → degraded */

/* VL53L0x I2C */
#define VL53L0X_ADDR              0x29
#define VL53L0X_REG_RESULT        0x1E    /* Result range (mm) — simplified */
#define VL53L0X_REG_SYSRANGE      0x00    /* System range start */
#define VL53L0X_REG_WHOAMI        0xC0    /* Device ID register */
#define VL53L0X_DEVICE_ID         0xEE    /* Expected WHO_AM_I value */

/* Ultrasonic HC-SR04 */
#define US_TRIG_PULSE_US          10      /* 10 µs trigger pulse */
#define US_MAX_ECHO_US            30000   /* ~5m max range at ~343 m/s */
#define US_SPEED_OF_SOUND_CM_US   0.0343f /* cm per µs */

/* Microwave RCWL-0516 */
#define MW_MOTION_THRESHOLD       500     /* ADC counts above baseline → motion */
#define MW_ADC_CHANNEL            6       /* GPIO34 = ADC1_CH6 */

/* Kalman filter */
#define KALMAN_Q                  0.01f   /* Process noise covariance */
#define KALMAN_R_TOF              0.5f    /* ToF measurement noise (cm²) */
#define KALMAN_R_US               2.0f    /* Ultrasonic measurement noise (cm²) */

/* Cross-validation */
#define CROSS_VALID_THRESHOLD     0.30f   /* 30% disagreement → flag */

/* Protocol polling */
#define PROTOCOL_POLL_MS          5

/* ========================================================================
 * Sensor Health Tracking
 * ======================================================================== */

enum sensor_id {
    SENSOR_TOF = 0,
    SENSOR_ULTRASONIC,
    SENSOR_MICROWAVE,
    SENSOR_COUNT
};

enum sensor_health {
    SENSOR_OK = 0,
    SENSOR_DEGRADED,
    SENSOR_FAULT,
    SENSOR_NOT_PRESENT,
};

struct sensor_reading {
    float    distance_cm;       /* distance in centimetres */
    int64_t  timestamp;         /* k_uptime_get() of last valid reading */
    enum sensor_health health;
    uint32_t read_count;        /* total successful reads */
    uint32_t error_count;       /* total read errors */
};

static struct sensor_reading sensors[SENSOR_COUNT];

/* ========================================================================
 * Zbus Message Types
 * ======================================================================== */

struct sensor_data_msg {
    float distance_cm;          /* fused distance estimate */
    float confidence;           /* 0.0..1.0 */
    uint8_t motion_detected;    /* microwave motion flag */
    uint8_t cross_valid_ok;     /* ToF/US agree within threshold */
};

struct sensor_status_msg {
    uint8_t state;              /* SMF state enum value */
    uint8_t health[SENSOR_COUNT]; /* per-sensor health */
    float   tof_cm;
    float   us_cm;
    float   fused_cm;
};

struct safety_event_msg {
    uint8_t event;              /* 0=sensor_timeout, 1=all_degraded, 2=fault */
};

ZBUS_CHAN_DEFINE(sensor_data_chan,
    struct sensor_data_msg, NULL, NULL,
    ZBUS_OBSERVERS_EMPTY,
    ZBUS_MSG_INIT(.distance_cm = 0, .confidence = 0, .motion_detected = 0,
                  .cross_valid_ok = 1));

ZBUS_CHAN_DEFINE(sensor_status_chan,
    struct sensor_status_msg, NULL, NULL,
    ZBUS_OBSERVERS_EMPTY,
    ZBUS_MSG_INIT(.state = 0));

ZBUS_CHAN_DEFINE(safety_event_chan,
    struct safety_event_msg, NULL, NULL,
    ZBUS_OBSERVERS_EMPTY,
    ZBUS_MSG_INIT(.event = 0));

/* ========================================================================
 * Hardware Handles
 * ======================================================================== */

/* I2C for ToF sensor */
static const struct device *i2c_dev = DEVICE_DT_GET(DT_NODELABEL(i2c0));

/* Ultrasonic GPIOs */
static const struct gpio_dt_spec us_trig =
    GPIO_DT_SPEC_GET(DT_NODELABEL(us_trig), gpios);
static const struct gpio_dt_spec us_echo =
    GPIO_DT_SPEC_GET(DT_NODELABEL(us_echo), gpios);

/* ADC for microwave sensor */
static const struct device *adc_dev = DEVICE_DT_GET(DT_NODELABEL(adc0));

static const struct adc_channel_cfg mw_adc_cfg = {
    .gain             = ADC_GAIN_1,
    .reference        = ADC_REF_INTERNAL,
    .acquisition_time = ADC_ACQ_TIME_DEFAULT,
    .channel_id       = MW_ADC_CHANNEL,
};

static int16_t mw_adc_buf;
static struct adc_sequence mw_adc_seq = {
    .channels    = BIT(MW_ADC_CHANNEL),
    .buffer      = &mw_adc_buf,
    .buffer_size = sizeof(mw_adc_buf),
    .resolution  = 12,
};

/* Microwave baseline (set during calibration) */
static int16_t mw_baseline = 0;
static bool    mw_motion_detected = false;

/* ========================================================================
 * Kalman Filter (1D)
 * ======================================================================== */

struct kalman_1d {
    float x;        /* state estimate (distance cm) */
    float p;        /* estimation error covariance */
    float q;        /* process noise */
};

static struct kalman_1d kf = {
    .x = 0.0f,
    .p = 100.0f,    /* high initial uncertainty */
    .q = KALMAN_Q,
};

/**
 * Kalman predict step: advance state with process noise.
 */
static void kalman_predict(struct kalman_1d *f)
{
    /* Constant velocity model (no explicit control input) */
    f->p += f->q;
}

/**
 * Kalman update step: incorporate a measurement.
 * @param f  filter state
 * @param z  measurement value
 * @param r  measurement noise covariance
 */
static void kalman_update(struct kalman_1d *f, float z, float r)
{
    float k = f->p / (f->p + r);       /* Kalman gain */
    f->x = f->x + k * (z - f->x);     /* state update */
    f->p = (1.0f - k) * f->p;          /* covariance update */
}

/* ========================================================================
 * Sensor Drivers
 * ======================================================================== */

/* --- VL53L0x ToF (simplified register interface) --- */

static int tof_init(void)
{
    if (!device_is_ready(i2c_dev)) {
        LOG_ERR("I2C device not ready");
        return -ENODEV;
    }

    /* Read WHO_AM_I register to verify sensor */
    uint8_t who;
    int ret = i2c_reg_read_byte(i2c_dev, VL53L0X_ADDR, VL53L0X_REG_WHOAMI, &who);
    if (ret != 0) {
        LOG_WRN("ToF: I2C read failed (%d) — sensor not present?", ret);
        sensors[SENSOR_TOF].health = SENSOR_NOT_PRESENT;
        return ret;
    }

    if (who != VL53L0X_DEVICE_ID) {
        LOG_WRN("ToF: unexpected ID 0x%02X (expected 0x%02X)", who, VL53L0X_DEVICE_ID);
        /* Continue anyway — some clones report different IDs */
    }

    LOG_INF("ToF: VL53L0x detected (ID=0x%02X)", who);
    sensors[SENSOR_TOF].health = SENSOR_OK;
    return 0;
}

static int tof_read_distance_cm(float *distance)
{
    /* Trigger a single-shot measurement */
    int ret = i2c_reg_write_byte(i2c_dev, VL53L0X_ADDR, VL53L0X_REG_SYSRANGE, 0x01);
    if (ret != 0) {
        return ret;
    }

    /* Wait for measurement — VL53L0x typical: 30ms */
    k_msleep(30);

    /* Read result (2 bytes, big-endian, millimetres) */
    uint8_t data[2];
    ret = i2c_burst_read(i2c_dev, VL53L0X_ADDR, VL53L0X_REG_RESULT, data, 2);
    if (ret != 0) {
        return ret;
    }

    uint16_t mm = ((uint16_t)data[0] << 8) | data[1];

    /* VL53L0x returns 8190 (0x1FFE) for out-of-range */
    if (mm >= 8190) {
        return -ERANGE;
    }

    *distance = (float)mm / 10.0f;  /* mm → cm */
    return 0;
}

/* --- HC-SR04 Ultrasonic --- */

static int us_init(void)
{
    int ret;

    if (!gpio_is_ready_dt(&us_trig)) {
        LOG_ERR("Ultrasonic TRIG GPIO not ready");
        sensors[SENSOR_ULTRASONIC].health = SENSOR_NOT_PRESENT;
        return -ENODEV;
    }
    if (!gpio_is_ready_dt(&us_echo)) {
        LOG_ERR("Ultrasonic ECHO GPIO not ready");
        sensors[SENSOR_ULTRASONIC].health = SENSOR_NOT_PRESENT;
        return -ENODEV;
    }

    ret = gpio_pin_configure_dt(&us_trig, GPIO_OUTPUT_INACTIVE);
    if (ret != 0) {
        LOG_ERR("US TRIG config failed: %d", ret);
        return ret;
    }

    ret = gpio_pin_configure_dt(&us_echo, GPIO_INPUT);
    if (ret != 0) {
        LOG_ERR("US ECHO config failed: %d", ret);
        return ret;
    }

    LOG_INF("Ultrasonic: HC-SR04 GPIOs ready (TRIG=%d, ECHO=%d)",
            us_trig.pin, us_echo.pin);
    sensors[SENSOR_ULTRASONIC].health = SENSOR_OK;
    return 0;
}

static int us_read_distance_cm(float *distance)
{
    /* Send 10 µs trigger pulse */
    gpio_pin_set_dt(&us_trig, 1);
    k_busy_wait(US_TRIG_PULSE_US);
    gpio_pin_set_dt(&us_trig, 0);

    /* Wait for echo pin to go HIGH (start of echo) */
    int64_t start_wait = k_uptime_get();
    while (gpio_pin_get_dt(&us_echo) == 0) {
        if ((k_uptime_get() - start_wait) > 10) {
            return -ETIMEDOUT;  /* no echo start within 10ms */
        }
        k_busy_wait(5);
    }

    /* Measure echo HIGH duration using cycle counter */
    uint32_t t_start = k_cycle_get_32();
    while (gpio_pin_get_dt(&us_echo) == 1) {
        uint32_t elapsed_us = k_cyc_to_us_floor32(k_cycle_get_32() - t_start);
        if (elapsed_us > US_MAX_ECHO_US) {
            return -ERANGE;  /* out of range */
        }
        k_busy_wait(5);
    }
    uint32_t t_end = k_cycle_get_32();

    uint32_t echo_us = k_cyc_to_us_floor32(t_end - t_start);
    /* Distance = (time × speed_of_sound) / 2 (round trip) */
    *distance = (float)echo_us * US_SPEED_OF_SOUND_CM_US / 2.0f;

    return 0;
}

/* --- RCWL-0516 Microwave Motion Detector (ADC) --- */

static int mw_init(void)
{
    if (!device_is_ready(adc_dev)) {
        LOG_ERR("ADC device not ready");
        sensors[SENSOR_MICROWAVE].health = SENSOR_NOT_PRESENT;
        return -ENODEV;
    }

    int ret = adc_channel_setup(adc_dev, &mw_adc_cfg);
    if (ret != 0) {
        LOG_ERR("ADC channel setup failed: %d", ret);
        sensors[SENSOR_MICROWAVE].health = SENSOR_NOT_PRESENT;
        return ret;
    }

    LOG_INF("Microwave: ADC CH%d ready", MW_ADC_CHANNEL);
    sensors[SENSOR_MICROWAVE].health = SENSOR_OK;
    return 0;
}

static int mw_read(int16_t *raw_value)
{
    int ret = adc_read(adc_dev, &mw_adc_seq);
    if (ret != 0) {
        return ret;
    }
    *raw_value = mw_adc_buf;
    return 0;
}

static void mw_update_motion(int16_t raw)
{
    int16_t diff = (raw > mw_baseline) ? (raw - mw_baseline) : (mw_baseline - raw);
    mw_motion_detected = (diff > MW_MOTION_THRESHOLD);

    /* Distance: not applicable for microwave — use as binary motion flag.
     * Store ADC delta as "distance" for debug purposes. */
    sensors[SENSOR_MICROWAVE].distance_cm = (float)diff;
    sensors[SENSOR_MICROWAVE].timestamp = k_uptime_get();
    sensors[SENSOR_MICROWAVE].read_count++;
}

/* ========================================================================
 * Sensor Read Thread (reads all sensors periodically)
 * ======================================================================== */

static void sensor_read_tick(void)
{
    int64_t now = k_uptime_get();

    /* --- ToF --- */
    if (sensors[SENSOR_TOF].health != SENSOR_NOT_PRESENT) {
        float tof_cm;
        int ret = tof_read_distance_cm(&tof_cm);
        if (ret == 0) {
            sensors[SENSOR_TOF].distance_cm = tof_cm;
            sensors[SENSOR_TOF].timestamp = now;
            sensors[SENSOR_TOF].read_count++;
            if (sensors[SENSOR_TOF].health == SENSOR_DEGRADED) {
                sensors[SENSOR_TOF].health = SENSOR_OK;
                LOG_INF("ToF: recovered");
            }
        } else {
            sensors[SENSOR_TOF].error_count++;
            if ((now - sensors[SENSOR_TOF].timestamp) > SENSOR_TIMEOUT_MS) {
                if (sensors[SENSOR_TOF].health == SENSOR_OK) {
                    LOG_WRN("ToF: timeout — degraded");
                }
                sensors[SENSOR_TOF].health = SENSOR_DEGRADED;
            }
        }
    }

    /* --- Ultrasonic --- */
    if (sensors[SENSOR_ULTRASONIC].health != SENSOR_NOT_PRESENT) {
        float us_cm;
        int ret = us_read_distance_cm(&us_cm);
        if (ret == 0) {
            sensors[SENSOR_ULTRASONIC].distance_cm = us_cm;
            sensors[SENSOR_ULTRASONIC].timestamp = now;
            sensors[SENSOR_ULTRASONIC].read_count++;
            if (sensors[SENSOR_ULTRASONIC].health == SENSOR_DEGRADED) {
                sensors[SENSOR_ULTRASONIC].health = SENSOR_OK;
                LOG_INF("Ultrasonic: recovered");
            }
        } else {
            sensors[SENSOR_ULTRASONIC].error_count++;
            if ((now - sensors[SENSOR_ULTRASONIC].timestamp) > SENSOR_TIMEOUT_MS) {
                if (sensors[SENSOR_ULTRASONIC].health == SENSOR_OK) {
                    LOG_WRN("Ultrasonic: timeout — degraded");
                }
                sensors[SENSOR_ULTRASONIC].health = SENSOR_DEGRADED;
            }
        }
    }

    /* --- Microwave --- */
    if (sensors[SENSOR_MICROWAVE].health != SENSOR_NOT_PRESENT) {
        int16_t raw;
        int ret = mw_read(&raw);
        if (ret == 0) {
            mw_update_motion(raw);
        } else {
            sensors[SENSOR_MICROWAVE].error_count++;
        }
    }
}

/* ========================================================================
 * Fusion Engine
 * ======================================================================== */

/* Fused output — shared with protocol and reporting threads */
static float    fused_distance_cm = 0.0f;
static float    fused_confidence  = 0.0f;
static bool     cross_valid_ok    = true;

static void fusion_tick(void)
{
    int64_t now = k_uptime_get();
    bool tof_ok = (sensors[SENSOR_TOF].health == SENSOR_OK) &&
                  ((now - sensors[SENSOR_TOF].timestamp) < SENSOR_TIMEOUT_MS);
    bool us_ok  = (sensors[SENSOR_ULTRASONIC].health == SENSOR_OK) &&
                  ((now - sensors[SENSOR_ULTRASONIC].timestamp) < SENSOR_TIMEOUT_MS);

    /* Kalman predict */
    kalman_predict(&kf);

    /* Cross-validation check */
    if (tof_ok && us_ok) {
        float avg = (sensors[SENSOR_TOF].distance_cm +
                     sensors[SENSOR_ULTRASONIC].distance_cm) / 2.0f;
        if (avg > 0.1f) {
            float diff = fabsf(sensors[SENSOR_TOF].distance_cm -
                               sensors[SENSOR_ULTRASONIC].distance_cm);
            cross_valid_ok = (diff / avg) < CROSS_VALID_THRESHOLD;
            if (!cross_valid_ok) {
                LOG_WRN("Cross-validation fail: ToF=%.1f US=%.1f (diff=%.1f%%)",
                        (double)sensors[SENSOR_TOF].distance_cm,
                        (double)sensors[SENSOR_ULTRASONIC].distance_cm,
                        (double)(diff / avg * 100.0f));
            }
        }
    }

    /* Fuse available measurements via Kalman update */
    int updates = 0;
    if (tof_ok) {
        kalman_update(&kf, sensors[SENSOR_TOF].distance_cm, KALMAN_R_TOF);
        updates++;
    }
    if (us_ok) {
        kalman_update(&kf, sensors[SENSOR_ULTRASONIC].distance_cm, KALMAN_R_US);
        updates++;
    }

    if (updates > 0) {
        fused_distance_cm = kf.x;
        /* Confidence based on covariance and sensor count */
        float max_p = 100.0f;
        fused_confidence = 1.0f - std::min(kf.p / max_p, 1.0f);
        if (updates == 2 && cross_valid_ok) {
            fused_confidence = std::min(fused_confidence + 0.1f, 1.0f);
        }
    } else {
        /* No sensors available */
        fused_confidence = 0.0f;
    }

    /* Publish to zbus */
    struct sensor_data_msg data = {
        .distance_cm     = fused_distance_cm,
        .confidence      = fused_confidence,
        .motion_detected = mw_motion_detected ? (uint8_t)1 : (uint8_t)0,
        .cross_valid_ok  = cross_valid_ok ? (uint8_t)1 : (uint8_t)0,
    };
    zbus_chan_pub(&sensor_data_chan, &data, K_NO_WAIT);
}

/* ========================================================================
 * SMF State Machine
 * ======================================================================== */

extern const struct smf_state sensor_states[];

enum sensor_state_e {
    STATE_INIT,
    STATE_CALIBRATING,
    STATE_ACTIVE,
    STATE_DEGRADED,
    STATE_FAULT,
    STATE_SM_COUNT
};

struct sensor_sm_obj {
    struct smf_ctx ctx;
    uint8_t  calib_count;
    float    calib_sum_tof;
    float    calib_sum_us;
    int16_t  calib_sum_mw;
    uint8_t  active_sensor_count;    /* sensors with health == OK */
};

static struct sensor_sm_obj sm_obj;

/* Helper: count healthy sensors */
static uint8_t count_active_sensors(void)
{
    uint8_t n = 0;
    for (int i = 0; i < SENSOR_COUNT; i++) {
        if (sensors[i].health == SENSOR_OK) {
            n++;
        }
    }
    return n;
}

/* --- INIT --- */
static void init_entry(void *o)
{
    LOG_INF("State: INIT");
}

static void init_run(void *o)
{
    struct sensor_sm_obj *obj = static_cast<struct sensor_sm_obj *>(o);
    /* Wait for at least one sensor to be present (not NOT_PRESENT) */
    uint8_t present = 0;
    for (int i = 0; i < SENSOR_COUNT; i++) {
        if (sensors[i].health != SENSOR_NOT_PRESENT) {
            present++;
        }
    }
    if (present > 0) {
        smf_set_state(SMF_CTX(obj), &sensor_states[STATE_CALIBRATING]);
    }
}

/* --- CALIBRATING --- */
static void calibrating_entry(void *o)
{
    struct sensor_sm_obj *obj = static_cast<struct sensor_sm_obj *>(o);
    LOG_INF("State: CALIBRATING (%d samples)", CALIBRATION_SAMPLES);
    obj->calib_count  = 0;
    obj->calib_sum_tof = 0.0f;
    obj->calib_sum_us  = 0.0f;
    obj->calib_sum_mw  = 0;
}

static void calibrating_run(void *o)
{
    struct sensor_sm_obj *obj = static_cast<struct sensor_sm_obj *>(o);

    /* Read sensor data during calibration */
    sensor_read_tick();

    /* Accumulate microwave baseline */
    int16_t raw;
    if (mw_read(&raw) == 0) {
        obj->calib_sum_mw += raw;
    }

    obj->calib_count++;

    if (obj->calib_count >= CALIBRATION_SAMPLES) {
        /* Compute microwave baseline */
        mw_baseline = obj->calib_sum_mw / CALIBRATION_SAMPLES;
        LOG_INF("Calibration complete — MW baseline=%d", mw_baseline);

        /* Initialize Kalman with first ToF/US reading */
        if (sensors[SENSOR_TOF].health == SENSOR_OK) {
            kf.x = sensors[SENSOR_TOF].distance_cm;
        } else if (sensors[SENSOR_ULTRASONIC].health == SENSOR_OK) {
            kf.x = sensors[SENSOR_ULTRASONIC].distance_cm;
        }
        kf.p = 10.0f;  /* reduced initial uncertainty after calibration */

        smf_set_state(SMF_CTX(obj), &sensor_states[STATE_ACTIVE]);
    }
}

/* --- ACTIVE --- */
static void active_entry(void *o)
{
    LOG_INF("State: ACTIVE");
}

static void active_run(void *o)
{
    struct sensor_sm_obj *obj = static_cast<struct sensor_sm_obj *>(o);

    sensor_read_tick();
    fusion_tick();

    obj->active_sensor_count = count_active_sensors();

    /* Check for degradation */
    if (obj->active_sensor_count == 0) {
        struct safety_event_msg evt = { .event = 1 };  /* all_degraded */
        zbus_chan_pub(&safety_event_chan, &evt, K_NO_WAIT);
        smf_set_state(SMF_CTX(obj), &sensor_states[STATE_FAULT]);
        return;
    }

    /* If at least one sensor is degraded, transition to DEGRADED */
    for (int i = 0; i < SENSOR_COUNT; i++) {
        if (sensors[i].health == SENSOR_DEGRADED) {
            smf_set_state(SMF_CTX(obj), &sensor_states[STATE_DEGRADED]);
            return;
        }
    }
}

/* --- DEGRADED --- */
static void degraded_entry(void *o)
{
    LOG_WRN("State: DEGRADED");
    /* Identify which sensors are degraded */
    const char *names[] = {"ToF", "Ultrasonic", "Microwave"};
    for (int i = 0; i < SENSOR_COUNT; i++) {
        if (sensors[i].health == SENSOR_DEGRADED) {
            LOG_WRN("  %s: DEGRADED (errors=%u)", names[i], sensors[i].error_count);
        }
    }
}

static void degraded_run(void *o)
{
    struct sensor_sm_obj *obj = static_cast<struct sensor_sm_obj *>(o);

    sensor_read_tick();
    fusion_tick();

    obj->active_sensor_count = count_active_sensors();

    /* All sensors dead → FAULT */
    if (obj->active_sensor_count == 0) {
        struct safety_event_msg evt = { .event = 1 };
        zbus_chan_pub(&safety_event_chan, &evt, K_NO_WAIT);
        smf_set_state(SMF_CTX(obj), &sensor_states[STATE_FAULT]);
        return;
    }

    /* All remaining sensors recovered → ACTIVE */
    bool any_degraded = false;
    for (int i = 0; i < SENSOR_COUNT; i++) {
        if (sensors[i].health == SENSOR_DEGRADED) {
            any_degraded = true;
            break;
        }
    }
    if (!any_degraded) {
        LOG_INF("All sensors recovered → ACTIVE");
        smf_set_state(SMF_CTX(obj), &sensor_states[STATE_ACTIVE]);
    }
}

/* --- FAULT --- */
static void fault_entry(void *o)
{
    LOG_ERR("State: FAULT — all distance sensors offline");
    struct safety_event_msg evt = { .event = 2 };  /* fault */
    zbus_chan_pub(&safety_event_chan, &evt, K_NO_WAIT);
}

static void fault_run(void *o)
{
    struct sensor_sm_obj *obj = static_cast<struct sensor_sm_obj *>(o);

    /* Keep trying to read sensors — they may come back */
    sensor_read_tick();

    if (count_active_sensors() > 0) {
        LOG_INF("Sensor recovered — returning to DEGRADED for validation");
        smf_set_state(SMF_CTX(obj), &sensor_states[STATE_DEGRADED]);
    }
}

/* State table */
const struct smf_state sensor_states[] = {
    [STATE_INIT]        = SMF_CREATE_STATE(init_entry,        init_run,        NULL, NULL, NULL),
    [STATE_CALIBRATING] = SMF_CREATE_STATE(calibrating_entry, calibrating_run, NULL, NULL, NULL),
    [STATE_ACTIVE]      = SMF_CREATE_STATE(active_entry,      active_run,      NULL, NULL, NULL),
    [STATE_DEGRADED]    = SMF_CREATE_STATE(degraded_entry,    degraded_run,    NULL, NULL, NULL),
    [STATE_FAULT]       = SMF_CREATE_STATE(fault_entry,       fault_run,       NULL, NULL, NULL),
};

/* ========================================================================
 * Protocol Handler (runs in its own thread)
 * ======================================================================== */

static protocol_parser_t proto_parser;

/**
 * Get current state index from SMF context.
 */
static uint8_t get_state_index(void)
{
    for (int i = 0; i < STATE_SM_COUNT; i++) {
        if (sm_obj.ctx.current == &sensor_states[i]) {
            return (uint8_t)i;
        }
    }
    return 0xFF;
}

static void handle_packet(const protocol_packet_t *pkt)
{
    uint8_t resp_buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t  resp_len;

    switch (pkt->command) {
    case CMD_SENSOR_TOF: {
        /* Return raw ToF reading */
        uint8_t payload[5];
        uint16_t mm = (uint16_t)(sensors[SENSOR_TOF].distance_cm * 10.0f);
        payload[0] = (uint8_t)(mm >> 8);
        payload[1] = (uint8_t)(mm & 0xFF);
        payload[2] = (uint8_t)sensors[SENSOR_TOF].health;
        payload[3] = 0;  /* reserved */
        payload[4] = 0;
        protocol_encode(CMD_SENSOR_TOF, payload, 5, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }

    case CMD_SENSOR_ULTRASONIC: {
        uint8_t payload[5];
        uint16_t mm = (uint16_t)(sensors[SENSOR_ULTRASONIC].distance_cm * 10.0f);
        payload[0] = (uint8_t)(mm >> 8);
        payload[1] = (uint8_t)(mm & 0xFF);
        payload[2] = (uint8_t)sensors[SENSOR_ULTRASONIC].health;
        payload[3] = 0;
        payload[4] = 0;
        protocol_encode(CMD_SENSOR_ULTRASONIC, payload, 5, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }

    case CMD_SENSOR_MICROWAVE: {
        uint8_t payload[4];
        payload[0] = mw_motion_detected ? 1 : 0;
        int16_t delta = (int16_t)sensors[SENSOR_MICROWAVE].distance_cm;
        payload[1] = (uint8_t)((delta >> 8) & 0xFF);
        payload[2] = (uint8_t)(delta & 0xFF);
        payload[3] = (uint8_t)sensors[SENSOR_MICROWAVE].health;
        protocol_encode(CMD_SENSOR_MICROWAVE, payload, 4, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }

    case CMD_SENSOR_FUSED: {
        /* Fused data: distance(u16 mm), confidence(u8 0-100), motion(u8), cross_valid(u8) */
        uint8_t payload[5];
        uint16_t mm = (uint16_t)(fused_distance_cm * 10.0f);
        payload[0] = (uint8_t)(mm >> 8);
        payload[1] = (uint8_t)(mm & 0xFF);
        payload[2] = (uint8_t)(fused_confidence * 100.0f);
        payload[3] = mw_motion_detected ? 1 : 0;
        payload[4] = cross_valid_ok ? 1 : 0;
        protocol_encode(CMD_SENSOR_FUSED, payload, 5, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }

    case CMD_SENSOR_STATUS: {
        /* Per-sensor health + state */
        uint8_t payload[5];
        payload[0] = get_state_index();
        payload[1] = (uint8_t)sensors[SENSOR_TOF].health;
        payload[2] = (uint8_t)sensors[SENSOR_ULTRASONIC].health;
        payload[3] = (uint8_t)sensors[SENSOR_MICROWAVE].health;
        payload[4] = count_active_sensors();
        protocol_encode(CMD_SENSOR_STATUS, payload, 5, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }

    case CMD_HEARTBEAT:
        LOG_DBG("CMD: HEARTBEAT");
        protocol_encode_ack(pkt->command, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;

    case CMD_VERSION: {
        const char *ver = FIRMWARE_VERSION;
        uint8_t vlen = (uint8_t)strlen(ver);
        protocol_encode(CMD_VERSION, (const uint8_t *)ver, vlen, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }

    case CMD_RESET:
        LOG_INF("CMD: RESET — reinitializing sensors");
        for (int i = 0; i < SENSOR_COUNT; i++) {
            if (sensors[i].health == SENSOR_DEGRADED ||
                sensors[i].health == SENSOR_FAULT) {
                sensors[i].health = SENSOR_OK;
                sensors[i].error_count = 0;
            }
        }
        smf_set_state(SMF_CTX(&sm_obj), &sensor_states[STATE_CALIBRATING]);
        protocol_encode_ack(pkt->command, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;

    default:
        LOG_WRN("Unknown command: 0x%02x", pkt->command);
        protocol_encode_nack(pkt->command, NACK_UNKNOWN_CMD, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }
}

/* Protocol thread: reads transport, feeds parser, dispatches packets */
static void protocol_thread_fn(void *, void *, void *)
{
    LOG_INF("Protocol thread started");

    transport_config_t tcfg = TRANSPORT_CONFIG_DEFAULT;
    int ret = transport_init(&tcfg);
    if (ret != TRANSPORT_OK) {
        LOG_ERR("Transport init failed: %d", ret);
        return;
    }
    LOG_INF("Transport ready (%s)", transport_backend_name());

    protocol_parser_init(&proto_parser);

    while (true) {
        uint8_t buf[64];
        int n = transport_read(buf, sizeof(buf));

        for (int i = 0; i < n; i++) {
            if (protocol_parser_feed(&proto_parser, buf[i])) {
                handle_packet(&proto_parser.packet);
                protocol_parser_reset(&proto_parser);
            }
        }

        k_msleep(PROTOCOL_POLL_MS);
    }
}

K_THREAD_STACK_DEFINE(protocol_stack, 2048);
static struct k_thread protocol_thread_data;

/* ========================================================================
 * Reporting Thread — periodically sends fused data to RPi
 * ======================================================================== */

static void reporting_thread_fn(void *, void *, void *)
{
    LOG_INF("Reporting thread started");

    while (true) {
        /* Auto-send fused data to RPi */
        uint8_t resp_buf[PROTOCOL_MAX_PACKET_SIZE];
        size_t  resp_len;

        uint8_t payload[5];
        uint16_t mm = (uint16_t)(fused_distance_cm * 10.0f);
        payload[0] = (uint8_t)(mm >> 8);
        payload[1] = (uint8_t)(mm & 0xFF);
        payload[2] = (uint8_t)(fused_confidence * 100.0f);
        payload[3] = mw_motion_detected ? 1 : 0;
        payload[4] = cross_valid_ok ? 1 : 0;

        protocol_encode(CMD_SENSOR_FUSED, payload, 5, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);

        /* Update zbus status */
        struct sensor_status_msg status = {
            .state    = get_state_index(),
            .health   = {
                (uint8_t)sensors[SENSOR_TOF].health,
                (uint8_t)sensors[SENSOR_ULTRASONIC].health,
                (uint8_t)sensors[SENSOR_MICROWAVE].health,
            },
            .tof_cm   = sensors[SENSOR_TOF].distance_cm,
            .us_cm    = sensors[SENSOR_ULTRASONIC].distance_cm,
            .fused_cm = fused_distance_cm,
        };
        zbus_chan_pub(&sensor_status_chan, &status, K_NO_WAIT);

        k_msleep(REPORT_PERIOD_MS);
    }
}

K_THREAD_STACK_DEFINE(reporting_stack, 1024);
static struct k_thread reporting_thread_data;

/* ========================================================================
 * Shell Commands (development/debug)
 * ======================================================================== */

static int cmd_sensor_status(const struct shell *sh, size_t argc, char **argv)
{
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    const char *state_names[] = {"INIT", "CALIBRATING", "ACTIVE", "DEGRADED", "FAULT"};
    const char *health_names[] = {"OK", "DEGRADED", "FAULT", "NOT_PRESENT"};
    const char *sensor_names[] = {"ToF", "Ultrasonic", "Microwave"};

    shell_print(sh, "State: %s", state_names[get_state_index()]);
    shell_print(sh, "");
    for (int i = 0; i < SENSOR_COUNT; i++) {
        shell_print(sh, "  %s: %s  dist=%.1f cm  reads=%u  errors=%u",
                    sensor_names[i],
                    health_names[sensors[i].health],
                    (double)sensors[i].distance_cm,
                    sensors[i].read_count,
                    sensors[i].error_count);
    }
    shell_print(sh, "");
    shell_print(sh, "Fused: %.1f cm  conf=%.0f%%  motion=%s  cross_valid=%s",
                (double)fused_distance_cm,
                (double)(fused_confidence * 100.0f),
                mw_motion_detected ? "YES" : "no",
                cross_valid_ok ? "OK" : "FAIL");
    shell_print(sh, "Kalman: x=%.2f  P=%.4f",
                (double)kf.x, (double)kf.p);
    return 0;
}

static int cmd_sensor_reset(const struct shell *sh, size_t argc, char **argv)
{
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    for (int i = 0; i < SENSOR_COUNT; i++) {
        if (sensors[i].health != SENSOR_NOT_PRESENT) {
            sensors[i].health = SENSOR_OK;
            sensors[i].error_count = 0;
        }
    }
    smf_set_state(SMF_CTX(&sm_obj), &sensor_states[STATE_CALIBRATING]);
    shell_print(sh, "Sensors reset → CALIBRATING");
    return 0;
}

static int cmd_sensor_raw(const struct shell *sh, size_t argc, char **argv)
{
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    shell_print(sh, "ToF:         %.1f cm", (double)sensors[SENSOR_TOF].distance_cm);
    shell_print(sh, "Ultrasonic:  %.1f cm", (double)sensors[SENSOR_ULTRASONIC].distance_cm);
    shell_print(sh, "Microwave:   raw_delta=%.0f  motion=%s",
                (double)sensors[SENSOR_MICROWAVE].distance_cm,
                mw_motion_detected ? "YES" : "no");
    shell_print(sh, "MW baseline: %d", mw_baseline);
    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sensor_cmds,
    SHELL_CMD(status, NULL, "Show sensor status and fused output", cmd_sensor_status),
    SHELL_CMD(raw,    NULL, "Show raw sensor readings", cmd_sensor_raw),
    SHELL_CMD(reset,  NULL, "Reset sensors, re-calibrate", cmd_sensor_reset),
    SHELL_SUBCMD_SET_END
);
SHELL_CMD_REGISTER(sensor, &sensor_cmds, "Sensor fusion commands", NULL);

/* ========================================================================
 * Hardware Initialization
 * ======================================================================== */

static int hw_init(void)
{
    /* Initialize sensor health to unknown/not-present */
    for (int i = 0; i < SENSOR_COUNT; i++) {
        sensors[i].health = SENSOR_NOT_PRESENT;
        sensors[i].distance_cm = 0.0f;
        sensors[i].timestamp = 0;
        sensors[i].read_count = 0;
        sensors[i].error_count = 0;
    }

    /* Initialize each sensor (non-fatal if not present) */
    tof_init();
    us_init();
    mw_init();

    /* Report which sensors are available */
    const char *names[] = {"ToF", "Ultrasonic", "Microwave"};
    uint8_t present = 0;
    for (int i = 0; i < SENSOR_COUNT; i++) {
        if (sensors[i].health != SENSOR_NOT_PRESENT) {
            present++;
            LOG_INF("Sensor %s: available", names[i]);
        } else {
            LOG_WRN("Sensor %s: NOT PRESENT", names[i]);
        }
    }

    if (present == 0) {
        LOG_ERR("No sensors detected — system will enter FAULT state");
    }

    return 0;
}

/* ========================================================================
 * Main Entry Point
 * ======================================================================== */

int main(void)
{
    LOG_INF("Porter Robot — Sensor Fusion v%s", FIRMWARE_VERSION);
    LOG_INF("VirtusCo (c) 2026");

    /* Initialize hardware */
    hw_init();

    /* Initialize state machine */
    smf_set_initial(SMF_CTX(&sm_obj), &sensor_states[STATE_INIT]);

    /* Start protocol thread (priority 1) */
    k_thread_create(&protocol_thread_data, protocol_stack,
                    K_THREAD_STACK_SIZEOF(protocol_stack),
                    protocol_thread_fn, NULL, NULL, NULL,
                    1, 0, K_NO_WAIT);
    k_thread_name_set(&protocol_thread_data, "proto");

    /* Start reporting thread (priority 5) */
    k_thread_create(&reporting_thread_data, reporting_stack,
                    K_THREAD_STACK_SIZEOF(reporting_stack),
                    reporting_thread_fn, NULL, NULL, NULL,
                    5, 0, K_NO_WAIT);
    k_thread_name_set(&reporting_thread_data, "report");

    LOG_INF("All subsystems initialized — entering main loop");

    /* Main sensor fusion loop (priority 0 — highest preemptible) */
    while (true) {
        int32_t smf_ret = smf_run_state(SMF_CTX(&sm_obj));
        if (smf_ret != 0) {
            LOG_ERR("SMF terminated with %d", smf_ret);
            break;
        }

        k_msleep(SENSOR_READ_PERIOD_MS);
    }

    return 0;
}

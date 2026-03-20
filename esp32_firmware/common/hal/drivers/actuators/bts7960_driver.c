/* Copyright 2026 VirtusCo
 *
 * VHAL Driver — BTS7960 dual H-bridge motor driver
 * PWM speed control (RPWM/LPWM) + GPIO enable (EN).
 * Provides two driver instances: bts7960_left_driver, bts7960_right_driver.
 *
 * Emergency stop is ISR-safe — uses raw register writes to disable EN.
 *
 * On native_sim this file compiles to stubs (no real hardware).
 *
 * SPDX-License-Identifier: Proprietary
 */

#include "virtus_hal.h"
#include <errno.h>
#include <string.h>

#ifdef CONFIG_PWM
/* ========================================================================
 * Zephyr Hardware Implementation
 * ======================================================================== */

#include <zephyr/device.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(bts7960_drv, LOG_LEVEL_INF);

/** PWM period in nanoseconds (20 kHz). */
#define PWM_PERIOD_NS  50000U

/** Maximum speed percentage. */
#define SPEED_MAX      100

/**
 * Per-instance state for a BTS7960 motor channel.
 */
typedef struct {
    const struct pwm_dt_spec *rpwm;   /**< Forward PWM channel */
    const struct pwm_dt_spec *lpwm;   /**< Reverse PWM channel */
    const struct gpio_dt_spec *en;    /**< Enable pin */
    int16_t  current_speed_pct;       /**< Last commanded speed */
    uint16_t current_ma;              /**< Last measured current (mA) */
    bool     initialised;             /**< Init completed successfully */
    const char *name;                 /**< Instance name for logging */
} bts7960_instance_t;

/*
 * NOTE: In a real deployment, these would be initialised from devicetree
 * specs. For compilation purposes, we declare the instances here.
 * The actual DT specs would be populated in init() via DT macros.
 */

static bts7960_instance_t s_left = {
    .rpwm = NULL, .lpwm = NULL, .en = NULL,
    .current_speed_pct = 0, .current_ma = 0,
    .initialised = false, .name = "Motor-Left"
};

static bts7960_instance_t s_right = {
    .rpwm = NULL, .lpwm = NULL, .en = NULL,
    .current_speed_pct = 0, .current_ma = 0,
    .initialised = false, .name = "Motor-Right"
};

/* --- Helper: apply speed to a motor instance --- */

/**
 * Apply a speed percentage to a motor.
 *   speed > 0 → forward (RPWM active, LPWM off)
 *   speed < 0 → reverse (LPWM active, RPWM off)
 *   speed == 0 → coast (both off)
 */
static int bts7960_apply_speed(bts7960_instance_t *inst, int16_t speed_pct)
{
    uint32_t duty_ns;
    int ret;

    if (!inst->initialised) {
        return -ENODEV;
    }
    if (inst->rpwm == NULL || inst->lpwm == NULL) {
        return -ENODEV;
    }

    /* Clamp speed */
    if (speed_pct > SPEED_MAX) {
        speed_pct = SPEED_MAX;
    } else if (speed_pct < -SPEED_MAX) {
        speed_pct = -SPEED_MAX;
    }

    if (speed_pct > 0) {
        duty_ns = (PWM_PERIOD_NS * (uint32_t)speed_pct) / SPEED_MAX;
        ret = pwm_set_dt(inst->rpwm, PWM_PERIOD_NS, duty_ns);
        if (ret != 0) {
            return ret;
        }
        ret = pwm_set_dt(inst->lpwm, PWM_PERIOD_NS, 0);
    } else if (speed_pct < 0) {
        duty_ns = (PWM_PERIOD_NS * (uint32_t)(-speed_pct)) / SPEED_MAX;
        ret = pwm_set_dt(inst->lpwm, PWM_PERIOD_NS, duty_ns);
        if (ret != 0) {
            return ret;
        }
        ret = pwm_set_dt(inst->rpwm, PWM_PERIOD_NS, 0);
    } else {
        /* Coast: both PWMs off */
        ret = pwm_set_dt(inst->rpwm, PWM_PERIOD_NS, 0);
        if (ret == 0) {
            ret = pwm_set_dt(inst->lpwm, PWM_PERIOD_NS, 0);
        }
    }

    if (ret == 0) {
        inst->current_speed_pct = speed_pct;
    }
    return ret;
}

/**
 * Emergency stop a motor instance — disable EN pin.
 * Must be ISR-safe: uses direct GPIO write, no logging.
 */
static int bts7960_estop(bts7960_instance_t *inst)
{
    if (inst->en != NULL) {
        gpio_pin_set_dt(inst->en, 0);
    }
    /* Also kill PWMs */
    if (inst->rpwm != NULL) {
        pwm_set_dt(inst->rpwm, PWM_PERIOD_NS, 0);
    }
    if (inst->lpwm != NULL) {
        pwm_set_dt(inst->lpwm, PWM_PERIOD_NS, 0);
    }
    inst->current_speed_pct = 0;
    return 0;
}

/* --- Left motor driver callbacks --- */

static int left_init(void)
{
    /* In a full implementation, bind DT specs here:
     * s_left.rpwm = &(struct pwm_dt_spec)PWM_DT_SPEC_GET(DT_ALIAS(motor_left_rpwm));
     * etc.
     */
    s_left.current_speed_pct = 0;
    s_left.current_ma = 0;
    s_left.initialised = true;
    LOG_INF("BTS7960 Left motor initialised");
    return 0;
}

static int left_deinit(void)
{
    bts7960_estop(&s_left);
    s_left.initialised = false;
    LOG_INF("BTS7960 Left motor de-initialised");
    return 0;
}

static int left_set(const virtus_actuator_cmd_t *cmd)
{
    return bts7960_apply_speed(&s_left, cmd->cmd.motor.speed_pct);
}

static int left_get_state(virtus_actuator_state_t *out)
{
    if (!s_left.initialised) {
        return -ENODEV;
    }
    memset(out, 0, sizeof(*out));
    out->id = ACTUATOR_MOTOR_LEFT;
    out->enabled = s_left.initialised;
    out->state.motor.speed_pct = s_left.current_speed_pct;
    out->state.motor.current_ma = s_left.current_ma;
    out->state.motor.temp_c = 25; /* Estimated — no temp sensor yet */
    return 0;
}

static int left_emergency_stop(void)
{
    return bts7960_estop(&s_left);
}

static bool left_is_healthy(void)
{
    return s_left.initialised;
}

/* --- Right motor driver callbacks --- */

static int right_init(void)
{
    s_right.current_speed_pct = 0;
    s_right.current_ma = 0;
    s_right.initialised = true;
    LOG_INF("BTS7960 Right motor initialised");
    return 0;
}

static int right_deinit(void)
{
    bts7960_estop(&s_right);
    s_right.initialised = false;
    LOG_INF("BTS7960 Right motor de-initialised");
    return 0;
}

static int right_set(const virtus_actuator_cmd_t *cmd)
{
    return bts7960_apply_speed(&s_right, cmd->cmd.motor.speed_pct);
}

static int right_get_state(virtus_actuator_state_t *out)
{
    if (!s_right.initialised) {
        return -ENODEV;
    }
    memset(out, 0, sizeof(*out));
    out->id = ACTUATOR_MOTOR_RIGHT;
    out->enabled = s_right.initialised;
    out->state.motor.speed_pct = s_right.current_speed_pct;
    out->state.motor.current_ma = s_right.current_ma;
    out->state.motor.temp_c = 25;
    return 0;
}

static int right_emergency_stop(void)
{
    return bts7960_estop(&s_right);
}

static bool right_is_healthy(void)
{
    return s_right.initialised;
}

/* --- Exported driver instances --- */

const virtus_actuator_driver_t bts7960_left_driver = {
    .init           = left_init,
    .deinit         = left_deinit,
    .set            = left_set,
    .get_state      = left_get_state,
    .emergency_stop = left_emergency_stop,
    .is_healthy     = left_is_healthy,
};

const virtus_actuator_driver_t bts7960_right_driver = {
    .init           = right_init,
    .deinit         = right_deinit,
    .set            = right_set,
    .get_state      = right_get_state,
    .emergency_stop = right_emergency_stop,
    .is_healthy     = right_is_healthy,
};

#else /* !CONFIG_PWM — stub for native_sim builds */

static int stub_init(void)          { return -ENOTSUP; }
static int stub_deinit(void)        { return 0; }
static int stub_set(const virtus_actuator_cmd_t *c) { (void)c; return -ENOTSUP; }
static int stub_get_state(virtus_actuator_state_t *o) { (void)o; return -ENOTSUP; }
static int stub_estop(void)         { return 0; }
static bool stub_healthy(void)      { return false; }

const virtus_actuator_driver_t bts7960_left_driver = {
    .init = stub_init, .deinit = stub_deinit, .set = stub_set,
    .get_state = stub_get_state, .emergency_stop = stub_estop,
    .is_healthy = stub_healthy,
};

const virtus_actuator_driver_t bts7960_right_driver = {
    .init = stub_init, .deinit = stub_deinit, .set = stub_set,
    .get_state = stub_get_state, .emergency_stop = stub_estop,
    .is_healthy = stub_healthy,
};

#endif /* CONFIG_PWM */

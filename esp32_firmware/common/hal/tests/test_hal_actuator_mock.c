/* Copyright 2026 VirtusCo
 *
 * VHAL Ztest — Mock actuator tests
 * Verifies actuator set dispatch, get_state, and emergency_stop
 * using a mock motor driver that records all commands.
 *
 * SPDX-License-Identifier: Proprietary
 */

#include <zephyr/ztest.h>
#include "virtus_hal.h"
#include <errno.h>
#include <string.h>

/* ========================================================================
 * Mock motor driver — records commands for verification
 * ======================================================================== */

static int mock_motor_init_called;
static int mock_motor_set_called;
static int mock_motor_estop_called;
static int16_t mock_motor_last_speed;
static uint8_t mock_motor_last_flags;

static int mock_motor_init(void)
{
    mock_motor_init_called++;
    mock_motor_last_speed = 0;
    mock_motor_last_flags = 0;
    return 0;
}

static int mock_motor_deinit(void)
{
    return 0;
}

static int mock_motor_set(const virtus_actuator_cmd_t *cmd)
{
    mock_motor_set_called++;
    mock_motor_last_speed = cmd->cmd.motor.speed_pct;
    mock_motor_last_flags = cmd->cmd.motor.flags;
    return 0;
}

static int mock_motor_get_state(virtus_actuator_state_t *out)
{
    memset(out, 0, sizeof(*out));
    out->id = ACTUATOR_MOTOR_LEFT;
    out->enabled = true;
    out->state.motor.speed_pct = mock_motor_last_speed;
    out->state.motor.current_ma = 500;
    out->state.motor.temp_c = 35;
    return 0;
}

static int mock_motor_emergency_stop(void)
{
    mock_motor_estop_called++;
    mock_motor_last_speed = 0;
    return 0;
}

static bool mock_motor_is_healthy(void)
{
    return true;
}

static const virtus_actuator_driver_t s_mock_motor = {
    .init           = mock_motor_init,
    .deinit         = mock_motor_deinit,
    .set            = mock_motor_set,
    .get_state      = mock_motor_get_state,
    .emergency_stop = mock_motor_emergency_stop,
    .is_healthy     = mock_motor_is_healthy,
};

/* Second mock motor for right side */
static int mock_motor_r_estop_called;

static int mock_motor_r_init(void) { return 0; }
static int mock_motor_r_deinit(void) { return 0; }
static int mock_motor_r_set(const virtus_actuator_cmd_t *cmd) { (void)cmd; return 0; }
static int mock_motor_r_get_state(virtus_actuator_state_t *out)
{
    memset(out, 0, sizeof(*out));
    out->id = ACTUATOR_MOTOR_RIGHT;
    out->enabled = true;
    return 0;
}
static int mock_motor_r_estop(void) { mock_motor_r_estop_called++; return 0; }
static bool mock_motor_r_healthy(void) { return true; }

static const virtus_actuator_driver_t s_mock_motor_r = {
    .init           = mock_motor_r_init,
    .deinit         = mock_motor_r_deinit,
    .set            = mock_motor_r_set,
    .get_state      = mock_motor_r_get_state,
    .emergency_stop = mock_motor_r_estop,
    .is_healthy     = mock_motor_r_healthy,
};

/* ========================================================================
 * Test setup
 * ======================================================================== */

static void actuator_before(void *fixture)
{
    ARG_UNUSED(fixture);

    mock_motor_init_called = 0;
    mock_motor_set_called = 0;
    mock_motor_estop_called = 0;
    mock_motor_last_speed = 0;
    mock_motor_last_flags = 0;
    mock_motor_r_estop_called = 0;
}

ZTEST_SUITE(hal_actuator_mock, NULL, NULL, actuator_before, NULL, NULL);

/* ========================================================================
 * Tests
 * ======================================================================== */

/**
 * Test: Set dispatches correctly with speed and flags.
 */
ZTEST(hal_actuator_mock, test_set_dispatches_correctly)
{
    virtus_actuator_cmd_t cmd;
    int ret;

    ret = virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &s_mock_motor);
    zassert_equal(ret, 0, "register should succeed");

    memset(&cmd, 0, sizeof(cmd));
    cmd.id = ACTUATOR_MOTOR_LEFT;
    cmd.cmd.motor.speed_pct = -80;
    cmd.cmd.motor.flags = 0x01;

    ret = virtus_actuator_set(&cmd);
    zassert_equal(ret, 0, "set should succeed");
    zassert_equal(mock_motor_set_called, 1, "set should be called once");
    zassert_equal(mock_motor_last_speed, -80, "speed should be -80");
    zassert_equal(mock_motor_last_flags, 0x01, "flags should be 0x01");
}

/**
 * Test: Get state returns last commanded speed.
 */
ZTEST(hal_actuator_mock, test_get_state_returns_last_command)
{
    virtus_actuator_cmd_t cmd;
    virtus_actuator_state_t state;
    int ret;

    ret = virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &s_mock_motor);
    zassert_equal(ret, 0, "register should succeed");

    memset(&cmd, 0, sizeof(cmd));
    cmd.id = ACTUATOR_MOTOR_LEFT;
    cmd.cmd.motor.speed_pct = 42;

    virtus_actuator_set(&cmd);

    ret = virtus_actuator_get_state(ACTUATOR_MOTOR_LEFT, &state);
    zassert_equal(ret, 0, "get_state should succeed");
    zassert_equal(state.state.motor.speed_pct, 42, "speed should be 42");
    zassert_equal(state.id, ACTUATOR_MOTOR_LEFT, "id should match");
    zassert_true(state.enabled, "should be enabled");
}

/**
 * Test: Emergency stop is called on all registered actuators.
 */
ZTEST(hal_actuator_mock, test_emergency_stop_all_both_motors)
{
    int ret;

    virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &s_mock_motor);
    virtus_actuator_register(ACTUATOR_MOTOR_RIGHT, &s_mock_motor_r);

    ret = virtus_actuator_emergency_stop_all();
    zassert_equal(ret, 0, "estop_all should succeed");
    zassert_true(mock_motor_estop_called >= 1,
                 "left estop should be called");
    zassert_true(mock_motor_r_estop_called >= 1,
                 "right estop should be called");
}

/**
 * Test: Set with zero speed (coast).
 */
ZTEST(hal_actuator_mock, test_set_zero_speed)
{
    virtus_actuator_cmd_t cmd;
    int ret;

    virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &s_mock_motor);

    memset(&cmd, 0, sizeof(cmd));
    cmd.id = ACTUATOR_MOTOR_LEFT;
    cmd.cmd.motor.speed_pct = 0;

    ret = virtus_actuator_set(&cmd);
    zassert_equal(ret, 0, "set zero should succeed");
    zassert_equal(mock_motor_last_speed, 0, "speed should be 0");
}

/**
 * Test: Set with max positive speed.
 */
ZTEST(hal_actuator_mock, test_set_max_speed)
{
    virtus_actuator_cmd_t cmd;
    int ret;

    virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &s_mock_motor);

    memset(&cmd, 0, sizeof(cmd));
    cmd.id = ACTUATOR_MOTOR_LEFT;
    cmd.cmd.motor.speed_pct = 100;

    ret = virtus_actuator_set(&cmd);
    zassert_equal(ret, 0, "set max speed should succeed");
    zassert_equal(mock_motor_last_speed, 100, "speed should be 100");
}

/**
 * Test: NULL command returns -EINVAL.
 */
ZTEST(hal_actuator_mock, test_set_null_cmd)
{
    int ret;

    virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &s_mock_motor);

    ret = virtus_actuator_set(NULL);
    zassert_equal(ret, -EINVAL, "NULL cmd should return -EINVAL");
}

/**
 * Test: Get state with NULL output returns -EINVAL.
 */
ZTEST(hal_actuator_mock, test_get_state_null_output)
{
    int ret;

    virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &s_mock_motor);

    ret = virtus_actuator_get_state(ACTUATOR_MOTOR_LEFT, NULL);
    zassert_equal(ret, -EINVAL, "NULL output should return -EINVAL");
}

/**
 * Test: Is healthy returns true for registered mock.
 */
ZTEST(hal_actuator_mock, test_actuator_is_healthy)
{
    virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &s_mock_motor);

    zassert_true(virtus_actuator_is_healthy(ACTUATOR_MOTOR_LEFT),
                 "registered mock should be healthy");
}

/**
 * Test: Is healthy returns false for unregistered slot.
 */
ZTEST(hal_actuator_mock, test_actuator_unregistered_not_healthy)
{
    zassert_false(virtus_actuator_is_healthy(ACTUATOR_SPARE),
                  "unregistered actuator should not be healthy");
}

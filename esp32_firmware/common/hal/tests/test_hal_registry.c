/* Copyright 2026 VirtusCo
 *
 * VHAL Ztest — Driver registry tests
 * Verifies sensor and actuator registration, dispatch, error handling,
 * init_all, emergency_stop_all, and name lookup.
 *
 * SPDX-License-Identifier: Proprietary
 */

#include <zephyr/ztest.h>
#include "virtus_hal.h"
#include <errno.h>
#include <string.h>

/* ========================================================================
 * Mock sensor driver
 * ======================================================================== */

static int mock_sensor_init_called;
static int mock_sensor_read_called;
static int mock_sensor_init_retval;
static int mock_sensor_read_retval;
static uint16_t mock_sensor_tof_mm;

static int mock_sensor_init(void)
{
    mock_sensor_init_called++;
    return mock_sensor_init_retval;
}

static int mock_sensor_deinit(void)
{
    return 0;
}

static bool mock_sensor_is_ready(void)
{
    return true;
}

static int mock_sensor_read(virtus_sensor_data_t *out)
{
    mock_sensor_read_called++;
    if (mock_sensor_read_retval != 0) {
        return mock_sensor_read_retval;
    }
    out->data.tof.mm = mock_sensor_tof_mm;
    out->data.tof.status = 0;
    out->valid = true;
    return 0;
}

static bool mock_sensor_is_healthy(void)
{
    return true;
}

static int mock_sensor_diagnostics(char *buf, size_t len)
{
    return snprintf(buf, len, "mock:ok");
}

static const virtus_sensor_driver_t mock_tof_driver = {
    .init            = mock_sensor_init,
    .deinit          = mock_sensor_deinit,
    .is_ready        = mock_sensor_is_ready,
    .read            = mock_sensor_read,
    .is_healthy      = mock_sensor_is_healthy,
    .get_diagnostics = mock_sensor_diagnostics,
};

/* ========================================================================
 * Mock actuator driver
 * ======================================================================== */

static int mock_act_init_called;
static int mock_act_set_called;
static int mock_act_estop_called;
static int16_t mock_act_last_speed;
static int mock_act_init_retval;

static int mock_act_init(void)
{
    mock_act_init_called++;
    return mock_act_init_retval;
}

static int mock_act_deinit(void)
{
    return 0;
}

static int mock_act_set(const virtus_actuator_cmd_t *cmd)
{
    mock_act_set_called++;
    mock_act_last_speed = cmd->cmd.motor.speed_pct;
    return 0;
}

static int mock_act_get_state(virtus_actuator_state_t *out)
{
    memset(out, 0, sizeof(*out));
    out->id = ACTUATOR_MOTOR_LEFT;
    out->enabled = true;
    out->state.motor.speed_pct = mock_act_last_speed;
    return 0;
}

static int mock_act_emergency_stop(void)
{
    mock_act_estop_called++;
    mock_act_last_speed = 0;
    return 0;
}

static bool mock_act_is_healthy(void)
{
    return true;
}

static const virtus_actuator_driver_t mock_motor_driver = {
    .init           = mock_act_init,
    .deinit         = mock_act_deinit,
    .set            = mock_act_set,
    .get_state      = mock_act_get_state,
    .emergency_stop = mock_act_emergency_stop,
    .is_healthy     = mock_act_is_healthy,
};

/* ========================================================================
 * Test setup: reset all mock counters before each test
 * ======================================================================== */

static void before_each(void *fixture)
{
    ARG_UNUSED(fixture);

    mock_sensor_init_called = 0;
    mock_sensor_read_called = 0;
    mock_sensor_init_retval = 0;
    mock_sensor_read_retval = 0;
    mock_sensor_tof_mm = 500;

    mock_act_init_called = 0;
    mock_act_set_called = 0;
    mock_act_estop_called = 0;
    mock_act_last_speed = 0;
    mock_act_init_retval = 0;
}

ZTEST_SUITE(hal_registry, NULL, NULL, before_each, NULL, NULL);

/* ========================================================================
 * Sensor registration tests
 * ======================================================================== */

/**
 * Test: Register sensor -> read dispatches to it.
 */
ZTEST(hal_registry, test_sensor_register_and_read)
{
    virtus_sensor_data_t data;
    int ret;

    mock_sensor_tof_mm = 1234;

    ret = virtus_sensor_register(SENSOR_TOF, &mock_tof_driver);
    zassert_equal(ret, 0, "register should succeed");

    ret = virtus_sensor_read(SENSOR_TOF, &data);
    zassert_equal(ret, 0, "read should succeed");
    zassert_equal(data.data.tof.mm, 1234, "should read 1234mm");
    zassert_true(data.valid, "data should be valid");
    zassert_equal(mock_sensor_read_called, 1, "read should be called once");
}

/**
 * Test: Unregistered sensor returns -ENODEV.
 */
ZTEST(hal_registry, test_sensor_unregistered_returns_enodev)
{
    virtus_sensor_data_t data;
    int ret;

    /* SENSOR_IMU is unlikely to be registered by other tests */
    ret = virtus_sensor_read(SENSOR_IMU, &data);
    zassert_equal(ret, -ENODEV, "unregistered sensor should return -ENODEV");
}

/**
 * Test: Re-register replaces previous driver.
 */
ZTEST(hal_registry, test_sensor_reregister_replaces)
{
    int ret;

    ret = virtus_sensor_register(SENSOR_TOF, &mock_tof_driver);
    zassert_equal(ret, 0, "first register should succeed");

    /* Re-register with the same driver (should warn but succeed) */
    ret = virtus_sensor_register(SENSOR_TOF, &mock_tof_driver);
    zassert_equal(ret, 0, "re-register should succeed");
}

/**
 * Test: NULL driver returns -EINVAL.
 */
ZTEST(hal_registry, test_sensor_null_driver_returns_einval)
{
    int ret;

    ret = virtus_sensor_register(SENSOR_TOF, NULL);
    zassert_equal(ret, -EINVAL, "NULL driver should return -EINVAL");
}

/**
 * Test: Invalid sensor ID returns -EINVAL.
 */
ZTEST(hal_registry, test_sensor_invalid_id)
{
    int ret;

    ret = virtus_sensor_register(SENSOR_MAX, &mock_tof_driver);
    zassert_equal(ret, -EINVAL, "SENSOR_MAX should return -EINVAL");
}

/**
 * Test: Init all calls each driver's init.
 */
ZTEST(hal_registry, test_sensor_init_all)
{
    int ret;

    ret = virtus_sensor_register(SENSOR_TOF, &mock_tof_driver);
    zassert_equal(ret, 0, "register should succeed");

    ret = virtus_sensor_init_all();
    zassert_equal(ret, 0, "init_all should succeed");
    zassert_true(mock_sensor_init_called >= 1, "init should be called");
}

/**
 * Test: Name returns correct string.
 */
ZTEST(hal_registry, test_sensor_name)
{
    const char *name;

    name = virtus_sensor_name(SENSOR_TOF);
    zassert_true(strcmp(name, "ToF") == 0, "ToF name mismatch: got '%s'", name);

    name = virtus_sensor_name(SENSOR_ULTRASONIC);
    zassert_true(strcmp(name, "Ultrasonic") == 0,
                 "Ultrasonic name mismatch: got '%s'", name);

    name = virtus_sensor_name(SENSOR_MAX);
    zassert_true(strcmp(name, "UNKNOWN") == 0,
                 "Invalid id should return UNKNOWN: got '%s'", name);
}

/* ========================================================================
 * Actuator registration tests
 * ======================================================================== */

/**
 * Test: Register actuator -> set dispatches to it.
 */
ZTEST(hal_registry, test_actuator_register_and_set)
{
    virtus_actuator_cmd_t cmd;
    int ret;

    ret = virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &mock_motor_driver);
    zassert_equal(ret, 0, "register should succeed");

    memset(&cmd, 0, sizeof(cmd));
    cmd.id = ACTUATOR_MOTOR_LEFT;
    cmd.cmd.motor.speed_pct = 75;

    ret = virtus_actuator_set(&cmd);
    zassert_equal(ret, 0, "set should succeed");
    zassert_equal(mock_act_set_called, 1, "set should be called once");
    zassert_equal(mock_act_last_speed, 75, "speed should be 75");
}

/**
 * Test: Emergency stop all calls each actuator's emergency_stop.
 */
ZTEST(hal_registry, test_actuator_emergency_stop_all)
{
    virtus_actuator_cmd_t cmd;
    int ret;

    ret = virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &mock_motor_driver);
    zassert_equal(ret, 0, "register should succeed");

    /* Set a speed first */
    memset(&cmd, 0, sizeof(cmd));
    cmd.id = ACTUATOR_MOTOR_LEFT;
    cmd.cmd.motor.speed_pct = 50;
    virtus_actuator_set(&cmd);

    /* Emergency stop all */
    ret = virtus_actuator_emergency_stop_all();
    zassert_equal(ret, 0, "emergency_stop_all should succeed");
    zassert_true(mock_act_estop_called >= 1, "estop should be called");
}

/**
 * Test: Unregistered actuator returns -ENODEV.
 */
ZTEST(hal_registry, test_actuator_unregistered_returns_enodev)
{
    virtus_actuator_state_t state;
    int ret;

    ret = virtus_actuator_get_state(ACTUATOR_SPARE, &state);
    zassert_equal(ret, -ENODEV, "unregistered actuator should return -ENODEV");
}

/**
 * Test: Actuator name returns correct string.
 */
ZTEST(hal_registry, test_actuator_name)
{
    const char *name;

    name = virtus_actuator_name(ACTUATOR_MOTOR_LEFT);
    zassert_true(strcmp(name, "Motor-Left") == 0,
                 "Motor-Left name mismatch: got '%s'", name);

    name = virtus_actuator_name(ACTUATOR_RELAY_1);
    zassert_true(strcmp(name, "Relay-1") == 0,
                 "Relay-1 name mismatch: got '%s'", name);

    name = virtus_actuator_name(ACTUATOR_MAX);
    zassert_true(strcmp(name, "UNKNOWN") == 0,
                 "Invalid id should return UNKNOWN: got '%s'", name);
}

/**
 * Test: Init all calls each actuator driver's init.
 */
ZTEST(hal_registry, test_actuator_init_all)
{
    int ret;

    ret = virtus_actuator_register(ACTUATOR_MOTOR_LEFT, &mock_motor_driver);
    zassert_equal(ret, 0, "register should succeed");

    ret = virtus_actuator_init_all();
    zassert_equal(ret, 0, "init_all should succeed");
    zassert_true(mock_act_init_called >= 1, "init should be called");
}

/**
 * Test: NULL actuator driver returns -EINVAL.
 */
ZTEST(hal_registry, test_actuator_null_driver_returns_einval)
{
    int ret;

    ret = virtus_actuator_register(ACTUATOR_MOTOR_LEFT, NULL);
    zassert_equal(ret, -EINVAL, "NULL driver should return -EINVAL");
}

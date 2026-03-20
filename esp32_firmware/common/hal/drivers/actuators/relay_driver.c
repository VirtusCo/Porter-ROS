/* Copyright 2026 VirtusCo
 *
 * VHAL Driver — GPIO relay outputs (up to 4 channels)
 * Simple on/off control with cumulative on-time tracking.
 *
 * On native_sim this file compiles to stubs (no real hardware).
 *
 * SPDX-License-Identifier: Proprietary
 */

#include "virtus_hal.h"
#include <errno.h>
#include <string.h>

#ifdef CONFIG_GPIO
/* ========================================================================
 * Zephyr Hardware Implementation
 * ======================================================================== */

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(relay_drv, LOG_LEVEL_INF);

/** Number of relay channels. */
#define RELAY_COUNT  4

/**
 * Per-relay state.
 */
typedef struct {
    bool     on;            /**< Current relay state */
    uint32_t on_start_ms;   /**< Timestamp when relay was turned ON */
    uint32_t total_on_ms;   /**< Cumulative on-time in milliseconds */
    bool     initialised;   /**< Init completed */
} relay_state_t;

static relay_state_t s_relays[RELAY_COUNT];

/*
 * NOTE: In production, GPIO specs would come from devicetree:
 *   DT_ALIAS(relay_1), DT_ALIAS(relay_2), etc.
 * For compilation, we handle the case where aliases may not exist.
 */

/**
 * Generic relay init for channel N.
 */
static int relay_init_channel(int ch)
{
    if (ch < 0 || ch >= RELAY_COUNT) {
        return -EINVAL;
    }

    memset(&s_relays[ch], 0, sizeof(relay_state_t));
    s_relays[ch].initialised = true;

    LOG_INF("Relay %d initialised", ch + 1);
    return 0;
}

/**
 * Set relay state for channel N.
 */
static int relay_set_channel(int ch, bool on)
{
    if (ch < 0 || ch >= RELAY_COUNT) {
        return -EINVAL;
    }
    if (!s_relays[ch].initialised) {
        return -ENODEV;
    }

    if (on && !s_relays[ch].on) {
        /* Turning ON: record start time */
        s_relays[ch].on_start_ms = k_uptime_get_32();
    } else if (!on && s_relays[ch].on) {
        /* Turning OFF: accumulate on-time */
        uint32_t now = k_uptime_get_32();
        s_relays[ch].total_on_ms += (now - s_relays[ch].on_start_ms);
    }

    s_relays[ch].on = on;
    /* In production: gpio_pin_set_dt(&relay_pins[ch], on ? 1 : 0); */

    return 0;
}

/**
 * Get relay state for channel N.
 */
static int relay_get_state_channel(int ch, virtus_actuator_state_t *out)
{
    uint32_t on_time;

    if (ch < 0 || ch >= RELAY_COUNT) {
        return -EINVAL;
    }
    if (!s_relays[ch].initialised) {
        return -ENODEV;
    }

    memset(out, 0, sizeof(*out));
    out->enabled = s_relays[ch].initialised;
    out->state.relay.on = s_relays[ch].on;

    /* Calculate total on-time including current session if on */
    on_time = s_relays[ch].total_on_ms;
    if (s_relays[ch].on) {
        on_time += (k_uptime_get_32() - s_relays[ch].on_start_ms);
    }
    out->state.relay.on_time_ms = on_time;

    return 0;
}

/* --- Relay 1 callbacks --- */

static int relay1_init(void) { return relay_init_channel(0); }
static int relay1_deinit(void) { s_relays[0].initialised = false; return 0; }
static int relay1_set(const virtus_actuator_cmd_t *cmd)
{
    return relay_set_channel(0, cmd->cmd.relay.on);
}
static int relay1_get_state(virtus_actuator_state_t *out)
{
    out->id = ACTUATOR_RELAY_1;
    return relay_get_state_channel(0, out);
}
static int relay1_estop(void) { return relay_set_channel(0, false); }
static bool relay1_healthy(void) { return s_relays[0].initialised; }

/* --- Relay 2 callbacks --- */

static int relay2_init(void) { return relay_init_channel(1); }
static int relay2_deinit(void) { s_relays[1].initialised = false; return 0; }
static int relay2_set(const virtus_actuator_cmd_t *cmd)
{
    return relay_set_channel(1, cmd->cmd.relay.on);
}
static int relay2_get_state(virtus_actuator_state_t *out)
{
    out->id = ACTUATOR_RELAY_2;
    return relay_get_state_channel(1, out);
}
static int relay2_estop(void) { return relay_set_channel(1, false); }
static bool relay2_healthy(void) { return s_relays[1].initialised; }

/* --- Relay 3 callbacks --- */

static int relay3_init(void) { return relay_init_channel(2); }
static int relay3_deinit(void) { s_relays[2].initialised = false; return 0; }
static int relay3_set(const virtus_actuator_cmd_t *cmd)
{
    return relay_set_channel(2, cmd->cmd.relay.on);
}
static int relay3_get_state(virtus_actuator_state_t *out)
{
    out->id = ACTUATOR_RELAY_3;
    return relay_get_state_channel(2, out);
}
static int relay3_estop(void) { return relay_set_channel(2, false); }
static bool relay3_healthy(void) { return s_relays[2].initialised; }

/* --- Relay 4 callbacks --- */

static int relay4_init(void) { return relay_init_channel(3); }
static int relay4_deinit(void) { s_relays[3].initialised = false; return 0; }
static int relay4_set(const virtus_actuator_cmd_t *cmd)
{
    return relay_set_channel(3, cmd->cmd.relay.on);
}
static int relay4_get_state(virtus_actuator_state_t *out)
{
    out->id = ACTUATOR_RELAY_4;
    return relay_get_state_channel(3, out);
}
static int relay4_estop(void) { return relay_set_channel(3, false); }
static bool relay4_healthy(void) { return s_relays[3].initialised; }

/* --- Exported driver instances --- */

const virtus_actuator_driver_t relay_1_driver = {
    .init = relay1_init, .deinit = relay1_deinit, .set = relay1_set,
    .get_state = relay1_get_state, .emergency_stop = relay1_estop,
    .is_healthy = relay1_healthy,
};

const virtus_actuator_driver_t relay_2_driver = {
    .init = relay2_init, .deinit = relay2_deinit, .set = relay2_set,
    .get_state = relay2_get_state, .emergency_stop = relay2_estop,
    .is_healthy = relay2_healthy,
};

const virtus_actuator_driver_t relay_3_driver = {
    .init = relay3_init, .deinit = relay3_deinit, .set = relay3_set,
    .get_state = relay3_get_state, .emergency_stop = relay3_estop,
    .is_healthy = relay3_healthy,
};

const virtus_actuator_driver_t relay_4_driver = {
    .init = relay4_init, .deinit = relay4_deinit, .set = relay4_set,
    .get_state = relay4_get_state, .emergency_stop = relay4_estop,
    .is_healthy = relay4_healthy,
};

#else /* !CONFIG_GPIO — stub for native_sim builds */

static int stub_init(void)          { return -ENOTSUP; }
static int stub_deinit(void)        { return 0; }
static int stub_set(const virtus_actuator_cmd_t *c) { (void)c; return -ENOTSUP; }
static int stub_get_state(virtus_actuator_state_t *o) { (void)o; return -ENOTSUP; }
static int stub_estop(void)         { return 0; }
static bool stub_healthy(void)      { return false; }

const virtus_actuator_driver_t relay_1_driver = {
    .init = stub_init, .deinit = stub_deinit, .set = stub_set,
    .get_state = stub_get_state, .emergency_stop = stub_estop,
    .is_healthy = stub_healthy,
};

const virtus_actuator_driver_t relay_2_driver = {
    .init = stub_init, .deinit = stub_deinit, .set = stub_set,
    .get_state = stub_get_state, .emergency_stop = stub_estop,
    .is_healthy = stub_healthy,
};

const virtus_actuator_driver_t relay_3_driver = {
    .init = stub_init, .deinit = stub_deinit, .set = stub_set,
    .get_state = stub_get_state, .emergency_stop = stub_estop,
    .is_healthy = stub_healthy,
};

const virtus_actuator_driver_t relay_4_driver = {
    .init = stub_init, .deinit = stub_deinit, .set = stub_set,
    .get_state = stub_get_state, .emergency_stop = stub_estop,
    .is_healthy = stub_healthy,
};

#endif /* CONFIG_GPIO */

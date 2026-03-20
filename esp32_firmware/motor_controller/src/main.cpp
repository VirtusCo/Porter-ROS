/*
 * Porter Robot — Motor Controller Firmware
 * ESP32 #1: Dual BTS7960 H-Bridge motor control via USB-UART bridge
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 *
 * Subsystems:
 *   - SMF state machine: IDLE → RUNNING → FAULT → ESTOP
 *   - PWM motor driver: BTS7960 dual H-bridge (RPWM/LPWM per motor)
 *   - Differential drive: (linear_x, angular_z) → left/right PWM
 *   - Speed ramping: acceleration/deceleration limits
 *   - Heartbeat watchdog: no command in 500ms → stop motors
 *   - Transport: protocol packets over UART/CDC ACM to RPi
 *   - Zbus channels: motor_cmd, motor_status, safety_event
 *   - Shell commands for development/debug
 *
 * Thread priorities: safety(-1) > motor(0) > protocol(1) > reporting(5) > shell(14)
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/logging/log.h>
#include <zephyr/smf.h>
#include <zephyr/zbus/zbus.h>
#include <zephyr/shell/shell.h>
#include <zephyr/task_wdt/task_wdt.h>
#include <zephyr/sys/atomic.h>

#include <cstring>
#include <cstdlib>
#include <algorithm>

#include "protocol.h"
#include "transport.h"

LOG_MODULE_REGISTER(motor_ctrl, LOG_LEVEL_INF);

/* ========================================================================
 * Configuration Constants
 * ======================================================================== */

#define FIRMWARE_VERSION          "0.2.0"

/* PWM */
#define PWM_PERIOD_US             1000    /* 1 kHz PWM frequency */
#define PWM_MAX_DUTY              100     /* max duty cycle % */

/* Speed ramping */
#define RAMP_STEP_PER_TICK        5       /* max duty % change per 10ms tick */
#define MOTOR_TICK_MS             10      /* motor control loop period */

/* Safety */
#define HEARTBEAT_TIMEOUT_MS      500     /* stop motors if no heartbeat/cmd */
#define FAULT_RECOVERY_DELAY_MS   2000    /* delay before allowing fault clear */

/* Protocol polling */
#define PROTOCOL_POLL_MS          5       /* transport read interval */

/* Reporting */
#define STATUS_REPORT_MS          200     /* motor status report interval */

/* ========================================================================
 * Zbus Message Types
 * ======================================================================== */

struct motor_cmd_msg {
    int16_t speed_left;     /* -100..+100 (percent duty, signed for direction) */
    int16_t speed_right;    /* -100..+100 */
    uint8_t flags;          /* bit 0: smooth ramp enable */
};

struct motor_status_msg {
    int16_t current_left;   /* actual duty after ramping */
    int16_t current_right;
    uint8_t state;          /* SMF state enum value */
    uint8_t fault_code;     /* 0 = no fault */
};

struct safety_event_msg {
    uint8_t event;          /* 0=heartbeat_timeout, 1=overcurrent, 2=estop_cmd */
};

/* Forward‐declare observers */
ZBUS_CHAN_DEFINE(motor_cmd_chan,
    struct motor_cmd_msg, NULL, NULL,
    ZBUS_OBSERVERS_EMPTY,
    ZBUS_MSG_INIT(.speed_left = 0, .speed_right = 0, .flags = 1));

ZBUS_CHAN_DEFINE(motor_status_chan,
    struct motor_status_msg, NULL, NULL,
    ZBUS_OBSERVERS_EMPTY,
    ZBUS_MSG_INIT(.current_left = 0, .current_right = 0, .state = 0, .fault_code = 0));

ZBUS_CHAN_DEFINE(safety_event_chan,
    struct safety_event_msg, NULL, NULL,
    ZBUS_OBSERVERS_EMPTY,
    ZBUS_MSG_INIT(.event = 0));

/* ========================================================================
 * Hardware Handles
 * ======================================================================== */

/* PWM — 4 channels: L_RPWM(ch0), L_LPWM(ch1), R_RPWM(ch2), R_LPWM(ch3) */
static const struct device *pwm_dev = DEVICE_DT_GET(DT_NODELABEL(ledc0));

/* Motor enable GPIOs */
static const struct gpio_dt_spec motor_l_en =
    GPIO_DT_SPEC_GET(DT_NODELABEL(motor_l_en), gpios);
static const struct gpio_dt_spec motor_r_en =
    GPIO_DT_SPEC_GET(DT_NODELABEL(motor_r_en), gpios);

/* Lift control */
static const struct gpio_dt_spec lift_ctrl =
    GPIO_DT_SPEC_GET(DT_NODELABEL(lift_ctrl), gpios);

/* ========================================================================
 * Motor PWM Driver
 * ======================================================================== */

/*
 * BTS7960 control: per motor has RPWM (forward) and LPWM (reverse) pins.
 * To go forward:  RPWM = duty, LPWM = 0
 * To go reverse:  RPWM = 0,    LPWM = duty
 * To brake:       RPWM = 0,    LPWM = 0   (with EN high = dynamic braking)
 */

static void pwm_set_channel(uint32_t channel, uint32_t duty_percent)
{
    if (duty_percent > PWM_MAX_DUTY) {
        duty_percent = PWM_MAX_DUTY;
    }
    uint32_t pulse_us = (PWM_PERIOD_US * duty_percent) / 100;
    int ret = pwm_set(pwm_dev, channel, PWM_USEC(PWM_PERIOD_US), PWM_USEC(pulse_us), 0);
    if (ret != 0) {
        LOG_ERR("PWM ch%u set failed: %d", channel, ret);
    }
}

/**
 * Set motor speed: -100..+100. Positive = forward, negative = reverse.
 */
static void motor_set_pwm(int side, int16_t speed)
{
    /* side: 0 = left (ch0=RPWM, ch1=LPWM), 1 = right (ch2=RPWM, ch3=LPWM) */
    uint32_t rpwm_ch = (side == 0) ? 0 : 2;
    uint32_t lpwm_ch = (side == 0) ? 1 : 3;

    int16_t clamped = std::clamp(speed, (int16_t)-100, (int16_t)100);
    uint32_t duty = (uint32_t)std::abs(clamped);

    if (clamped > 0) {
        pwm_set_channel(rpwm_ch, duty);
        pwm_set_channel(lpwm_ch, 0);
    } else if (clamped < 0) {
        pwm_set_channel(rpwm_ch, 0);
        pwm_set_channel(lpwm_ch, duty);
    } else {
        pwm_set_channel(rpwm_ch, 0);
        pwm_set_channel(lpwm_ch, 0);
    }
}

static void motors_stop(void)
{
    motor_set_pwm(0, 0);
    motor_set_pwm(1, 0);
}

static void motors_enable(bool enable)
{
    gpio_pin_set_dt(&motor_l_en, enable ? 1 : 0);
    gpio_pin_set_dt(&motor_r_en, enable ? 1 : 0);
}

/* ========================================================================
 * Speed Ramping
 * ======================================================================== */

static int16_t target_left  = 0;
static int16_t target_right = 0;
static int16_t actual_left  = 0;
static int16_t actual_right = 0;
static bool    ramp_enabled = true;

static int16_t ramp_towards(int16_t current, int16_t target, int16_t step)
{
    int16_t diff = target - current;
    if (diff > step) {
        return current + step;
    } else if (diff < -step) {
        return current - step;
    }
    return target;
}

static void ramp_tick(void)
{
    int16_t step = ramp_enabled ? RAMP_STEP_PER_TICK : 100;
    actual_left  = ramp_towards(actual_left,  target_left,  step);
    actual_right = ramp_towards(actual_right, target_right, step);
    motor_set_pwm(0, actual_left);
    motor_set_pwm(1, actual_right);
}

/* ========================================================================
 * Heartbeat / Command Watchdog
 * ======================================================================== */

static int64_t last_cmd_time = 0;

static void heartbeat_refresh(void)
{
    last_cmd_time = k_uptime_get();
}

static bool heartbeat_expired(void)
{
    return (k_uptime_get() - last_cmd_time) > HEARTBEAT_TIMEOUT_MS;
}

/* ========================================================================
 * Lift Mechanism (simple GPIO up/down)
 * ======================================================================== */

static void lift_set(bool raise)
{
    gpio_pin_set_dt(&lift_ctrl, raise ? 1 : 0);
    LOG_INF("Lift: %s", raise ? "UP" : "DOWN");
}

/* ========================================================================
 * SMF State Machine
 * ======================================================================== */

extern const struct smf_state motor_states[];

enum motor_state_e {
    STATE_IDLE,
    STATE_RUNNING,
    STATE_FAULT,
    STATE_ESTOP,
    STATE_COUNT
};

struct motor_sm_obj {
    struct smf_ctx ctx;
    uint8_t fault_code;
    int64_t fault_entry_time;
};

static struct motor_sm_obj sm_obj;

/* --- IDLE --- */
static void idle_entry(void *o)
{
    LOG_INF("State: IDLE");
    motors_stop();
    motors_enable(false);
    target_left = target_right = 0;
    actual_left = actual_right = 0;
}

static void idle_run(void *o)
{
    struct motor_sm_obj *obj = static_cast<struct motor_sm_obj *>(o);

    /* Check for ESTOP */
    struct safety_event_msg evt;
    if (zbus_chan_read(&safety_event_chan, &evt, K_NO_WAIT) == 0 && evt.event == 2) {
        smf_set_state(SMF_CTX(obj), &motor_states[STATE_ESTOP]);
        return;
    }

    /* Transition to RUNNING if speed command received */
    if (target_left != 0 || target_right != 0) {
        smf_set_state(SMF_CTX(obj), &motor_states[STATE_RUNNING]);
    }
}

/* --- RUNNING --- */
static void running_entry(void *o)
{
    LOG_INF("State: RUNNING");
    motors_enable(true);
    heartbeat_refresh();
}

static void running_run(void *o)
{
    struct motor_sm_obj *obj = static_cast<struct motor_sm_obj *>(o);

    /* Check for ESTOP */
    struct safety_event_msg evt;
    if (zbus_chan_read(&safety_event_chan, &evt, K_NO_WAIT) == 0 && evt.event == 2) {
        smf_set_state(SMF_CTX(obj), &motor_states[STATE_ESTOP]);
        return;
    }

    /* Heartbeat timeout → fault */
    if (heartbeat_expired()) {
        LOG_WRN("Heartbeat timeout — stopping motors");
        obj->fault_code = 1;  /* heartbeat timeout */
        smf_set_state(SMF_CTX(obj), &motor_states[STATE_FAULT]);
        return;
    }

    /* Apply speed ramping */
    ramp_tick();

    /* If target is zero and we've ramped down, return to IDLE */
    if (target_left == 0 && target_right == 0 &&
        actual_left == 0 && actual_right == 0) {
        smf_set_state(SMF_CTX(obj), &motor_states[STATE_IDLE]);
    }
}

static void running_exit(void *o)
{
    motors_stop();
    motors_enable(false);
}

/* --- FAULT --- */
static void fault_entry(void *o)
{
    struct motor_sm_obj *obj = static_cast<struct motor_sm_obj *>(o);
    LOG_ERR("State: FAULT (code=%u)", obj->fault_code);
    motors_stop();
    motors_enable(false);
    target_left = target_right = 0;
    actual_left = actual_right = 0;
    obj->fault_entry_time = k_uptime_get();
}

static void fault_run(void *o)
{
    struct motor_sm_obj *obj = static_cast<struct motor_sm_obj *>(o);

    /* Check for ESTOP — overrides fault */
    struct safety_event_msg evt;
    if (zbus_chan_read(&safety_event_chan, &evt, K_NO_WAIT) == 0 && evt.event == 2) {
        smf_set_state(SMF_CTX(obj), &motor_states[STATE_ESTOP]);
        return;
    }

    /* Recovery: wait for delay then allow transition to IDLE on explicit reset */
    if ((k_uptime_get() - obj->fault_entry_time) > FAULT_RECOVERY_DELAY_MS) {
        /* Reset command comes via protocol (CMD_RESET handled in protocol thread) */
        if (obj->fault_code == 0) {
            LOG_INF("Fault cleared, returning to IDLE");
            smf_set_state(SMF_CTX(obj), &motor_states[STATE_IDLE]);
        }
    }
}

/* --- ESTOP --- */
static void estop_entry(void *o)
{
    LOG_WRN("State: EMERGENCY STOP");
    motors_stop();
    motors_enable(false);
    target_left = target_right = 0;
    actual_left = actual_right = 0;
}

static void estop_run(void *o)
{
    /*
     * Latched state — requires explicit CMD_RESET from host to exit.
     * Motors remain disabled. No automatic recovery.
     */
    (void)o;
}

/* State table */
const struct smf_state motor_states[] = {
    [STATE_IDLE]    = SMF_CREATE_STATE(idle_entry,    idle_run,    NULL,         NULL, NULL),
    [STATE_RUNNING] = SMF_CREATE_STATE(running_entry, running_run, running_exit, NULL, NULL),
    [STATE_FAULT]   = SMF_CREATE_STATE(fault_entry,   fault_run,   NULL,         NULL, NULL),
    [STATE_ESTOP]   = SMF_CREATE_STATE(estop_entry,   estop_run,   NULL,         NULL, NULL),
};

/* ========================================================================
 * Protocol Handler (runs in its own thread)
 * ======================================================================== */

static protocol_parser_t proto_parser;

static void handle_packet(const protocol_packet_t *pkt)
{
    uint8_t resp_buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t  resp_len;

    heartbeat_refresh();

    switch (pkt->command) {
    case CMD_MOTOR_SET_SPEED: {
        if (pkt->length < 5) {
            protocol_encode_nack(pkt->command, NACK_BAD_PAYLOAD, resp_buf, &resp_len);
            transport_write(resp_buf, resp_len);
            return;
        }
        int16_t left  = (int16_t)((pkt->payload[0] << 8) | pkt->payload[1]);
        int16_t right = (int16_t)((pkt->payload[2] << 8) | pkt->payload[3]);
        uint8_t flags = pkt->payload[4];

        /* Clamp to valid range */
        left  = std::clamp(left,  (int16_t)-100, (int16_t)100);
        right = std::clamp(right, (int16_t)-100, (int16_t)100);

        target_left  = left;
        target_right = right;
        ramp_enabled = (flags & 0x01) != 0;

        LOG_INF("CMD: speed L=%d R=%d flags=0x%02x", left, right, flags);

        /* Publish to zbus */
        struct motor_cmd_msg cmd = {
            .speed_left = left, .speed_right = right, .flags = flags
        };
        zbus_chan_pub(&motor_cmd_chan, &cmd, K_NO_WAIT);

        protocol_encode_ack(pkt->command, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }

    case CMD_MOTOR_STOP:
        LOG_WRN("CMD: EMERGENCY STOP");
        target_left = target_right = 0;
        actual_left = actual_right = 0;
        motors_stop();
        {
            struct safety_event_msg evt = { .event = 2 };
            zbus_chan_pub(&safety_event_chan, &evt, K_NO_WAIT);
        }
        protocol_encode_ack(pkt->command, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;

    case CMD_MOTOR_STATUS: {
        LOG_DBG("CMD: STATUS request");
        uint8_t payload[5];
        payload[0] = (uint8_t)((actual_left  >> 8) & 0xFF);
        payload[1] = (uint8_t)(actual_left & 0xFF);
        payload[2] = (uint8_t)((actual_right >> 8) & 0xFF);
        payload[3] = (uint8_t)(actual_right & 0xFF);
        /* Encode current state as index */
        payload[4] = 0;
        for (int i = 0; i < STATE_COUNT; i++) {
            if (sm_obj.ctx.current == &motor_states[i]) {
                payload[4] = (uint8_t)i;
                break;
            }
        }
        protocol_encode(CMD_MOTOR_STATUS, payload, 5, resp_buf, &resp_len);
        transport_write(resp_buf, resp_len);
        break;
    }

    case CMD_HEARTBEAT:
        /* Already refreshed at top of function */
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
        LOG_INF("CMD: RESET — clearing faults");
        sm_obj.fault_code = 0;
        /* Return to IDLE (SMF will pick it up in fault_run or estop_run) */
        smf_set_state(SMF_CTX(&sm_obj), &motor_states[STATE_IDLE]);
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

    /* Initialize transport */
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
 * Status Reporting Thread
 * ======================================================================== */

static void reporting_thread_fn(void *, void *, void *)
{
    LOG_INF("Reporting thread started");

    while (true) {
        /* Update zbus status channel */
        struct motor_status_msg status = {
            .current_left  = actual_left,
            .current_right = actual_right,
            .state         = 0,
            .fault_code    = sm_obj.fault_code,
        };

        for (int i = 0; i < STATE_COUNT; i++) {
            if (sm_obj.ctx.current == &motor_states[i]) {
                status.state = (uint8_t)i;
                break;
            }
        }

        zbus_chan_pub(&motor_status_chan, &status, K_NO_WAIT);

        k_msleep(STATUS_REPORT_MS);
    }
}

K_THREAD_STACK_DEFINE(reporting_stack, 1024);
static struct k_thread reporting_thread_data;

/* ========================================================================
 * Shell Commands (development/debug)
 * ======================================================================== */

static int cmd_motor_speed(const struct shell *sh, size_t argc, char **argv)
{
    if (argc != 3) {
        shell_error(sh, "Usage: motor speed <left> <right>");
        return -EINVAL;
    }
    int16_t left  = (int16_t)atoi(argv[1]);
    int16_t right = (int16_t)atoi(argv[2]);

    target_left = std::clamp(left, (int16_t)-100, (int16_t)100);
    target_right = std::clamp(right, (int16_t)-100, (int16_t)100);
    heartbeat_refresh();
    shell_print(sh, "Target: L=%d R=%d", target_left, target_right);
    return 0;
}

static int cmd_motor_stop(const struct shell *sh, size_t argc, char **argv)
{
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    target_left = target_right = 0;
    actual_left = actual_right = 0;
    motors_stop();
    shell_print(sh, "Motors stopped");
    return 0;
}

static int cmd_motor_status(const struct shell *sh, size_t argc, char **argv)
{
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    const char *state_names[] = {"IDLE", "RUNNING", "FAULT", "ESTOP"};
    uint8_t si = 0;
    for (int i = 0; i < STATE_COUNT; i++) {
        if (sm_obj.ctx.current == &motor_states[i]) { si = i; break; }
    }
    shell_print(sh, "State: %s  Fault: %u", state_names[si], sm_obj.fault_code);
    shell_print(sh, "Target:  L=%d R=%d", target_left, target_right);
    shell_print(sh, "Actual:  L=%d R=%d", actual_left, actual_right);
    shell_print(sh, "Ramp: %s  HB age: %lld ms",
                ramp_enabled ? "ON" : "OFF",
                k_uptime_get() - last_cmd_time);
    return 0;
}

static int cmd_motor_reset(const struct shell *sh, size_t argc, char **argv)
{
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    sm_obj.fault_code = 0;
    smf_set_state(SMF_CTX(&sm_obj), &motor_states[STATE_IDLE]);
    shell_print(sh, "Faults cleared, state → IDLE");
    return 0;
}

static int cmd_motor_lift(const struct shell *sh, size_t argc, char **argv)
{
    if (argc != 2) {
        shell_error(sh, "Usage: motor lift <up|down>");
        return -EINVAL;
    }
    bool up = (strcmp(argv[1], "up") == 0);
    lift_set(up);
    shell_print(sh, "Lift: %s", up ? "UP" : "DOWN");
    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(motor_cmds,
    SHELL_CMD(speed,  NULL, "Set motor speed <left> <right> (-100..100)", cmd_motor_speed),
    SHELL_CMD(stop,   NULL, "Emergency stop", cmd_motor_stop),
    SHELL_CMD(status, NULL, "Show motor status", cmd_motor_status),
    SHELL_CMD(reset,  NULL, "Clear faults, return to IDLE", cmd_motor_reset),
    SHELL_CMD(lift,   NULL, "Lift control <up|down>", cmd_motor_lift),
    SHELL_SUBCMD_SET_END
);
SHELL_CMD_REGISTER(motor, &motor_cmds, "Motor control commands", NULL);

/* ========================================================================
 * Hardware Initialization
 * ======================================================================== */

static int hw_init(void)
{
    int ret;

    /* PWM device */
    if (!device_is_ready(pwm_dev)) {
        LOG_ERR("PWM device not ready");
        return -ENODEV;
    }
    LOG_INF("PWM ready");

    /* Motor enable GPIOs */
    ret = gpio_pin_configure_dt(&motor_l_en, GPIO_OUTPUT_INACTIVE);
    if (ret != 0) { LOG_ERR("Motor L EN config failed: %d", ret); return ret; }

    ret = gpio_pin_configure_dt(&motor_r_en, GPIO_OUTPUT_INACTIVE);
    if (ret != 0) { LOG_ERR("Motor R EN config failed: %d", ret); return ret; }

    /* Lift GPIO */
    ret = gpio_pin_configure_dt(&lift_ctrl, GPIO_OUTPUT_INACTIVE);
    if (ret != 0) { LOG_ERR("Lift GPIO config failed: %d", ret); return ret; }

    LOG_INF("GPIO ready (motor enable + lift)");

    /* Start with motors disabled and PWM at zero */
    motors_stop();
    motors_enable(false);

    return 0;
}

/* ========================================================================
 * Main Entry Point
 * ======================================================================== */

int main(void)
{
    LOG_INF("Porter Robot — Motor Controller v%s", FIRMWARE_VERSION);
    LOG_INF("VirtusCo (c) 2026");

    /* Initialize hardware */
    int ret = hw_init();
    if (ret != 0) {
        LOG_ERR("Hardware init failed (%d) — halting", ret);
        return ret;
    }

    /* Initialize state machine */
    smf_set_initial(SMF_CTX(&sm_obj), &motor_states[STATE_IDLE]);
    heartbeat_refresh();

    /* Start protocol thread (priority 1 = cooperative) */
    k_thread_create(&protocol_thread_data, protocol_stack,
                    K_THREAD_STACK_SIZEOF(protocol_stack),
                    protocol_thread_fn, NULL, NULL, NULL,
                    1, 0, K_NO_WAIT);
    k_thread_name_set(&protocol_thread_data, "proto");

    /* Start reporting thread (priority 5 = preemptible) */
    k_thread_create(&reporting_thread_data, reporting_stack,
                    K_THREAD_STACK_SIZEOF(reporting_stack),
                    reporting_thread_fn, NULL, NULL, NULL,
                    5, 0, K_NO_WAIT);
    k_thread_name_set(&reporting_thread_data, "report");

    LOG_INF("All subsystems initialized — entering main loop");

    /* Main motor control loop (priority 0 — highest preemptible) */
    while (true) {
        int32_t smf_ret = smf_run_state(SMF_CTX(&sm_obj));
        if (smf_ret != 0) {
            LOG_ERR("SMF terminated with %d", smf_ret);
            break;
        }

        k_msleep(MOTOR_TICK_MS);
    }

    /* Should never reach here */
    motors_stop();
    motors_enable(false);
    return 0;
}

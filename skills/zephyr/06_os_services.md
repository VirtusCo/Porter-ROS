# Zephyr RTOS — OS Services (Logging, Shell, SMF, zbus, Power, Storage) — Skill File

> Source: https://docs.zephyrproject.org/latest/services/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

Zephyr provides rich OS-level services beyond the kernel primitives. This file covers the services most relevant to the Porter robot firmware.

---

## 1. Logging Subsystem

### Configuration
```kconfig
CONFIG_LOG=y
CONFIG_LOG_DEFAULT_LEVEL=3          # 0=OFF 1=ERR 2=WRN 3=INF 4=DBG
CONFIG_LOG_BACKEND_UART=y
CONFIG_LOG_BUFFER_SIZE=1024
CONFIG_CBPRINTF_FP_SUPPORT=y        # Enable float in log messages
```

### Usage
```c
#include <zephyr/logging/log.h>

/* Register module — one per .c file */
LOG_MODULE_REGISTER(motor_ctrl, LOG_LEVEL_INF);

/* Or declare (reference existing module) */
LOG_MODULE_DECLARE(motor_ctrl, LOG_LEVEL_INF);

/* Log messages */
LOG_ERR("Motor fault: overcurrent on channel %d", ch);
LOG_WRN("Battery voltage low: %d mV", voltage);
LOG_INF("Motor speed set: L=%d R=%d", left, right);
LOG_DBG("Encoder tick: %d", count);

/* Hexdump */
LOG_HEXDUMP_INF(buffer, len, "RX data:");
```

### Log Levels
| Level | Macro | Kconfig Value | Use |
|-------|-------|---------------|-----|
| Error | `LOG_ERR` | 1 | Unrecoverable errors |
| Warning | `LOG_WRN` | 2 | Recoverable issues |
| Info | `LOG_INF` | 3 | Normal operation events |
| Debug | `LOG_DBG` | 4 | Development debugging |

---

## 2. Shell Subsystem

Interactive command-line interface over UART (development/debug).

### Configuration
```kconfig
CONFIG_SHELL=y
CONFIG_SHELL_BACKEND_SERIAL=y
CONFIG_SHELL_PROMPT_UART="porter> "
```

### Creating Custom Shell Commands
```c
#include <zephyr/shell/shell.h>

static int cmd_motor_speed(const struct shell *sh, size_t argc, char **argv) {
    if (argc != 3) {
        shell_error(sh, "Usage: motor speed <left> <right>");
        return -EINVAL;
    }
    int left = atoi(argv[1]);
    int right = atoi(argv[2]);
    shell_print(sh, "Setting motors: L=%d R=%d", left, right);
    /* set_motor_speed(left, right); */
    return 0;
}

static int cmd_motor_stop(const struct shell *sh, size_t argc, char **argv) {
    shell_print(sh, "Emergency stop!");
    /* motor_emergency_stop(); */
    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(motor_cmds,
    SHELL_CMD(speed, NULL, "Set motor speed <left> <right>", cmd_motor_speed),
    SHELL_CMD(stop, NULL, "Emergency stop", cmd_motor_stop),
    SHELL_SUBCMD_SET_END
);

SHELL_CMD_REGISTER(motor, &motor_cmds, "Motor control commands", NULL);
```

Shell access: connect via serial terminal → type `help`, `motor speed 50 50`, etc.

---

## 3. State Machine Framework (SMF)

Application-agnostic state machine with optional hierarchical states.

### Configuration
```kconfig
CONFIG_SMF=y
CONFIG_SMF_ANCESTOR_SUPPORT=y          # Hierarchical states
CONFIG_SMF_INITIAL_TRANSITION=y        # Initial transitions to child states
```

### Flat State Machine Example

```c
#include <zephyr/smf.h>

/* Forward declaration of state table */
static const struct smf_state motor_states[];

/* State enumeration */
enum motor_state { IDLE, RUNNING, FAULT, ESTOP };

/* User-defined state object (smf_ctx MUST be first) */
struct motor_obj {
    struct smf_ctx ctx;
    int target_speed_l;
    int target_speed_r;
    bool fault_detected;
};

static struct motor_obj s_obj;

/* --- State handlers --- */

/* IDLE state */
static void idle_entry(void *o) { LOG_INF("Motor: IDLE"); }
static enum smf_state_result idle_run(void *o) {
    struct motor_obj *obj = (struct motor_obj *)o;
    if (obj->target_speed_l != 0 || obj->target_speed_r != 0) {
        smf_set_state(SMF_CTX(obj), &motor_states[RUNNING]);
    }
    return SMF_EVENT_HANDLED;
}

/* RUNNING state */
static void running_entry(void *o) { LOG_INF("Motor: RUNNING"); }
static enum smf_state_result running_run(void *o) {
    struct motor_obj *obj = (struct motor_obj *)o;
    if (obj->fault_detected) {
        smf_set_state(SMF_CTX(obj), &motor_states[FAULT]);
    }
    if (obj->target_speed_l == 0 && obj->target_speed_r == 0) {
        smf_set_state(SMF_CTX(obj), &motor_states[IDLE]);
    }
    return SMF_EVENT_HANDLED;
}
static void running_exit(void *o) { /* stop PWM */ }

/* FAULT state */
static void fault_entry(void *o) { LOG_ERR("Motor: FAULT"); }
static enum smf_state_result fault_run(void *o) {
    /* Wait for reset command */
    return SMF_EVENT_HANDLED;
}

/* ESTOP state */
static void estop_entry(void *o) { LOG_WRN("Motor: EMERGENCY STOP"); }
static enum smf_state_result estop_run(void *o) {
    return SMF_EVENT_HANDLED;
}

/* State table */
static const struct smf_state motor_states[] = {
    [IDLE]    = SMF_CREATE_STATE(idle_entry, idle_run, NULL, NULL, NULL),
    [RUNNING] = SMF_CREATE_STATE(running_entry, running_run, running_exit, NULL, NULL),
    [FAULT]   = SMF_CREATE_STATE(fault_entry, fault_run, NULL, NULL, NULL),
    [ESTOP]   = SMF_CREATE_STATE(estop_entry, estop_run, NULL, NULL, NULL),
};

/* Usage in main thread */
smf_set_initial(SMF_CTX(&s_obj), &motor_states[IDLE]);
while (1) {
    int32_t ret = smf_run_state(SMF_CTX(&s_obj));
    if (ret) { break; }  /* terminated */
    k_msleep(10);
}
```

### Key SMF Rules
- `smf_ctx` MUST be the **first member** of user object
- Call `smf_set_state()` only from entry or run functions (NOT exit)
- Run function returns `SMF_EVENT_HANDLED` or `SMF_EVENT_PROPAGATE` (hierarchical)
- Use `smf_set_terminate()` to end the state machine

---

## 4. Zephyr Bus (zbus)

Lightweight publish/subscribe message bus for inter-thread communication.

### Configuration
```kconfig
CONFIG_ZBUS=y
CONFIG_ZBUS_CHANNEL_NAME=y
CONFIG_ZBUS_OBSERVER_NAME=y
CONFIG_ZBUS_MSG_SUBSCRIBER=y
```

### Define Channels and Observers

```c
#include <zephyr/zbus/zbus.h>

/* Message types */
struct motor_cmd_msg {
    int16_t speed_left;
    int16_t speed_right;
};

struct sensor_data_msg {
    uint16_t tof_distance_mm;
    uint16_t ultrasonic_distance_mm;
    bool obstacle_detected;
};

/* Channel definitions */
ZBUS_CHAN_DEFINE(motor_cmd_chan,
    struct motor_cmd_msg,
    NULL,                                    /* validator */
    NULL,                                    /* user data */
    ZBUS_OBSERVERS(motor_listener),          /* observers */
    ZBUS_MSG_INIT(.speed_left = 0, .speed_right = 0)
);

ZBUS_CHAN_DEFINE(sensor_data_chan,
    struct sensor_data_msg,
    NULL, NULL,
    ZBUS_OBSERVERS(sensor_subscriber),
    ZBUS_MSG_INIT(0)
);

/* Listener (synchronous callback) */
void motor_cmd_callback(const struct zbus_channel *chan) {
    const struct motor_cmd_msg *msg = zbus_chan_const_msg(chan);
    LOG_INF("Motor cmd: L=%d R=%d", msg->speed_left, msg->speed_right);
}
ZBUS_LISTENER_DEFINE(motor_listener, motor_cmd_callback);

/* Subscriber (async, thread-based) */
ZBUS_SUBSCRIBER_DEFINE(sensor_subscriber, 4);
void sensor_thread(void) {
    const struct zbus_channel *chan;
    while (!zbus_sub_wait(&sensor_subscriber, &chan, K_FOREVER)) {
        struct sensor_data_msg data;
        zbus_chan_read(&sensor_data_chan, &data, K_MSEC(100));
        LOG_INF("Sensor: ToF=%d mm", data.tof_distance_mm);
    }
}

/* Publish */
struct motor_cmd_msg cmd = { .speed_left = 100, .speed_right = 100 };
zbus_chan_pub(&motor_cmd_chan, &cmd, K_MSEC(100));
```

### zbus Observer Types
| Type | Context | Gets Message? | Use Case |
|------|---------|---------------|----------|
| **Listener** | Publisher thread | Direct ref (const) | Quick callbacks |
| **Async Listener** | Work queue | Copy | Deferred processing |
| **Subscriber** | Own thread | Notification only (must read) | Thread-based consumers |
| **Message Subscriber** | Own thread | Copy delivered | Thread + guaranteed data |

---

## 5. Task Watchdog

Monitor thread liveness — detect stuck threads.

### Configuration
```kconfig
CONFIG_TASK_WDT=y
```

### Usage
```c
#include <zephyr/task_wdt/task_wdt.h>

/* Initialize */
task_wdt_init(DEVICE_DT_GET(DT_NODELABEL(wdt0)));

/* Register a channel (returns channel ID) */
int wdt_channel = task_wdt_add(1000, /* timeout_ms */
    task_wdt_callback, NULL);

/* Feed in your thread loop */
while (1) {
    task_wdt_feed(wdt_channel);
    /* do work */
    k_msleep(100);
}
```

---

## 6. Power Management

```kconfig
CONFIG_PM=y
CONFIG_PM_DEVICE=y
```

```c
#include <zephyr/pm/pm.h>
#include <zephyr/pm/device.h>

/* Suspend a device */
pm_device_action_run(dev, PM_DEVICE_ACTION_SUSPEND);

/* Resume a device */
pm_device_action_run(dev, PM_DEVICE_ACTION_RESUME);
```

---

## 7. Storage (NVS — Non-Volatile Storage)

For persisting configuration data.

```kconfig
CONFIG_NVS=y
CONFIG_FLASH=y
CONFIG_FLASH_MAP=y
CONFIG_FLASH_PAGE_LAYOUT=y
```

```c
#include <zephyr/fs/nvs.h>

static struct nvs_fs fs;
#define NVS_PARTITION storage_partition
#define NVS_PARTITION_DEVICE FIXED_PARTITION_DEVICE(NVS_PARTITION)
#define NVS_PARTITION_OFFSET FIXED_PARTITION_OFFSET(NVS_PARTITION)

/* Initialize */
fs.flash_device = NVS_PARTITION_DEVICE;
fs.offset = NVS_PARTITION_OFFSET;
fs.sector_size = 4096;
fs.sector_count = 4;
nvs_mount(&fs);

/* Write */
uint16_t id = 1;
int32_t value = 42;
nvs_write(&fs, id, &value, sizeof(value));

/* Read */
int32_t read_val;
nvs_read(&fs, id, &read_val, sizeof(read_val));
```

---

## 8. CRC (Cyclic Redundancy Check)

Built-in CRC functions — useful for the USB CDC protocol.

```c
#include <zephyr/sys/crc.h>

uint16_t crc = crc16_ccitt(0xFFFF, data, len);
uint32_t crc32 = crc32_ieee(data, len);
```

---

## 9. Other Notable Services

| Service | Description | Kconfig |
|---------|-------------|---------|
| **Console** | Simple console output | `CONFIG_CONSOLE=y` |
| **Serialization** | zcbor/protobuf support | `CONFIG_ZCBOR=y` |
| **Sensing** | Sensor management framework | `CONFIG_SENSING=y` |
| **RTIO** | Real-Time I/O subsystem | `CONFIG_RTIO=y` |
| **Device Management** | MCUmgr for OTA updates | `CONFIG_MCUMGR=y` |
| **Tracing** | Execution tracing | `CONFIG_TRACING=y` |

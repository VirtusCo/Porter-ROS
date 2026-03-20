# Zephyr RTOS — Testing, Samples & Debugging — Skill File

> Source: https://docs.zephyrproject.org/latest/develop/test/index.html
> Source: https://docs.zephyrproject.org/latest/samples/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

Zephyr provides built-in testing frameworks, extensive samples, and debugging tools. Testing on `native_sim` allows running Zephyr applications on the host without hardware.

---

## 1. Testing Framework (Ztest)

### Configuration
```kconfig
CONFIG_ZTEST=y
CONFIG_ZTEST_NEW_API=y
```

### Writing Tests

```c
#include <zephyr/ztest.h>

ZTEST_SUITE(protocol_tests, NULL, NULL, NULL, NULL, NULL);

ZTEST(protocol_tests, test_crc16_known_value)
{
    uint8_t data[] = {0x01, 0x02, 0x03};
    uint16_t crc = crc16_ccitt(data, sizeof(data));
    zassert_equal(crc, 0x6131, "CRC mismatch: 0x%04X", crc);
}

ZTEST(protocol_tests, test_parser_valid_packet)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    uint8_t packet[] = {0xAA, 0x55, 0x01, 0x01, 0x42, 0x12, 0x34};
    bool complete = false;
    for (int i = 0; i < sizeof(packet); i++) {
        complete = protocol_parser_feed(&parser, packet[i]);
    }
    zassert_true(complete, "Packet should be complete");
    zassert_equal(parser.packet.command, 0x01, "Wrong command");
}

ZTEST(protocol_tests, test_parser_reject_bad_header)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    /* Wrong header bytes */
    zassert_false(protocol_parser_feed(&parser, 0xBB), "Should reject");
}

ZTEST(protocol_tests, test_encode_roundtrip)
{
    uint8_t payload[] = {0x42};
    uint8_t buf[16];
    size_t len;

    int ret = protocol_encode(0x01, payload, 1, buf, &len);
    zassert_equal(ret, 0, "Encode should succeed");

    /* Parse the encoded packet */
    protocol_parser_t parser;
    protocol_parser_init(&parser);
    bool complete = false;
    for (size_t i = 0; i < len; i++) {
        complete = protocol_parser_feed(&parser, buf[i]);
    }
    zassert_true(complete, "Should parse back to complete packet");
}
```

### Test Project Structure
```
tests/
├── protocol/
│   ├── CMakeLists.txt
│   ├── prj.conf
│   ├── testcase.yaml
│   └── src/
│       └── test_protocol.cpp
```

### testcase.yaml
```yaml
tests:
  protocol.crc:
    tags: protocol
    platform_allow: native_sim
  protocol.parser:
    tags: protocol
    platform_allow: native_sim
```

---

## 2. Twister (Test Runner)

Zephyr's test automation tool:

```bash
# Run all tests for native_sim
cd ~/zephyrproject/zephyr
./scripts/twister -p native_sim -T tests/

# Run specific test suite
./scripts/twister -p native_sim -T tests/protocol/

# Run for ESP32 (requires hardware)
./scripts/twister -p esp32_devkitc/esp32/procpu -T tests/ --device-testing
```

---

## 3. Native Simulation Testing

Run Zephyr apps on the host machine — no hardware needed:

```bash
# Build for native_sim
west build -b native_sim my_app

# Run
./build/zephyr/zephyr.exe

# With test timeout
timeout 10 ./build/zephyr/zephyr.exe
```

**Native sim is ideal for:**
- Protocol parser testing
- State machine logic testing
- zbus communication testing
- CRC implementation validation
- Unit testing without hardware

---

## 4. Relevant Zephyr Samples

### Essential Samples for Porter

| Sample | Path | Relevance |
|--------|------|-----------|
| Hello World | `samples/hello_world` | Basic verification |
| Blinky | `samples/basic/blinky` | GPIO test |
| USB CDC ACM | `samples/subsys/usb/cdc_acm` | **Critical** — USB serial |
| Console over CDC | `samples/subsys/usb/console` | CDC ACM console |
| Shell Module | `samples/subsys/shell/shell_module` | Custom shell commands |
| SMF Calculator | `samples/subsys/smf/smf_calculator` | State machine example |
| SMF HSM | `samples/subsys/smf/hsm_psicc2` | Hierarchical SM |
| zbus Hello World | `samples/subsys/zbus/hello_world` | Message bus basics |
| zbus UART Bridge | `samples/subsys/zbus/uart_bridge` | **Useful** — UART+zbus |
| Task Watchdog | `samples/subsys/task_wdt` | Watchdog monitoring |
| PWM Blinky | `samples/basic/blinky_pwm` | PWM test |
| Sensor Sample | `samples/sensor/*` | Sensor API usage |
| Philosophers | `samples/philosophers` | Multi-threading |
| Settings API | `samples/subsys/settings` | NVS persistence |

### Build a Sample
```bash
cd ~/zephyrproject/zephyr
west build -p always -b esp32_devkitc/esp32/procpu samples/subsys/usb/cdc_acm
west flash
```

---

## 5. Debugging Techniques

### Serial Logging (Primary)
```c
LOG_MODULE_REGISTER(my_module, LOG_LEVEL_DBG);

LOG_DBG("Variable x = %d", x);
LOG_HEXDUMP_DBG(buf, len, "Buffer contents:");
```

### Shell Commands (Interactive Debug)
```
porter> motor speed 50 50
porter> sensor status
porter> kernel threads
porter> kernel stacks
```

### GDB Debugging
```bash
# Start debug server
west debugserver

# In another terminal
west debug
# or connect manually:
# xtensa-esp32-elf-gdb build/zephyr/zephyr.elf
# (gdb) target remote :3333
```

### Thread Analysis
```kconfig
CONFIG_THREAD_ANALYZER=y
CONFIG_THREAD_ANALYZER_AUTO=y
CONFIG_THREAD_ANALYZER_AUTO_INTERVAL=5  # seconds
```

This periodically prints thread stack usage and CPU utilization.

### Stack Usage Analysis
```bash
west build -t rom_report    # ROM/Flash usage
west build -t ram_report    # RAM usage
```

---

## 6. Tracing

For detailed execution analysis:

```kconfig
CONFIG_TRACING=y
CONFIG_TRACING_BACKEND_UART=y
```

Outputs trace data that can be analyzed with tools like Percepio Tracealyzer or custom parsers.

---

## 7. CI Testing Strategy for Porter

### Unit Tests (Run on Host)
- Protocol parser tests → `native_sim`
- CRC16 tests → `native_sim`
- State machine logic → `native_sim`

### Integration Tests (Require Hardware)
- USB CDC ACM connectivity → `esp32_devkitc`
- GPIO/PWM output → `esp32_devkitc` + oscilloscope
- I2C sensor communication → `esp32_devkitc` + sensors
- End-to-end protocol → RPi + ESP32

### Automated Test Commands
```bash
# Run all unit tests on native_sim
./scripts/twister -p native_sim -T tests/

# Generate test report
./scripts/twister -p native_sim -T tests/ --report-dir reports/
```

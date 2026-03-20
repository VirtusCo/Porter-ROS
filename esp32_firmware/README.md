# ESP32 Firmware — Zephyr RTOS

> VirtusCo Porter Robot — ESP32 Motor Controller & Sensor Fusion Firmware
> RTOS: Zephyr · Build Tool: west · Language: C++17

---

## Overview

The Porter robot uses **2× ESP32** microcontrollers running **Zephyr RTOS**, communicating with the RPi 4/5 master over **USB CDC Serial** (`/dev/ttyACM*`).

| ESP32 | Role | Key Peripherals |
|-------|------|-----------------|
| **ESP32 #1** | Motor Controller | 2× BTS7960 H-Bridge (PWM), Encoder inputs, USB CDC ACM |
| **ESP32 #2** | Sensor Fusion | ToF, Ultrasonic, Microwave sensors, USB CDC ACM |

## Folder Structure

```
esp32_firmware/
├── README.md                 # This file
├── motor_controller/         # ESP32 #1 — Motor control firmware
│   ├── CMakeLists.txt
│   ├── prj.conf              # Kconfig configuration
│   ├── app.overlay            # Devicetree overlay (GPIO, PWM, USB)
│   └── src/
│       └── main.cpp
├── sensor_fusion/            # ESP32 #2 — Sensor fusion firmware
│   ├── CMakeLists.txt
│   ├── prj.conf
│   ├── app.overlay
│   └── src/
│       └── main.cpp
└── common/                   # Shared code between both firmwares
    ├── include/
    │   ├── protocol.h        # USB CDC binary protocol (shared with RPi)
    │   └── crc16.h           # CRC16 implementation
    └── src/
        ├── protocol.cpp
        └── crc16.cpp
```

## Build & Flash

### Prerequisites

```bash
# Install Zephyr SDK and west (see skills/zephyr/01_getting_started.md)
pip install west
west init ~/zephyrproject
cd ~/zephyrproject && west update
west zephyr-export
pip install -r ~/zephyrproject/zephyr/scripts/requirements.txt
west sdk install
```

### Build Motor Controller

```bash
cd esp32_firmware/motor_controller
west build -p always -b esp32_devkitc/esp32/procpu
west flash
```

### Build Sensor Fusion

```bash
cd esp32_firmware/sensor_fusion
west build -p always -b esp32_devkitc/esp32/procpu
west flash
```

### Monitor Serial Output

```bash
west espressif monitor
# or
minicom --device /dev/ttyUSB0 -b 115200
```

## Communication Protocol

The RPi ↔ ESP32 communication uses USB CDC ACM (virtual serial) with a binary protocol:

| Field | Size | Description |
|-------|------|-------------|
| Header | 2 bytes | `0xAA 0x55` |
| Length | 1 byte | Payload length |
| Command | 1 byte | Command ID |
| Payload | N bytes | Command-specific data |
| CRC16 | 2 bytes | CRC16 over Length+Command+Payload |

## Key Zephyr Features Used

- **USB CDC ACM** — Virtual serial port for RPi communication
- **PWM** — Motor speed control via BTS7960
- **GPIO** — Direction control, encoder inputs, sensor triggers
- **ADC** — Battery voltage monitoring
- **State Machine Framework (SMF)** — Motor control state machine
- **zbus** — Internal message passing between subsystems
- **Logging** — Structured logging via Zephyr logging subsystem
- **Task Watchdog** — Safety monitoring for motor control
- **Shell** — Debug shell over secondary UART (development only)

## References

- [Zephyr Skills](../skills/zephyr/) — Comprehensive Zephyr RTOS reference
- [OBJECTIVES.md](../OBJECTIVES.md) — Project goals and hardware architecture
- [COMPANY.md](../COMPANY.md) — Company context and product vision

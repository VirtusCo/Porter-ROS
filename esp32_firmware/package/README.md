# @virtusco/porter-firmware

Pre-built ESP32 firmware binaries for the Porter Robot.

## Contents

| Binary | Target | Description |
|--------|--------|-------------|
| `motor_controller.bin` | ESP32 #1 | BTS7960 H-bridge, differential drive, PWM, watchdog |
| `sensor_fusion.bin` | ESP32 #2 | Kalman filter: ToF + Ultrasonic + Microwave fusion |

Built with **Zephyr RTOS v4.0.0** for `esp32_devkitc_wroom`.

## Usage in VS Code Extension

```bash
npm install @virtusco/porter-firmware --registry=https://npm.pkg.github.com
```

```typescript
const fw = require('@virtusco/porter-firmware');

// Get binary paths
const motorBin = fw.getMotorControllerPath();   // -> .../bin/motor_controller.bin
const sensorBin = fw.getSensorFusionPath();     // -> .../bin/sensor_fusion.bin

// List available firmware
console.log(fw.listFirmware()); // ['motor_controller', 'sensor_fusion']

// Verify integrity
console.log(fw.getFirmwareHash('motor_controller')); // SHA256 hex string

// Check version
console.log(fw.getVersion()); // '0.3.2'
```

### Flash with esptool

```bash
esptool.py --chip esp32 --port /dev/ttyUSB0 write_flash 0x0 $(node -e "console.log(require('@virtusco/porter-firmware').getMotorControllerPath())")
```

## Authentication

This package is hosted on GitHub Packages. Add to your `.npmrc`:

```
@virtusco:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

## License

Proprietary - VirtusCo

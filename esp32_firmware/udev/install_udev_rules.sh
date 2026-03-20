#!/bin/bash
# Porter Robot — Install udev rules for ESP32 device stable naming
#
# Usage:
#   sudo ./install_udev_rules.sh
#
# After installation, plug in ESP32 devices and check:
#   ls -la /dev/esp32_*
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_FILE="$SCRIPT_DIR/99-porter-esp32.rules"
DEST="/etc/udev/rules.d/99-porter-esp32.rules"

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

if [ ! -f "$RULES_FILE" ]; then
    echo "Error: Rules file not found: $RULES_FILE"
    exit 1
fi

echo "Installing udev rules..."
cp "$RULES_FILE" "$DEST"
echo "  → Copied to $DEST"

echo "Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

echo ""
echo "Done! udev rules installed."
echo ""
echo "IMPORTANT: You need to customize the rules file with your actual device serial numbers."
echo "  1. Plug in one ESP32 at a time"
echo "  2. Run: udevadm info -a -n /dev/ttyUSB0 | grep -E 'serial|idVendor|idProduct'"
echo "  3. Edit $DEST with the correct serial numbers"
echo "  4. Re-run: sudo udevadm control --reload-rules && sudo udevadm trigger"
echo ""
echo "After setup, your devices will appear as:"
echo "  /dev/esp32_motors  → ESP32 #1 (motor controller)"
echo "  /dev/esp32_sensors → ESP32 #2 (sensor fusion)"

// @virtusco/porter-firmware
// Pre-built ESP32 firmware binaries for the Porter Robot
//
// Usage in VS Code extension:
//   const fw = require('@virtusco/porter-firmware');
//   const motorBin = fw.getMotorControllerPath();
//   const sensorBin = fw.getSensorFusionPath();

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const BIN_DIR = path.join(__dirname, 'bin');

/**
 * Get absolute path to the motor controller firmware binary.
 * @returns {string} Path to motor_controller.bin
 */
function getMotorControllerPath() {
  return path.join(BIN_DIR, 'motor_controller.bin');
}

/**
 * Get absolute path to the sensor fusion firmware binary.
 * @returns {string} Path to sensor_fusion.bin
 */
function getSensorFusionPath() {
  return path.join(BIN_DIR, 'sensor_fusion.bin');
}

/**
 * Get absolute path to any firmware binary by name.
 * @param {string} name - Firmware name (e.g., 'motor_controller', 'sensor_fusion')
 * @returns {string} Path to the .bin file
 */
function getFirmwarePath(name) {
  return path.join(BIN_DIR, `${name}.bin`);
}

/**
 * List all available firmware binaries.
 * @returns {string[]} Array of firmware names (without .bin extension)
 */
function listFirmware() {
  if (!fs.existsSync(BIN_DIR)) return [];
  return fs.readdirSync(BIN_DIR)
    .filter(f => f.endsWith('.bin'))
    .map(f => f.replace('.bin', ''));
}

/**
 * Get SHA256 hash of a firmware binary for verification.
 * @param {string} name - Firmware name (e.g., 'motor_controller')
 * @returns {string} Hex-encoded SHA256 hash
 */
function getFirmwareHash(name) {
  const binPath = getFirmwarePath(name);
  if (!fs.existsSync(binPath)) throw new Error(`Firmware not found: ${name}`);
  const data = fs.readFileSync(binPath);
  return crypto.createHash('sha256').update(data).digest('hex');
}

/**
 * Get firmware package version.
 * @returns {string} Package version
 */
function getVersion() {
  return require('./package.json').version;
}

module.exports = {
  getMotorControllerPath,
  getSensorFusionPath,
  getFirmwarePath,
  listFirmware,
  getFirmwareHash,
  getVersion,
  BIN_DIR,
};

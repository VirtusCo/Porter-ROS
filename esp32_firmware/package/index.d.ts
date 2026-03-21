/** Get absolute path to motor controller firmware binary */
export function getMotorControllerPath(): string;

/** Get absolute path to sensor fusion firmware binary */
export function getSensorFusionPath(): string;

/** Get absolute path to any firmware binary by name */
export function getFirmwarePath(name: string): string;

/** List all available firmware binaries (names without .bin) */
export function listFirmware(): string[];

/** Get SHA256 hash of a firmware binary for verification */
export function getFirmwareHash(name: string): string;

/** Get firmware package version */
export function getVersion(): string;

/** Absolute path to the bin/ directory containing firmware files */
export const BIN_DIR: string;

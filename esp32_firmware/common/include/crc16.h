/*
 * Porter Robot — CRC16-CCITT Implementation
 * Used for protocol packet integrity verification
 *
 * Polynomial: 0x1021 (x^16 + x^12 + x^5 + 1)
 * Initial value: 0xFFFF
 * No final XOR
 *
 * Produces identical results on ESP32 (Zephyr) and RPi (Linux).
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef PORTER_CRC16_H
#define PORTER_CRC16_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/** CRC16-CCITT parameters */
#define CRC16_CCITT_INIT  0xFFFF
#define CRC16_CCITT_POLY  0x1021

/**
 * @brief Calculate CRC16-CCITT over a buffer
 * @param data Pointer to data buffer
 * @param len Length of data in bytes
 * @return CRC16 value
 */
uint16_t crc16_ccitt(const uint8_t *data, size_t len);

/**
 * @brief Update CRC16-CCITT with a single byte (incremental)
 *
 * Use this for streaming / byte-by-byte CRC computation:
 *   uint16_t crc = CRC16_CCITT_INIT;
 *   crc = crc16_ccitt_byte(crc, byte1);
 *   crc = crc16_ccitt_byte(crc, byte2);
 *   ...
 *
 * @param crc Current CRC accumulator value
 * @param byte Input byte
 * @return Updated CRC value
 */
uint16_t crc16_ccitt_byte(uint16_t crc, uint8_t byte);

#ifdef __cplusplus
}
#endif

#endif /* PORTER_CRC16_H */

/*
 * Porter Robot — USB CDC Binary Protocol
 * Shared between RPi (ROS 2) and ESP32 (Zephyr)
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 *
 * Protocol Format:
 *   [Header: 0xAA 0x55] [Length: 1B] [Command: 1B] [Payload: 0..64B] [CRC16: 2B]
 *
 * Length field = number of payload bytes (0..64). Does NOT include command or CRC.
 * CRC16-CCITT is computed over: Length + Command + Payload bytes.
 *
 * Total wire size = 2 (header) + 1 (length) + 1 (command) + length (payload) + 2 (CRC) = length + 6
 */

#ifndef PORTER_PROTOCOL_H
#define PORTER_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- Protocol Constants --- */
#define PROTOCOL_HEADER_BYTE1   0xAA
#define PROTOCOL_HEADER_BYTE2   0x55
#define PROTOCOL_MAX_PAYLOAD    64
#define PROTOCOL_HEADER_SIZE    2
#define PROTOCOL_OVERHEAD        6  /* Header(2) + Length(1) + Command(1) + CRC16(2) */
#define PROTOCOL_MAX_PACKET_SIZE (PROTOCOL_OVERHEAD + PROTOCOL_MAX_PAYLOAD)  /* 70 bytes */

/* --- Command IDs --- */

/* Motor Controller Commands (ESP32 #1) */
#define CMD_MOTOR_SET_SPEED     0x01  /* Set motor speed: [left_i16][right_i16][flags_u8] */
#define CMD_MOTOR_STOP          0x02  /* Emergency stop, no payload */
#define CMD_MOTOR_STATUS        0x03  /* Request/report motor status */
#define CMD_MOTOR_ENCODER       0x04  /* Encoder tick report */

/* Sensor Fusion Commands (ESP32 #2) */
#define CMD_SENSOR_TOF          0x10  /* ToF distance reading */
#define CMD_SENSOR_ULTRASONIC   0x11  /* Ultrasonic distance reading */
#define CMD_SENSOR_MICROWAVE    0x12  /* Microwave presence detection */
#define CMD_SENSOR_FUSED        0x13  /* Fused sensor data */
#define CMD_SENSOR_STATUS       0x14  /* Request/report sensor status */

/* Common Commands */
#define CMD_HEARTBEAT           0xF0  /* Keepalive heartbeat */
#define CMD_VERSION             0xF1  /* Firmware version query */
#define CMD_NACK                0xFD  /* Negative acknowledgement (unknown/bad command) */
#define CMD_RESET               0xFE  /* Software reset */
#define CMD_ACK                 0xFF  /* Acknowledgement */

/* --- NACK Reason Codes --- */
#define NACK_UNKNOWN_CMD        0x01
#define NACK_BAD_PAYLOAD        0x02
#define NACK_BAD_STATE          0x03

/* --- Protocol Packet Structure --- */
typedef struct {
    uint8_t command;
    uint8_t length;    /* payload length (0..64) */
    uint8_t payload[PROTOCOL_MAX_PAYLOAD];
    uint16_t crc;      /* received CRC (for parsed packets) */
} protocol_packet_t;

/* --- Parser State Machine --- */
typedef enum {
    PARSE_HEADER1,
    PARSE_HEADER2,
    PARSE_LENGTH,
    PARSE_COMMAND,
    PARSE_PAYLOAD,
    PARSE_CRC_LOW,
    PARSE_CRC_HIGH,
    PARSE_COMPLETE,
    PARSE_ERROR
} parse_state_t;

typedef struct {
    parse_state_t state;
    protocol_packet_t packet;
    uint8_t payload_idx;
    uint16_t computed_crc;  /* running CRC during parse */
} protocol_parser_t;

/* --- Parser Statistics (optional, for diagnostics) --- */
typedef struct {
    uint32_t packets_ok;
    uint32_t crc_errors;
    uint32_t overflow_errors;
    uint32_t total_bytes;
} protocol_stats_t;

/* --- API Functions --- */

/**
 * @brief Initialize the protocol parser
 * @param parser Pointer to parser context
 */
void protocol_parser_init(protocol_parser_t *parser);

/**
 * @brief Reset parser to initial state (after error or after reading packet)
 * @param parser Pointer to parser context
 */
void protocol_parser_reset(protocol_parser_t *parser);

/**
 * @brief Feed a byte to the protocol parser
 *
 * Call this for each received byte. When it returns true, a complete
 * and CRC-validated packet is available in parser->packet.
 * After reading the packet, call protocol_parser_reset() before
 * feeding more bytes.
 *
 * @param parser Pointer to parser context
 * @param byte Input byte
 * @return true if a complete valid packet is available (state == PARSE_COMPLETE)
 */
bool protocol_parser_feed(protocol_parser_t *parser, uint8_t byte);

/**
 * @brief Encode a packet for transmission
 *
 * Writes: [0xAA][0x55][length][command][payload...][CRC16_lo][CRC16_hi]
 *
 * @param cmd Command ID
 * @param payload Payload data (can be NULL if payload_len is 0)
 * @param payload_len Payload length (0..64)
 * @param out_buf Output buffer (must be at least payload_len + PROTOCOL_OVERHEAD bytes)
 * @param out_len Pointer to store total encoded length
 * @return 0 on success, -1 on invalid args (payload too large, NULL out_buf, etc.)
 */
int protocol_encode(uint8_t cmd, const uint8_t *payload, uint8_t payload_len,
                    uint8_t *out_buf, size_t *out_len);

/**
 * @brief Encode an ACK response packet
 * @param acked_cmd The command being acknowledged
 * @param out_buf Output buffer (must be at least PROTOCOL_OVERHEAD + 1 bytes)
 * @param out_len Pointer to store total encoded length
 * @return 0 on success
 */
int protocol_encode_ack(uint8_t acked_cmd, uint8_t *out_buf, size_t *out_len);

/**
 * @brief Encode a NACK response packet
 * @param nacked_cmd The command being rejected
 * @param reason NACK reason code (NACK_UNKNOWN_CMD, etc.)
 * @param out_buf Output buffer (must be at least PROTOCOL_OVERHEAD + 2 bytes)
 * @param out_len Pointer to store total encoded length
 * @return 0 on success
 */
int protocol_encode_nack(uint8_t nacked_cmd, uint8_t reason,
                         uint8_t *out_buf, size_t *out_len);

#ifdef __cplusplus
}
#endif

#endif /* PORTER_PROTOCOL_H */

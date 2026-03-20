/*
 * Porter Robot — USB CDC Binary Protocol Implementation
 *
 * Byte-by-byte parser state machine and packet encoder.
 * CRC16-CCITT computed over: Length + Command + Payload bytes.
 *
 * Wire format:
 *   [0xAA] [0x55] [Length] [Command] [Payload: 0..64B] [CRC16_lo] [CRC16_hi]
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */

#include "protocol.h"
#include "crc16.h"
#include <string.h>

/* ------------------------------------------------------------------ */
/*  Parser                                                             */
/* ------------------------------------------------------------------ */

void protocol_parser_init(protocol_parser_t *parser)
{
    memset(parser, 0, sizeof(*parser));
    parser->state = PARSE_HEADER1;
}

void protocol_parser_reset(protocol_parser_t *parser)
{
    parser->state       = PARSE_HEADER1;
    parser->payload_idx = 0;
    parser->computed_crc = CRC16_CCITT_INIT;
    /* packet fields are overwritten during next parse — no need to zero */
}

bool protocol_parser_feed(protocol_parser_t *parser, uint8_t byte)
{
    switch (parser->state) {

    case PARSE_HEADER1:
        if (byte == PROTOCOL_HEADER_BYTE1) {
            parser->state = PARSE_HEADER2;
            parser->computed_crc = CRC16_CCITT_INIT;
            parser->payload_idx = 0;
        }
        /* else: stay in HEADER1 — silently skip garbage bytes */
        break;

    case PARSE_HEADER2:
        if (byte == PROTOCOL_HEADER_BYTE2) {
            parser->state = PARSE_LENGTH;
        } else if (byte == PROTOCOL_HEADER_BYTE1) {
            /* Got another 0xAA — could be start of a new header, stay in HEADER2 */
            parser->state = PARSE_HEADER2;
        } else {
            /* Not a valid header — restart */
            parser->state = PARSE_HEADER1;
        }
        break;

    case PARSE_LENGTH:
        if (byte > PROTOCOL_MAX_PAYLOAD) {
            /* Oversized payload — reject and restart */
            parser->state = PARSE_ERROR;
        } else {
            parser->packet.length = byte;
            /* Start CRC over: Length + Command + Payload */
            parser->computed_crc = CRC16_CCITT_INIT;
            parser->computed_crc = crc16_ccitt_byte(parser->computed_crc, byte);
            parser->state = PARSE_COMMAND;
        }
        break;

    case PARSE_COMMAND:
        parser->packet.command = byte;
        parser->computed_crc = crc16_ccitt_byte(parser->computed_crc, byte);
        if (parser->packet.length == 0) {
            /* No payload — go straight to CRC */
            parser->state = PARSE_CRC_LOW;
        } else {
            parser->payload_idx = 0;
            parser->state = PARSE_PAYLOAD;
        }
        break;

    case PARSE_PAYLOAD:
        parser->packet.payload[parser->payload_idx] = byte;
        parser->computed_crc = crc16_ccitt_byte(parser->computed_crc, byte);
        parser->payload_idx++;
        if (parser->payload_idx >= parser->packet.length) {
            parser->state = PARSE_CRC_LOW;
        }
        break;

    case PARSE_CRC_LOW:
        /* CRC is transmitted little-endian: low byte first */
        parser->packet.crc = (uint16_t)byte;
        parser->state = PARSE_CRC_HIGH;
        break;

    case PARSE_CRC_HIGH:
        parser->packet.crc |= (uint16_t)(byte << 8);
        if (parser->packet.crc == parser->computed_crc) {
            parser->state = PARSE_COMPLETE;
            return true;
        } else {
            /* CRC mismatch — corrupted packet */
            parser->state = PARSE_ERROR;
        }
        break;

    case PARSE_COMPLETE:
        /* Caller hasn't consumed the packet yet.
         * If they keep feeding bytes, auto-reset and try to parse.
         */
        protocol_parser_reset(parser);
        return protocol_parser_feed(parser, byte);

    case PARSE_ERROR:
        /* Auto-reset on next potential header byte */
        protocol_parser_reset(parser);
        if (byte == PROTOCOL_HEADER_BYTE1) {
            parser->state = PARSE_HEADER2;
        }
        break;
    }

    return false;
}

/* ------------------------------------------------------------------ */
/*  Encoder                                                            */
/* ------------------------------------------------------------------ */

int protocol_encode(uint8_t cmd, const uint8_t *payload, uint8_t payload_len,
                    uint8_t *out_buf, size_t *out_len)
{
    if (out_buf == NULL || out_len == NULL) {
        return -1;
    }
    if (payload_len > PROTOCOL_MAX_PAYLOAD) {
        return -1;
    }
    if (payload_len > 0 && payload == NULL) {
        return -1;
    }

    size_t idx = 0;

    /* Header */
    out_buf[idx++] = PROTOCOL_HEADER_BYTE1;
    out_buf[idx++] = PROTOCOL_HEADER_BYTE2;

    /* Length (payload bytes only) */
    out_buf[idx++] = payload_len;

    /* Command */
    out_buf[idx++] = cmd;

    /* Payload */
    if (payload_len > 0) {
        memcpy(&out_buf[idx], payload, payload_len);
        idx += payload_len;
    }

    /* CRC16 over Length + Command + Payload */
    /* CRC data starts at out_buf[2] (the Length byte) */
    uint16_t crc = crc16_ccitt(&out_buf[2], (size_t)(1 + 1 + payload_len));

    /* CRC little-endian */
    out_buf[idx++] = (uint8_t)(crc & 0xFF);
    out_buf[idx++] = (uint8_t)((crc >> 8) & 0xFF);

    *out_len = idx;
    return 0;
}

int protocol_encode_ack(uint8_t acked_cmd, uint8_t *out_buf, size_t *out_len)
{
    uint8_t payload[1] = { acked_cmd };
    return protocol_encode(CMD_ACK, payload, 1, out_buf, out_len);
}

int protocol_encode_nack(uint8_t nacked_cmd, uint8_t reason,
                         uint8_t *out_buf, size_t *out_len)
{
    uint8_t payload[2] = { nacked_cmd, reason };
    return protocol_encode(CMD_NACK, payload, 2, out_buf, out_len);
}

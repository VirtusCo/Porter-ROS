/*
 * Porter Robot — Protocol Parser & Encoder Unit Tests
 * Run on native_sim via Ztest
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/ztest.h>
#include <cstring>
#include "protocol.h"
#include "crc16.h"

/* ========================================================================
 * Parser Tests
 * ======================================================================== */

ZTEST_SUITE(parser_tests, NULL, NULL, NULL, NULL, NULL);

/* Helper: build a valid raw packet from command + payload.
 * Returns total wire size written to out_buf. */
static size_t build_raw_packet(uint8_t cmd, const uint8_t *payload,
                               uint8_t payload_len, uint8_t *out_buf)
{
    out_buf[0] = PROTOCOL_HEADER_BYTE1;
    out_buf[1] = PROTOCOL_HEADER_BYTE2;
    out_buf[2] = payload_len;
    out_buf[3] = cmd;

    if (payload_len > 0 && payload != NULL) {
        memcpy(&out_buf[4], payload, payload_len);
    }

    /* CRC over length + command + payload */
    uint16_t crc = crc16_ccitt(&out_buf[2], 2 + payload_len);
    out_buf[4 + payload_len] = (uint8_t)(crc & 0xFF);
    out_buf[5 + payload_len] = (uint8_t)((crc >> 8) & 0xFF);

    return 6 + payload_len;
}

/* Helper: feed raw bytes into parser, return true if packet completed */
static bool feed_all(protocol_parser_t *p, const uint8_t *data, size_t len)
{
    bool complete = false;
    for (size_t i = 0; i < len; i++) {
        complete = protocol_parser_feed(p, data[i]);
        if (complete) {
            return true;
        }
    }
    return complete;
}

/* -- Basic valid packets -- */

ZTEST(parser_tests, test_parse_zero_length_payload)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
    size_t len = build_raw_packet(CMD_HEARTBEAT, NULL, 0, raw);

    zassert_true(feed_all(&parser, raw, len), "Should parse zero-payload packet");
    zassert_equal(parser.packet.command, CMD_HEARTBEAT, "Command mismatch");
    zassert_equal(parser.packet.length, 0, "Length should be 0");
}

ZTEST(parser_tests, test_parse_single_byte_payload)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    uint8_t payload[] = {0x42};
    uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
    size_t len = build_raw_packet(CMD_VERSION, payload, 1, raw);

    zassert_true(feed_all(&parser, raw, len), "Should parse 1-byte payload packet");
    zassert_equal(parser.packet.command, CMD_VERSION);
    zassert_equal(parser.packet.length, 1);
    zassert_equal(parser.packet.payload[0], 0x42);
}

ZTEST(parser_tests, test_parse_5_byte_payload)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    uint8_t payload[] = {0x00, 0x64, 0xFF, 0x9C, 0x01};  /* motor speed cmd */
    uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
    size_t len = build_raw_packet(CMD_MOTOR_SET_SPEED, payload, 5, raw);

    zassert_true(feed_all(&parser, raw, len), "Should parse 5-byte payload");
    zassert_equal(parser.packet.command, CMD_MOTOR_SET_SPEED);
    zassert_equal(parser.packet.length, 5);
    zassert_mem_equal(parser.packet.payload, payload, 5);
}

ZTEST(parser_tests, test_parse_max_payload)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    uint8_t payload[PROTOCOL_MAX_PAYLOAD];
    for (int i = 0; i < PROTOCOL_MAX_PAYLOAD; i++) {
        payload[i] = (uint8_t)(i & 0xFF);
    }

    uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
    size_t len = build_raw_packet(0x50, payload, PROTOCOL_MAX_PAYLOAD, raw);

    zassert_true(feed_all(&parser, raw, len), "Should parse full 64-byte payload");
    zassert_equal(parser.packet.length, PROTOCOL_MAX_PAYLOAD);
    zassert_mem_equal(parser.packet.payload, payload, PROTOCOL_MAX_PAYLOAD);
}

/* -- Error cases -- */

ZTEST(parser_tests, test_reject_bad_header_byte1)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    /* Wrong first byte */
    zassert_false(protocol_parser_feed(&parser, 0xBB), "Bad header byte should not complete");
    /* Parser should reset to HEADER1, so valid header should work next */
    zassert_false(protocol_parser_feed(&parser, PROTOCOL_HEADER_BYTE1), "Partial");
}

ZTEST(parser_tests, test_reject_bad_header_byte2)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    /* Valid first byte, wrong second byte */
    protocol_parser_feed(&parser, PROTOCOL_HEADER_BYTE1);
    /* Wrong second byte — parser should reset or go back to looking for header */
    bool result = protocol_parser_feed(&parser, 0xEE);
    zassert_false(result, "Bad header byte 2 should not complete");
}

ZTEST(parser_tests, test_reject_bad_crc)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
    size_t len = build_raw_packet(CMD_HEARTBEAT, NULL, 0, raw);

    /* Corrupt CRC */
    raw[len - 1] ^= 0xFF;

    zassert_false(feed_all(&parser, raw, len),
                  "Corrupted CRC should not produce valid packet");
}

ZTEST(parser_tests, test_reject_oversized_payload)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    /* Manually construct packet with length > 64 */
    uint8_t raw[] = {PROTOCOL_HEADER_BYTE1, PROTOCOL_HEADER_BYTE2, 65, 0x01};
    bool result = false;
    for (size_t i = 0; i < sizeof(raw); i++) {
        result = protocol_parser_feed(&parser, raw[i]);
    }
    /* Parser should reject length > 64 and go to error state */
    zassert_false(result, "Oversized payload should be rejected");
}

/* -- Multiple packets in sequence -- */

ZTEST(parser_tests, test_sequential_packets)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    /* First packet */
    uint8_t payload1[] = {0x01};
    uint8_t raw1[PROTOCOL_MAX_PACKET_SIZE];
    size_t len1 = build_raw_packet(CMD_HEARTBEAT, payload1, 1, raw1);

    zassert_true(feed_all(&parser, raw1, len1), "First packet should parse");
    zassert_equal(parser.packet.command, CMD_HEARTBEAT);
    protocol_parser_reset(&parser);

    /* Second packet */
    uint8_t payload2[] = {0x02, 0x03};
    uint8_t raw2[PROTOCOL_MAX_PACKET_SIZE];
    size_t len2 = build_raw_packet(CMD_VERSION, payload2, 2, raw2);

    zassert_true(feed_all(&parser, raw2, len2), "Second packet should parse");
    zassert_equal(parser.packet.command, CMD_VERSION);
    zassert_equal(parser.packet.length, 2);
}

ZTEST(parser_tests, test_back_to_back_packets)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    uint8_t raw1[PROTOCOL_MAX_PACKET_SIZE];
    uint8_t raw2[PROTOCOL_MAX_PACKET_SIZE];
    size_t len1 = build_raw_packet(CMD_HEARTBEAT, NULL, 0, raw1);
    uint8_t pay2[] = {0xAA};
    size_t len2 = build_raw_packet(CMD_MOTOR_STOP, pay2, 1, raw2);

    /* Feed back-to-back bytes */
    uint8_t combined[PROTOCOL_MAX_PACKET_SIZE * 2];
    memcpy(combined, raw1, len1);
    memcpy(combined + len1, raw2, len2);

    /* First packet */
    bool got_first = false;
    size_t i;
    for (i = 0; i < len1 + len2; i++) {
        if (protocol_parser_feed(&parser, combined[i])) {
            got_first = true;
            zassert_equal(parser.packet.command, CMD_HEARTBEAT);
            protocol_parser_reset(&parser);
            i++;
            break;
        }
    }
    zassert_true(got_first, "Should parse first packet");

    /* Second packet from remaining bytes */
    bool got_second = false;
    for (; i < len1 + len2; i++) {
        if (protocol_parser_feed(&parser, combined[i])) {
            got_second = true;
            zassert_equal(parser.packet.command, CMD_MOTOR_STOP);
            break;
        }
    }
    zassert_true(got_second, "Should parse second packet");
}

/* -- Parser with garbage before valid packet -- */

ZTEST(parser_tests, test_garbage_before_packet)
{
    protocol_parser_t parser;
    protocol_parser_init(&parser);

    /* Feed garbage */
    uint8_t garbage[] = {0x12, 0x34, 0x56, 0x78, 0x9A};
    feed_all(&parser, garbage, sizeof(garbage));
    protocol_parser_reset(&parser);

    /* Now feed a valid packet */
    uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
    size_t len = build_raw_packet(CMD_HEARTBEAT, NULL, 0, raw);
    zassert_true(feed_all(&parser, raw, len), "Valid packet after garbage should parse");
}

/* -- All command IDs -- */

ZTEST(parser_tests, test_all_motor_commands)
{
    uint8_t cmds[] = {CMD_MOTOR_SET_SPEED, CMD_MOTOR_STOP, CMD_MOTOR_STATUS, CMD_MOTOR_ENCODER};
    for (size_t c = 0; c < sizeof(cmds); c++) {
        protocol_parser_t parser;
        protocol_parser_init(&parser);

        uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
        size_t len = build_raw_packet(cmds[c], NULL, 0, raw);
        zassert_true(feed_all(&parser, raw, len),
                     "Motor cmd 0x%02X should parse", cmds[c]);
        zassert_equal(parser.packet.command, cmds[c]);
    }
}

ZTEST(parser_tests, test_all_sensor_commands)
{
    uint8_t cmds[] = {CMD_SENSOR_TOF, CMD_SENSOR_ULTRASONIC, CMD_SENSOR_MICROWAVE,
                      CMD_SENSOR_FUSED, CMD_SENSOR_STATUS};
    for (size_t c = 0; c < sizeof(cmds); c++) {
        protocol_parser_t parser;
        protocol_parser_init(&parser);

        uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
        size_t len = build_raw_packet(cmds[c], NULL, 0, raw);
        zassert_true(feed_all(&parser, raw, len),
                     "Sensor cmd 0x%02X should parse", cmds[c]);
    }
}

ZTEST(parser_tests, test_common_commands)
{
    uint8_t cmds[] = {CMD_HEARTBEAT, CMD_VERSION, CMD_NACK, CMD_RESET, CMD_ACK};
    for (size_t c = 0; c < sizeof(cmds); c++) {
        protocol_parser_t parser;
        protocol_parser_init(&parser);

        uint8_t raw[PROTOCOL_MAX_PACKET_SIZE];
        size_t len = build_raw_packet(cmds[c], NULL, 0, raw);
        zassert_true(feed_all(&parser, raw, len),
                     "Common cmd 0x%02X should parse", cmds[c]);
    }
}

/* ========================================================================
 * Encoder Tests
 * ======================================================================== */

ZTEST_SUITE(encoder_tests, NULL, NULL, NULL, NULL, NULL);

ZTEST(encoder_tests, test_encode_zero_payload)
{
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    int ret = protocol_encode(CMD_HEARTBEAT, NULL, 0, buf, &len);
    zassert_equal(ret, 0, "Encode should succeed");
    zassert_equal(len, PROTOCOL_OVERHEAD, "Zero-payload packet should be %d bytes",
                  PROTOCOL_OVERHEAD);

    /* Verify header */
    zassert_equal(buf[0], PROTOCOL_HEADER_BYTE1);
    zassert_equal(buf[1], PROTOCOL_HEADER_BYTE2);
    /* Verify length field */
    zassert_equal(buf[2], 0, "Payload length should be 0");
    /* Verify command */
    zassert_equal(buf[3], CMD_HEARTBEAT);
}

ZTEST(encoder_tests, test_encode_with_payload)
{
    uint8_t payload[] = {0xDE, 0xAD, 0xBE, 0xEF};
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    int ret = protocol_encode(0x42, payload, 4, buf, &len);
    zassert_equal(ret, 0, "Encode should succeed");
    zassert_equal(len, PROTOCOL_OVERHEAD + 4, "Should be overhead + 4 payload bytes");

    /* Verify payload is in the right place */
    zassert_mem_equal(&buf[4], payload, 4, "Payload data mismatch");
}

ZTEST(encoder_tests, test_encode_max_payload)
{
    uint8_t payload[PROTOCOL_MAX_PAYLOAD];
    for (int i = 0; i < PROTOCOL_MAX_PAYLOAD; i++) {
        payload[i] = (uint8_t)i;
    }

    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    int ret = protocol_encode(0x50, payload, PROTOCOL_MAX_PAYLOAD, buf, &len);
    zassert_equal(ret, 0, "Max payload encode should succeed");
    zassert_equal(len, PROTOCOL_MAX_PACKET_SIZE, "Should be max packet size");
}

ZTEST(encoder_tests, test_encode_reject_oversized)
{
    uint8_t payload[PROTOCOL_MAX_PAYLOAD + 1];
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE + 10];
    size_t len;

    int ret = protocol_encode(0x50, payload, PROTOCOL_MAX_PAYLOAD + 1, buf, &len);
    zassert_not_equal(ret, 0, "Should reject payload > 64 bytes");
}

ZTEST(encoder_tests, test_encode_reject_null_outbuf)
{
    size_t len;
    int ret = protocol_encode(0x01, NULL, 0, NULL, &len);
    zassert_not_equal(ret, 0, "Should reject NULL output buffer");
}

ZTEST(encoder_tests, test_encode_ack)
{
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    int ret = protocol_encode_ack(CMD_MOTOR_SET_SPEED, buf, &len);
    zassert_equal(ret, 0, "ACK encode should succeed");
    zassert_true(len > 0, "ACK should produce bytes");

    /* Parse it back */
    protocol_parser_t parser;
    protocol_parser_init(&parser);
    zassert_true(feed_all(&parser, buf, len), "ACK should parse back");
    zassert_equal(parser.packet.command, CMD_ACK);
    /* ACK payload contains the acked command */
    zassert_equal(parser.packet.payload[0], CMD_MOTOR_SET_SPEED);
}

ZTEST(encoder_tests, test_encode_nack)
{
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    int ret = protocol_encode_nack(CMD_RESET, NACK_BAD_PAYLOAD, buf, &len);
    zassert_equal(ret, 0, "NACK encode should succeed");

    /* Parse it back */
    protocol_parser_t parser;
    protocol_parser_init(&parser);
    zassert_true(feed_all(&parser, buf, len), "NACK should parse back");
    zassert_equal(parser.packet.command, CMD_NACK);
    zassert_equal(parser.packet.payload[0], CMD_RESET);
    zassert_equal(parser.packet.payload[1], NACK_BAD_PAYLOAD);
}

/* ========================================================================
 * Round-trip Tests (encode → parse)
 * ======================================================================== */

ZTEST_SUITE(roundtrip_tests, NULL, NULL, NULL, NULL, NULL);

ZTEST(roundtrip_tests, test_roundtrip_zero_payload)
{
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    protocol_encode(CMD_HEARTBEAT, NULL, 0, buf, &len);

    protocol_parser_t parser;
    protocol_parser_init(&parser);
    zassert_true(feed_all(&parser, buf, len), "Round-trip zero-payload");
    zassert_equal(parser.packet.command, CMD_HEARTBEAT);
    zassert_equal(parser.packet.length, 0);
}

ZTEST(roundtrip_tests, test_roundtrip_with_payload)
{
    uint8_t payload[] = {0x00, 0x64, 0xFF, 0x9C, 0x01};
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    protocol_encode(CMD_MOTOR_SET_SPEED, payload, 5, buf, &len);

    protocol_parser_t parser;
    protocol_parser_init(&parser);
    zassert_true(feed_all(&parser, buf, len), "Round-trip with payload");
    zassert_equal(parser.packet.command, CMD_MOTOR_SET_SPEED);
    zassert_equal(parser.packet.length, 5);
    zassert_mem_equal(parser.packet.payload, payload, 5);
}

ZTEST(roundtrip_tests, test_roundtrip_max_payload)
{
    uint8_t payload[PROTOCOL_MAX_PAYLOAD];
    for (int i = 0; i < PROTOCOL_MAX_PAYLOAD; i++) {
        payload[i] = (uint8_t)(0xFF - i);
    }

    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    protocol_encode(0x42, payload, PROTOCOL_MAX_PAYLOAD, buf, &len);

    protocol_parser_t parser;
    protocol_parser_init(&parser);
    zassert_true(feed_all(&parser, buf, len), "Round-trip max payload");
    zassert_equal(parser.packet.length, PROTOCOL_MAX_PAYLOAD);
    zassert_mem_equal(parser.packet.payload, payload, PROTOCOL_MAX_PAYLOAD);
}

ZTEST(roundtrip_tests, test_roundtrip_all_commands)
{
    uint8_t all_cmds[] = {
        CMD_MOTOR_SET_SPEED, CMD_MOTOR_STOP, CMD_MOTOR_STATUS, CMD_MOTOR_ENCODER,
        CMD_SENSOR_TOF, CMD_SENSOR_ULTRASONIC, CMD_SENSOR_MICROWAVE,
        CMD_SENSOR_FUSED, CMD_SENSOR_STATUS,
        CMD_HEARTBEAT, CMD_VERSION, CMD_NACK, CMD_RESET, CMD_ACK,
    };

    for (size_t c = 0; c < sizeof(all_cmds); c++) {
        uint8_t payload[] = {0xAA};
        uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
        size_t len;

        protocol_encode(all_cmds[c], payload, 1, buf, &len);

        protocol_parser_t parser;
        protocol_parser_init(&parser);
        zassert_true(feed_all(&parser, buf, len),
                     "Round-trip cmd 0x%02X", all_cmds[c]);
        zassert_equal(parser.packet.command, all_cmds[c],
                      "Command mismatch for 0x%02X", all_cmds[c]);
    }
}

/* CRC verification: encoded packet CRC should match what parser computes */
ZTEST(roundtrip_tests, test_encoded_crc_matches_parser_crc)
{
    uint8_t payload[] = {0x01, 0x02, 0x03};
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len;

    protocol_encode(CMD_MOTOR_STATUS, payload, 3, buf, &len);

    /* Manually compute CRC over the same segment */
    uint16_t expected_crc = crc16_ccitt(&buf[2], 2 + 3);  /* length + cmd + payload */

    /* Read CRC from wire (little-endian) */
    uint16_t wire_crc = (uint16_t)buf[len - 2] | ((uint16_t)buf[len - 1] << 8);

    zassert_equal(wire_crc, expected_crc,
                  "Wire CRC 0x%04X should match computed 0x%04X",
                  wire_crc, expected_crc);
}

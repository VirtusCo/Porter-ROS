/*
 * Porter Robot — Transport Abstraction Layer Unit Tests
 * Run on native_sim with mock transport backend via Ztest
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/ztest.h>
#include <cstring>
#include "transport.h"
#include "protocol.h"
#include "crc16.h"

/* ========================================================================
 * Test fixtures — reset mock state before each test
 * ======================================================================== */

static void *transport_setup(void)
{
    transport_mock_reset();
    return NULL;
}

static void transport_before(void *fixture)
{
    ARG_UNUSED(fixture);
    transport_mock_reset();
    transport_config_t cfg = TRANSPORT_CONFIG_DEFAULT;
    int ret = transport_init(&cfg);
    zassert_equal(ret, TRANSPORT_OK, "transport_init should succeed");
}

static void transport_after(void *fixture)
{
    ARG_UNUSED(fixture);
    transport_deinit();
}

ZTEST_SUITE(transport_tests, NULL, NULL, transport_before, transport_after, NULL);

/* ========================================================================
 * Basic Init/Ready Tests
 * ======================================================================== */

ZTEST(transport_tests, test_init_success)
{
    /* Already initialized in before(), just verify */
    zassert_true(transport_is_ready(), "Should be ready after init");
}

ZTEST(transport_tests, test_backend_name)
{
    const char *name = transport_backend_name();
    zassert_equal(strcmp(name, "mock"), 0,
                  "Backend should be 'mock', got '%s'", name);
}

ZTEST(transport_tests, test_not_ready_before_init)
{
    transport_deinit();
    zassert_false(transport_is_ready(), "Should not be ready after deinit");
}

ZTEST(transport_tests, test_read_not_ready)
{
    transport_deinit();
    uint8_t buf[16];
    int ret = transport_read(buf, sizeof(buf));
    zassert_true(ret < 0, "Read should fail when not ready");
}

ZTEST(transport_tests, test_write_not_ready)
{
    transport_deinit();
    uint8_t data[] = {0x01};
    int ret = transport_write(data, 1);
    zassert_true(ret < 0, "Write should fail when not ready");
}

/* ========================================================================
 * Read/Write Tests
 * ======================================================================== */

ZTEST(transport_tests, test_read_empty)
{
    uint8_t buf[16];
    int n = transport_read(buf, sizeof(buf));
    zassert_equal(n, 0, "Should read 0 from empty buffer");
}

ZTEST(transport_tests, test_inject_and_read)
{
    uint8_t inject[] = {0xDE, 0xAD, 0xBE, 0xEF};
    transport_mock_inject_rx(inject, sizeof(inject));

    uint8_t buf[16];
    int n = transport_read(buf, sizeof(buf));
    zassert_equal(n, 4, "Should read 4 injected bytes");
    zassert_mem_equal(buf, inject, 4, "Data should match injected bytes");
}

ZTEST(transport_tests, test_partial_read)
{
    uint8_t inject[] = {0x01, 0x02, 0x03, 0x04, 0x05};
    transport_mock_inject_rx(inject, sizeof(inject));

    /* Read only 3 bytes */
    uint8_t buf[3];
    int n = transport_read(buf, sizeof(buf));
    zassert_equal(n, 3, "Should read 3 bytes");
    zassert_mem_equal(buf, inject, 3);

    /* Read remaining 2 */
    n = transport_read(buf, sizeof(buf));
    zassert_equal(n, 2, "Should read remaining 2 bytes");
    zassert_equal(buf[0], 0x04);
    zassert_equal(buf[1], 0x05);
}

ZTEST(transport_tests, test_write_and_capture)
{
    uint8_t data[] = {0xAA, 0x55, 0x01, 0x02};
    int n = transport_write(data, sizeof(data));
    zassert_equal(n, 4, "Should write 4 bytes, got %d", n);

    uint8_t captured[16];
    size_t cap_len = transport_mock_get_tx(captured, sizeof(captured));
    zassert_equal(cap_len, 4, "Should capture 4 bytes");
    zassert_mem_equal(captured, data, 4);
}

ZTEST(transport_tests, test_write_multiple_then_capture)
{
    uint8_t data1[] = {0x01, 0x02};
    uint8_t data2[] = {0x03, 0x04};

    transport_write(data1, sizeof(data1));
    transport_write(data2, sizeof(data2));

    uint8_t captured[16];
    size_t cap_len = transport_mock_get_tx(captured, sizeof(captured));
    zassert_equal(cap_len, 4, "Should capture all 4 bytes");
    zassert_equal(captured[0], 0x01);
    zassert_equal(captured[1], 0x02);
    zassert_equal(captured[2], 0x03);
    zassert_equal(captured[3], 0x04);
}

ZTEST(transport_tests, test_read_null_buffer)
{
    int n = transport_read(NULL, 10);
    zassert_equal(n, 0, "NULL buffer read should return 0");
}

ZTEST(transport_tests, test_read_zero_length)
{
    uint8_t buf[16];
    int n = transport_read(buf, 0);
    zassert_equal(n, 0, "Zero-length read should return 0");
}

ZTEST(transport_tests, test_write_null_buffer)
{
    int n = transport_write(NULL, 10);
    zassert_equal(n, 0, "NULL buffer write should return 0");
}

ZTEST(transport_tests, test_write_zero_length)
{
    uint8_t data[] = {0x01};
    int n = transport_write(data, 0);
    zassert_equal(n, 0, "Zero-length write should return 0");
}

/* ========================================================================
 * Flush Test
 * ======================================================================== */

ZTEST(transport_tests, test_flush_clears_rx)
{
    uint8_t inject[] = {0x01, 0x02, 0x03};
    transport_mock_inject_rx(inject, sizeof(inject));

    transport_flush();

    uint8_t buf[16];
    int n = transport_read(buf, sizeof(buf));
    zassert_equal(n, 0, "After flush, read should return 0");
}

/* ========================================================================
 * RX Callback Tests
 * ======================================================================== */

static uint8_t cb_data[64];
static size_t  cb_data_len;
static int     cb_count;

static void test_rx_callback(const uint8_t *data, size_t len, void *user_data)
{
    (void)user_data;
    if (len <= sizeof(cb_data)) {
        memcpy(cb_data, data, len);
        cb_data_len = len;
    }
    cb_count++;
}

ZTEST(transport_tests, test_rx_callback_invoked)
{
    cb_count = 0;
    cb_data_len = 0;

    transport_set_rx_callback(test_rx_callback, NULL);

    uint8_t inject[] = {0xAA, 0x55};
    transport_mock_inject_rx(inject, sizeof(inject));

    zassert_equal(cb_count, 1, "Callback should be invoked once");
    zassert_equal(cb_data_len, 2, "Callback should receive 2 bytes");
    zassert_mem_equal(cb_data, inject, 2);

    transport_set_rx_callback(NULL, NULL);
}

ZTEST(transport_tests, test_rx_callback_null_disables)
{
    cb_count = 0;
    transport_set_rx_callback(test_rx_callback, NULL);
    transport_set_rx_callback(NULL, NULL);

    uint8_t inject[] = {0x01};
    transport_mock_inject_rx(inject, 1);

    zassert_equal(cb_count, 0, "Callback should not be invoked after unregistration");
}

/* ========================================================================
 * Deinit/Reinit Tests
 * ======================================================================== */

ZTEST(transport_tests, test_deinit_and_reinit)
{
    transport_deinit();
    zassert_false(transport_is_ready());

    transport_config_t cfg = TRANSPORT_CONFIG_DEFAULT;
    int ret = transport_init(&cfg);
    zassert_equal(ret, TRANSPORT_OK);
    zassert_true(transport_is_ready());
}

/* ========================================================================
 * Integration: Protocol over Mock Transport
 * ======================================================================== */

ZTEST(transport_tests, test_protocol_roundtrip_over_transport)
{
    /* Encode a protocol packet */
    uint8_t payload[] = {0x42, 0x43};
    uint8_t encoded[PROTOCOL_MAX_PACKET_SIZE];
    size_t enc_len;

    int ret = protocol_encode(CMD_HEARTBEAT, payload, 2, encoded, &enc_len);
    zassert_equal(ret, 0, "Encode should succeed");

    /* Write the encoded packet to transport (simulates device → host) */
    int n = transport_write(encoded, enc_len);
    zassert_equal(n, (int)enc_len, "All bytes should be written");

    /* Capture what was written (simulates host reading) */
    uint8_t captured[PROTOCOL_MAX_PACKET_SIZE];
    size_t cap_len = transport_mock_get_tx(captured, sizeof(captured));
    zassert_equal(cap_len, enc_len, "Captured length should match encoded");

    /* Parse the captured data */
    protocol_parser_t parser;
    protocol_parser_init(&parser);
    bool complete = false;
    for (size_t i = 0; i < cap_len; i++) {
        complete = protocol_parser_feed(&parser, captured[i]);
        if (complete) break;
    }
    zassert_true(complete, "Should parse complete packet from captured data");
    zassert_equal(parser.packet.command, CMD_HEARTBEAT);
    zassert_equal(parser.packet.length, 2);
    zassert_mem_equal(parser.packet.payload, payload, 2);
}

ZTEST(transport_tests, test_inject_protocol_packet_and_read)
{
    /* Encode a packet and inject it (simulates host → device) */
    uint8_t payload[] = {0xAA};
    uint8_t encoded[PROTOCOL_MAX_PACKET_SIZE];
    size_t enc_len;

    protocol_encode(CMD_MOTOR_STOP, payload, 1, encoded, &enc_len);
    transport_mock_inject_rx(encoded, enc_len);

    /* Read from transport and parse */
    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    int n = transport_read(buf, sizeof(buf));
    zassert_equal(n, (int)enc_len, "Should read all injected bytes");

    protocol_parser_t parser;
    protocol_parser_init(&parser);
    bool complete = false;
    for (int i = 0; i < n; i++) {
        complete = protocol_parser_feed(&parser, buf[i]);
        if (complete) break;
    }
    zassert_true(complete, "Should parse injected packet");
    zassert_equal(parser.packet.command, CMD_MOTOR_STOP);
}

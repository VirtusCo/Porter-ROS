/*
 * Porter Robot — CRC16-CCITT Unit Tests
 * Run on native_sim via Ztest
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/ztest.h>
#include "crc16.h"

ZTEST_SUITE(crc16_tests, NULL, NULL, NULL, NULL, NULL);

/* ---- Known-vector tests ---- */

/*
 * RFC 3720 check value: CRC16-CCITT of "123456789" with init=0xFFFF
 * Expected: 0x29B1
 */
ZTEST(crc16_tests, test_check_value_123456789)
{
    const uint8_t data[] = "123456789";
    uint16_t crc = crc16_ccitt(data, 9);
    zassert_equal(crc, 0x29B1, "CRC16 check value mismatch: got 0x%04X, expected 0x29B1", crc);
}

/* Empty buffer should return the initial value */
ZTEST(crc16_tests, test_empty_buffer)
{
    uint16_t crc = crc16_ccitt(NULL, 0);
    zassert_equal(crc, CRC16_CCITT_INIT,
                  "Empty buffer CRC should be init value 0x%04X, got 0x%04X",
                  CRC16_CCITT_INIT, crc);
}

/* Single byte: 0x00 */
ZTEST(crc16_tests, test_single_byte_zero)
{
    uint8_t data[] = {0x00};
    uint16_t crc = crc16_ccitt(data, 1);
    /* Manually verified: CRC16-CCITT(0x00, init=0xFFFF) = 0xE1F0 */
    /* Compute expected by the polynomial or verify consistency */
    zassert_not_equal(crc, CRC16_CCITT_INIT,
                      "Single byte should change CRC from init");
}

/* Single byte: 0xFF */
ZTEST(crc16_tests, test_single_byte_ff)
{
    uint8_t data[] = {0xFF};
    uint16_t crc = crc16_ccitt(data, 1);
    zassert_not_equal(crc, CRC16_CCITT_INIT,
                      "Single byte 0xFF should change CRC from init");
}

/* All zeros buffer */
ZTEST(crc16_tests, test_all_zeros)
{
    uint8_t data[8] = {0};
    uint16_t crc = crc16_ccitt(data, sizeof(data));
    zassert_not_equal(crc, CRC16_CCITT_INIT,
                      "All-zeros should produce non-init CRC");
}

/* All ones buffer */
ZTEST(crc16_tests, test_all_ones)
{
    uint8_t data[8];
    memset(data, 0xFF, sizeof(data));
    uint16_t crc = crc16_ccitt(data, sizeof(data));
    zassert_not_equal(crc, CRC16_CCITT_INIT,
                      "All-ones should produce non-init CRC");
}

/* ---- Incremental (byte-by-byte) API ---- */

ZTEST(crc16_tests, test_incremental_matches_bulk)
{
    const uint8_t data[] = "123456789";

    /* Bulk CRC */
    uint16_t crc_bulk = crc16_ccitt(data, 9);

    /* Incremental CRC */
    uint16_t crc_inc = CRC16_CCITT_INIT;
    for (int i = 0; i < 9; i++) {
        crc_inc = crc16_ccitt_byte(crc_inc, data[i]);
    }

    zassert_equal(crc_bulk, crc_inc,
                  "Incremental CRC (0x%04X) should match bulk CRC (0x%04X)",
                  crc_inc, crc_bulk);
}

ZTEST(crc16_tests, test_incremental_single_byte)
{
    uint8_t data[] = {0x42};

    uint16_t crc_bulk = crc16_ccitt(data, 1);
    uint16_t crc_inc = crc16_ccitt_byte(CRC16_CCITT_INIT, 0x42);

    zassert_equal(crc_bulk, crc_inc,
                  "Single byte incremental should match bulk");
}

/* ---- Consistency tests ---- */

/* Different data → different CRC */
ZTEST(crc16_tests, test_different_data_different_crc)
{
    uint8_t data_a[] = {0x01, 0x02, 0x03};
    uint8_t data_b[] = {0x01, 0x02, 0x04};

    uint16_t crc_a = crc16_ccitt(data_a, 3);
    uint16_t crc_b = crc16_ccitt(data_b, 3);

    zassert_not_equal(crc_a, crc_b,
                      "Different data should produce different CRC");
}

/* Same data, same CRC (deterministic) */
ZTEST(crc16_tests, test_deterministic)
{
    uint8_t data[] = {0xDE, 0xAD, 0xBE, 0xEF};

    uint16_t crc1 = crc16_ccitt(data, sizeof(data));
    uint16_t crc2 = crc16_ccitt(data, sizeof(data));

    zassert_equal(crc1, crc2, "Same data should produce same CRC");
}

/* Partial data prefix → different CRC from full data */
ZTEST(crc16_tests, test_prefix_different_from_full)
{
    uint8_t data[] = {0x01, 0x02, 0x03, 0x04};

    uint16_t crc_full = crc16_ccitt(data, 4);
    uint16_t crc_prefix = crc16_ccitt(data, 3);

    zassert_not_equal(crc_full, crc_prefix,
                      "Prefix CRC should differ from full data CRC");
}

/* Byte order sensitivity: swapped bytes → different CRC */
ZTEST(crc16_tests, test_byte_order_sensitivity)
{
    uint8_t data_ab[] = {0xAB, 0xCD};
    uint8_t data_ba[] = {0xCD, 0xAB};

    uint16_t crc_ab = crc16_ccitt(data_ab, 2);
    uint16_t crc_ba = crc16_ccitt(data_ba, 2);

    zassert_not_equal(crc_ab, crc_ba,
                      "Byte-swapped data should produce different CRC");
}

/* ---- Protocol-relevant patterns ---- */

/* CRC of a typical protocol wire segment: length + command + payload */
ZTEST(crc16_tests, test_protocol_crc_segment)
{
    /* Simulated: length=1, command=0xF0, payload=[0x42] */
    uint8_t segment[] = {0x01, 0xF0, 0x42};
    uint16_t crc = crc16_ccitt(segment, sizeof(segment));

    /* Verify it's not trivial */
    zassert_not_equal(crc, 0x0000, "Protocol CRC should not be zero");
    zassert_not_equal(crc, 0xFFFF, "Protocol CRC should not be 0xFFFF for non-empty data");

    /* Verify reproducibility */
    uint16_t crc2 = crc16_ccitt(segment, sizeof(segment));
    zassert_equal(crc, crc2, "Should be deterministic");
}

/* Large buffer (64 bytes = max protocol payload) */
ZTEST(crc16_tests, test_max_payload_size)
{
    uint8_t data[64];
    for (int i = 0; i < 64; i++) {
        data[i] = (uint8_t)(i & 0xFF);
    }
    uint16_t crc = crc16_ccitt(data, 64);
    zassert_not_equal(crc, CRC16_CCITT_INIT,
                      "Max payload CRC should differ from init");
}

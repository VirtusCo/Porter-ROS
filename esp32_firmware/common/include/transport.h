/*
 * Porter Robot — Transport Abstraction Layer
 * Shared between ESP32 firmware applications
 *
 * Copyright (c) 2026 VirtusCo
 * SPDX-License-Identifier: Apache-2.0
 *
 * Provides a hardware-independent API for host (RPi) communication.
 * Two backends, selected at build time via Kconfig:
 *
 *   CONFIG_PORTER_TRANSPORT_UART    — Hardware UART via external USB-UART bridge
 *                                     (CP2102/CH340) for ESP32-WROOM-32.
 *   CONFIG_PORTER_TRANSPORT_CDC_ACM — USB CDC ACM (native USB) for ESP32-S2/S3.
 *
 * Both backends use Zephyr's UART driver API. The devicetree alias
 * "protocol-uart" determines which physical device is used.
 *
 * The protocol layer (protocol.h) calls transport functions and has
 * no knowledge of the underlying hardware.
 */

#ifndef PORTER_TRANSPORT_H
#define PORTER_TRANSPORT_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- Error Codes --- */
#define TRANSPORT_OK             0
#define TRANSPORT_ERR_INIT      -1   /* Device not ready or init failed */
#define TRANSPORT_ERR_IO        -2   /* Read/write failure */
#define TRANSPORT_ERR_TIMEOUT   -3   /* Initialization timeout (CDC: DTR wait) */
#define TRANSPORT_ERR_NOT_READY -4   /* Transport not initialized or host disconnected */

/* --- Configuration --- */
typedef struct {
    uint32_t baudrate;          /* UART baudrate (UART backend only; ignored for CDC ACM) */
    uint32_t init_timeout_ms;   /* Max wait for ready state (CDC: DTR timeout, UART: unused) */
} transport_config_t;

/* Default configuration values */
#define TRANSPORT_CONFIG_DEFAULT {  \
    .baudrate = 115200,            \
    .init_timeout_ms = 5000        \
}

/* --- RX Callback --- */

/**
 * @brief Receive callback type (interrupt-driven mode)
 *
 * Called from ISR context when data arrives. Keep processing minimal.
 * Feed received bytes into protocol_parser_feed() or copy to a ring buffer.
 *
 * @param data Pointer to received bytes
 * @param len  Number of bytes received
 * @param user_data Opaque pointer passed during registration
 */
typedef void (*transport_rx_cb_t)(const uint8_t *data, size_t len, void *user_data);

/* --- API Functions --- */

/**
 * @brief Initialize the transport layer
 *
 * UART backend: configures baudrate, ready immediately.
 * CDC ACM backend: waits for host DTR signal (up to init_timeout_ms).
 *
 * @param config Configuration (pass NULL for defaults)
 * @return TRANSPORT_OK on success, negative error code on failure
 */
int transport_init(const transport_config_t *config);

/**
 * @brief Check if transport is ready for communication
 *
 * UART backend: always true after successful init.
 * CDC ACM backend: re-checks DTR signal (host may disconnect).
 *
 * @return true if ready to read/write
 */
bool transport_is_ready(void);

/**
 * @brief Read bytes from transport (non-blocking, polling)
 *
 * Reads up to max_len bytes that are currently available.
 * Returns 0 if no data is available (not an error).
 * Use transport_set_rx_callback() for interrupt-driven reception.
 *
 * @param buf     Buffer to store received bytes
 * @param max_len Maximum number of bytes to read
 * @return Number of bytes read (>= 0), or negative error code
 */
int transport_read(uint8_t *buf, size_t max_len);

/**
 * @brief Write bytes to transport (blocking)
 *
 * Blocks until all bytes are transmitted.
 *
 * @param buf Data to transmit
 * @param len Number of bytes to transmit
 * @return Number of bytes written (== len on success), or negative error code
 */
int transport_write(const uint8_t *buf, size_t len);

/**
 * @brief Register RX callback for interrupt-driven reception
 *
 * When a callback is registered, incoming data triggers the callback
 * from ISR context. Polling via transport_read() is still available
 * but may return 0 if the callback consumed the data.
 *
 * Pass NULL to disable the callback and revert to polling mode.
 *
 * @param cb        Callback function, or NULL to disable
 * @param user_data Opaque pointer passed to callback
 * @return TRANSPORT_OK on success
 */
int transport_set_rx_callback(transport_rx_cb_t cb, void *user_data);

/**
 * @brief Flush pending data
 *
 * Discards any unread RX data. Useful after error recovery.
 */
void transport_flush(void);

/**
 * @brief Deinitialize transport, release resources
 *
 * Disables interrupts, clears callbacks, marks transport as not ready.
 */
void transport_deinit(void);

/**
 * @brief Get the name of the active transport backend
 * @return "uart", "cdc_acm", or "mock" depending on build configuration
 */
const char *transport_backend_name(void);

/* --- Mock/Test Helpers (non-Zephyr builds AND Zephyr mock backend) --- */
#if !defined(__ZEPHYR__) || defined(CONFIG_PORTER_TRANSPORT_MOCK)

/**
 * @brief Inject data into the mock RX buffer (simulates host → device)
 * @param data Bytes to inject
 * @param len  Number of bytes
 */
void transport_mock_inject_rx(const uint8_t *data, size_t len);

/**
 * @brief Read data from the mock TX buffer (captures device → host)
 * @param buf     Buffer to store captured TX data
 * @param max_len Maximum bytes to read
 * @return Number of bytes retrieved from TX buffer
 */
size_t transport_mock_get_tx(uint8_t *buf, size_t max_len);

/**
 * @brief Reset all mock state (buffers, ready flag, callback)
 */
void transport_mock_reset(void);

#endif /* !__ZEPHYR__ || CONFIG_PORTER_TRANSPORT_MOCK */

#ifdef __cplusplus
}
#endif

#endif /* PORTER_TRANSPORT_H */

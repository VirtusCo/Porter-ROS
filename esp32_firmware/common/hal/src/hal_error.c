/* Copyright 2026 VirtusCo
 *
 * VHAL Error Reporting — Maps errno values to human-readable strings
 * and provides a fatal error callback mechanism.
 *
 * SPDX-License-Identifier: Proprietary
 */

#include "virtus_hal.h"
#include <errno.h>

/* ========================================================================
 * Error Callback
 * ======================================================================== */

/** Currently registered error callback (NULL if none). */
static virtus_hal_error_cb_t s_error_cb;

/**
 * Register a callback for fatal HAL errors.
 * Pass NULL to unregister.
 */
void virtus_hal_set_error_callback(virtus_hal_error_cb_t cb)
{
    s_error_cb = cb;
}

/**
 * Internal: invoke the error callback if one is registered.
 * Safe to call even if no callback is set.
 */
void virtus_hal_report_error(int err, const char *msg)
{
    if (s_error_cb != NULL) {
        s_error_cb(err, msg);
    }
}

/* ========================================================================
 * Error String Mapping
 * ======================================================================== */

/**
 * Convert an errno-style error code to a human-readable string.
 * Accepts both positive and negative values (absolute value is used).
 */
const char *virtus_hal_error_to_string(int err)
{
    /* Normalise to positive */
    if (err < 0) {
        err = -err;
    }

    switch (err) {
    case 0:
        return "OK";
    case EINVAL:
        return "Invalid argument";
    case ENODEV:
        return "No device / driver not registered";
    case ENOSYS:
        return "Function not implemented";
    case EIO:
        return "I/O error";
    case EBUSY:
        return "Device busy";
    case ETIMEDOUT:
        return "Operation timed out";
    case ENOMEM:
        return "Out of memory";
    case ENOENT:
        return "No such entry";
    case EPERM:
        return "Operation not permitted";
    case EAGAIN:
        return "Resource temporarily unavailable";
    case ERANGE:
        return "Value out of range";
    case ENOTSUP:
        return "Operation not supported";
    default:
        return "Unknown error";
    }
}

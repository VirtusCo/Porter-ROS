"""Scan filter implementations for Porter LIDAR processor.

Each filter operates on numpy arrays of ranges and returns the filtered result.
Filters are composable — they can be chained in any order within the
processing pipeline. All filters preserve the original array length and
angle geometry; only range values are modified.

Copyright 2026 VirtusCo. All rights reserved. Proprietary and confidential.
"""

import math

import numpy as np


def median_filter(ranges: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Apply a sliding-window median filter to range data.

    Replaces each range value with the median of its neighbourhood,
    which is effective at removing salt-and-pepper noise without
    blurring edges as much as a mean filter.

    Args:
        ranges: 1-D array of range values (may contain NaN).
        kernel_size: Width of the sliding window (must be odd, >= 3).

    Returns:
        Filtered copy of ranges.
    """
    if kernel_size < 3:
        kernel_size = 3
    if kernel_size % 2 == 0:
        kernel_size += 1

    n = len(ranges)
    if n == 0:
        return ranges.copy()

    half = kernel_size // 2
    result = ranges.copy()

    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        window = ranges[start:end]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            result[i] = np.median(valid)

    return result


def moving_average_filter(
    ranges: np.ndarray, kernel_size: int = 5
) -> np.ndarray:
    """Apply a sliding-window moving average (smoothing) filter.

    Uses only valid (non-NaN) values in each window for the average.

    Args:
        ranges: 1-D array of range values (may contain NaN).
        kernel_size: Width of the sliding window (must be odd, >= 3).

    Returns:
        Smoothed copy of ranges.
    """
    if kernel_size < 3:
        kernel_size = 3
    if kernel_size % 2 == 0:
        kernel_size += 1

    n = len(ranges)
    if n == 0:
        return ranges.copy()

    half = kernel_size // 2
    result = ranges.copy()

    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        window = ranges[start:end]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            result[i] = np.mean(valid)

    return result


def outlier_rejection_filter(
    ranges: np.ndarray,
    kernel_size: int = 5,
    threshold: float = 1.5,
) -> np.ndarray:
    """Reject outlier range values that differ significantly from neighbours.

    For each point, computes the median of its neighbourhood. If the point's
    range differs from the local median by more than ``threshold`` times the
    local median absolute deviation (MAD), it is replaced with NaN.

    Args:
        ranges: 1-D array of range values (may contain NaN).
        kernel_size: Neighbourhood window width (must be odd, >= 3).
        threshold: Rejection threshold in multiples of local MAD.

    Returns:
        Filtered copy of ranges with outliers set to NaN.
    """
    if kernel_size < 3:
        kernel_size = 3
    if kernel_size % 2 == 0:
        kernel_size += 1

    n = len(ranges)
    if n == 0:
        return ranges.copy()

    half = kernel_size // 2
    result = ranges.copy()

    for i in range(n):
        if np.isnan(ranges[i]):
            continue

        start = max(0, i - half)
        end = min(n, i + half + 1)
        window = ranges[start:end]
        valid = window[~np.isnan(window)]

        if len(valid) < 3:
            continue

        local_median = np.median(valid)
        mad = np.median(np.abs(valid - local_median))

        if mad < 1e-6:
            # Very uniform neighbourhood — only reject extreme outliers
            mad = 0.01

        if abs(ranges[i] - local_median) > threshold * mad:
            result[i] = float('nan')

    return result


def downsample_filter(
    ranges: np.ndarray, factor: int = 2
) -> np.ndarray:
    """Downsample ranges by taking every Nth point.

    Note: this changes the effective angular resolution. The processor node
    must update ``angle_increment`` accordingly in the published message.
    Positions not selected are NOT removed — instead, intermediate values
    are set to NaN to preserve array alignment with the original geometry.

    Args:
        ranges: 1-D array of range values.
        factor: Downsample factor (keep every Nth point).

    Returns:
        Copy of ranges with non-selected indices set to NaN.
    """
    if factor < 2:
        return ranges.copy()

    result = np.full_like(ranges, float('nan'))
    result[::factor] = ranges[::factor]
    return result


def roi_crop_filter(
    ranges: np.ndarray,
    angle_min_rad: float,
    angle_max_rad: float,
    angle_increment_rad: float,
    roi_angle_min_deg: float = -90.0,
    roi_angle_max_deg: float = 90.0,
) -> np.ndarray:
    """Crop scan to a Region of Interest defined by angle bounds.

    Points outside the ROI are set to NaN.

    Args:
        ranges: 1-D array of range values.
        angle_min_rad: Scan's minimum angle in radians.
        angle_max_rad: Scan's maximum angle in radians.
        angle_increment_rad: Angular step between consecutive rays in radians.
        roi_angle_min_deg: ROI lower bound in degrees.
        roi_angle_max_deg: ROI upper bound in degrees.

    Returns:
        Copy of ranges with out-of-ROI indices set to NaN.
    """
    roi_min = math.radians(roi_angle_min_deg)
    roi_max = math.radians(roi_angle_max_deg)

    n = len(ranges)
    if n == 0:
        return ranges.copy()

    result = ranges.copy()

    for i in range(n):
        angle = angle_min_rad + i * angle_increment_rad
        if angle < roi_min or angle > roi_max:
            result[i] = float('nan')

    return result


def range_clamp_filter(
    ranges: np.ndarray,
    min_range: float = 0.05,
    max_range: float = 12.0,
) -> np.ndarray:
    """Clamp ranges to valid bounds, setting out-of-range values to NaN.

    Args:
        ranges: 1-D array of range values.
        min_range: Minimum valid range in metres.
        max_range: Maximum valid range in metres.

    Returns:
        Copy of ranges with clamped values.
    """
    result = ranges.copy()
    mask = (result < min_range) | (result > max_range)
    result[mask] = float('nan')
    return result

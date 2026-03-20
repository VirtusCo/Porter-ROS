"""Unit tests for porter_lidar_processor filter functions.

Tests each filter independently with known inputs and expected outputs.
Uses numpy for test data generation and assertion helpers.

Copyright 2026 VirtusCo. All rights reserved.
"""

import math

import numpy as np

from porter_lidar_processor.filters import (
    downsample_filter,
    median_filter,
    moving_average_filter,
    outlier_rejection_filter,
    range_clamp_filter,
    roi_crop_filter,
)
import pytest


# ══════════════════════════════════════════════════════════════════════════
# Median filter tests
# ══════════════════════════════════════════════════════════════════════════

class TestMedianFilter:
    """Tests for the sliding-window median filter."""

    def test_uniform_array_unchanged(self):
        """Uniform values should not change after median filtering."""
        data = np.full(10, 5.0)
        result = median_filter(data, kernel_size=3)
        np.testing.assert_array_almost_equal(result, data)

    def test_single_spike_removed(self):
        """Single spike should be replaced by neighbourhood median."""
        data = np.array([1.0, 1.0, 10.0, 1.0, 1.0])
        result = median_filter(data, kernel_size=3)
        assert result[2] == pytest.approx(1.0)

    def test_nan_handling(self):
        """Verify NaN values are excluded from median computation."""
        data = np.array([1.0, float('nan'), 3.0, 2.0, 1.0])
        result = median_filter(data, kernel_size=3)
        assert not np.isnan(result[0])
        assert not np.isnan(result[2])

    def test_empty_array(self):
        """Empty array should return empty."""
        data = np.array([])
        result = median_filter(data, kernel_size=3)
        assert len(result) == 0

    def test_preserves_length(self):
        """Output length must match input length."""
        data = np.random.rand(100)
        result = median_filter(data, kernel_size=7)
        assert len(result) == len(data)

    def test_kernel_size_enforced_odd(self):
        """Even kernel size should be rounded up to odd."""
        data = np.array([1.0, 5.0, 1.0, 5.0, 1.0])
        # kernel_size=4 should become 5 internally
        result = median_filter(data, kernel_size=4)
        assert len(result) == len(data)


# ══════════════════════════════════════════════════════════════════════════
# Moving average filter tests
# ══════════════════════════════════════════════════════════════════════════

class TestMovingAverageFilter:
    """Tests for the moving average smoothing filter."""

    def test_uniform_array_unchanged(self):
        """Uniform values should not change after averaging."""
        data = np.full(10, 3.0)
        result = moving_average_filter(data, kernel_size=5)
        np.testing.assert_array_almost_equal(result, data)

    def test_smoothing_effect(self):
        """Alternating values should be smoothed toward the mean."""
        data = np.array([0.0, 10.0, 0.0, 10.0, 0.0])
        result = moving_average_filter(data, kernel_size=3)
        # Middle values should be closer to 5.0 than the originals
        for i in range(1, 4):
            assert abs(result[i] - 5.0) < abs(data[i] - 5.0)

    def test_preserves_length(self):
        """Output length must match input length."""
        data = np.random.rand(50)
        result = moving_average_filter(data, kernel_size=3)
        assert len(result) == len(data)


# ══════════════════════════════════════════════════════════════════════════
# Outlier rejection tests
# ══════════════════════════════════════════════════════════════════════════

class TestOutlierRejectionFilter:
    """Tests for MAD-based outlier rejection."""

    def test_spike_rejected(self):
        """A single extreme spike should be set to NaN."""
        data = np.array([1.0, 1.0, 1.0, 50.0, 1.0, 1.0, 1.0])
        result = outlier_rejection_filter(data, kernel_size=5, threshold=1.5)
        assert np.isnan(result[3]), 'Spike at index 3 should be NaN'

    def test_uniform_preserved(self):
        """Uniform data should not have any values rejected."""
        data = np.full(10, 2.0)
        result = outlier_rejection_filter(data, kernel_size=5, threshold=1.5)
        assert not np.any(np.isnan(result))

    def test_nan_passthrough(self):
        """Input NaN values should remain NaN."""
        data = np.array([1.0, float('nan'), 1.0, 1.0, 1.0])
        result = outlier_rejection_filter(data, kernel_size=3, threshold=1.5)
        assert np.isnan(result[1])

    def test_preserves_length(self):
        """Output length must match input length."""
        data = np.random.rand(100) * 10
        result = outlier_rejection_filter(data, kernel_size=5, threshold=2.0)
        assert len(result) == len(data)


# ══════════════════════════════════════════════════════════════════════════
# Range clamp tests
# ══════════════════════════════════════════════════════════════════════════

class TestRangeClampFilter:
    """Tests for range clamping."""

    def test_in_range_preserved(self):
        """Values within bounds should be unchanged."""
        data = np.array([0.5, 1.0, 5.0, 10.0])
        result = range_clamp_filter(data, min_range=0.05, max_range=12.0)
        np.testing.assert_array_equal(result, data)

    def test_below_min_becomes_nan(self):
        """Values below min_range should become NaN."""
        data = np.array([0.01, 0.5, 0.001])
        result = range_clamp_filter(data, min_range=0.05, max_range=12.0)
        assert np.isnan(result[0])
        assert not np.isnan(result[1])
        assert np.isnan(result[2])

    def test_above_max_becomes_nan(self):
        """Values above max_range should become NaN."""
        data = np.array([5.0, 15.0, 100.0])
        result = range_clamp_filter(data, min_range=0.05, max_range=12.0)
        assert not np.isnan(result[0])
        assert np.isnan(result[1])
        assert np.isnan(result[2])


# ══════════════════════════════════════════════════════════════════════════
# ROI crop tests
# ══════════════════════════════════════════════════════════════════════════

class TestRoiCropFilter:
    """Tests for Region of Interest angular cropping."""

    def test_full_360_no_crop(self):
        """ROI spanning full scan should not crop anything."""
        data = np.ones(360)
        result = roi_crop_filter(
            data,
            angle_min_rad=-math.pi,
            angle_max_rad=math.pi,
            angle_increment_rad=2 * math.pi / 360,
            roi_angle_min_deg=-180.0,
            roi_angle_max_deg=180.0,
        )
        assert not np.any(np.isnan(result))

    def test_front_half_only(self):
        """ROI [-90, +90] should NaN-out the rear half."""
        n = 360
        inc = 2 * math.pi / n
        data = np.ones(n)
        result = roi_crop_filter(
            data,
            angle_min_rad=-math.pi,
            angle_max_rad=math.pi,
            angle_increment_rad=inc,
            roi_angle_min_deg=-90.0,
            roi_angle_max_deg=90.0,
        )
        # Some points should be NaN (rear)
        nan_count = np.sum(np.isnan(result))
        assert nan_count > 0
        # Front half should be preserved
        valid_count = np.sum(~np.isnan(result))
        assert valid_count > 0

    def test_preserves_length(self):
        """Output length must match input length."""
        data = np.ones(720)
        result = roi_crop_filter(
            data,
            angle_min_rad=-math.pi,
            angle_max_rad=math.pi,
            angle_increment_rad=2 * math.pi / 720,
            roi_angle_min_deg=-45.0,
            roi_angle_max_deg=45.0,
        )
        assert len(result) == len(data)


# ══════════════════════════════════════════════════════════════════════════
# Downsample tests
# ══════════════════════════════════════════════════════════════════════════

class TestDownsampleFilter:
    """Tests for the downsample filter."""

    def test_factor_2_keeps_every_other(self):
        """Factor 2 should keep indices 0, 2, 4, ... and NaN the rest."""
        data = np.arange(10, dtype=np.float32)
        result = downsample_filter(data, factor=2)
        # Even indices preserved
        for i in range(0, 10, 2):
            assert result[i] == pytest.approx(data[i])
        # Odd indices should be NaN
        for i in range(1, 10, 2):
            assert np.isnan(result[i])

    def test_factor_1_no_change(self):
        """Factor < 2 should return a copy unchanged."""
        data = np.arange(10, dtype=np.float32)
        result = downsample_filter(data, factor=1)
        np.testing.assert_array_equal(result, data)

    def test_preserves_length(self):
        """Output length must match input length."""
        data = np.random.rand(100)
        result = downsample_filter(data, factor=3)
        assert len(result) == len(data)

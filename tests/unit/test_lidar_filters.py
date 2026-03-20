"""Unit tests for porter_lidar_processor filter pipeline.

Tests the 6-stage LIDAR scan processing pipeline:
1. Range clamp (min/max)
2. Outlier rejection (isolated spikes)
3. Median filter (smoothing)
4. Exponential smoothing
5. ROI crop (angle range)
6. Downsampling

Can run WITHOUT ROS 2 — pure Python filter implementations.
"""

import pytest
import math


# ──────────────────────────────────────────────────────────────
# Filter implementations (mirrors porter_lidar_processor logic)
# ──────────────────────────────────────────────────────────────

def range_clamp(ranges, min_range=0.15, max_range=12.0):
    """Clamp range values to [min_range, max_range], set outliers to NaN.

    Args:
        ranges: List of float range values in meters.
        min_range: Minimum valid range (default 0.15m for YDLIDAR X4).
        max_range: Maximum valid range (default 12.0m).

    Returns:
        List with out-of-range values replaced by NaN.
    """
    result = []
    for r in ranges:
        if math.isnan(r) or math.isinf(r) or r < min_range or r > max_range:
            result.append(float('nan'))
        else:
            result.append(r)
    return result


def outlier_rejection(ranges, threshold=1.5, window=3):
    """Reject isolated spike outliers using neighbor comparison.

    A point is an outlier if it differs from the median of its neighbors
    by more than threshold meters.

    Args:
        ranges: List of float range values.
        threshold: Maximum allowed deviation from neighbor median.
        window: Number of neighbors on each side to consider.

    Returns:
        List with outlier values replaced by NaN.
    """
    n = len(ranges)
    if n < 2 * window + 1:
        return list(ranges)

    result = list(ranges)
    for i in range(window, n - window):
        if math.isnan(ranges[i]):
            continue

        neighbors = []
        for j in range(i - window, i + window + 1):
            if j != i and not math.isnan(ranges[j]):
                neighbors.append(ranges[j])

        if not neighbors:
            continue

        neighbors.sort()
        median = neighbors[len(neighbors) // 2]
        if abs(ranges[i] - median) > threshold:
            result[i] = float('nan')

    return result


def median_filter(ranges, kernel_size=3):
    """Apply median filter to smooth noisy scans.

    Args:
        ranges: List of float range values.
        kernel_size: Odd number, size of median window.

    Returns:
        Median-filtered range values.
    """
    n = len(ranges)
    half = kernel_size // 2
    result = list(ranges)

    for i in range(half, n - half):
        window = []
        for j in range(i - half, i + half + 1):
            if not math.isnan(ranges[j]):
                window.append(ranges[j])

        if window:
            window.sort()
            result[i] = window[len(window) // 2]
        else:
            result[i] = float('nan')

    return result


def exponential_smoothing(ranges, alpha=0.3, prev_ranges=None):
    """Apply exponential smoothing (low-pass filter).

    x_t = alpha * measurement + (1 - alpha) * x_{t-1}

    Args:
        ranges: Current scan range values.
        alpha: Smoothing factor (0 < alpha <= 1). Higher = more responsive.
        prev_ranges: Previous smoothed values (None = first scan).

    Returns:
        Smoothed range values.
    """
    if prev_ranges is None:
        return list(ranges)

    result = []
    for curr, prev in zip(ranges, prev_ranges):
        if math.isnan(curr):
            result.append(prev)
        elif math.isnan(prev):
            result.append(curr)
        else:
            result.append(alpha * curr + (1.0 - alpha) * prev)

    return result


def roi_crop(ranges, angles, min_angle=-math.pi, max_angle=math.pi):
    """Crop scan to region of interest by angle.

    Args:
        ranges: List of range values.
        angles: List of corresponding angles in radians.
        min_angle: Minimum angle to keep.
        max_angle: Maximum angle to keep.

    Returns:
        Tuple of (cropped_ranges, cropped_angles).
    """
    cropped_ranges = []
    cropped_angles = []
    for r, a in zip(ranges, angles):
        if min_angle <= a <= max_angle:
            cropped_ranges.append(r)
            cropped_angles.append(a)
    return cropped_ranges, cropped_angles


def downsample(ranges, factor=2):
    """Reduce scan point count by taking every Nth point.

    Args:
        ranges: List of range values.
        factor: Take every `factor`-th point.

    Returns:
        Downsampled range list.
    """
    return ranges[::factor]


# ──────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────

class TestRangeClamp:
    """Tests for range clamping filter."""

    def test_values_within_range_unchanged(self):
        """Values within [min, max] are not modified."""
        ranges = [0.5, 1.0, 5.0, 10.0]
        result = range_clamp(ranges)
        assert result == ranges

    def test_below_min_set_to_nan(self):
        """Values below min_range become NaN."""
        ranges = [0.01, 0.05, 0.14, 0.5]
        result = range_clamp(ranges, min_range=0.15)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert math.isnan(result[2])
        assert result[3] == 0.5

    def test_above_max_set_to_nan(self):
        """Values above max_range become NaN."""
        ranges = [1.0, 12.5, 20.0, 100.0]
        result = range_clamp(ranges, max_range=12.0)
        assert result[0] == 1.0
        assert math.isnan(result[1])
        assert math.isnan(result[2])
        assert math.isnan(result[3])

    def test_nan_values_stay_nan(self):
        """NaN input values remain NaN."""
        ranges = [1.0, float('nan'), 5.0]
        result = range_clamp(ranges)
        assert result[0] == 1.0
        assert math.isnan(result[1])
        assert result[2] == 5.0

    def test_inf_values_become_nan(self):
        """Infinity values become NaN."""
        ranges = [float('inf'), float('-inf'), 5.0]
        result = range_clamp(ranges)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert result[2] == 5.0

    def test_empty_scan(self):
        """Empty scan returns empty list without error."""
        assert range_clamp([]) == []

    def test_boundary_values_included(self):
        """Exact min and max values are kept (inclusive)."""
        ranges = [0.15, 12.0]
        result = range_clamp(ranges, min_range=0.15, max_range=12.0)
        assert result[0] == 0.15
        assert result[1] == 12.0

    def test_custom_range_limits(self):
        """Custom min/max range values work correctly."""
        ranges = [0.5, 1.0, 3.0, 5.0]
        result = range_clamp(ranges, min_range=0.8, max_range=4.0)
        assert math.isnan(result[0])
        assert result[1] == 1.0
        assert result[2] == 3.0
        assert math.isnan(result[3])


class TestOutlierRejection:
    """Tests for isolated spike outlier rejection."""

    def test_smooth_scan_unchanged(self):
        """Smooth scan with no outliers passes through unchanged."""
        ranges = [1.0, 1.1, 1.0, 0.9, 1.0, 1.1, 1.0]
        result = outlier_rejection(ranges, threshold=1.5, window=2)
        # Interior points should be unchanged
        for i in range(2, 5):
            assert result[i] == ranges[i]

    def test_spike_removed(self):
        """Isolated spike is replaced with NaN."""
        ranges = [1.0, 1.0, 1.0, 10.0, 1.0, 1.0, 1.0]
        result = outlier_rejection(ranges, threshold=1.5, window=2)
        assert math.isnan(result[3]), "Spike at index 3 should be NaN"
        assert result[2] == 1.0
        assert result[4] == 1.0

    def test_nan_values_preserved(self):
        """Existing NaN values are preserved."""
        ranges = [1.0, 1.0, float('nan'), 1.0, 1.0, 1.0, 1.0]
        result = outlier_rejection(ranges, threshold=1.5, window=2)
        assert math.isnan(result[2])

    def test_short_scan_unchanged(self):
        """Scans shorter than 2*window+1 are returned unchanged."""
        ranges = [1.0, 10.0, 1.0]
        result = outlier_rejection(ranges, threshold=1.5, window=3)
        assert result == ranges

    def test_threshold_sensitivity(self):
        """Lower threshold catches smaller spikes."""
        ranges = [1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 1.0]
        # threshold=0.5 should catch the 2.0 spike
        result_strict = outlier_rejection(ranges, threshold=0.5, window=2)
        assert math.isnan(result_strict[3])
        # threshold=2.0 should NOT catch it
        result_lenient = outlier_rejection(ranges, threshold=2.0, window=2)
        assert result_lenient[3] == 2.0


class TestMedianFilter:
    """Tests for median filter smoothing."""

    def test_constant_scan_unchanged(self):
        """Constant values pass through median filter unchanged."""
        ranges = [5.0] * 10
        result = median_filter(ranges, kernel_size=3)
        for r in result:
            assert r == 5.0

    def test_noise_smoothed(self):
        """Noisy scan is smoothed by median filter."""
        # Alternating 1.0 and 3.0
        ranges = [1.0, 3.0, 1.0, 3.0, 1.0, 3.0, 1.0]
        result = median_filter(ranges, kernel_size=3)
        # Median of [1,3,1] = 1, median of [3,1,3] = 3, etc.
        # Interior points should be the median
        for i in range(1, 6):
            assert result[i] in [1.0, 3.0]

    def test_single_spike_removed(self):
        """Median filter removes isolated single-point spikes."""
        ranges = [1.0, 1.0, 1.0, 10.0, 1.0, 1.0, 1.0]
        result = median_filter(ranges, kernel_size=3)
        # Median of [1.0, 10.0, 1.0] = 1.0
        assert result[3] == 1.0

    def test_nan_handling(self):
        """Median filter handles NaN values by excluding them."""
        ranges = [1.0, float('nan'), 3.0, 2.0, 1.0]
        result = median_filter(ranges, kernel_size=3)
        # Position 2: window = [nan, 3.0, 2.0] -> valid = [3.0, 2.0] -> median = 2.0
        assert not math.isnan(result[2])

    def test_all_nan_window(self):
        """All-NaN window produces NaN output."""
        ranges = [float('nan'), float('nan'), float('nan'), 1.0, 1.0]
        result = median_filter(ranges, kernel_size=3)
        assert math.isnan(result[1])

    def test_preserves_length(self):
        """Output length matches input length."""
        ranges = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = median_filter(ranges, kernel_size=3)
        assert len(result) == len(ranges)


class TestExponentialSmoothing:
    """Tests for exponential smoothing (low-pass filter)."""

    def test_first_scan_passthrough(self):
        """First scan (no previous) passes through unchanged."""
        ranges = [1.0, 2.0, 3.0]
        result = exponential_smoothing(ranges, alpha=0.3, prev_ranges=None)
        assert result == ranges

    def test_smoothing_blends_current_and_previous(self):
        """Result is weighted blend of current and previous."""
        prev = [10.0]
        curr = [20.0]
        alpha = 0.3
        result = exponential_smoothing(curr, alpha=alpha, prev_ranges=prev)
        expected = alpha * 20.0 + (1 - alpha) * 10.0  # 13.0
        assert result[0] == pytest.approx(expected)

    def test_alpha_1_tracks_immediately(self):
        """Alpha=1.0 means output equals current measurement."""
        prev = [10.0, 20.0, 30.0]
        curr = [100.0, 200.0, 300.0]
        result = exponential_smoothing(curr, alpha=1.0, prev_ranges=prev)
        assert result == curr

    def test_alpha_0_ignores_new_measurement(self):
        """Alpha=0.0 means output equals previous value (ignores new data)."""
        prev = [10.0, 20.0, 30.0]
        curr = [100.0, 200.0, 300.0]
        result = exponential_smoothing(curr, alpha=0.0, prev_ranges=prev)
        assert result == prev

    def test_nan_current_uses_previous(self):
        """NaN current value falls back to previous value."""
        prev = [10.0]
        curr = [float('nan')]
        result = exponential_smoothing(curr, alpha=0.3, prev_ranges=prev)
        assert result[0] == 10.0

    def test_nan_previous_uses_current(self):
        """NaN previous value uses current value directly."""
        prev = [float('nan')]
        curr = [10.0]
        result = exponential_smoothing(curr, alpha=0.3, prev_ranges=prev)
        assert result[0] == 10.0


class TestROICrop:
    """Tests for region of interest cropping."""

    def test_full_range_keeps_all(self):
        """Full angle range keeps all points."""
        ranges = [1.0, 2.0, 3.0]
        angles = [-math.pi, 0.0, math.pi]
        r, a = roi_crop(ranges, angles)
        assert len(r) == 3

    def test_front_only_crop(self):
        """Crop to front-facing sector only."""
        ranges = [1.0, 2.0, 3.0, 4.0, 5.0]
        angles = [-math.pi, -math.pi / 4, 0.0, math.pi / 4, math.pi]
        r, a = roi_crop(ranges, angles, min_angle=-math.pi / 2, max_angle=math.pi / 2)
        assert len(r) == 3
        assert r == [2.0, 3.0, 4.0]

    def test_empty_roi(self):
        """No points in angle range returns empty lists."""
        ranges = [1.0, 2.0, 3.0]
        angles = [-0.1, 0.0, 0.1]
        r, a = roi_crop(ranges, angles, min_angle=1.0, max_angle=2.0)
        assert len(r) == 0
        assert len(a) == 0

    def test_boundary_angles_included(self):
        """Exact boundary angles are included (inclusive)."""
        ranges = [1.0, 2.0, 3.0]
        angles = [-0.5, 0.0, 0.5]
        r, a = roi_crop(ranges, angles, min_angle=-0.5, max_angle=0.5)
        assert len(r) == 3

    def test_empty_input(self):
        """Empty input returns empty output."""
        r, a = roi_crop([], [])
        assert r == []
        assert a == []


class TestDownsample:
    """Tests for scan downsampling."""

    def test_factor_2_halves_count(self):
        """Downsample by 2 takes every other point."""
        ranges = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        result = downsample(ranges, factor=2)
        assert result == [1.0, 3.0, 5.0]

    def test_factor_3_takes_every_third(self):
        """Downsample by 3 takes every third point."""
        ranges = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
        result = downsample(ranges, factor=3)
        assert result == [1.0, 4.0, 7.0]

    def test_factor_1_unchanged(self):
        """Factor of 1 returns the same list."""
        ranges = [1.0, 2.0, 3.0]
        result = downsample(ranges, factor=1)
        assert result == ranges

    def test_empty_input(self):
        """Empty input returns empty output."""
        assert downsample([], factor=2) == []

    def test_single_element(self):
        """Single element scan returns that element."""
        assert downsample([5.0], factor=2) == [5.0]

    def test_factor_larger_than_input(self):
        """Factor larger than input length returns first element only."""
        ranges = [1.0, 2.0, 3.0]
        result = downsample(ranges, factor=10)
        assert result == [1.0]

    def test_output_length_correct(self):
        """Output length is ceil(n/factor)."""
        ranges = list(range(100))
        result = downsample(ranges, factor=4)
        assert len(result) == 25

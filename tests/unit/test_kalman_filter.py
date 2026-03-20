"""Unit tests for the 1D Kalman filter used in sensor fusion.

Tests convergence, noise handling, outlier rejection, and ramp tracking.
Mirrors the Kalman filter in esp32_firmware/sensor_fusion.

Can run WITHOUT ROS 2 or ESP32 hardware — pure Python math.
"""

import pytest
import math
import random


class KalmanFilter1D:
    """1D Kalman filter matching esp32_firmware/sensor_fusion implementation.

    State model:
        x_k = x_{k-1} + w_k      (random walk process model)
        z_k = x_k + v_k           (direct measurement)
        w_k ~ N(0, q), v_k ~ N(0, r)

    Args:
        q: Process noise covariance.
        r: Measurement noise covariance.
    """

    def __init__(self, q: float = 0.1, r: float = 1.0):
        self.x = 0.0   # state estimate
        self.p = 1.0   # estimate covariance
        self.q = q      # process noise
        self.r = r      # measurement noise

    def update(self, measurement: float) -> float:
        """Incorporate a new measurement and return updated estimate.

        Args:
            measurement: New sensor reading.

        Returns:
            Updated state estimate.
        """
        # Predict step
        self.p += self.q

        # Update step
        k = self.p / (self.p + self.r)  # Kalman gain
        self.x += k * (measurement - self.x)
        self.p *= (1.0 - k)

        return self.x

    @property
    def gain(self) -> float:
        """Current Kalman gain (how much we trust new measurements)."""
        return self.p / (self.p + self.r)

    def reset(self, x: float = 0.0, p: float = 1.0):
        """Reset filter state."""
        self.x = x
        self.p = p


class TestKalmanConvergence:
    """Tests that the filter converges to the true value."""

    def test_converges_to_constant_with_zero_noise(self):
        """Filter estimate converges to true value with perfect measurements."""
        kf = KalmanFilter1D(q=0.01, r=0.1)
        true_value = 42.0

        for _ in range(100):
            estimate = kf.update(true_value)

        assert estimate == pytest.approx(true_value, abs=0.01)

    def test_converges_from_different_initial(self):
        """Filter converges regardless of initial estimate distance."""
        kf = KalmanFilter1D(q=0.01, r=0.1)
        kf.x = 1000.0  # start far from true value
        true_value = 50.0

        for _ in range(200):
            estimate = kf.update(true_value)

        assert estimate == pytest.approx(true_value, abs=0.1)

    def test_covariance_decreases_with_constant_input(self):
        """Estimate covariance decreases as more measurements arrive."""
        kf = KalmanFilter1D(q=0.01, r=1.0)
        initial_p = kf.p

        for _ in range(50):
            kf.update(100.0)

        assert kf.p < initial_p

    def test_covariance_reaches_steady_state(self):
        """Covariance reaches a steady state (not zero, due to process noise)."""
        kf = KalmanFilter1D(q=0.1, r=1.0)

        covariances = []
        for _ in range(500):
            kf.update(100.0)
            covariances.append(kf.p)

        # Last 10 covariances should be nearly identical (steady state)
        last_10 = covariances[-10:]
        spread = max(last_10) - min(last_10)
        assert spread < 0.001

        # Steady-state covariance should be positive (not zero)
        assert covariances[-1] > 0.0


class TestKalmanNoiseHandling:
    """Tests filter behavior with noisy measurements."""

    def test_estimate_within_3_sigma_of_true_value(self):
        """With noisy measurements, estimate stays within 3 sigma of truth."""
        random.seed(42)  # reproducible
        kf = KalmanFilter1D(q=0.1, r=4.0)
        true_value = 100.0
        noise_std = 2.0  # sqrt(r)

        for _ in range(200):
            noise = random.gauss(0, noise_std)
            kf.update(true_value + noise)

        error = abs(kf.x - true_value)
        # 3*sigma bound: with well-tuned filter, should be within 3*sqrt(P)
        bound = 3.0 * math.sqrt(kf.p) + 3.0 * noise_std * 0.1  # generous bound
        assert error < bound, (
            f"Estimate {kf.x:.2f} too far from truth {true_value:.2f} "
            f"(error={error:.2f}, bound={bound:.2f})"
        )

    def test_smoother_than_raw_measurements(self):
        """Filtered output has lower variance than raw measurements."""
        random.seed(123)
        kf = KalmanFilter1D(q=0.1, r=4.0)
        true_value = 50.0
        noise_std = 2.0

        raw = []
        filtered = []
        for _ in range(500):
            measurement = true_value + random.gauss(0, noise_std)
            raw.append(measurement)
            filtered.append(kf.update(measurement))

        # Skip first 50 samples (transient)
        raw_var = _variance(raw[50:])
        filtered_var = _variance(filtered[50:])

        assert filtered_var < raw_var, (
            f"Filtered variance ({filtered_var:.4f}) should be less than "
            f"raw variance ({raw_var:.4f})"
        )

    def test_high_measurement_noise_slow_tracking(self):
        """High measurement noise (large r) makes filter respond slowly."""
        kf_fast = KalmanFilter1D(q=0.1, r=0.1)   # trusts measurements
        kf_slow = KalmanFilter1D(q=0.1, r=100.0)  # distrusts measurements

        # Apply a step input
        for _ in range(10):
            kf_fast.update(100.0)
            kf_slow.update(100.0)

        # Fast filter should be closer to 100 after 10 samples
        assert abs(kf_fast.x - 100.0) < abs(kf_slow.x - 100.0)

    def test_high_process_noise_fast_tracking(self):
        """High process noise (large q) makes filter track faster."""
        kf_fast = KalmanFilter1D(q=10.0, r=1.0)   # high process noise
        kf_slow = KalmanFilter1D(q=0.001, r=1.0)   # low process noise

        # Apply a step input
        for _ in range(5):
            kf_fast.update(100.0)
            kf_slow.update(100.0)

        assert abs(kf_fast.x - 100.0) < abs(kf_slow.x - 100.0)


class TestKalmanOutlierRejection:
    """Tests that outliers don't catastrophically shift the estimate."""

    def test_single_spike_minimal_impact(self):
        """A single large outlier doesn't shift the estimate much relative to its size."""
        kf = KalmanFilter1D(q=0.01, r=1.0)
        true_value = 100.0

        # Converge to true value
        for _ in range(100):
            kf.update(true_value)
        estimate_before = kf.x

        # Inject one massive outlier
        outlier = 10000.0
        kf.update(outlier)
        estimate_after = kf.x

        # The shift should be much less than the full outlier deviation.
        # With q=0.01 and r=1.0, steady-state gain ≈ 0.095, so shift ≈ 941.
        # Key assertion: shift is <15% of the outlier deviation (9900).
        shift = abs(estimate_after - estimate_before)
        outlier_deviation = abs(outlier - estimate_before)
        shift_ratio = shift / outlier_deviation

        assert shift_ratio < 0.15, (
            f"Single outlier shifted estimate by {shift:.2f} "
            f"({shift_ratio:.1%} of deviation {outlier_deviation:.0f}). "
            f"Expected <15% shift for a converged filter."
        )

    def test_recovers_after_outlier(self):
        """Filter recovers to true value after outlier passes."""
        kf = KalmanFilter1D(q=0.01, r=1.0)
        true_value = 100.0

        # Converge
        for _ in range(100):
            kf.update(true_value)

        # Inject outlier
        kf.update(500.0)

        # Recovery: feed true value again
        for _ in range(50):
            kf.update(true_value)

        assert kf.x == pytest.approx(true_value, abs=1.0)

    def test_multiple_consecutive_outliers_shift_estimate(self):
        """Multiple consecutive outliers DO shift the estimate (they're real)."""
        kf = KalmanFilter1D(q=0.1, r=1.0)

        # Converge to 100
        for _ in range(100):
            kf.update(100.0)

        # 50 consecutive "outliers" at 200 — this is actually a step change
        for _ in range(50):
            kf.update(200.0)

        # Filter should have tracked towards 200
        assert kf.x > 150.0, "Filter should track persistent signal changes"


class TestKalmanRampTracking:
    """Tests filter tracking of linearly increasing input."""

    def test_tracks_ramp_with_lag(self):
        """Filter tracks a ramp input with some lag."""
        kf = KalmanFilter1D(q=1.0, r=0.1)

        final_value = 0.0
        for i in range(100):
            true_value = float(i)
            final_value = kf.update(true_value)

        # Should be close to 99 but with some lag
        assert final_value > 90.0
        assert final_value <= 99.5

    def test_higher_process_noise_reduces_ramp_lag(self):
        """Higher process noise reduces tracking lag on ramp input."""
        kf_high_q = KalmanFilter1D(q=10.0, r=0.1)
        kf_low_q = KalmanFilter1D(q=0.01, r=0.1)

        for i in range(100):
            true_value = float(i)
            kf_high_q.update(true_value)
            kf_low_q.update(true_value)

        # Higher q filter should be closer to final ramp value
        lag_high_q = abs(kf_high_q.x - 99.0)
        lag_low_q = abs(kf_low_q.x - 99.0)
        assert lag_high_q < lag_low_q


class TestKalmanGain:
    """Tests for Kalman gain behavior."""

    def test_initial_gain_is_high(self):
        """Initial Kalman gain is high (uncertain estimate, trust measurements)."""
        kf = KalmanFilter1D(q=0.1, r=1.0)
        # Initial: p=1.0, r=1.0, gain = 1/(1+1) = 0.5
        assert kf.gain == pytest.approx(0.5, abs=0.01)

    def test_gain_decreases_over_time(self):
        """Kalman gain decreases as filter becomes more confident."""
        kf = KalmanFilter1D(q=0.01, r=1.0)
        initial_gain = kf.gain

        for _ in range(50):
            kf.update(100.0)

        assert kf.gain < initial_gain

    def test_gain_bounded_between_0_and_1(self):
        """Kalman gain always stays between 0 and 1."""
        kf = KalmanFilter1D(q=0.1, r=1.0)

        for i in range(1000):
            kf.update(float(i))
            assert 0.0 <= kf.gain <= 1.0


class TestKalmanReset:
    """Tests for filter reset functionality."""

    def test_reset_restores_defaults(self):
        """Reset restores initial state."""
        kf = KalmanFilter1D(q=0.1, r=1.0)

        for _ in range(100):
            kf.update(42.0)

        kf.reset()
        assert kf.x == 0.0
        assert kf.p == 1.0

    def test_reset_with_custom_values(self):
        """Reset with custom initial estimate and covariance."""
        kf = KalmanFilter1D()
        kf.reset(x=50.0, p=0.5)
        assert kf.x == 50.0
        assert kf.p == 0.5


class TestKalmanEdgeCases:
    """Edge case tests."""

    def test_zero_process_noise(self):
        """Zero process noise: filter converges and stops updating."""
        kf = KalmanFilter1D(q=0.0, r=1.0)

        # After many updates, covariance approaches zero
        for _ in range(1000):
            kf.update(100.0)

        # Gain should be very small
        assert kf.gain < 0.01

    def test_very_small_measurement_noise(self):
        """Very small r means filter trusts measurements almost completely."""
        kf = KalmanFilter1D(q=0.1, r=0.001)

        kf.update(42.0)
        # Should be very close to measurement after single update
        assert kf.x == pytest.approx(42.0, abs=0.5)

    def test_negative_measurement(self):
        """Filter handles negative measurements correctly."""
        kf = KalmanFilter1D(q=0.1, r=1.0)

        for _ in range(100):
            kf.update(-50.0)

        assert kf.x == pytest.approx(-50.0, abs=0.5)

    def test_alternating_measurements(self):
        """Filter averages alternating measurements."""
        kf = KalmanFilter1D(q=0.01, r=1.0)

        for _ in range(500):
            kf.update(90.0)
            kf.update(110.0)

        # Should converge near the average (100)
        assert kf.x == pytest.approx(100.0, abs=2.0)


# ──────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────

def _variance(data):
    """Calculate population variance."""
    n = len(data)
    if n < 2:
        return 0.0
    mean = sum(data) / n
    return sum((x - mean) ** 2 for x in data) / n

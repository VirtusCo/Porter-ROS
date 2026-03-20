// Copyright 2026 VirtusCo. All rights reserved.
// Proprietary and confidential.
//
// Pure filter functions for LIDAR scan processing.
// No ROS dependency — all functions operate on std::vector<float> and are
// independently testable via GTest. Each filter preserves array length and
// angle geometry; only range values are modified.

#pragma once

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <vector>

namespace porter_lidar_processor
{

/// Filter 1: Clamp ranges outside [min_range, max_range] to NaN.
/// Values that are already NaN are preserved as NaN.
std::vector<float> range_clamp(
  const std::vector<float> & ranges,
  float min_range,
  float max_range);

/// Filter 2: MAD-based outlier rejection (Median Absolute Deviation).
/// Computes the global median and MAD, then marks values whose deviation
/// from the median exceeds threshold * MAD as NaN. NaN inputs are skipped.
std::vector<float> outlier_rejection(
  const std::vector<float> & ranges,
  float threshold = 3.0f);

/// Filter 3: Sliding-window median filter with configurable window size.
/// Applies a centred sliding window, computing the median of valid (non-NaN)
/// values within each window. If all values in a window are NaN, the output
/// at that index is NaN. Window size is forced odd (rounded up if even).
std::vector<float> median_filter(
  const std::vector<float> & ranges,
  int window_size = 5);

/// Filter 4: Exponential moving average smoothing.
/// result[i] = alpha * ranges[i] + (1 - alpha) * previous[i]
/// If previous is empty or size-mismatched, ranges is returned unchanged.
/// NaN values in either array propagate to the output.
/// alpha is clamped to [0, 1]: 0 = no change (keep previous), 1 = instant.
std::vector<float> exponential_smoothing(
  const std::vector<float> & ranges,
  const std::vector<float> & previous,
  float alpha = 0.3f);

/// Filter 5: ROI (Region of Interest) angular crop.
/// Sets ranges outside [roi_angle_min, roi_angle_max] to NaN.
/// Angles are computed as: angle = scan_angle_min + index * scan_angle_increment.
/// All angles are in radians.
std::vector<float> roi_crop(
  const std::vector<float> & ranges,
  float scan_angle_min,
  float scan_angle_increment,
  float roi_angle_min,
  float roi_angle_max);

/// Filter 6: Downsample by factor N — keep every Nth point, set others to NaN.
/// Factor <= 1 returns an unchanged copy. Preserves array length and geometry.
std::vector<float> downsample(
  const std::vector<float> & ranges,
  int factor);

/// Utility: count valid (non-NaN) values in the array.
size_t count_valid(const std::vector<float> & ranges);

/// Scan statistics computed from a range array.
struct ScanStats
{
  size_t total;         ///< Total number of range values
  size_t valid;         ///< Number of non-NaN values
  float min_range;      ///< Minimum valid range (NaN if no valid values)
  float max_range;      ///< Maximum valid range (NaN if no valid values)
  float mean_range;     ///< Mean of valid ranges (NaN if no valid values)
  float invalid_ratio;  ///< Fraction of NaN values (0.0 if empty)
};

/// Utility: compute statistics over a range array.
ScanStats compute_stats(const std::vector<float> & ranges);

}  // namespace porter_lidar_processor

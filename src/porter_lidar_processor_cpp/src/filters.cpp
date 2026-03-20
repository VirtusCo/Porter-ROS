// Copyright 2026 VirtusCo. All rights reserved.
// Proprietary and confidential.
//
// Implementation of the 6-stage LIDAR scan filter pipeline.
// All functions are pure (no ROS dependency), const-correct, and handle
// edge cases: empty arrays, all-NaN arrays, single-element arrays.

#include "porter_lidar_processor/filters.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <vector>

namespace porter_lidar_processor
{

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 1: Range clamp
// ═══════════════════════════════════════════════════════════════════════════════

std::vector<float> range_clamp(
  const std::vector<float> & ranges,
  float min_range,
  float max_range)
{
  std::vector<float> result;
  result.reserve(ranges.size());

  for (const float r : ranges) {
    if (std::isnan(r) || r < min_range || r > max_range) {
      result.push_back(std::numeric_limits<float>::quiet_NaN());
    } else {
      result.push_back(r);
    }
  }

  return result;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 2: MAD-based outlier rejection
// ═══════════════════════════════════════════════════════════════════════════════

std::vector<float> outlier_rejection(
  const std::vector<float> & ranges,
  float threshold)
{
  if (ranges.empty()) {
    return {};
  }

  // Collect valid (non-NaN) values to compute global median and MAD
  std::vector<float> valid_values;
  valid_values.reserve(ranges.size());
  for (const float r : ranges) {
    if (!std::isnan(r)) {
      valid_values.push_back(r);
    }
  }

  // Need at least 3 valid values for meaningful statistics
  if (valid_values.size() < 3) {
    return std::vector<float>(ranges);
  }

  // Compute median via nth_element (O(n) average)
  std::vector<float> sorted_vals = valid_values;
  const size_t mid = sorted_vals.size() / 2;
  std::nth_element(sorted_vals.begin(), sorted_vals.begin() + mid, sorted_vals.end());
  float median = sorted_vals[mid];

  // For even-length arrays, use the lower-median (consistent, fast)
  // This avoids the extra nth_element call for marginal accuracy gain

  // Compute MAD (Median Absolute Deviation)
  std::vector<float> deviations;
  deviations.reserve(valid_values.size());
  for (const float v : valid_values) {
    deviations.push_back(std::fabs(v - median));
  }
  const size_t dev_mid = deviations.size() / 2;
  std::nth_element(deviations.begin(), deviations.begin() + dev_mid, deviations.end());
  float mad = deviations[dev_mid];

  // Guard against zero MAD (all values identical) — use a small floor
  if (mad < 1e-6f) {
    mad = 0.01f;
  }

  // Reject values exceeding threshold * MAD from median
  std::vector<float> result;
  result.reserve(ranges.size());
  const float rejection_limit = threshold * mad;

  for (const float r : ranges) {
    if (std::isnan(r)) {
      result.push_back(std::numeric_limits<float>::quiet_NaN());
    } else if (std::fabs(r - median) > rejection_limit) {
      result.push_back(std::numeric_limits<float>::quiet_NaN());
    } else {
      result.push_back(r);
    }
  }

  return result;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 3: Median filter (sliding window)
// ═══════════════════════════════════════════════════════════════════════════════

std::vector<float> median_filter(
  const std::vector<float> & ranges,
  int window_size)
{
  if (ranges.empty()) {
    return {};
  }

  // Enforce odd window size >= 3
  if (window_size < 3) {
    window_size = 3;
  }
  if (window_size % 2 == 0) {
    window_size += 1;
  }

  const int n = static_cast<int>(ranges.size());
  const int half = window_size / 2;
  std::vector<float> result(ranges.size());

  // Reusable window buffer to avoid per-iteration allocation
  std::vector<float> window_valid;
  window_valid.reserve(window_size);

  for (int i = 0; i < n; ++i) {
    const int start = std::max(0, i - half);
    const int end = std::min(n, i + half + 1);

    window_valid.clear();
    for (int j = start; j < end; ++j) {
      if (!std::isnan(ranges[j])) {
        window_valid.push_back(ranges[j]);
      }
    }

    if (window_valid.empty()) {
      result[i] = std::numeric_limits<float>::quiet_NaN();
    } else {
      const size_t mid = window_valid.size() / 2;
      std::nth_element(window_valid.begin(), window_valid.begin() + mid, window_valid.end());
      result[i] = window_valid[mid];
    }
  }

  return result;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 4: Exponential moving average smoothing
// ═══════════════════════════════════════════════════════════════════════════════

std::vector<float> exponential_smoothing(
  const std::vector<float> & ranges,
  const std::vector<float> & previous,
  float alpha)
{
  // If no valid previous state, return a copy of current ranges
  if (previous.empty() || previous.size() != ranges.size()) {
    return std::vector<float>(ranges);
  }

  // Clamp alpha to [0, 1]
  alpha = std::max(0.0f, std::min(1.0f, alpha));

  const float one_minus_alpha = 1.0f - alpha;
  std::vector<float> result;
  result.reserve(ranges.size());

  for (size_t i = 0; i < ranges.size(); ++i) {
    if (std::isnan(ranges[i]) || std::isnan(previous[i])) {
      // If either value is NaN, propagate the current value (or NaN)
      result.push_back(ranges[i]);
    } else {
      result.push_back(alpha * ranges[i] + one_minus_alpha * previous[i]);
    }
  }

  return result;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 5: ROI (Region of Interest) crop
// ═══════════════════════════════════════════════════════════════════════════════

std::vector<float> roi_crop(
  const std::vector<float> & ranges,
  float scan_angle_min,
  float scan_angle_increment,
  float roi_angle_min,
  float roi_angle_max)
{
  if (ranges.empty()) {
    return {};
  }

  std::vector<float> result;
  result.reserve(ranges.size());

  for (size_t i = 0; i < ranges.size(); ++i) {
    const float angle = scan_angle_min +
      static_cast<float>(i) * scan_angle_increment;
    if (angle < roi_angle_min || angle > roi_angle_max) {
      result.push_back(std::numeric_limits<float>::quiet_NaN());
    } else {
      result.push_back(ranges[i]);
    }
  }

  return result;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 6: Downsample
// ═══════════════════════════════════════════════════════════════════════════════

std::vector<float> downsample(
  const std::vector<float> & ranges,
  int factor)
{
  if (factor <= 1) {
    return std::vector<float>(ranges);
  }

  if (ranges.empty()) {
    return {};
  }

  std::vector<float> result(ranges.size(), std::numeric_limits<float>::quiet_NaN());

  for (size_t i = 0; i < ranges.size(); i += static_cast<size_t>(factor)) {
    result[i] = ranges[i];
  }

  return result;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════════════════════

size_t count_valid(const std::vector<float> & ranges)
{
  size_t count = 0;
  for (const float r : ranges) {
    if (!std::isnan(r)) {
      ++count;
    }
  }
  return count;
}

ScanStats compute_stats(const std::vector<float> & ranges)
{
  ScanStats stats{};
  stats.total = ranges.size();
  stats.valid = 0;
  stats.min_range = std::numeric_limits<float>::quiet_NaN();
  stats.max_range = std::numeric_limits<float>::quiet_NaN();
  stats.mean_range = std::numeric_limits<float>::quiet_NaN();
  stats.invalid_ratio = 0.0f;

  if (ranges.empty()) {
    return stats;
  }

  float sum = 0.0f;
  float local_min = std::numeric_limits<float>::max();
  float local_max = std::numeric_limits<float>::lowest();

  for (const float r : ranges) {
    if (!std::isnan(r)) {
      ++stats.valid;
      sum += r;
      if (r < local_min) {
        local_min = r;
      }
      if (r > local_max) {
        local_max = r;
      }
    }
  }

  if (stats.valid > 0) {
    stats.min_range = local_min;
    stats.max_range = local_max;
    stats.mean_range = sum / static_cast<float>(stats.valid);
  }

  stats.invalid_ratio =
    static_cast<float>(stats.total - stats.valid) / static_cast<float>(stats.total);

  return stats;
}

}  // namespace porter_lidar_processor

// Copyright 2026 VirtusCo. All rights reserved.
// Proprietary and confidential.
//
// GTest suite for the LIDAR filter library.
// Tests all 6 filters + 2 utility functions with edge cases.
// Every test uses EXPECT_FLOAT_EQ or EXPECT_NEAR for float comparisons.

#include <cmath>
#include <limits>
#include <vector>

#include "gtest/gtest.h"
#include "porter_lidar_processor/filters.hpp"

namespace plp = porter_lidar_processor;

static const float NaN = std::numeric_limits<float>::quiet_NaN();

// Helper: check if a float is NaN
static bool is_nan(float v)
{
  return std::isnan(v);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 1: range_clamp
// ═══════════════════════════════════════════════════════════════════════════════

TEST(RangeClamp, NormalValues)
{
  std::vector<float> ranges = {0.5f, 1.0f, 5.0f, 10.0f};
  auto result = plp::range_clamp(ranges, 0.12f, 12.0f);
  ASSERT_EQ(result.size(), 4u);
  EXPECT_FLOAT_EQ(result[0], 0.5f);
  EXPECT_FLOAT_EQ(result[1], 1.0f);
  EXPECT_FLOAT_EQ(result[2], 5.0f);
  EXPECT_FLOAT_EQ(result[3], 10.0f);
}

TEST(RangeClamp, AllBelowMin)
{
  std::vector<float> ranges = {0.01f, 0.05f, 0.10f};
  auto result = plp::range_clamp(ranges, 0.12f, 12.0f);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_TRUE(is_nan(result[0]));
  EXPECT_TRUE(is_nan(result[1]));
  EXPECT_TRUE(is_nan(result[2]));
}

TEST(RangeClamp, AllAboveMax)
{
  std::vector<float> ranges = {13.0f, 15.0f, 100.0f};
  auto result = plp::range_clamp(ranges, 0.12f, 12.0f);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_TRUE(is_nan(result[0]));
  EXPECT_TRUE(is_nan(result[1]));
  EXPECT_TRUE(is_nan(result[2]));
}

TEST(RangeClamp, NaNPassthrough)
{
  std::vector<float> ranges = {1.0f, NaN, 5.0f};
  auto result = plp::range_clamp(ranges, 0.12f, 12.0f);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_TRUE(is_nan(result[1]));
  EXPECT_FLOAT_EQ(result[2], 5.0f);
}

TEST(RangeClamp, EmptyInput)
{
  std::vector<float> ranges;
  auto result = plp::range_clamp(ranges, 0.12f, 12.0f);
  EXPECT_TRUE(result.empty());
}

TEST(RangeClamp, BoundaryValues)
{
  std::vector<float> ranges = {0.12f, 12.0f};
  auto result = plp::range_clamp(ranges, 0.12f, 12.0f);
  ASSERT_EQ(result.size(), 2u);
  EXPECT_FLOAT_EQ(result[0], 0.12f);
  EXPECT_FLOAT_EQ(result[1], 12.0f);
}

TEST(RangeClamp, MixedValidInvalid)
{
  std::vector<float> ranges = {0.05f, 1.0f, 15.0f, 3.0f, 0.01f};
  auto result = plp::range_clamp(ranges, 0.12f, 12.0f);
  ASSERT_EQ(result.size(), 5u);
  EXPECT_TRUE(is_nan(result[0]));
  EXPECT_FLOAT_EQ(result[1], 1.0f);
  EXPECT_TRUE(is_nan(result[2]));
  EXPECT_FLOAT_EQ(result[3], 3.0f);
  EXPECT_TRUE(is_nan(result[4]));
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 2: outlier_rejection
// ═══════════════════════════════════════════════════════════════════════════════

TEST(OutlierRejection, NormalNoOutliers)
{
  std::vector<float> ranges = {1.0f, 1.1f, 1.0f, 0.9f, 1.05f};
  auto result = plp::outlier_rejection(ranges, 3.0f);
  ASSERT_EQ(result.size(), 5u);
  // All values are close to median — none should be rejected
  for (size_t i = 0; i < result.size(); ++i) {
    EXPECT_FALSE(is_nan(result[i])) << "Index " << i << " unexpectedly NaN";
  }
}

TEST(OutlierRejection, ClearOutlier)
{
  std::vector<float> ranges = {1.0f, 1.0f, 1.0f, 50.0f, 1.0f};
  auto result = plp::outlier_rejection(ranges, 3.0f);
  ASSERT_EQ(result.size(), 5u);
  // The 50.0 value should be rejected as outlier
  EXPECT_TRUE(is_nan(result[3]));
  // Others should remain
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_FLOAT_EQ(result[1], 1.0f);
  EXPECT_FLOAT_EQ(result[4], 1.0f);
}

TEST(OutlierRejection, SingleValue)
{
  std::vector<float> ranges = {5.0f};
  auto result = plp::outlier_rejection(ranges, 3.0f);
  ASSERT_EQ(result.size(), 1u);
  // Too few values for statistics — should pass through unchanged
  EXPECT_FLOAT_EQ(result[0], 5.0f);
}

TEST(OutlierRejection, AllSameValues)
{
  std::vector<float> ranges = {2.0f, 2.0f, 2.0f, 2.0f};
  auto result = plp::outlier_rejection(ranges, 3.0f);
  ASSERT_EQ(result.size(), 4u);
  for (size_t i = 0; i < result.size(); ++i) {
    EXPECT_FLOAT_EQ(result[i], 2.0f);
  }
}

TEST(OutlierRejection, WithNaN)
{
  std::vector<float> ranges = {1.0f, NaN, 1.1f, 0.9f, 1.0f};
  auto result = plp::outlier_rejection(ranges, 3.0f);
  ASSERT_EQ(result.size(), 5u);
  EXPECT_TRUE(is_nan(result[1]));  // NaN stays NaN
  EXPECT_FALSE(is_nan(result[0]));
  EXPECT_FALSE(is_nan(result[2]));
}

TEST(OutlierRejection, EmptyInput)
{
  std::vector<float> ranges;
  auto result = plp::outlier_rejection(ranges, 3.0f);
  EXPECT_TRUE(result.empty());
}

TEST(OutlierRejection, TwoValues)
{
  std::vector<float> ranges = {1.0f, 100.0f};
  auto result = plp::outlier_rejection(ranges, 3.0f);
  ASSERT_EQ(result.size(), 2u);
  // Too few values (< 3) — pass through unchanged
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_FLOAT_EQ(result[1], 100.0f);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 3: median_filter
// ═══════════════════════════════════════════════════════════════════════════════

TEST(MedianFilter, OddWindow)
{
  std::vector<float> ranges = {1.0f, 10.0f, 2.0f, 3.0f, 4.0f};
  auto result = plp::median_filter(ranges, 3);
  ASSERT_EQ(result.size(), 5u);
  // Window around index 1 (sizes 0-2): {1, 10, 2} -> median = 2
  EXPECT_FLOAT_EQ(result[1], 2.0f);
}

TEST(MedianFilter, EvenWindowForcedOdd)
{
  // Even window_size should be rounded up to next odd
  std::vector<float> ranges = {5.0f, 3.0f, 8.0f, 1.0f, 7.0f};
  auto result_even = plp::median_filter(ranges, 4);  // Should become 5
  auto result_odd = plp::median_filter(ranges, 5);
  ASSERT_EQ(result_even.size(), result_odd.size());
  for (size_t i = 0; i < result_even.size(); ++i) {
    EXPECT_FLOAT_EQ(result_even[i], result_odd[i]);
  }
}

TEST(MedianFilter, SingleElement)
{
  std::vector<float> ranges = {42.0f};
  auto result = plp::median_filter(ranges, 5);
  ASSERT_EQ(result.size(), 1u);
  EXPECT_FLOAT_EQ(result[0], 42.0f);
}

TEST(MedianFilter, NaNHandling)
{
  std::vector<float> ranges = {1.0f, NaN, 3.0f, 2.0f, 4.0f};
  auto result = plp::median_filter(ranges, 3);
  ASSERT_EQ(result.size(), 5u);
  // NaN should be skipped in median computation
  // Index 1 window {1.0, NaN, 3.0} -> valid = {1.0, 3.0} -> median = 3.0 (upper of 2)
  EXPECT_FALSE(is_nan(result[1]));
}

TEST(MedianFilter, AllNaN)
{
  std::vector<float> ranges = {NaN, NaN, NaN};
  auto result = plp::median_filter(ranges, 3);
  ASSERT_EQ(result.size(), 3u);
  for (size_t i = 0; i < result.size(); ++i) {
    EXPECT_TRUE(is_nan(result[i]));
  }
}

TEST(MedianFilter, PreservesConstant)
{
  std::vector<float> ranges = {5.0f, 5.0f, 5.0f, 5.0f, 5.0f};
  auto result = plp::median_filter(ranges, 3);
  ASSERT_EQ(result.size(), 5u);
  for (size_t i = 0; i < result.size(); ++i) {
    EXPECT_FLOAT_EQ(result[i], 5.0f);
  }
}

TEST(MedianFilter, EmptyInput)
{
  std::vector<float> ranges;
  auto result = plp::median_filter(ranges, 5);
  EXPECT_TRUE(result.empty());
}

TEST(MedianFilter, WindowSizeLargerThanArray)
{
  std::vector<float> ranges = {3.0f, 1.0f};
  auto result = plp::median_filter(ranges, 11);
  ASSERT_EQ(result.size(), 2u);
  // Both indices see the full array {3.0, 1.0} -> median = 3.0 (nth_element mid=1)
  // Valid behaviour regardless
  EXPECT_FALSE(is_nan(result[0]));
  EXPECT_FALSE(is_nan(result[1]));
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 4: exponential_smoothing
// ═══════════════════════════════════════════════════════════════════════════════

TEST(ExponentialSmoothing, Convergence)
{
  std::vector<float> ranges = {10.0f, 10.0f, 10.0f};
  std::vector<float> previous = {5.0f, 5.0f, 5.0f};
  auto result = plp::exponential_smoothing(ranges, previous, 0.5f);
  ASSERT_EQ(result.size(), 3u);
  // 0.5 * 10 + 0.5 * 5 = 7.5
  for (size_t i = 0; i < result.size(); ++i) {
    EXPECT_FLOAT_EQ(result[i], 7.5f);
  }
}

TEST(ExponentialSmoothing, AlphaZero)
{
  std::vector<float> ranges = {10.0f, 10.0f};
  std::vector<float> previous = {5.0f, 5.0f};
  auto result = plp::exponential_smoothing(ranges, previous, 0.0f);
  ASSERT_EQ(result.size(), 2u);
  // alpha=0 means keep previous entirely
  EXPECT_FLOAT_EQ(result[0], 5.0f);
  EXPECT_FLOAT_EQ(result[1], 5.0f);
}

TEST(ExponentialSmoothing, AlphaOne)
{
  std::vector<float> ranges = {10.0f, 10.0f};
  std::vector<float> previous = {5.0f, 5.0f};
  auto result = plp::exponential_smoothing(ranges, previous, 1.0f);
  ASSERT_EQ(result.size(), 2u);
  // alpha=1 means take current entirely (instant)
  EXPECT_FLOAT_EQ(result[0], 10.0f);
  EXPECT_FLOAT_EQ(result[1], 10.0f);
}

TEST(ExponentialSmoothing, EmptyPrevious)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f};
  std::vector<float> previous;
  auto result = plp::exponential_smoothing(ranges, previous, 0.3f);
  ASSERT_EQ(result.size(), 3u);
  // Empty previous — returns ranges unchanged
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_FLOAT_EQ(result[1], 2.0f);
  EXPECT_FLOAT_EQ(result[2], 3.0f);
}

TEST(ExponentialSmoothing, SizeMismatch)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f};
  std::vector<float> previous = {1.0f, 2.0f};
  auto result = plp::exponential_smoothing(ranges, previous, 0.3f);
  ASSERT_EQ(result.size(), 3u);
  // Size mismatch — returns ranges unchanged
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_FLOAT_EQ(result[1], 2.0f);
  EXPECT_FLOAT_EQ(result[2], 3.0f);
}

TEST(ExponentialSmoothing, NaNInCurrent)
{
  std::vector<float> ranges = {NaN, 10.0f};
  std::vector<float> previous = {5.0f, 5.0f};
  auto result = plp::exponential_smoothing(ranges, previous, 0.5f);
  ASSERT_EQ(result.size(), 2u);
  // NaN in current propagates
  EXPECT_TRUE(is_nan(result[0]));
  EXPECT_FLOAT_EQ(result[1], 7.5f);
}

TEST(ExponentialSmoothing, NaNInPrevious)
{
  std::vector<float> ranges = {10.0f, 10.0f};
  std::vector<float> previous = {NaN, 5.0f};
  auto result = plp::exponential_smoothing(ranges, previous, 0.5f);
  ASSERT_EQ(result.size(), 2u);
  // NaN in previous -> use current value
  EXPECT_FLOAT_EQ(result[0], 10.0f);
  EXPECT_FLOAT_EQ(result[1], 7.5f);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 5: roi_crop
// ═══════════════════════════════════════════════════════════════════════════════

TEST(RoiCrop, FullRange)
{
  // ROI covers full 360 scan — nothing cropped
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f, 4.0f};
  float angle_min = -3.14159f;
  float angle_inc = 6.28318f / 4.0f;
  auto result = plp::roi_crop(ranges, angle_min, angle_inc, -3.15f, 3.15f);
  ASSERT_EQ(result.size(), 4u);
  for (size_t i = 0; i < result.size(); ++i) {
    EXPECT_FALSE(is_nan(result[i]));
  }
}

TEST(RoiCrop, NarrowCrop)
{
  // 10 points spanning -PI to PI
  const int n = 10;
  const float angle_min = -3.14159f;
  const float angle_inc = 6.28318f / static_cast<float>(n);
  std::vector<float> ranges(n, 5.0f);

  // ROI: only keep front [-0.5, 0.5] radians
  auto result = plp::roi_crop(ranges, angle_min, angle_inc, -0.5f, 0.5f);
  ASSERT_EQ(result.size(), static_cast<size_t>(n));

  // Count how many are valid (inside ROI)
  size_t valid = plp::count_valid(result);
  EXPECT_GT(valid, 0u);
  EXPECT_LT(valid, static_cast<size_t>(n));
}

TEST(RoiCrop, EmptyInput)
{
  std::vector<float> ranges;
  auto result = plp::roi_crop(ranges, -3.14f, 0.01f, -1.0f, 1.0f);
  EXPECT_TRUE(result.empty());
}

TEST(RoiCrop, AllOutsideRoi)
{
  // All angles are negative, ROI is positive only
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f};
  float angle_min = -3.0f;
  float angle_inc = 0.5f;
  // angles: -3.0, -2.5, -2.0 — all below roi_min of 0.0
  auto result = plp::roi_crop(ranges, angle_min, angle_inc, 0.0f, 1.0f);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_TRUE(is_nan(result[0]));
  EXPECT_TRUE(is_nan(result[1]));
  EXPECT_TRUE(is_nan(result[2]));
}

TEST(RoiCrop, PreservesNaN)
{
  std::vector<float> ranges = {1.0f, NaN, 3.0f};
  float angle_min = -1.0f;
  float angle_inc = 1.0f;
  // angles: -1.0, 0.0, 1.0 — all within [-1.5, 1.5]
  auto result = plp::roi_crop(ranges, angle_min, angle_inc, -1.5f, 1.5f);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_TRUE(is_nan(result[1]));  // was NaN, stays NaN (inside ROI)
  EXPECT_FLOAT_EQ(result[2], 3.0f);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Filter 6: downsample
// ═══════════════════════════════════════════════════════════════════════════════

TEST(Downsample, FactorOne)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f, 4.0f};
  auto result = plp::downsample(ranges, 1);
  ASSERT_EQ(result.size(), 4u);
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_FLOAT_EQ(result[1], 2.0f);
  EXPECT_FLOAT_EQ(result[2], 3.0f);
  EXPECT_FLOAT_EQ(result[3], 4.0f);
}

TEST(Downsample, FactorTwo)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f, 4.0f};
  auto result = plp::downsample(ranges, 2);
  ASSERT_EQ(result.size(), 4u);
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_TRUE(is_nan(result[1]));
  EXPECT_FLOAT_EQ(result[2], 3.0f);
  EXPECT_TRUE(is_nan(result[3]));
}

TEST(Downsample, FactorThree)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
  auto result = plp::downsample(ranges, 3);
  ASSERT_EQ(result.size(), 6u);
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_TRUE(is_nan(result[1]));
  EXPECT_TRUE(is_nan(result[2]));
  EXPECT_FLOAT_EQ(result[3], 4.0f);
  EXPECT_TRUE(is_nan(result[4]));
  EXPECT_TRUE(is_nan(result[5]));
}

TEST(Downsample, NonDivisible)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f};
  auto result = plp::downsample(ranges, 2);
  ASSERT_EQ(result.size(), 5u);
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_TRUE(is_nan(result[1]));
  EXPECT_FLOAT_EQ(result[2], 3.0f);
  EXPECT_TRUE(is_nan(result[3]));
  EXPECT_FLOAT_EQ(result[4], 5.0f);
}

TEST(Downsample, EmptyInput)
{
  std::vector<float> ranges;
  auto result = plp::downsample(ranges, 2);
  EXPECT_TRUE(result.empty());
}

TEST(Downsample, FactorZero)
{
  // Factor <= 1 should return unchanged copy
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f};
  auto result = plp::downsample(ranges, 0);
  ASSERT_EQ(result.size(), 3u);
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_FLOAT_EQ(result[1], 2.0f);
  EXPECT_FLOAT_EQ(result[2], 3.0f);
}

TEST(Downsample, FactorLargerThanArray)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f};
  auto result = plp::downsample(ranges, 10);
  ASSERT_EQ(result.size(), 3u);
  // Only index 0 is kept
  EXPECT_FLOAT_EQ(result[0], 1.0f);
  EXPECT_TRUE(is_nan(result[1]));
  EXPECT_TRUE(is_nan(result[2]));
}

// ═══════════════════════════════════════════════════════════════════════════════
// Utility: count_valid
// ═══════════════════════════════════════════════════════════════════════════════

TEST(CountValid, AllValid)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f, 4.0f};
  EXPECT_EQ(plp::count_valid(ranges), 4u);
}

TEST(CountValid, AllNaN)
{
  std::vector<float> ranges = {NaN, NaN, NaN};
  EXPECT_EQ(plp::count_valid(ranges), 0u);
}

TEST(CountValid, Mixed)
{
  std::vector<float> ranges = {1.0f, NaN, 3.0f, NaN, 5.0f};
  EXPECT_EQ(plp::count_valid(ranges), 3u);
}

TEST(CountValid, EmptyInput)
{
  std::vector<float> ranges;
  EXPECT_EQ(plp::count_valid(ranges), 0u);
}

TEST(CountValid, SingleValid)
{
  std::vector<float> ranges = {42.0f};
  EXPECT_EQ(plp::count_valid(ranges), 1u);
}

TEST(CountValid, SingleNaN)
{
  std::vector<float> ranges = {NaN};
  EXPECT_EQ(plp::count_valid(ranges), 0u);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Utility: compute_stats
// ═══════════════════════════════════════════════════════════════════════════════

TEST(ComputeStats, NormalScan)
{
  std::vector<float> ranges = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f};
  auto stats = plp::compute_stats(ranges);
  EXPECT_EQ(stats.total, 5u);
  EXPECT_EQ(stats.valid, 5u);
  EXPECT_FLOAT_EQ(stats.min_range, 1.0f);
  EXPECT_FLOAT_EQ(stats.max_range, 5.0f);
  EXPECT_FLOAT_EQ(stats.mean_range, 3.0f);
  EXPECT_FLOAT_EQ(stats.invalid_ratio, 0.0f);
}

TEST(ComputeStats, EmptyScan)
{
  std::vector<float> ranges;
  auto stats = plp::compute_stats(ranges);
  EXPECT_EQ(stats.total, 0u);
  EXPECT_EQ(stats.valid, 0u);
  EXPECT_TRUE(is_nan(stats.min_range));
  EXPECT_TRUE(is_nan(stats.max_range));
  EXPECT_TRUE(is_nan(stats.mean_range));
  EXPECT_FLOAT_EQ(stats.invalid_ratio, 0.0f);
}

TEST(ComputeStats, AllNaN)
{
  std::vector<float> ranges = {NaN, NaN, NaN, NaN};
  auto stats = plp::compute_stats(ranges);
  EXPECT_EQ(stats.total, 4u);
  EXPECT_EQ(stats.valid, 0u);
  EXPECT_TRUE(is_nan(stats.min_range));
  EXPECT_TRUE(is_nan(stats.max_range));
  EXPECT_TRUE(is_nan(stats.mean_range));
  EXPECT_FLOAT_EQ(stats.invalid_ratio, 1.0f);
}

TEST(ComputeStats, MixedWithNaN)
{
  std::vector<float> ranges = {1.0f, NaN, 3.0f, NaN};
  auto stats = plp::compute_stats(ranges);
  EXPECT_EQ(stats.total, 4u);
  EXPECT_EQ(stats.valid, 2u);
  EXPECT_FLOAT_EQ(stats.min_range, 1.0f);
  EXPECT_FLOAT_EQ(stats.max_range, 3.0f);
  EXPECT_FLOAT_EQ(stats.mean_range, 2.0f);
  EXPECT_FLOAT_EQ(stats.invalid_ratio, 0.5f);
}

TEST(ComputeStats, SingleValue)
{
  std::vector<float> ranges = {7.5f};
  auto stats = plp::compute_stats(ranges);
  EXPECT_EQ(stats.total, 1u);
  EXPECT_EQ(stats.valid, 1u);
  EXPECT_FLOAT_EQ(stats.min_range, 7.5f);
  EXPECT_FLOAT_EQ(stats.max_range, 7.5f);
  EXPECT_FLOAT_EQ(stats.mean_range, 7.5f);
  EXPECT_FLOAT_EQ(stats.invalid_ratio, 0.0f);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Integration: pipeline composition
// ═══════════════════════════════════════════════════════════════════════════════

TEST(Pipeline, ClampThenOutlier)
{
  // Simulate a typical scan with out-of-range values and an outlier
  std::vector<float> ranges = {0.01f, 1.0f, 1.0f, 50.0f, 1.0f, 1.0f, 15.0f};
  auto step1 = plp::range_clamp(ranges, 0.12f, 12.0f);
  auto step2 = plp::outlier_rejection(step1, 3.0f);
  ASSERT_EQ(step2.size(), 7u);
  // Index 0 (0.01) clamped to NaN, index 6 (15.0) clamped to NaN
  EXPECT_TRUE(is_nan(step2[0]));
  EXPECT_TRUE(is_nan(step2[6]));
  // Index 3 (50.0) was also clamped, so it's NaN after clamp
  EXPECT_TRUE(is_nan(step2[3]));
}

TEST(Pipeline, FullPipelineSmoke)
{
  // Run all 6 filters in sequence
  std::vector<float> ranges = {
    0.05f, 1.0f, 1.1f, 0.9f, 100.0f, 1.0f, 1.2f, 0.8f, 1.0f, 15.0f};
  std::vector<float> previous = {
    1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f};

  auto step1 = plp::range_clamp(ranges, 0.12f, 12.0f);
  auto step2 = plp::outlier_rejection(step1, 3.0f);
  auto step3 = plp::median_filter(step2, 5);
  auto step4 = plp::exponential_smoothing(step3, previous, 0.3f);
  auto step5 = plp::roi_crop(step4, -3.14159f, 0.6283f, -1.5f, 1.5f);
  auto step6 = plp::downsample(step5, 2);

  ASSERT_EQ(step6.size(), 10u);
  // Pipeline should produce a valid output without crashing
  // At least index 0 should be kept by downsample (factor 2)
  // Some values may be NaN due to various filters — that's expected
}

TEST(Pipeline, AllFiltersOnConstant)
{
  // A uniform scan should pass through mostly unchanged
  std::vector<float> ranges(100, 5.0f);
  std::vector<float> previous(100, 5.0f);

  auto step1 = plp::range_clamp(ranges, 0.12f, 12.0f);
  auto step2 = plp::outlier_rejection(step1, 3.0f);
  auto step3 = plp::median_filter(step2, 5);
  auto step4 = plp::exponential_smoothing(step3, previous, 0.3f);

  // All values should still be 5.0 after processing a uniform scan
  for (size_t i = 0; i < step4.size(); ++i) {
    EXPECT_FLOAT_EQ(step4[i], 5.0f) << "Index " << i;
  }
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}

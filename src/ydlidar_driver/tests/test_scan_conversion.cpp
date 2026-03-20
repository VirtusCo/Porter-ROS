// Copyright 2026 VirtusCo. All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/// @file test_scan_conversion.cpp
/// @brief Integration tests for SDK-to-ROS2 LaserScan conversion logic.
///
/// Tests the scan data conversion algorithm with simulated data matching
/// what the YDLidar SDK produces for the S2PRO and other models.
/// The conversion logic is replicated from ydlidar_node.cpp so it can
/// be validated in isolation without hardware or a running ROS 2 graph.

#include <gtest/gtest.h>

#include <cmath>
#include <limits>
#include <vector>

#include "CYdLidar.h"

// ═══════════════════════════════════════════════════════════════════════════
// Conversion Algorithm — extracted from ydlidar_node.cpp scan_callback()
// ═══════════════════════════════════════════════════════════════════════════

/// @brief Result of converting an SDK LaserScan to a binned array.
struct ConvertedScan
{
  float angle_min = 0.0f;
  float angle_max = 0.0f;
  float angle_increment = 0.0f;
  float scan_time = 0.0f;
  float time_increment = 0.0f;
  float range_min = 0.0f;
  float range_max = 0.0f;
  std::vector<float> ranges;
  std::vector<float> intensities;
  size_t invalid_count = 0;
};

/// @brief Convert SDK LaserScan to binned arrays (same algorithm as the node).
/// @param[in] sdk_scan SDK scan with points array.
/// @param[out] out Populated converted scan.
/// @return true if conversion succeeded, false if geometry is invalid.
bool convert_sdk_scan(const LaserScan & sdk_scan, ConvertedScan & out)
{
  out.angle_min = sdk_scan.config.min_angle;
  out.angle_max = sdk_scan.config.max_angle;
  out.angle_increment = sdk_scan.config.angle_increment;
  out.scan_time = sdk_scan.config.scan_time;
  out.time_increment = sdk_scan.config.time_increment;
  out.range_min = sdk_scan.config.min_range;
  out.range_max = sdk_scan.config.max_range;
  out.invalid_count = 0;

  // Compute array size from geometry
  int size = 0;
  if (sdk_scan.config.angle_increment > 0.0f) {
    size = static_cast<int>(std::ceil(
        (sdk_scan.config.max_angle - sdk_scan.config.min_angle) /
        sdk_scan.config.angle_increment)) + 1;
  }

  if (size <= 0) {
    return false;
  }

  // Initialize arrays with NaN (standard for no-return)
  out.ranges.assign(size, std::numeric_limits<float>::quiet_NaN());
  out.intensities.assign(size, 0.0f);

  // Place each point into the correct angular bin
  for (const auto & point : sdk_scan.points) {
    int index = static_cast<int>(std::ceil(
        (point.angle - sdk_scan.config.min_angle) /
        sdk_scan.config.angle_increment));

    if (index >= 0 && index < size) {
      if (point.range >= sdk_scan.config.min_range &&
        point.range <= sdk_scan.config.max_range)
      {
        out.ranges[index] = point.range;
        out.intensities[index] = point.intensity;
      } else {
        out.invalid_count++;
      }
    }
  }

  return true;
}

// ═══════════════════════════════════════════════════════════════════════════
// Test Helpers
// ═══════════════════════════════════════════════════════════════════════════

/// @brief Create a LaserScan config typical of X4 Pro / S2PRO.
LaserScan create_s2pro_scan()
{
  LaserScan scan;
  scan.stamp = 1000000000UL;  // 1 second
  scan.config.min_angle = static_cast<float>(-M_PI);
  scan.config.max_angle = static_cast<float>(M_PI);
  scan.config.angle_increment = 2.0f * static_cast<float>(M_PI) / 720.0f;
  scan.config.scan_time = 0.25f;  // 4 Hz delivery
  scan.config.time_increment = 0.25f / 720.0f;
  scan.config.min_range = 0.01f;
  scan.config.max_range = 12.0f;
  scan.scanFreq = 4.0f;
  return scan;
}

/// @brief Create a single LaserPoint at a known angle.
LaserPoint make_point(float angle_rad, float range, float intensity = 0.0f)
{
  LaserPoint pt;
  pt.angle = angle_rad;
  pt.range = range;
  pt.intensity = intensity;
  return pt;
}

/// @brief Compute the expected bin index for a given angle.
int expected_bin(const LaserScan & scan, float angle)
{
  return static_cast<int>(std::ceil(
           (angle - scan.config.min_angle) /
           scan.config.angle_increment));
}

// ═══════════════════════════════════════════════════════════════════════════
// Basic Conversion Tests
// ═══════════════════════════════════════════════════════════════════════════

class ScanConversionTest : public ::testing::Test
{
protected:
  LaserScan base_scan_;

  void SetUp() override
  {
    base_scan_ = create_s2pro_scan();
  }
};

TEST_F(ScanConversionTest, EmptyScanProducesAllNaN)
{
  // No points in the scan
  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  EXPECT_GT(result.ranges.size(), 0u);

  for (const auto & r : result.ranges) {
    EXPECT_TRUE(std::isnan(r));
  }
  EXPECT_EQ(result.invalid_count, 0u);
}

TEST_F(ScanConversionTest, SinglePointPlacedCorrectly)
{
  base_scan_.points.push_back(make_point(0.0f, 5.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  int idx = expected_bin(base_scan_, 0.0f);
  ASSERT_GE(idx, 0);
  ASSERT_LT(idx, static_cast<int>(result.ranges.size()));
  EXPECT_FLOAT_EQ(result.ranges[idx], 5.0f);
  EXPECT_EQ(result.invalid_count, 0u);
}

TEST_F(ScanConversionTest, OutOfRangePointCountedAsInvalid)
{
  // Point beyond max_range (12.0m)
  base_scan_.points.push_back(make_point(0.0f, 15.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  EXPECT_EQ(result.invalid_count, 1u);

  // Bin should remain NaN
  int idx = expected_bin(base_scan_, 0.0f);
  EXPECT_TRUE(std::isnan(result.ranges[idx]));
}

TEST_F(ScanConversionTest, BelowMinRangePointCountedAsInvalid)
{
  // Point at 0.005m, below min_range of 0.01m
  base_scan_.points.push_back(make_point(0.0f, 0.005f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  EXPECT_EQ(result.invalid_count, 1u);
}

TEST_F(ScanConversionTest, IntensityPreserved)
{
  base_scan_.points.push_back(make_point(0.0f, 5.0f, 42.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  int idx = expected_bin(base_scan_, 0.0f);
  EXPECT_FLOAT_EQ(result.intensities[idx], 42.0f);
}

// ═══════════════════════════════════════════════════════════════════════════
// Geometry Field Tests
// ═══════════════════════════════════════════════════════════════════════════

TEST_F(ScanConversionTest, GeometryFieldsCopiedCorrectly)
{
  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  EXPECT_FLOAT_EQ(result.angle_min, base_scan_.config.min_angle);
  EXPECT_FLOAT_EQ(result.angle_max, base_scan_.config.max_angle);
  EXPECT_FLOAT_EQ(result.angle_increment, base_scan_.config.angle_increment);
  EXPECT_FLOAT_EQ(result.scan_time, base_scan_.config.scan_time);
  EXPECT_FLOAT_EQ(result.time_increment, base_scan_.config.time_increment);
  EXPECT_FLOAT_EQ(result.range_min, base_scan_.config.min_range);
  EXPECT_FLOAT_EQ(result.range_max, base_scan_.config.max_range);
}

TEST_F(ScanConversionTest, ArraySizeMatchesGeometry)
{
  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  int expected_size = static_cast<int>(std::ceil(
      (base_scan_.config.max_angle - base_scan_.config.min_angle) /
      base_scan_.config.angle_increment)) + 1;

  EXPECT_EQ(static_cast<int>(result.ranges.size()), expected_size);
  EXPECT_EQ(static_cast<int>(result.intensities.size()), expected_size);
}

TEST_F(ScanConversionTest, RangesAndIntensitiesSameSize)
{
  base_scan_.points.push_back(make_point(0.0f, 5.0f, 10.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  EXPECT_EQ(result.ranges.size(), result.intensities.size());
}

// ═══════════════════════════════════════════════════════════════════════════
// Invalid Geometry Tests
// ═══════════════════════════════════════════════════════════════════════════

TEST_F(ScanConversionTest, ZeroIncrementFails)
{
  base_scan_.config.angle_increment = 0.0f;

  ConvertedScan result;
  EXPECT_FALSE(convert_sdk_scan(base_scan_, result));
}

TEST_F(ScanConversionTest, NegativeIncrementFails)
{
  base_scan_.config.angle_increment = -0.01f;

  ConvertedScan result;
  EXPECT_FALSE(convert_sdk_scan(base_scan_, result));
}

// ═══════════════════════════════════════════════════════════════════════════
// Boundary Tests
// ═══════════════════════════════════════════════════════════════════════════

TEST_F(ScanConversionTest, PointExactlyAtMinRange)
{
  base_scan_.points.push_back(make_point(0.0f, 0.01f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  int idx = expected_bin(base_scan_, 0.0f);
  EXPECT_FLOAT_EQ(result.ranges[idx], 0.01f);
  EXPECT_EQ(result.invalid_count, 0u);
}

TEST_F(ScanConversionTest, PointExactlyAtMaxRange)
{
  base_scan_.points.push_back(make_point(0.0f, 12.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  int idx = expected_bin(base_scan_, 0.0f);
  EXPECT_FLOAT_EQ(result.ranges[idx], 12.0f);
  EXPECT_EQ(result.invalid_count, 0u);
}

TEST_F(ScanConversionTest, PointAtMinAngle)
{
  base_scan_.points.push_back(
    make_point(base_scan_.config.min_angle, 3.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  // Should be placed at or near the beginning of the array
  bool found = false;
  int limit = std::min(2, static_cast<int>(result.ranges.size()));
  for (int i = 0; i < limit; ++i) {
    if (!std::isnan(result.ranges[i])) {
      EXPECT_FLOAT_EQ(result.ranges[i], 3.0f);
      found = true;
    }
  }
  EXPECT_TRUE(found) << "Point at min_angle not found near array start";
}

TEST_F(ScanConversionTest, PointAtMaxAngle)
{
  base_scan_.points.push_back(
    make_point(base_scan_.config.max_angle, 3.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  // Should be placed near the end of the array
  bool found = false;
  int size = static_cast<int>(result.ranges.size());
  for (int i = std::max(0, size - 2); i < size; ++i) {
    if (!std::isnan(result.ranges[i])) {
      EXPECT_FLOAT_EQ(result.ranges[i], 3.0f);
      found = true;
    }
  }
  EXPECT_TRUE(found) << "Point at max_angle not found near array end";
}

// ═══════════════════════════════════════════════════════════════════════════
// Multi-Point Tests
// ═══════════════════════════════════════════════════════════════════════════

TEST_F(ScanConversionTest, OverlappingPointsLastWins)
{
  // Two points at same angle — later one in array overwrites
  base_scan_.points.push_back(make_point(0.0f, 3.0f));
  base_scan_.points.push_back(make_point(0.0f, 5.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  int idx = expected_bin(base_scan_, 0.0f);
  EXPECT_FLOAT_EQ(result.ranges[idx], 5.0f);
}

TEST_F(ScanConversionTest, MultipleDistinctPoints)
{
  // Place 3 points at different known angles
  float angles[] = {-1.0f, 0.0f, 1.0f};
  float ranges[] = {2.0f, 4.0f, 6.0f};

  for (int i = 0; i < 3; ++i) {
    base_scan_.points.push_back(make_point(angles[i], ranges[i]));
  }

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  for (int i = 0; i < 3; ++i) {
    int idx = expected_bin(base_scan_, angles[i]);
    ASSERT_GE(idx, 0);
    ASSERT_LT(idx, static_cast<int>(result.ranges.size()));
    EXPECT_FLOAT_EQ(result.ranges[idx], ranges[i]);
  }
  EXPECT_EQ(result.invalid_count, 0u);
}

TEST_F(ScanConversionTest, MixOfValidAndInvalidPoints)
{
  // Valid
  base_scan_.points.push_back(make_point(-1.0f, 5.0f));
  base_scan_.points.push_back(make_point(0.0f, 3.0f));
  // Out of max range
  base_scan_.points.push_back(make_point(0.5f, 20.0f));
  // Below min range
  base_scan_.points.push_back(make_point(1.0f, 0.001f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  EXPECT_EQ(result.invalid_count, 2u);

  // Valid points should be placed
  int idx1 = expected_bin(base_scan_, -1.0f);
  int idx2 = expected_bin(base_scan_, 0.0f);
  EXPECT_FLOAT_EQ(result.ranges[idx1], 5.0f);
  EXPECT_FLOAT_EQ(result.ranges[idx2], 3.0f);
}

// ═══════════════════════════════════════════════════════════════════════════
// Simulated S2PRO Integration Test — Recorded Data Pattern
// ═══════════════════════════════════════════════════════════════════════════

TEST_F(ScanConversionTest, RealisticS2ProScanPattern)
{
  // Simulate a realistic indoor S2PRO scan: ~1300 points over 360°
  // with ~30% invalid points (typical indoor environment)
  const int num_points = 1300;
  const float pi = static_cast<float>(M_PI);
  int expected_invalid = 0;

  for (int i = 0; i < num_points; ++i) {
    float angle = -pi + 2.0f * pi * static_cast<float>(i) / num_points;
    float range;

    if (i % 4 == 0) {
      // ~25% beyond max_range (open doors, long corridors)
      range = 15.0f;
      expected_invalid++;
    } else if (i % 13 == 0) {
      // ~7% below min_range (noise, near misses)
      range = 0.005f;
      expected_invalid++;
    } else {
      // Valid wall returns at 2-6m
      range = 3.0f + 2.0f * std::sin(angle);
    }

    base_scan_.points.push_back(make_point(angle, range));
  }

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(base_scan_, result));

  // Verify arrays are populated
  EXPECT_GT(result.ranges.size(), 0u);
  EXPECT_EQ(result.ranges.size(), result.intensities.size());

  // Count valid ranges
  size_t valid = 0;
  for (const auto & r : result.ranges) {
    if (!std::isnan(r)) {
      valid++;
      // All placed ranges must be within [min_range, max_range]
      EXPECT_GE(r, result.range_min);
      EXPECT_LE(r, result.range_max);
    }
  }

  // Should have both valid and invalid data
  EXPECT_GT(valid, 0u) << "Expected some valid ranges";
  EXPECT_GT(result.invalid_count, 0u) << "Expected some invalid points";

  // The invalid count should be close to our expected count
  // (some out-of-angle-range points may not have been counted)
  EXPECT_GE(result.invalid_count, static_cast<size_t>(expected_invalid * 0.8));
}

// ═══════════════════════════════════════════════════════════════════════════
// ToF LIDAR Config — Different Geometry
// ═══════════════════════════════════════════════════════════════════════════

TEST(ScanConversionToFTest, TG30ScanConfig)
{
  // TG30 has fewer points per revolution and longer range
  LaserScan scan;
  scan.stamp = 1000000000UL;
  scan.config.min_angle = static_cast<float>(-M_PI);
  scan.config.max_angle = static_cast<float>(M_PI);
  scan.config.angle_increment = 2.0f * static_cast<float>(M_PI) / 500.0f;
  scan.config.scan_time = 0.1f;  // 10 Hz
  scan.config.time_increment = 0.1f / 500.0f;
  scan.config.min_range = 0.01f;
  scan.config.max_range = 30.0f;
  scan.scanFreq = 10.0f;

  // Add a valid long-range point
  scan.points.push_back(make_point(0.0f, 25.0f));

  ConvertedScan result;
  ASSERT_TRUE(convert_sdk_scan(scan, result));

  int idx = expected_bin(scan, 0.0f);
  EXPECT_FLOAT_EQ(result.ranges[idx], 25.0f);

  // Array should be smaller than S2PRO (500 resolution vs 720)
  int expected_size = static_cast<int>(std::ceil(
      (scan.config.max_angle - scan.config.min_angle) /
      scan.config.angle_increment)) + 1;
  EXPECT_EQ(static_cast<int>(result.ranges.size()), expected_size);
  EXPECT_LE(result.ranges.size(), 502u);  // ~501 bins
}

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}

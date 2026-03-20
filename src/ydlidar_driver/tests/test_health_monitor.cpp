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

/// @file test_health_monitor.cpp
/// @brief Unit tests for the HealthMonitor class.

#include <gtest/gtest.h>

#include "ydlidar_driver/health_monitor.hpp"

using ydlidar_driver::HealthLevel;
using ydlidar_driver::HealthMonitor;
using ydlidar_driver::HealthSnapshot;

class HealthMonitorTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    HealthMonitor::Config cfg;
    cfg.window_size = 10;
    cfg.freq_warn_ratio = 0.8;
    cfg.freq_error_ratio = 0.5;
    cfg.invalid_point_warn_ratio = 0.5;
    cfg.invalid_point_error_ratio = 0.8;
    cfg.consecutive_failure_limit = 5;
    cfg.reconnect_threshold = 10;
    cfg.expected_freq_hz = 10.0;
    monitor_ = std::make_unique<HealthMonitor>(cfg);
  }

  std::unique_ptr<HealthMonitor> monitor_;
};

TEST_F(HealthMonitorTest, InitialStateIsStale)
{
  auto health = monitor_->get_health();
  EXPECT_EQ(health.level, HealthLevel::kStale);
  EXPECT_EQ(health.total_scans, 0u);
}

TEST_F(HealthMonitorTest, SingleGoodScanIsOk)
{
  monitor_->record_scan(500, 10, 10.0);
  auto health = monitor_->get_health();
  EXPECT_EQ(health.level, HealthLevel::kOk);
  EXPECT_EQ(health.total_scans, 1u);
  EXPECT_DOUBLE_EQ(health.actual_scan_freq_hz, 10.0);
}

TEST_F(HealthMonitorTest, LowFrequencyWarns)
{
  // Record scans at 7 Hz (below 80% of 10 Hz)
  for (int i = 0; i < 5; ++i) {
    monitor_->record_scan(500, 10, 7.0);
  }
  auto health = monitor_->get_health();
  EXPECT_EQ(health.level, HealthLevel::kWarn);
}

TEST_F(HealthMonitorTest, CriticallyLowFrequencyErrors)
{
  // Record scans at 4 Hz (below 50% of 10 Hz)
  for (int i = 0; i < 5; ++i) {
    monitor_->record_scan(500, 10, 4.0);
  }
  auto health = monitor_->get_health();
  EXPECT_EQ(health.level, HealthLevel::kError);
}

TEST_F(HealthMonitorTest, HighInvalidRatioWarns)
{
  // 60% invalid points (above 50% threshold)
  for (int i = 0; i < 5; ++i) {
    monitor_->record_scan(100, 60, 10.0);
  }
  auto health = monitor_->get_health();
  EXPECT_EQ(health.level, HealthLevel::kWarn);
}

TEST_F(HealthMonitorTest, VeryHighInvalidRatioErrors)
{
  // 85% invalid points (above 80% threshold)
  for (int i = 0; i < 5; ++i) {
    monitor_->record_scan(100, 85, 10.0);
  }
  auto health = monitor_->get_health();
  EXPECT_EQ(health.level, HealthLevel::kError);
}

TEST_F(HealthMonitorTest, ConsecutiveFailuresError)
{
  // 5 consecutive failures → ERROR
  for (int i = 0; i < 5; ++i) {
    monitor_->record_failure();
  }
  auto health = monitor_->get_health();
  EXPECT_EQ(health.level, HealthLevel::kError);
  EXPECT_EQ(health.consecutive_failures, 5u);
}

TEST_F(HealthMonitorTest, SuccessResetsConsecutiveFailures)
{
  monitor_->record_failure();
  monitor_->record_failure();
  monitor_->record_failure();
  // One success should reset the counter
  monitor_->record_scan(500, 10, 10.0);
  auto health = monitor_->get_health();
  EXPECT_EQ(health.consecutive_failures, 0u);
}

TEST_F(HealthMonitorTest, ShouldReconnectAfterThreshold)
{
  // Default 10 consecutive failures
  for (int i = 0; i < 9; ++i) {
    monitor_->record_failure();
    EXPECT_FALSE(monitor_->should_reconnect());
  }
  monitor_->record_failure();
  EXPECT_TRUE(monitor_->should_reconnect());
}

TEST_F(HealthMonitorTest, ReconnectCountTracking)
{
  monitor_->record_reconnect();
  monitor_->record_reconnect();
  auto health = monitor_->get_health();
  EXPECT_EQ(health.reconnect_count, 2u);
}

TEST_F(HealthMonitorTest, ResetClearsAll)
{
  monitor_->record_scan(500, 10, 10.0);
  monitor_->record_failure();
  monitor_->record_reconnect();
  monitor_->reset();

  auto health = monitor_->get_health();
  EXPECT_EQ(health.level, HealthLevel::kStale);
  EXPECT_EQ(health.total_scans, 0u);
  EXPECT_EQ(health.failed_scans, 0u);
  EXPECT_EQ(health.reconnect_count, 0u);
}

TEST_F(HealthMonitorTest, WindowSlides)
{
  // Fill window (size=10) with good scans at 10 Hz
  for (int i = 0; i < 10; ++i) {
    monitor_->record_scan(500, 10, 10.0);
  }

  // Now add 10 slow scans — window should contain only the new ones
  for (int i = 0; i < 10; ++i) {
    monitor_->record_scan(500, 10, 7.0);
  }

  auto health = monitor_->get_health();
  // Window average should be ~7 Hz now
  EXPECT_NEAR(health.actual_scan_freq_hz, 7.0, 0.1);
  EXPECT_EQ(health.level, HealthLevel::kWarn);
}

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}

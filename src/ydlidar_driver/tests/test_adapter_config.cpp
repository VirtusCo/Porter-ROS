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

/// @file test_adapter_config.cpp
/// @brief Unit tests for AdapterConfig defaults and AdapterResult enum values.
///
/// Validates that the configuration struct has correct production defaults
/// matching the Porter Robot's X4 Pro LIDAR, and that model-specific
/// profiles can be constructed correctly.

#include <gtest/gtest.h>

#include <string>

#include "ydlidar_driver/sdk_adapter.hpp"

using ydlidar_driver::AdapterConfig;
using ydlidar_driver::AdapterResult;

// ═══════════════════════════════════════════════════════════════════════════
// AdapterConfig Default Values
// ═══════════════════════════════════════════════════════════════════════════

class AdapterConfigDefaultsTest : public ::testing::Test
{
protected:
  AdapterConfig config_;  // Default-constructed
};

TEST_F(AdapterConfigDefaultsTest, DefaultPort)
{
  EXPECT_EQ(config_.port, "/dev/ttyUSB0");
}

TEST_F(AdapterConfigDefaultsTest, DefaultBaudrate)
{
  EXPECT_EQ(config_.baudrate, 128000);
}

TEST_F(AdapterConfigDefaultsTest, DefaultAngleRange)
{
  EXPECT_FLOAT_EQ(config_.angle_min, -180.0f);
  EXPECT_FLOAT_EQ(config_.angle_max, 180.0f);
}

TEST_F(AdapterConfigDefaultsTest, DefaultRangeMetres)
{
  EXPECT_FLOAT_EQ(config_.min_range, 0.01f);
  EXPECT_FLOAT_EQ(config_.max_range, 64.0f);
}

TEST_F(AdapterConfigDefaultsTest, DefaultFrequency)
{
  EXPECT_FLOAT_EQ(config_.frequency, 10.0f);
}

TEST_F(AdapterConfigDefaultsTest, DefaultSampleRate)
{
  EXPECT_EQ(config_.samp_rate, 5);
}

TEST_F(AdapterConfigDefaultsTest, DefaultResolutionNotFixed)
{
  EXPECT_FALSE(config_.resolution_fixed);
}

TEST_F(AdapterConfigDefaultsTest, DefaultNotSingleChannel)
{
  // Default is false — must be explicitly set to true for X4 Pro
  EXPECT_FALSE(config_.single_channel);
}

TEST_F(AdapterConfigDefaultsTest, DefaultAutoReconnectEnabled)
{
  EXPECT_TRUE(config_.auto_reconnect);
}

TEST_F(AdapterConfigDefaultsTest, DefaultNotToFLidar)
{
  EXPECT_FALSE(config_.is_tof_lidar);
}

TEST_F(AdapterConfigDefaultsTest, DefaultEmptyIgnoreArray)
{
  EXPECT_EQ(config_.ignore_array, "");
}

TEST_F(AdapterConfigDefaultsTest, DefaultLidarTypeTriangle)
{
  EXPECT_EQ(config_.lidar_type, 1);  // TYPE_TRIANGLE
}

TEST_F(AdapterConfigDefaultsTest, DefaultDeviceTypeSerial)
{
  EXPECT_EQ(config_.device_type, 0);  // YDLIDAR_TYPE_SERIAL
}

TEST_F(AdapterConfigDefaultsTest, DefaultIntensityDisabled)
{
  EXPECT_FALSE(config_.intensity);
}

TEST_F(AdapterConfigDefaultsTest, DefaultIntensityBit)
{
  EXPECT_EQ(config_.intensity_bit, 10);
}

TEST_F(AdapterConfigDefaultsTest, DefaultMotorDtrControlEnabled)
{
  EXPECT_TRUE(config_.support_motor_dtr_ctrl);
}

TEST_F(AdapterConfigDefaultsTest, DefaultHeartbeatDisabled)
{
  EXPECT_FALSE(config_.support_heartbeat);
}

TEST_F(AdapterConfigDefaultsTest, DefaultGlassNoiseDisabled)
{
  EXPECT_FALSE(config_.glass_noise);
}

TEST_F(AdapterConfigDefaultsTest, DefaultSunNoiseDisabled)
{
  EXPECT_FALSE(config_.sun_noise);
}

TEST_F(AdapterConfigDefaultsTest, DefaultAbnormalCheckCount)
{
  EXPECT_EQ(config_.abnormal_check_count, 4);
}

// ═══════════════════════════════════════════════════════════════════════════
// Model-Specific Configuration Profiles
// ═══════════════════════════════════════════════════════════════════════════

TEST(AdapterConfigProfileTest, X4ProProfile)
{
  AdapterConfig cfg;
  cfg.port = "/dev/ttyUSB0";
  cfg.baudrate = 128000;
  cfg.single_channel = true;
  cfg.lidar_type = 1;  // TYPE_TRIANGLE
  cfg.is_tof_lidar = false;
  cfg.intensity = false;
  cfg.samp_rate = 5;
  cfg.max_range = 12.0f;
  cfg.support_motor_dtr_ctrl = true;

  EXPECT_EQ(cfg.baudrate, 128000);
  EXPECT_TRUE(cfg.single_channel);
  EXPECT_EQ(cfg.lidar_type, 1);
  EXPECT_FALSE(cfg.is_tof_lidar);
  EXPECT_FALSE(cfg.intensity);
  EXPECT_EQ(cfg.samp_rate, 5);
  EXPECT_FLOAT_EQ(cfg.max_range, 12.0f);
  EXPECT_TRUE(cfg.support_motor_dtr_ctrl);
}

TEST(AdapterConfigProfileTest, G4Profile)
{
  AdapterConfig cfg;
  cfg.baudrate = 230400;
  cfg.single_channel = false;
  cfg.lidar_type = 1;  // TYPE_TRIANGLE
  cfg.is_tof_lidar = false;
  cfg.intensity = true;
  cfg.samp_rate = 9;
  cfg.max_range = 16.0f;
  cfg.support_motor_dtr_ctrl = false;

  EXPECT_EQ(cfg.baudrate, 230400);
  EXPECT_FALSE(cfg.single_channel);
  EXPECT_TRUE(cfg.intensity);
  EXPECT_EQ(cfg.samp_rate, 9);
  EXPECT_FLOAT_EQ(cfg.max_range, 16.0f);
  EXPECT_FALSE(cfg.support_motor_dtr_ctrl);
}

TEST(AdapterConfigProfileTest, TGSeriesProfile)
{
  AdapterConfig cfg;
  cfg.baudrate = 512000;
  cfg.single_channel = false;
  cfg.lidar_type = 0;  // TYPE_TOF
  cfg.is_tof_lidar = true;
  cfg.intensity = false;
  cfg.samp_rate = 10;
  cfg.max_range = 30.0f;
  cfg.support_motor_dtr_ctrl = false;

  EXPECT_EQ(cfg.baudrate, 512000);
  EXPECT_FALSE(cfg.single_channel);
  EXPECT_EQ(cfg.lidar_type, 0);
  EXPECT_TRUE(cfg.is_tof_lidar);
  EXPECT_FLOAT_EQ(cfg.max_range, 30.0f);
}

TEST(AdapterConfigProfileTest, X2Profile)
{
  AdapterConfig cfg;
  cfg.baudrate = 115200;
  cfg.single_channel = true;
  cfg.lidar_type = 1;
  cfg.samp_rate = 3;
  cfg.max_range = 8.0f;

  EXPECT_EQ(cfg.baudrate, 115200);
  EXPECT_TRUE(cfg.single_channel);
  EXPECT_EQ(cfg.samp_rate, 3);
  EXPECT_FLOAT_EQ(cfg.max_range, 8.0f);
}

// ═══════════════════════════════════════════════════════════════════════════
// AdapterConfig Field Assignment
// ═══════════════════════════════════════════════════════════════════════════

TEST(AdapterConfigFieldTest, PortCanBeChanged)
{
  AdapterConfig cfg;
  cfg.port = "/dev/ttyACM0";
  EXPECT_EQ(cfg.port, "/dev/ttyACM0");
}

TEST(AdapterConfigFieldTest, IgnoreArrayCanBeSet)
{
  AdapterConfig cfg;
  cfg.ignore_array = "-1,1,170,180";
  EXPECT_EQ(cfg.ignore_array, "-1,1,170,180");
}

TEST(AdapterConfigFieldTest, BaudrateAcceptsHighValues)
{
  AdapterConfig cfg;
  cfg.baudrate = 921600;
  EXPECT_EQ(cfg.baudrate, 921600);
}

// ═══════════════════════════════════════════════════════════════════════════
// AdapterResult Enum
// ═══════════════════════════════════════════════════════════════════════════

TEST(AdapterResultTest, SuccessIsZero)
{
  EXPECT_EQ(static_cast<int>(AdapterResult::kSuccess), 0);
}

TEST(AdapterResultTest, ErrorCodesAreDistinct)
{
  // All error codes are unique and sequential
  int s = static_cast<int>(AdapterResult::kSuccess);
  int i = static_cast<int>(AdapterResult::kInitFailed);
  int ss = static_cast<int>(AdapterResult::kScanStartFailed);
  int sr = static_cast<int>(AdapterResult::kScanReadFailed);
  int h = static_cast<int>(AdapterResult::kHealthError);
  int d = static_cast<int>(AdapterResult::kDisconnected);

  EXPECT_NE(s, i);
  EXPECT_NE(i, ss);
  EXPECT_NE(ss, sr);
  EXPECT_NE(sr, h);
  EXPECT_NE(h, d);
}

TEST(AdapterResultTest, AllCodesNonNegative)
{
  EXPECT_GE(static_cast<int>(AdapterResult::kSuccess), 0);
  EXPECT_GE(static_cast<int>(AdapterResult::kInitFailed), 0);
  EXPECT_GE(static_cast<int>(AdapterResult::kScanStartFailed), 0);
  EXPECT_GE(static_cast<int>(AdapterResult::kScanReadFailed), 0);
  EXPECT_GE(static_cast<int>(AdapterResult::kHealthError), 0);
  EXPECT_GE(static_cast<int>(AdapterResult::kDisconnected), 0);
}

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}

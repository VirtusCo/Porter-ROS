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

/// @file sdk_adapter.cpp
/// @brief YDLidar SDK adapter — wraps CYdLidar for ROS 2 integration.
///
/// Provides connect, configure, scan, and disconnect lifecycle with
/// retry logic and exponential backoff. Model-agnostic: all hardware
/// properties are set via AdapterConfig populated from ROS parameters.

#include "ydlidar_driver/sdk_adapter.hpp"

#include <chrono>
#include <cmath>
#include <thread>

namespace ydlidar_driver
{

// Log level constants matching ROS severity
static constexpr int kLogInfo = 0;
static constexpr int kLogWarn = 1;
static constexpr int kLogError = 2;

SdkAdapter::SdkAdapter()
: laser_(std::make_unique<CYdLidar>())
{
}

SdkAdapter::~SdkAdapter()
{
  disconnect();
}

void SdkAdapter::configure(const AdapterConfig & config)
{
  config_ = config;
}

void SdkAdapter::set_log_callback(LogCallback callback)
{
  log_callback_ = std::move(callback);
}

void SdkAdapter::log(int level, const std::string & msg) const
{
  if (log_callback_) {
    log_callback_(level, msg);
  }
}

void SdkAdapter::apply_config_to_sdk()
{
  // ── String properties ──
  laser_->setlidaropt(
    LidarPropSerialPort,
    config_.port.c_str(),
    config_.port.size());

  laser_->setlidaropt(
    LidarPropIgnoreArray,
    config_.ignore_array.c_str(),
    config_.ignore_array.size());

  // ── Integer properties ──
  int i_val = config_.baudrate;
  laser_->setlidaropt(LidarPropSerialBaudrate, &i_val, sizeof(int));

  i_val = config_.lidar_type;
  laser_->setlidaropt(LidarPropLidarType, &i_val, sizeof(int));

  i_val = config_.device_type;
  laser_->setlidaropt(LidarPropDeviceType, &i_val, sizeof(int));

  i_val = config_.samp_rate;
  laser_->setlidaropt(LidarPropSampleRate, &i_val, sizeof(int));

  i_val = config_.abnormal_check_count;
  laser_->setlidaropt(LidarPropAbnormalCheckCount, &i_val, sizeof(int));

  i_val = config_.intensity_bit;
  laser_->setlidaropt(LidarPropIntenstiyBit, &i_val, sizeof(int));

  // ── Float properties (MUST be float, not double — SDK requirement) ──
  float f_val = config_.max_range;
  laser_->setlidaropt(LidarPropMaxRange, &f_val, sizeof(float));

  f_val = config_.min_range;
  laser_->setlidaropt(LidarPropMinRange, &f_val, sizeof(float));

  f_val = config_.angle_max;
  laser_->setlidaropt(LidarPropMaxAngle, &f_val, sizeof(float));

  f_val = config_.angle_min;
  laser_->setlidaropt(LidarPropMinAngle, &f_val, sizeof(float));

  f_val = config_.frequency;
  laser_->setlidaropt(LidarPropScanFrequency, &f_val, sizeof(float));

  // ── Boolean properties ──
  bool b_val = config_.resolution_fixed;
  laser_->setlidaropt(LidarPropFixedResolution, &b_val, sizeof(bool));

  b_val = false;  // No 180° rotation by default
  laser_->setlidaropt(LidarPropReversion, &b_val, sizeof(bool));

  b_val = false;  // Not inverted (clockwise) by default
  laser_->setlidaropt(LidarPropInverted, &b_val, sizeof(bool));

  b_val = config_.auto_reconnect;
  laser_->setlidaropt(LidarPropAutoReconnect, &b_val, sizeof(bool));

  b_val = config_.single_channel;
  laser_->setlidaropt(LidarPropSingleChannel, &b_val, sizeof(bool));

  b_val = config_.intensity;
  laser_->setlidaropt(LidarPropIntenstiy, &b_val, sizeof(bool));

  b_val = config_.support_motor_dtr_ctrl;
  laser_->setlidaropt(LidarPropSupportMotorDtrCtrl, &b_val, sizeof(bool));

  b_val = config_.support_heartbeat;
  laser_->setlidaropt(LidarPropSupportHeartBeat, &b_val, sizeof(bool));

  // ── Optional noise filters ──
  laser_->enableGlassNoise(config_.glass_noise);
  laser_->enableSunNoise(config_.sun_noise);
  laser_->setBottomPriority(true);
}

AdapterResult SdkAdapter::initialize(int max_retries)
{
  if (initialized_) {
    log(kLogWarn, "Already initialized, disconnecting first");
    disconnect();
  }

  // Reset the SDK instance for a clean state
  laser_ = std::make_unique<CYdLidar>();

  // Apply all configuration to the SDK
  apply_config_to_sdk();

  log(kLogInfo,
    "Initializing YDLIDAR on port=" + config_.port +
    " baudrate=" + std::to_string(config_.baudrate) +
    " type=" + std::to_string(config_.lidar_type));

  // Retry loop with exponential backoff
  int backoff_ms = 500;
  for (int attempt = 1; attempt <= max_retries; ++attempt) {
    log(kLogInfo,
      "Connection attempt " + std::to_string(attempt) +
      "/" + std::to_string(max_retries));

    ydlidar::os_init();

    if (laser_->initialize()) {
      initialized_ = true;
      log(kLogInfo, "YDLIDAR initialized successfully");

      // NOTE: Do NOT call getDeviceInfo() here.
      // The SDK already queries device info during initialize().
      // Sending additional serial commands between initialize() and
      // turnOn() can corrupt the protocol state and cause scan start
      // failure on some models (observed on X4 Pro / S2PRO).

      return AdapterResult::kSuccess;
    }

    std::string err = laser_->DescribeError();
    log(kLogWarn,
      "Attempt " + std::to_string(attempt) + " failed: " + err);

    if (attempt < max_retries) {
      log(kLogInfo,
        "Retrying in " + std::to_string(backoff_ms) + " ms...");
      std::this_thread::sleep_for(std::chrono::milliseconds(backoff_ms));
      backoff_ms *= 2;  // Exponential backoff

      // Reset SDK for next attempt
      laser_->disconnecting();
      laser_ = std::make_unique<CYdLidar>();
      apply_config_to_sdk();
    }
  }

  log(kLogError,
    "Failed to initialize YDLIDAR after " +
    std::to_string(max_retries) + " attempts");
  return AdapterResult::kInitFailed;
}

AdapterResult SdkAdapter::start_scan(int max_retries)
{
  if (!initialized_) {
    log(kLogError, "Cannot start scan: not initialized");
    return AdapterResult::kInitFailed;
  }

  if (scanning_) {
    log(kLogWarn, "Scan already running");
    return AdapterResult::kSuccess;
  }

  // Retry loop — the motor needs time to spin up on some models.
  // The SDK's turnOn() starts the motor (DTR) then sends the scan
  // start command. If the motor hasn't reached operating speed,
  // the scan command can fail.
  int backoff_ms = 1000;
  for (int attempt = 1; attempt <= max_retries; ++attempt) {
    log(kLogInfo,
      "Starting YDLIDAR scan (attempt " + std::to_string(attempt) +
      "/" + std::to_string(max_retries) + ")...");

    if (laser_->turnOn()) {
      scanning_ = true;
      log(kLogInfo, "YDLIDAR scan started successfully");
      return AdapterResult::kSuccess;
    }

    std::string err = laser_->DescribeError();
    log(kLogWarn,
      "Scan start attempt " + std::to_string(attempt) +
      " failed: " + err);

    if (attempt < max_retries) {
      log(kLogInfo,
        "Waiting " + std::to_string(backoff_ms) +
        " ms for motor spin-up before retry...");
      std::this_thread::sleep_for(std::chrono::milliseconds(backoff_ms));
      backoff_ms = std::min(backoff_ms * 2, 5000);
    }
  }

  log(kLogError,
    "Failed to start YDLIDAR scan after " +
    std::to_string(max_retries) + " attempts");
  return AdapterResult::kScanStartFailed;
}

void SdkAdapter::stop_scan()
{
  if (scanning_) {
    log(kLogInfo, "Stopping YDLIDAR scan...");
    laser_->turnOff();
    scanning_ = false;
    log(kLogInfo, "YDLIDAR scan stopped");
  }
}

AdapterResult SdkAdapter::read_scan(LaserScan & scan)
{
  if (!scanning_) {
    return AdapterResult::kDisconnected;
  }

  if (laser_->doProcessSimple(scan)) {
    return AdapterResult::kSuccess;
  }

  return AdapterResult::kScanReadFailed;
}

void SdkAdapter::disconnect()
{
  if (scanning_) {
    stop_scan();
  }
  if (initialized_) {
    log(kLogInfo, "Disconnecting YDLIDAR...");
    laser_->disconnecting();
    initialized_ = false;
    log(kLogInfo, "YDLIDAR disconnected");
  }
}

bool SdkAdapter::is_scanning() const
{
  return scanning_;
}

std::string SdkAdapter::get_last_error() const
{
  if (laser_) {
    return laser_->DescribeError();
  }
  return "No SDK instance";
}

bool SdkAdapter::get_device_info(device_info & info) const
{
  if (!laser_ || !initialized_) {
    return false;
  }
  // EPT_Module = 0 for main module info
  return laser_->getDeviceInfo(info, 0);
}

bool SdkAdapter::get_version_info(LidarVersion & version) const
{
  if (!laser_ || !initialized_) {
    return false;
  }
  laser_->GetLidarVersion(version);
  return true;
}

}  // namespace ydlidar_driver

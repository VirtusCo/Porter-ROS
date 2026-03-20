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

#ifndef YDLIDAR_DRIVER__SDK_ADAPTER_HPP_
#define YDLIDAR_DRIVER__SDK_ADAPTER_HPP_

#include <string>
#include <vector>
#include <memory>
#include <functional>

#include "CYdLidar.h"

namespace ydlidar_driver
{

/// @brief Result code from SDK operations.
enum class AdapterResult
{
  kSuccess = 0,
  kInitFailed,
  kScanStartFailed,
  kScanReadFailed,
  kHealthError,
  kDisconnected
};

/// @brief Configuration for the SDK adapter, populated from ROS 2 parameters.
struct AdapterConfig
{
  // Connection
  std::string port = "/dev/ttyUSB0";
  int baudrate = 128000;

  // Scan geometry (degrees — converted to radians internally)
  float angle_min = -180.0f;
  float angle_max = 180.0f;
  float min_range = 0.01f;
  float max_range = 64.0f;

  // Scan behaviour
  float frequency = 10.0f;
  int samp_rate = 5;
  bool resolution_fixed = false;
  bool single_channel = false;
  bool auto_reconnect = true;
  bool is_tof_lidar = false;

  // Angle ignore filter
  std::string ignore_array = "";

  // Model-agnostic type settings
  // TYPE_TRIANGLE=1 for X4 Pro, S2 Pro, G4, G2, etc.
  // TYPE_TOF=0 for TG series, TYPE_GS=3, etc.
  int lidar_type = 1;  // TYPE_TRIANGLE
  int device_type = 0;  // YDLIDAR_TYPE_SERIAL

  // Intensity
  bool intensity = false;
  int intensity_bit = 10;

  // Motor control
  bool support_motor_dtr_ctrl = true;
  bool support_heartbeat = false;

  // Glass/sun noise
  bool glass_noise = false;
  bool sun_noise = false;

  // Abnormal check
  int abnormal_check_count = 4;
};

/// @brief Wraps the YDLidar CYdLidar SDK for use in ROS 2 nodes.
///
/// Handles initialization, scanning, health checks, and clean shutdown.
/// Thread-safe for the scan-read path (SDK handles internal locking).
class SdkAdapter
{
public:
  /// Logger callback type for routing SDK messages to ROS 2 logging.
  using LogCallback = std::function<void(int level, const std::string & msg)>;

  SdkAdapter();
  ~SdkAdapter();

  // Non-copyable, non-movable
  SdkAdapter(const SdkAdapter &) = delete;
  SdkAdapter & operator=(const SdkAdapter &) = delete;

  /// @brief Apply configuration. Must be called before initialize().
  void configure(const AdapterConfig & config);

  /// @brief Set logger callback for diagnostic messages.
  void set_log_callback(LogCallback callback);

  /// @brief Initialize the SDK, connect to device, verify health.
  /// @param max_retries Number of retry attempts (with exponential backoff).
  /// @return AdapterResult::kSuccess on success, error code otherwise.
  AdapterResult initialize(int max_retries = 3);

  /// @brief Start the scan motor and scan thread.
  /// @param max_retries Number of retry attempts (with delay for motor spin-up).
  /// @return AdapterResult::kSuccess on success.
  AdapterResult start_scan(int max_retries = 3);

  /// @brief Stop the scan motor and scan thread.
  void stop_scan();

  /// @brief Read one complete scan from the device.
  /// @param[out] scan Populated with scan data on success.
  /// @return AdapterResult::kSuccess on success.
  AdapterResult read_scan(LaserScan & scan);

  /// @brief Disconnect from the device and release resources.
  void disconnect();

  /// @brief Check if the adapter is currently scanning.
  bool is_scanning() const;

  /// @brief Get the last error description from the SDK.
  std::string get_last_error() const;

  /// @brief Get device information (model, firmware, serial number).
  /// @param[out] info Populated on success.
  /// @return true if info was retrieved.
  bool get_device_info(device_info & info) const;

  /// @brief Get lidar version info.
  /// @param[out] version Populated on success.
  /// @return true if version was retrieved.
  bool get_version_info(LidarVersion & version) const;

private:
  void log(int level, const std::string & msg) const;
  void apply_config_to_sdk();

  std::unique_ptr<CYdLidar> laser_;
  AdapterConfig config_;
  LogCallback log_callback_;
  bool initialized_ = false;
  bool scanning_ = false;
};

}  // namespace ydlidar_driver

#endif  // YDLIDAR_DRIVER__SDK_ADAPTER_HPP_

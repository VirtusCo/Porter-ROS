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

#ifndef YDLIDAR_DRIVER__HEALTH_MONITOR_HPP_
#define YDLIDAR_DRIVER__HEALTH_MONITOR_HPP_

#include <cstdint>
#include <deque>
#include <string>

namespace ydlidar_driver
{

/// @brief Health status levels (matches diagnostic_msgs/DiagnosticStatus).
enum class HealthLevel
{
  kOk = 0,
  kWarn = 1,
  kError = 2,
  kStale = 3
};

/// @brief Snapshot of driver health at a point in time.
struct HealthSnapshot
{
  HealthLevel level = HealthLevel::kOk;
  std::string message = "OK";

  // Scan statistics
  uint64_t total_scans = 0;
  uint64_t failed_scans = 0;
  uint64_t total_points = 0;
  uint64_t invalid_points = 0;

  // Timing
  double actual_scan_freq_hz = 0.0;
  double expected_scan_freq_hz = 0.0;

  // Error tracking
  uint32_t consecutive_failures = 0;
  uint32_t reconnect_count = 0;
};

/// @brief Tracks LIDAR health over a sliding window of recent scans.
///
/// Monitors scan frequency, point validity ratio, consecutive failures,
/// and provides aggregated health status for diagnostics publishing.
class HealthMonitor
{
public:
  /// @brief Configuration for health monitoring thresholds.
  struct Config
  {
    /// Window size for rolling statistics (number of scans).
    size_t window_size = 50;

    /// Minimum acceptable scan frequency ratio (actual/expected).
    /// Below this → WARN.
    double freq_warn_ratio = 0.8;

    /// Critical scan frequency ratio. Below this → ERROR.
    double freq_error_ratio = 0.5;

    /// Maximum acceptable ratio of invalid points per scan.
    /// Above this → WARN.  33% is normal indoors.
    double invalid_point_warn_ratio = 0.5;

    /// Above this → ERROR.
    double invalid_point_error_ratio = 0.8;

    /// Number of consecutive read failures before ERROR.
    uint32_t consecutive_failure_limit = 5;

    /// Number of consecutive read failures before suggesting reconnect.
    uint32_t reconnect_threshold = 10;

    /// Expected scan frequency (Hz) — set from driver config.
    double expected_freq_hz = 10.0;
  };

  HealthMonitor();
  explicit HealthMonitor(const Config & config);

  /// @brief Reset all counters and history.
  void reset();

  /// @brief Update with a successful scan result.
  /// @param point_count Total points in this scan.
  /// @param invalid_count Invalid/out-of-range points in this scan.
  /// @param scan_freq_hz Measured scan frequency.
  void record_scan(size_t point_count, size_t invalid_count, double scan_freq_hz);

  /// @brief Record a scan read failure.
  void record_failure();

  /// @brief Record a reconnection attempt.
  void record_reconnect();

  /// @brief Get current aggregated health status.
  HealthSnapshot get_health() const;

  /// @brief Check if a reconnect should be attempted.
  bool should_reconnect() const;

  /// @brief Update configuration.
  void set_config(const Config & config);

private:
  struct ScanRecord
  {
    size_t point_count = 0;
    size_t invalid_count = 0;
    double freq_hz = 0.0;
    bool success = true;
  };

  Config config_;
  std::deque<ScanRecord> history_;

  uint64_t total_scans_ = 0;
  uint64_t failed_scans_ = 0;
  uint64_t total_points_ = 0;
  uint64_t invalid_points_ = 0;
  uint32_t consecutive_failures_ = 0;
  uint32_t reconnect_count_ = 0;
};

}  // namespace ydlidar_driver

#endif  // YDLIDAR_DRIVER__HEALTH_MONITOR_HPP_

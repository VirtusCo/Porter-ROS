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

/// @file health_monitor.cpp
/// @brief LIDAR health monitoring — sliding-window statistics and status.
///
/// Tracks scan frequency, point validity, and consecutive failures
/// over a configurable window. Used by the driver node to publish
/// diagnostic_msgs/DiagnosticArray.

#include "ydlidar_driver/health_monitor.hpp"

#include <algorithm>
#include <numeric>

namespace ydlidar_driver
{

HealthMonitor::HealthMonitor()
: config_{}
{
}

HealthMonitor::HealthMonitor(const Config & config)
: config_(config)
{
}

void HealthMonitor::reset()
{
  history_.clear();
  total_scans_ = 0;
  failed_scans_ = 0;
  total_points_ = 0;
  invalid_points_ = 0;
  consecutive_failures_ = 0;
  reconnect_count_ = 0;
}

void HealthMonitor::set_config(const Config & config)
{
  config_ = config;
}

void HealthMonitor::record_scan(
  size_t point_count,
  size_t invalid_count,
  double scan_freq_hz)
{
  ScanRecord record;
  record.point_count = point_count;
  record.invalid_count = invalid_count;
  record.freq_hz = scan_freq_hz;
  record.success = true;

  history_.push_back(record);
  while (history_.size() > config_.window_size) {
    history_.pop_front();
  }

  total_scans_++;
  total_points_ += point_count;
  invalid_points_ += invalid_count;
  consecutive_failures_ = 0;  // Reset on success
}

void HealthMonitor::record_failure()
{
  ScanRecord record;
  record.success = false;

  history_.push_back(record);
  while (history_.size() > config_.window_size) {
    history_.pop_front();
  }

  failed_scans_++;
  consecutive_failures_++;
}

void HealthMonitor::record_reconnect()
{
  reconnect_count_++;
}

HealthSnapshot HealthMonitor::get_health() const
{
  HealthSnapshot snap;
  snap.total_scans = total_scans_;
  snap.failed_scans = failed_scans_;
  snap.total_points = total_points_;
  snap.invalid_points = invalid_points_;
  snap.consecutive_failures = consecutive_failures_;
  snap.reconnect_count = reconnect_count_;
  snap.expected_scan_freq_hz = config_.expected_freq_hz;

  // If no data yet → STALE
  if (history_.empty()) {
    snap.level = HealthLevel::kStale;
    snap.message = "No scan data received yet";
    return snap;
  }

  // Compute windowed statistics
  size_t window_successes = 0;
  double freq_sum = 0.0;
  size_t freq_count = 0;
  size_t window_points = 0;
  size_t window_invalid = 0;

  for (const auto & rec : history_) {
    if (rec.success) {
      window_successes++;
      freq_sum += rec.freq_hz;
      freq_count++;
      window_points += rec.point_count;
      window_invalid += rec.invalid_count;
    }
  }

  // Average scan frequency over the window
  if (freq_count > 0) {
    snap.actual_scan_freq_hz = freq_sum / static_cast<double>(freq_count);
  }

  // ── Check consecutive failures (highest priority) ──
  if (consecutive_failures_ >= config_.consecutive_failure_limit) {
    snap.level = HealthLevel::kError;
    snap.message = "Consecutive scan failures: " +
      std::to_string(consecutive_failures_);
    return snap;
  }

  // ── Check scan frequency ──
  if (config_.expected_freq_hz > 0.0 && freq_count > 0) {
    double freq_ratio = snap.actual_scan_freq_hz / config_.expected_freq_hz;

    if (freq_ratio < config_.freq_error_ratio) {
      snap.level = HealthLevel::kError;
      snap.message = "Scan frequency critically low: " +
        std::to_string(snap.actual_scan_freq_hz) + " Hz (expected " +
        std::to_string(config_.expected_freq_hz) + " Hz)";
      return snap;
    }

    if (freq_ratio < config_.freq_warn_ratio) {
      snap.level = HealthLevel::kWarn;
      snap.message = "Scan frequency below target: " +
        std::to_string(snap.actual_scan_freq_hz) + " Hz (expected " +
        std::to_string(config_.expected_freq_hz) + " Hz)";
      return snap;
    }
  }

  // ── Check invalid point ratio ──
  if (window_points > 0) {
    double invalid_ratio =
      static_cast<double>(window_invalid) / static_cast<double>(window_points);

    if (invalid_ratio > config_.invalid_point_error_ratio) {
      snap.level = HealthLevel::kError;
      snap.message = "Too many invalid points: " +
        std::to_string(static_cast<int>(invalid_ratio * 100)) + "%";
      return snap;
    }

    if (invalid_ratio > config_.invalid_point_warn_ratio) {
      snap.level = HealthLevel::kWarn;
      snap.message = "High invalid point ratio: " +
        std::to_string(static_cast<int>(invalid_ratio * 100)) + "%";
      return snap;
    }
  }

  // ── All checks passed ──
  snap.level = HealthLevel::kOk;
  snap.message = "OK — " +
    std::to_string(snap.actual_scan_freq_hz).substr(0, 5) + " Hz, " +
    std::to_string(total_scans_) + " scans";
  return snap;
}

bool HealthMonitor::should_reconnect() const
{
  return consecutive_failures_ >= config_.reconnect_threshold;
}

}  // namespace ydlidar_driver

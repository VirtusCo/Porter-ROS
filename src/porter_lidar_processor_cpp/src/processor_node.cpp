// Copyright 2026 VirtusCo. All rights reserved.
// Proprietary and confidential.
//
// Implementation of the LIDAR processor node.
// Applies a 6-stage filter pipeline to raw LaserScan data:
//   1. Range clamp     — discard out-of-spec values
//   2. Outlier reject  — MAD-based spike removal
//   3. Median filter   — salt-and-pepper noise reduction
//   4. EMA smoothing   — temporal smoothing across scans
//   5. ROI crop        — angular region of interest
//   6. Downsample      — reduce point density
//
// Target: < 2ms per scan on Raspberry Pi 5.

#include "porter_lidar_processor/processor_node.hpp"
#include "porter_lidar_processor/filters.hpp"

#include <chrono>
#include <string>
#include <vector>

#include "diagnostic_msgs/msg/diagnostic_status.hpp"
#include "diagnostic_msgs/msg/key_value.hpp"

namespace porter_lidar_processor
{

ProcessorNode::ProcessorNode()
: Node("lidar_processor_node"),
  scan_count_(0),
  processing_time_ms_avg_(0.0)
{
  // ── Declare all parameters with typed defaults ──────────────────────────
  min_range_ = this->declare_parameter<double>("min_range", 0.12);
  max_range_ = this->declare_parameter<double>("max_range", 12.0);
  outlier_threshold_ = this->declare_parameter<double>("outlier_threshold", 3.0);
  median_window_ = this->declare_parameter<int>("median_window", 5);
  smoothing_alpha_ = this->declare_parameter<double>("smoothing_alpha", 0.3);
  roi_angle_min_ = this->declare_parameter<double>("roi_angle_min", -3.14159);
  roi_angle_max_ = this->declare_parameter<double>("roi_angle_max", 3.14159);
  downsample_factor_ = this->declare_parameter<int>("downsample_factor", 1);
  enable_range_clamp_ = this->declare_parameter<bool>("enable_range_clamp", true);
  enable_outlier_rejection_ = this->declare_parameter<bool>("enable_outlier_rejection", true);
  enable_median_ = this->declare_parameter<bool>("enable_median", true);
  enable_smoothing_ = this->declare_parameter<bool>("enable_smoothing", true);
  enable_roi_crop_ = this->declare_parameter<bool>("enable_roi_crop", false);
  enable_downsample_ = this->declare_parameter<bool>("enable_downsample", false);

  // ── QoS: SensorDataQoS with RELIABLE override ──────────────────────────
  // Matches ydlidar_driver publisher and RViz2 subscriber expectations.
  auto scan_qos = rclcpp::SensorDataQoS();
  scan_qos.reliable();

  // ── Subscriber ──────────────────────────────────────────────────────────
  scan_sub_ = this->create_subscription<sensor_msgs::msg::LaserScan>(
    "scan", scan_qos,
    std::bind(&ProcessorNode::on_scan, this, std::placeholders::_1));

  // ── Publishers ──────────────────────────────────────────────────────────
  scan_pub_ = this->create_publisher<sensor_msgs::msg::LaserScan>(
    "scan/processed", scan_qos);

  diag_pub_ = this->create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
    "/diagnostics", 10);

  // ── Diagnostics timer: every 2 seconds ──────────────────────────────────
  diag_timer_ = this->create_wall_timer(
    std::chrono::seconds(2),
    std::bind(&ProcessorNode::publish_diagnostics, this));

  // ── Initialise last_scan_time_ ──────────────────────────────────────────
  last_scan_time_ = this->now();

  RCLCPP_INFO(
    this->get_logger(),
    "Porter LIDAR Processor (C++) started — "
    "clamp=%s outlier=%s median=%s smooth=%s roi=%s downsample=%s",
    enable_range_clamp_ ? "ON" : "OFF",
    enable_outlier_rejection_ ? "ON" : "OFF",
    enable_median_ ? "ON" : "OFF",
    enable_smoothing_ ? "ON" : "OFF",
    enable_roi_crop_ ? "ON" : "OFF",
    enable_downsample_ ? "ON" : "OFF");
}

// ═══════════════════════════════════════════════════════════════════════════════
// Scan processing callback
// ═══════════════════════════════════════════════════════════════════════════════

void ProcessorNode::on_scan(const sensor_msgs::msg::LaserScan::SharedPtr msg)
{
  const auto t_start = std::chrono::high_resolution_clock::now();

  // Work on a mutable copy of ranges
  std::vector<float> ranges(msg->ranges.begin(), msg->ranges.end());

  // ── Filter pipeline (each stage is optional) ───────────────────────────

  // 1. Range clamp — discard physically impossible values first
  if (enable_range_clamp_) {
    ranges = range_clamp(
      ranges,
      static_cast<float>(min_range_),
      static_cast<float>(max_range_));
  }

  // 2. Outlier rejection — remove spikes before smoothing
  if (enable_outlier_rejection_) {
    ranges = outlier_rejection(
      ranges,
      static_cast<float>(outlier_threshold_));
  }

  // 3. Median filter — denoise
  if (enable_median_) {
    ranges = median_filter(ranges, median_window_);
  }

  // 4. Exponential moving average smoothing — temporal consistency
  if (enable_smoothing_) {
    ranges = exponential_smoothing(
      ranges,
      previous_ranges_,
      static_cast<float>(smoothing_alpha_));
  }

  // 5. ROI crop — restrict angular field of view
  if (enable_roi_crop_) {
    ranges = roi_crop(
      ranges,
      msg->angle_min,
      msg->angle_increment,
      static_cast<float>(roi_angle_min_),
      static_cast<float>(roi_angle_max_));
  }

  // 6. Downsample — reduce point density
  if (enable_downsample_) {
    ranges = downsample(ranges, downsample_factor_);
  }

  // Store for next EMA iteration
  previous_ranges_ = ranges;

  // ── Build output message ────────────────────────────────────────────────
  auto out = sensor_msgs::msg::LaserScan();
  out.header = msg->header;
  out.angle_min = msg->angle_min;
  out.angle_max = msg->angle_max;
  out.angle_increment = msg->angle_increment;
  out.time_increment = msg->time_increment;
  out.scan_time = msg->scan_time;
  out.range_min = msg->range_min;
  out.range_max = msg->range_max;
  out.ranges = std::move(ranges);

  // Copy intensities if present
  if (!msg->intensities.empty()) {
    out.intensities = msg->intensities;
  }

  scan_pub_->publish(out);

  // ── Timing ──────────────────────────────────────────────────────────────
  const auto t_end = std::chrono::high_resolution_clock::now();
  const double elapsed_ms =
    std::chrono::duration<double, std::milli>(t_end - t_start).count();

  // Exponential moving average of processing time
  ++scan_count_;
  if (scan_count_ == 1) {
    processing_time_ms_avg_ = elapsed_ms;
  } else {
    processing_time_ms_avg_ = 0.95 * processing_time_ms_avg_ + 0.05 * elapsed_ms;
  }

  last_scan_time_ = this->now();

  // Warn if processing time exceeds 5ms (target < 2ms on RPi 5)
  if (elapsed_ms > 5.0) {
    RCLCPP_WARN(
      this->get_logger(),
      "Scan processing took %.2f ms (target < 2ms)", elapsed_ms);
  }

  // Log first scan
  if (scan_count_ == 1) {
    RCLCPP_INFO(
      this->get_logger(),
      "First processed scan published (%zu points, %.2f ms)",
      out.ranges.size(), elapsed_ms);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Diagnostics publisher
// ═══════════════════════════════════════════════════════════════════════════════

void ProcessorNode::publish_diagnostics()
{
  auto diag_msg = diagnostic_msgs::msg::DiagnosticArray();
  diag_msg.header.stamp = this->now();

  auto status = diagnostic_msgs::msg::DiagnosticStatus();
  status.name = "porter_lidar_processor_cpp: scan_pipeline";
  status.hardware_id = "lidar_processor";

  if (scan_count_ == 0) {
    status.level = diagnostic_msgs::msg::DiagnosticStatus::WARN;
    status.message = "No scans received yet";
  } else {
    status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
    status.message = "Filter pipeline active";
  }

  // Key-value pairs
  auto kv_count = diagnostic_msgs::msg::KeyValue();
  kv_count.key = "scans_processed";
  kv_count.value = std::to_string(scan_count_);
  status.values.push_back(kv_count);

  auto kv_time = diagnostic_msgs::msg::KeyValue();
  kv_time.key = "avg_processing_ms";
  kv_time.value = std::to_string(processing_time_ms_avg_);
  status.values.push_back(kv_time);

  // Compute scan rate from last_scan_time
  const double age_s = (this->now() - last_scan_time_).seconds();
  auto kv_age = diagnostic_msgs::msg::KeyValue();
  kv_age.key = "last_scan_age_s";
  kv_age.value = std::to_string(age_s);
  status.values.push_back(kv_age);

  // Report valid point ratio from the most recent processed scan
  if (!previous_ranges_.empty()) {
    const auto stats = compute_stats(previous_ranges_);

    auto kv_valid = diagnostic_msgs::msg::KeyValue();
    kv_valid.key = "valid_point_ratio";
    kv_valid.value = std::to_string(
      1.0f - stats.invalid_ratio);
    status.values.push_back(kv_valid);

    auto kv_total = diagnostic_msgs::msg::KeyValue();
    kv_total.key = "total_points";
    kv_total.value = std::to_string(stats.total);
    status.values.push_back(kv_total);
  }

  // Active filters summary
  std::string active_filters;
  if (enable_range_clamp_) {active_filters += "clamp ";}
  if (enable_outlier_rejection_) {active_filters += "outlier ";}
  if (enable_median_) {active_filters += "median ";}
  if (enable_smoothing_) {active_filters += "smooth ";}
  if (enable_roi_crop_) {active_filters += "roi ";}
  if (enable_downsample_) {active_filters += "downsample ";}
  if (active_filters.empty()) {active_filters = "none";}

  auto kv_filters = diagnostic_msgs::msg::KeyValue();
  kv_filters.key = "active_filters";
  kv_filters.value = active_filters;
  status.values.push_back(kv_filters);

  // Stale scan warning
  if (scan_count_ > 0 && age_s > 5.0) {
    status.level = diagnostic_msgs::msg::DiagnosticStatus::WARN;
    status.message = "No scan received for " + std::to_string(age_s) + " seconds";
  }

  diag_msg.status.push_back(status);
  diag_pub_->publish(diag_msg);
}

}  // namespace porter_lidar_processor

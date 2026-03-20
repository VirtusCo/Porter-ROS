// Copyright 2026 VirtusCo. All rights reserved.
// Proprietary and confidential.
//
// ROS 2 LIDAR processor node for Porter Robot.
// Subscribes to /scan, applies a configurable 6-stage filter pipeline,
// publishes /scan/processed and periodic /diagnostics.

#pragma once

#include <chrono>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"
#include "diagnostic_msgs/msg/diagnostic_array.hpp"

namespace porter_lidar_processor
{

class ProcessorNode : public rclcpp::Node
{
public:
  ProcessorNode();

private:
  /// Callback for incoming raw LaserScan messages.
  void on_scan(const sensor_msgs::msg::LaserScan::SharedPtr msg);

  /// Publish diagnostic information (called by timer every 2 seconds).
  void publish_diagnostics();

  // ── Parameters (all declared with typed defaults) ────────────────────────
  double min_range_;
  double max_range_;
  double outlier_threshold_;
  int median_window_;
  double smoothing_alpha_;
  double roi_angle_min_;
  double roi_angle_max_;
  int downsample_factor_;
  bool enable_range_clamp_;
  bool enable_outlier_rejection_;
  bool enable_median_;
  bool enable_smoothing_;
  bool enable_roi_crop_;
  bool enable_downsample_;

  // ── State ────────────────────────────────────────────────────────────────
  std::vector<float> previous_ranges_;
  rclcpp::Time last_scan_time_;
  size_t scan_count_;
  double processing_time_ms_avg_;

  // ── ROS 2 interfaces ────────────────────────────────────────────────────
  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr scan_sub_;
  rclcpp::Publisher<sensor_msgs::msg::LaserScan>::SharedPtr scan_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diag_pub_;
  rclcpp::TimerBase::SharedPtr diag_timer_;
};

}  // namespace porter_lidar_processor

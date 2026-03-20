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

/// @file ydlidar_node.cpp
/// @brief ROS 2 Jazzy YDLIDAR driver node — publishes LaserScan and diagnostics.
///
/// Production-grade, model-agnostic driver for the Porter Robot.
/// Supports YDLIDAR X4 Pro 360°, S2 Pro, G4, and other models via
/// YAML parameter configuration. Uses SensorDataQoS for scan data
/// and publishes health/diagnostics for the orchestration layer.

#include <chrono>
#include <cmath>
#include <memory>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"
#include "diagnostic_msgs/msg/diagnostic_array.hpp"
#include "diagnostic_msgs/msg/diagnostic_status.hpp"
#include "diagnostic_msgs/msg/key_value.hpp"

#include "ydlidar_driver/sdk_adapter.hpp"
#include "ydlidar_driver/health_monitor.hpp"

namespace ydlidar_driver
{

class YdlidarNode : public rclcpp::Node
{
public:
  YdlidarNode()
  : Node("ydlidar_node"),
    adapter_(std::make_unique<SdkAdapter>()),
    health_monitor_()
  {
    // ── Declare all parameters with typed defaults ────────────────────────
    declare_parameters();

    // ── Create publishers ────────────────────────────────────────────────
    // Use SensorDataQoS (BEST_EFFORT + KEEP_LAST) but override reliability
    // to RELIABLE so RViz2 (which subscribes RELIABLE) can receive data.
    // This is compatible with Nav2 which accepts both QoS policies.
    auto scan_qos = rclcpp::SensorDataQoS();
    scan_qos.reliable();
    scan_pub_ = this->create_publisher<sensor_msgs::msg::LaserScan>(
      "scan", scan_qos);

    diag_pub_ = this->create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
      "diagnostics", rclcpp::SystemDefaultsQoS());

    // ── Configure SDK adapter from parameters ────────────────────────────
    configure_adapter();

    // ── Configure health monitor ─────────────────────────────────────────
    configure_health_monitor();

    // ── Route SDK logs to ROS 2 logging ──────────────────────────────────
    adapter_->set_log_callback(
      [this](int level, const std::string & msg) {
        switch (level) {
          case 0:
            RCLCPP_INFO(this->get_logger(), "[SDK] %s", msg.c_str());
            break;
          case 1:
            RCLCPP_WARN(this->get_logger(), "[SDK] %s", msg.c_str());
            break;
          default:
            RCLCPP_ERROR(this->get_logger(), "[SDK] %s", msg.c_str());
            break;
        }
      });

    // ── Initialize and start scanning ────────────────────────────────────
    if (!initialize_and_start()) {
      RCLCPP_FATAL(
        this->get_logger(),
        "Failed to initialize YDLIDAR — node will shut down");
      // Schedule shutdown outside the constructor to avoid
      // destroying context while node is still being constructed.
      shutdown_timer_ = this->create_wall_timer(
        std::chrono::milliseconds(100),
        [this]() {
          shutdown_timer_->cancel();
          rclcpp::shutdown();
        });
      return;
    }

    // ── Create scan timer ────────────────────────────────────────────────
    double frequency = this->get_parameter("frequency").as_double();
    auto period = std::chrono::duration<double>(1.0 / frequency);
    scan_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      std::bind(&YdlidarNode::scan_callback, this));

    // ── Create diagnostics timer (1 Hz) ──────────────────────────────────
    diag_timer_ = this->create_wall_timer(
      std::chrono::seconds(1),
      std::bind(&YdlidarNode::diagnostics_callback, this));

    RCLCPP_INFO(
      this->get_logger(),
      "YDLIDAR node started — publishing /scan at %.1f Hz", frequency);
  }

  ~YdlidarNode() override
  {
    RCLCPP_INFO(this->get_logger(), "Shutting down YDLIDAR node...");
    adapter_->stop_scan();
    adapter_->disconnect();
    RCLCPP_INFO(this->get_logger(), "YDLIDAR node shutdown complete");
  }

private:
  // ══════════════════════════════════════════════════════════════════════════
  // Parameter Declaration
  // ══════════════════════════════════════════════════════════════════════════

  void declare_parameters()
  {
    // Connection
    this->declare_parameter<std::string>("port", "/dev/ttyUSB0");
    this->declare_parameter<int>("baudrate", 128000);
    this->declare_parameter<std::string>("frame_id", "laser_frame");

    // Scan geometry
    this->declare_parameter<double>("frequency", 10.0);
    this->declare_parameter<double>("angle_min", -180.0);
    this->declare_parameter<double>("angle_max", 180.0);
    this->declare_parameter<double>("min_range", 0.01);
    this->declare_parameter<double>("max_range", 64.0);
    this->declare_parameter<int>("samp_rate", 5);

    // Behaviour
    this->declare_parameter<bool>("resolution_fixed", false);
    this->declare_parameter<bool>("singleChannel", true);
    this->declare_parameter<bool>("auto_reconnect", true);
    this->declare_parameter<bool>("isToFLidar", false);
    this->declare_parameter<std::string>("ignore_array", "");

    // Model-agnostic type selection
    // 1 = TYPE_TRIANGLE (X4 Pro, S2 Pro, G4, G2, Tmini)
    // 0 = TYPE_TOF (TG series)
    // 3 = TYPE_GS (GS series)
    this->declare_parameter<int>("lidar_type", 1);
    this->declare_parameter<int>("device_type", 0);  // 0 = SERIAL

    // Intensity
    this->declare_parameter<bool>("intensity", false);
    this->declare_parameter<int>("intensity_bit", 10);

    // Motor control
    this->declare_parameter<bool>("support_motor_dtr_ctrl", true);
    this->declare_parameter<bool>("support_heartbeat", false);

    // Noise filters
    this->declare_parameter<bool>("glass_noise", false);
    this->declare_parameter<bool>("sun_noise", false);

    // Health monitoring
    this->declare_parameter<int>("abnormal_check_count", 4);
    this->declare_parameter<int>("health_window_size", 50);
    this->declare_parameter<double>("health_freq_warn_ratio", 0.8);
    this->declare_parameter<double>("health_freq_error_ratio", 0.5);
    this->declare_parameter<double>("health_invalid_warn_ratio", 0.5);
    this->declare_parameter<double>("health_invalid_error_ratio", 0.8);
    this->declare_parameter<int>("health_consecutive_failure_limit", 5);
    this->declare_parameter<int>("health_reconnect_threshold", 10);
    // health_expected_freq: 0 = use 'frequency' param; >0 = override.
    // S2PRO motor spins at 10 Hz but scan delivery rate is ~4 Hz.
    this->declare_parameter<double>("health_expected_freq", 0.0);

    // Retry settings
    this->declare_parameter<int>("init_max_retries", 3);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // Configuration
  // ══════════════════════════════════════════════════════════════════════════

  void configure_adapter()
  {
    AdapterConfig cfg;
    cfg.port = this->get_parameter("port").as_string();
    cfg.baudrate = this->get_parameter("baudrate").as_int();
    cfg.angle_min = static_cast<float>(this->get_parameter("angle_min").as_double());
    cfg.angle_max = static_cast<float>(this->get_parameter("angle_max").as_double());
    cfg.min_range = static_cast<float>(this->get_parameter("min_range").as_double());
    cfg.max_range = static_cast<float>(this->get_parameter("max_range").as_double());
    cfg.frequency = static_cast<float>(this->get_parameter("frequency").as_double());
    cfg.samp_rate = this->get_parameter("samp_rate").as_int();
    cfg.resolution_fixed = this->get_parameter("resolution_fixed").as_bool();
    cfg.single_channel = this->get_parameter("singleChannel").as_bool();
    cfg.auto_reconnect = this->get_parameter("auto_reconnect").as_bool();
    cfg.is_tof_lidar = this->get_parameter("isToFLidar").as_bool();
    cfg.ignore_array = this->get_parameter("ignore_array").as_string();
    cfg.lidar_type = this->get_parameter("lidar_type").as_int();
    cfg.device_type = this->get_parameter("device_type").as_int();
    cfg.intensity = this->get_parameter("intensity").as_bool();
    cfg.intensity_bit = this->get_parameter("intensity_bit").as_int();
    cfg.support_motor_dtr_ctrl = this->get_parameter("support_motor_dtr_ctrl").as_bool();
    cfg.support_heartbeat = this->get_parameter("support_heartbeat").as_bool();
    cfg.glass_noise = this->get_parameter("glass_noise").as_bool();
    cfg.sun_noise = this->get_parameter("sun_noise").as_bool();
    cfg.abnormal_check_count = this->get_parameter("abnormal_check_count").as_int();

    // Override lidar_type if isToFLidar is set (convenience parameter)
    if (cfg.is_tof_lidar) {
      cfg.lidar_type = 0;  // TYPE_TOF
    }

    frame_id_ = this->get_parameter("frame_id").as_string();

    RCLCPP_INFO(this->get_logger(),
      "Configuration: port=%s baudrate=%d frame=%s freq=%.1f Hz "
      "angle=[%.1f, %.1f] range=[%.2f, %.2f] type=%d singleChannel=%s",
      cfg.port.c_str(), cfg.baudrate, frame_id_.c_str(),
      cfg.frequency, cfg.angle_min, cfg.angle_max,
      cfg.min_range, cfg.max_range, cfg.lidar_type,
      cfg.single_channel ? "true" : "false");

    adapter_->configure(cfg);
  }

  void configure_health_monitor()
  {
    HealthMonitor::Config hcfg;
    hcfg.window_size = static_cast<size_t>(
      this->get_parameter("health_window_size").as_int());
    hcfg.freq_warn_ratio = this->get_parameter("health_freq_warn_ratio").as_double();
    hcfg.freq_error_ratio = this->get_parameter("health_freq_error_ratio").as_double();
    hcfg.invalid_point_warn_ratio =
      this->get_parameter("health_invalid_warn_ratio").as_double();
    hcfg.invalid_point_error_ratio =
      this->get_parameter("health_invalid_error_ratio").as_double();
    hcfg.consecutive_failure_limit = static_cast<uint32_t>(
      this->get_parameter("health_consecutive_failure_limit").as_int());
    hcfg.reconnect_threshold = static_cast<uint32_t>(
      this->get_parameter("health_reconnect_threshold").as_int());

    // Use explicit health_expected_freq if set, otherwise fall back to frequency.
    // On S2PRO: motor targets 10 Hz but SDK scan delivery is ~4 Hz.
    double health_freq = this->get_parameter("health_expected_freq").as_double();
    if (health_freq <= 0.0) {
      health_freq = this->get_parameter("frequency").as_double();
    }
    hcfg.expected_freq_hz = health_freq;

    RCLCPP_INFO(this->get_logger(),
      "Health monitor: expected_freq=%.1f Hz, freq_warn_ratio=%.2f, freq_error_ratio=%.2f",
      hcfg.expected_freq_hz, hcfg.freq_warn_ratio, hcfg.freq_error_ratio);

    health_monitor_.set_config(hcfg);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // Initialization
  // ══════════════════════════════════════════════════════════════════════════

  bool initialize_and_start()
  {
    int max_retries = this->get_parameter("init_max_retries").as_int();

    auto result = adapter_->initialize(max_retries);
    if (result != AdapterResult::kSuccess) {
      RCLCPP_ERROR(this->get_logger(),
        "YDLIDAR initialization failed: %s",
        adapter_->get_last_error().c_str());
      return false;
    }

    result = adapter_->start_scan(max_retries);
    if (result != AdapterResult::kSuccess) {
      RCLCPP_ERROR(this->get_logger(),
        "Failed to start YDLIDAR scan: %s",
        adapter_->get_last_error().c_str());
      return false;
    }

    return true;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // Scan Callback — Main Loop
  // ══════════════════════════════════════════════════════════════════════════

  void scan_callback()
  {
    LaserScan sdk_scan;
    auto result = adapter_->read_scan(sdk_scan);

    if (result != AdapterResult::kSuccess) {
      health_monitor_.record_failure();

      // Check if we should attempt reconnection
      if (health_monitor_.should_reconnect()) {
        RCLCPP_WARN(this->get_logger(),
          "Too many consecutive failures — attempting reconnect...");
        attempt_reconnect();
      }
      return;
    }

    // ── Convert SDK LaserScan → ROS 2 LaserScan ──────────────────────────
    auto scan_msg = std::make_unique<sensor_msgs::msg::LaserScan>();

    // Header
    scan_msg->header.stamp.sec =
      static_cast<int32_t>(sdk_scan.stamp / 1000000000UL);
    scan_msg->header.stamp.nanosec =
      static_cast<uint32_t>(sdk_scan.stamp % 1000000000UL);
    scan_msg->header.frame_id = frame_id_;

    // Scan geometry (SDK provides these in radians already)
    scan_msg->angle_min = sdk_scan.config.min_angle;
    scan_msg->angle_max = sdk_scan.config.max_angle;
    scan_msg->angle_increment = sdk_scan.config.angle_increment;
    scan_msg->scan_time = sdk_scan.config.scan_time;
    scan_msg->time_increment = sdk_scan.config.time_increment;
    scan_msg->range_min = sdk_scan.config.min_range;
    scan_msg->range_max = sdk_scan.config.max_range;

    // Compute array size from geometry
    int size = 0;
    if (sdk_scan.config.angle_increment > 0.0f) {
      size = static_cast<int>(std::ceil(
          (sdk_scan.config.max_angle - sdk_scan.config.min_angle) /
          sdk_scan.config.angle_increment)) + 1;
    }

    if (size <= 0) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
        "Invalid scan geometry: angle_increment=%.6f",
        sdk_scan.config.angle_increment);
      health_monitor_.record_failure();
      return;
    }

    // Initialize arrays with NaN (standard for no-return)
    scan_msg->ranges.assign(size, std::numeric_limits<float>::quiet_NaN());
    scan_msg->intensities.assign(size, 0.0f);

    // Place each point into the correct angular bin
    size_t invalid_count = 0;
    for (const auto & point : sdk_scan.points) {
      int index = static_cast<int>(std::ceil(
          (point.angle - sdk_scan.config.min_angle) /
          sdk_scan.config.angle_increment));

      if (index >= 0 && index < size) {
        if (point.range >= sdk_scan.config.min_range &&
          point.range <= sdk_scan.config.max_range)
        {
          scan_msg->ranges[index] = point.range;
          scan_msg->intensities[index] = point.intensity;
        } else {
          invalid_count++;
        }
      }
    }

    // Publish
    scan_pub_->publish(std::move(scan_msg));

    // Update health monitor
    health_monitor_.record_scan(
      sdk_scan.points.size(),
      invalid_count,
      static_cast<double>(sdk_scan.scanFreq));
  }

  // ══════════════════════════════════════════════════════════════════════════
  // Diagnostics Callback (1 Hz)
  // ══════════════════════════════════════════════════════════════════════════

  void diagnostics_callback()
  {
    auto health = health_monitor_.get_health();

    auto diag_msg = std::make_unique<diagnostic_msgs::msg::DiagnosticArray>();
    diag_msg->header.stamp = this->now();

    diagnostic_msgs::msg::DiagnosticStatus status;
    status.name = "ydlidar_driver: LIDAR";
    status.hardware_id = frame_id_;

    // Map health level to diagnostic status level
    switch (health.level) {
      case HealthLevel::kOk:
        status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
        break;
      case HealthLevel::kWarn:
        status.level = diagnostic_msgs::msg::DiagnosticStatus::WARN;
        break;
      case HealthLevel::kError:
        status.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
        break;
      case HealthLevel::kStale:
        status.level = diagnostic_msgs::msg::DiagnosticStatus::STALE;
        break;
    }
    status.message = health.message;

    // Key-value pairs
    auto make_kv = [](const std::string & key, const std::string & value) {
        diagnostic_msgs::msg::KeyValue kv;
        kv.key = key;
        kv.value = value;
        return kv;
      };

    status.values.push_back(
      make_kv("total_scans", std::to_string(health.total_scans)));
    status.values.push_back(
      make_kv("failed_scans", std::to_string(health.failed_scans)));
    status.values.push_back(
      make_kv("total_points", std::to_string(health.total_points)));
    status.values.push_back(
      make_kv("invalid_points", std::to_string(health.invalid_points)));
    status.values.push_back(
      make_kv("actual_freq_hz",
      std::to_string(health.actual_scan_freq_hz).substr(0, 6)));
    status.values.push_back(
      make_kv("expected_freq_hz",
      std::to_string(health.expected_scan_freq_hz).substr(0, 6)));
    status.values.push_back(
      make_kv("consecutive_failures",
      std::to_string(health.consecutive_failures)));
    status.values.push_back(
      make_kv("reconnect_count", std::to_string(health.reconnect_count)));
    status.values.push_back(
      make_kv("port", this->get_parameter("port").as_string()));
    status.values.push_back(
      make_kv("baudrate",
      std::to_string(this->get_parameter("baudrate").as_int())));

    diag_msg->status.push_back(status);
    diag_pub_->publish(std::move(diag_msg));
  }

  // ══════════════════════════════════════════════════════════════════════════
  // Reconnection
  // ══════════════════════════════════════════════════════════════════════════

  void attempt_reconnect()
  {
    RCLCPP_WARN(this->get_logger(), "Attempting YDLIDAR reconnection...");
    health_monitor_.record_reconnect();

    adapter_->stop_scan();
    adapter_->disconnect();

    // Re-read configuration in case parameters changed
    configure_adapter();

    int max_retries = this->get_parameter("init_max_retries").as_int();
    auto result = adapter_->initialize(max_retries);
    if (result != AdapterResult::kSuccess) {
      RCLCPP_ERROR(this->get_logger(),
        "Reconnection failed: %s", adapter_->get_last_error().c_str());
      return;
    }

    result = adapter_->start_scan(max_retries);
    if (result != AdapterResult::kSuccess) {
      RCLCPP_ERROR(this->get_logger(),
        "Failed to restart scan after reconnect: %s",
        adapter_->get_last_error().c_str());
      return;
    }

    RCLCPP_INFO(this->get_logger(), "YDLIDAR reconnected successfully");
  }

  // ══════════════════════════════════════════════════════════════════════════
  // Members
  // ══════════════════════════════════════════════════════════════════════════

  std::unique_ptr<SdkAdapter> adapter_;
  HealthMonitor health_monitor_;
  std::string frame_id_;

  rclcpp::Publisher<sensor_msgs::msg::LaserScan>::SharedPtr scan_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diag_pub_;

  rclcpp::TimerBase::SharedPtr scan_timer_;
  rclcpp::TimerBase::SharedPtr diag_timer_;
  rclcpp::TimerBase::SharedPtr shutdown_timer_;
};

}  // namespace ydlidar_driver

// ════════════════════════════════════════════════════════════════════════════
// Main
// ════════════════════════════════════════════════════════════════════════════

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<ydlidar_driver::YdlidarNode>();

  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}

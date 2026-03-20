// Copyright 2026 VirtusCo
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
//
// ESP32 Motor Bridge Node — bridges /cmd_vel to ESP32 #1 motor controller
// over USB serial using the Porter binary protocol.

// ARCHITECTURAL NOTE — DO NOT MIGRATE TO PYTHON
//
// This node MUST remain in C++. The 500ms heartbeat watchdog on the ESP32
// motor controller requires sub-millisecond timer callback latency.
// Python's GIL cannot guarantee this under load (Nav2 + inference concurrent).
// A missed heartbeat stops the motors mid-task with passenger luggage loaded.
//
// If you are considering changing this to Python for any reason,
// read Plans/Migration/VIRTUS_LANGUAGE_MIGRATION_PLAN.md section 5 first.

#include <chrono>
#include <cmath>
#include <cstring>
#include <string>
#include <vector>

#include "diagnostic_msgs/msg/diagnostic_array.hpp"
#include "diagnostic_msgs/msg/diagnostic_status.hpp"
#include "diagnostic_msgs/msg/key_value.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

#include "porter_esp32_bridge/serial_port.hpp"

extern "C" {
#include "crc16.h"  // NOLINT(build/include_subdir)
#include "protocol.h"  // NOLINT(build/include_subdir)
}

using namespace std::chrono_literals;

namespace porter_esp32_bridge
{

class Esp32MotorBridge : public rclcpp::Node
{
public:
  Esp32MotorBridge()
  : Node("esp32_motor_bridge")
  {
    // --- Declare parameters ---
    this->declare_parameter<std::string>("port", "/dev/esp32_motors");
    this->declare_parameter<int>("baudrate", 115200);
    this->declare_parameter<double>("heartbeat_interval", 0.2);
    this->declare_parameter<double>("status_poll_interval", 1.0);
    this->declare_parameter<double>("cmd_vel_timeout", 0.5);
    this->declare_parameter<double>("wheel_separation", 0.35);
    this->declare_parameter<double>("wheel_radius", 0.05);
    this->declare_parameter<double>("max_speed_pct", 100.0);
    this->declare_parameter<double>("reconnect_interval", 3.0);

    port_ = this->get_parameter("port").as_string();
    baudrate_ = this->get_parameter("baudrate").as_int();
    heartbeat_interval_ = this->get_parameter("heartbeat_interval").as_double();
    cmd_vel_timeout_ = this->get_parameter("cmd_vel_timeout").as_double();
    wheel_separation_ = this->get_parameter("wheel_separation").as_double();
    wheel_radius_ = this->get_parameter("wheel_radius").as_double();
    max_speed_pct_ = this->get_parameter("max_speed_pct").as_double();
    reconnect_interval_ = this->get_parameter("reconnect_interval").as_double();

    double status_poll_interval = this->get_parameter("status_poll_interval").as_double();

    // --- Publishers ---
    motor_status_pub_ = this->create_publisher<std_msgs::msg::String>(
      "motor_status", 10);
    diag_pub_ = this->create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
      "/diagnostics", 10);

    // --- Subscriber ---
    cmd_vel_sub_ = this->create_subscription<geometry_msgs::msg::Twist>(
      "cmd_vel", 10,
      std::bind(&Esp32MotorBridge::cmd_vel_callback, this, std::placeholders::_1));

    // --- Initialize protocol parser ---
    protocol_parser_init(&parser_);

    // --- Try initial connection ---
    connect();

    // --- Timers ---
    serial_read_timer_ = this->create_wall_timer(
      10ms, std::bind(&Esp32MotorBridge::serial_read_callback, this));

    heartbeat_timer_ = this->create_wall_timer(
      std::chrono::duration<double>(heartbeat_interval_),
      std::bind(&Esp32MotorBridge::heartbeat_callback, this));

    status_poll_timer_ = this->create_wall_timer(
      std::chrono::duration<double>(status_poll_interval),
      std::bind(&Esp32MotorBridge::status_poll_callback, this));

    cmd_vel_watchdog_timer_ = this->create_wall_timer(
      100ms, std::bind(&Esp32MotorBridge::cmd_vel_watchdog_callback, this));

    reconnect_timer_ = this->create_wall_timer(
      std::chrono::duration<double>(reconnect_interval_),
      std::bind(&Esp32MotorBridge::reconnect_callback, this));

    diag_timer_ = this->create_wall_timer(
      1s, std::bind(&Esp32MotorBridge::publish_diagnostics, this));

    RCLCPP_INFO(this->get_logger(), "ESP32 Motor Bridge started — port: %s, baud: %d",
      port_.c_str(), baudrate_);
  }

  ~Esp32MotorBridge() override
  {
    // Send stop command before shutting down
    if (serial_.is_open()) {
      send_motor_stop();
    }
  }

private:
  // --- Serial connection ---
  SerialPort serial_;
  std::string port_;
  int baudrate_;
  protocol_parser_t parser_;
  bool connected_ = false;

  // --- Parameters ---
  double heartbeat_interval_;
  double cmd_vel_timeout_;
  double wheel_separation_;
  double wheel_radius_;
  double max_speed_pct_;
  double reconnect_interval_;

  // --- Stats ---
  uint32_t packets_sent_ = 0;
  uint32_t packets_received_ = 0;
  uint32_t parse_errors_ = 0;
  uint32_t serial_errors_ = 0;
  rclcpp::Time last_cmd_vel_time_;
  bool cmd_vel_active_ = false;

  // --- ROS interfaces ---
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr motor_status_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diag_pub_;
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr cmd_vel_sub_;

  // --- Timers ---
  rclcpp::TimerBase::SharedPtr serial_read_timer_;
  rclcpp::TimerBase::SharedPtr heartbeat_timer_;
  rclcpp::TimerBase::SharedPtr status_poll_timer_;
  rclcpp::TimerBase::SharedPtr cmd_vel_watchdog_timer_;
  rclcpp::TimerBase::SharedPtr reconnect_timer_;
  rclcpp::TimerBase::SharedPtr diag_timer_;

  // --- Connection ---
  void connect()
  {
    if (serial_.open(port_, baudrate_)) {
      connected_ = true;
      RCLCPP_INFO(this->get_logger(), "Connected to ESP32 motors on %s", port_.c_str());
    } else {
      connected_ = false;
      RCLCPP_WARN(this->get_logger(), "Failed to open %s — will retry", port_.c_str());
    }
  }

  void reconnect_callback()
  {
    if (!connected_) {
      RCLCPP_DEBUG(this->get_logger(), "Attempting reconnect to %s...", port_.c_str());
      connect();
    }
  }

  // --- /cmd_vel subscriber ---
  void cmd_vel_callback(const geometry_msgs::msg::Twist::SharedPtr msg)
  {
    if (!connected_) {
      return;
    }

    last_cmd_vel_time_ = this->now();
    cmd_vel_active_ = true;

    // Differential drive: convert (linear.x, angular.z) to left/right wheel speeds
    double v = msg->linear.x;    // m/s
    double w = msg->angular.z;   // rad/s

    // Wheel speeds in m/s
    double v_left = v - (w * wheel_separation_ / 2.0);
    double v_right = v + (w * wheel_separation_ / 2.0);

    // Convert to percentage of max speed (-100..+100)
    // Assume max wheel speed corresponds to max_speed_pct_ at some reference
    // For now: normalize by a reasonable max (1.0 m/s)
    constexpr double MAX_WHEEL_SPEED = 1.0;  // m/s — tune for your robot
    double left_pct = std::clamp(v_left / MAX_WHEEL_SPEED * 100.0,
      -max_speed_pct_, max_speed_pct_);
    double right_pct = std::clamp(v_right / MAX_WHEEL_SPEED * 100.0,
      -max_speed_pct_, max_speed_pct_);

    send_motor_speed(static_cast<int16_t>(left_pct), static_cast<int16_t>(right_pct), 0);
  }

  // --- Watchdog: stop motors if no cmd_vel for timeout ---
  void cmd_vel_watchdog_callback()
  {
    if (!cmd_vel_active_ || !connected_) {
      return;
    }

    double elapsed = (this->now() - last_cmd_vel_time_).seconds();
    if (elapsed > cmd_vel_timeout_) {
      RCLCPP_WARN(this->get_logger(),
        "cmd_vel timeout (%.2fs) — stopping motors", elapsed);
      send_motor_stop();
      cmd_vel_active_ = false;
    }
  }

  // --- Serial reading (poll at 100 Hz) ---
  void serial_read_callback()
  {
    if (!connected_) {
      return;
    }

    uint8_t buf[256];
    int n = serial_.read(buf, sizeof(buf));

    if (n < 0) {
      serial_errors_++;
      RCLCPP_ERROR(this->get_logger(), "Serial read error — disconnecting");
      serial_.close();
      connected_ = false;
      return;
    }

    for (int i = 0; i < n; i++) {
      bool complete = protocol_parser_feed(&parser_, buf[i]);
      if (complete) {
        handle_packet(parser_.packet);
        protocol_parser_reset(&parser_);
        packets_received_++;
      } else if (parser_.state == PARSE_ERROR) {
        parse_errors_++;
        protocol_parser_reset(&parser_);
      }
    }
  }

  // --- Heartbeat ---
  void heartbeat_callback()
  {
    if (!connected_) {
      return;
    }
    send_command(CMD_HEARTBEAT, nullptr, 0);
  }

  // --- Status poll ---
  void status_poll_callback()
  {
    if (!connected_) {
      return;
    }
    send_command(CMD_MOTOR_STATUS, nullptr, 0);
  }

  // --- Packet handler ---
  void handle_packet(const protocol_packet_t & pkt)
  {
    switch (pkt.command) {
      case CMD_MOTOR_STATUS:
        handle_motor_status(pkt);
        break;
      case CMD_MOTOR_ENCODER:
        handle_motor_encoder(pkt);
        break;
      case CMD_ACK:
        RCLCPP_DEBUG(this->get_logger(), "ACK received for cmd 0x%02X",
          pkt.length > 0 ? pkt.payload[0] : 0);
        break;
      case CMD_NACK:
        RCLCPP_WARN(this->get_logger(), "NACK received: cmd=0x%02X reason=0x%02X",
          pkt.length > 0 ? pkt.payload[0] : 0,
          pkt.length > 1 ? pkt.payload[1] : 0);
        break;
      default:
        RCLCPP_DEBUG(this->get_logger(), "Unknown packet cmd=0x%02X len=%d",
          pkt.command, pkt.length);
        break;
    }
  }

  void handle_motor_status(const protocol_packet_t & pkt)
  {
    // Motor status payload: [state:u8][left_speed:i16][right_speed:i16][fault_flags:u8]
    if (pkt.length < 6) {
      RCLCPP_WARN(this->get_logger(), "Motor status too short: %d bytes", pkt.length);
      return;
    }

    uint8_t state = pkt.payload[0];
    int16_t left_speed;
    int16_t right_speed;
    uint8_t faults = pkt.payload[5];

    std::memcpy(&left_speed, &pkt.payload[1], 2);
    std::memcpy(&right_speed, &pkt.payload[3], 2);

    // Publish as JSON string
    auto msg = std_msgs::msg::String();
    char json[256];
    std::snprintf(json, sizeof(json),
      R"({"state":%d,"left_speed":%d,"right_speed":%d,"faults":%d})",
      state, left_speed, right_speed, faults);
    msg.data = json;
    motor_status_pub_->publish(msg);

    if (faults != 0) {
      RCLCPP_WARN(this->get_logger(), "Motor fault flags: 0x%02X", faults);
    }
  }

  void handle_motor_encoder(const protocol_packet_t & pkt)
  {
    // Encoder payload: [left_ticks:i32][right_ticks:i32]
    if (pkt.length < 8) {
      return;
    }

    int32_t left_ticks, right_ticks;
    std::memcpy(&left_ticks, &pkt.payload[0], 4);
    std::memcpy(&right_ticks, &pkt.payload[4], 4);

    RCLCPP_DEBUG(this->get_logger(), "Encoder: L=%d R=%d", left_ticks, right_ticks);
    // TODO(antony): publish as odometry or encoder topic when encoder hardware is connected
  }

  // --- Send commands ---
  void send_command(uint8_t cmd, const uint8_t * payload, uint8_t payload_len)
  {
    if (!connected_) {
      return;
    }

    uint8_t buf[PROTOCOL_MAX_PACKET_SIZE];
    size_t len = 0;

    if (protocol_encode(cmd, payload, payload_len, buf, &len) != 0) {
      RCLCPP_ERROR(this->get_logger(), "Failed to encode cmd 0x%02X", cmd);
      return;
    }

    int written = serial_.write(buf, len);
    if (written < 0) {
      serial_errors_++;
      RCLCPP_ERROR(this->get_logger(), "Serial write error — disconnecting");
      serial_.close();
      connected_ = false;
      return;
    }
    packets_sent_++;
  }

  void send_motor_speed(int16_t left, int16_t right, uint8_t flags)
  {
    // Payload: [left_i16][right_i16][flags_u8] = 5 bytes
    uint8_t payload[5];
    std::memcpy(&payload[0], &left, 2);
    std::memcpy(&payload[2], &right, 2);
    payload[4] = flags;

    send_command(CMD_MOTOR_SET_SPEED, payload, 5);
  }

  void send_motor_stop()
  {
    send_command(CMD_MOTOR_STOP, nullptr, 0);
  }

  // --- Diagnostics ---
  void publish_diagnostics()
  {
    auto diag_msg = diagnostic_msgs::msg::DiagnosticArray();
    diag_msg.header.stamp = this->now();

    auto status = diagnostic_msgs::msg::DiagnosticStatus();
    status.name = "esp32_motor_bridge";
    status.hardware_id = port_;

    if (connected_) {
      status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
      status.message = "Connected";
    } else {
      status.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
      status.message = "Disconnected";
    }

    auto add_kv = [&status](const std::string & key, const std::string & value) {
        auto kv = diagnostic_msgs::msg::KeyValue();
        kv.key = key;
        kv.value = value;
        status.values.push_back(kv);
      };

    add_kv("connected", connected_ ? "true" : "false");
    add_kv("port", port_);
    add_kv("baudrate", std::to_string(baudrate_));
    add_kv("packets_sent", std::to_string(packets_sent_));
    add_kv("packets_received", std::to_string(packets_received_));
    add_kv("parse_errors", std::to_string(parse_errors_));
    add_kv("serial_errors", std::to_string(serial_errors_));
    add_kv("cmd_vel_active", cmd_vel_active_ ? "true" : "false");

    diag_msg.status.push_back(status);
    diag_pub_->publish(diag_msg);
  }
};

}  // namespace porter_esp32_bridge

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<porter_esp32_bridge::Esp32MotorBridge>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}

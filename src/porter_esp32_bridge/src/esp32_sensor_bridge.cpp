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
// ESP32 Sensor Bridge Node — bridges ESP32 #2 sensor fusion data to ROS 2.

#include <chrono>
#include <cmath>
#include <cstring>
#include <string>
#include <vector>

#include "diagnostic_msgs/msg/diagnostic_array.hpp"
#include "diagnostic_msgs/msg/diagnostic_status.hpp"
#include "diagnostic_msgs/msg/key_value.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/range.hpp"
#include "std_msgs/msg/string.hpp"

#include "porter_esp32_bridge/serial_port.hpp"

extern "C" {
#include "crc16.h"  // NOLINT(build/include_subdir)
#include "protocol.h"  // NOLINT(build/include_subdir)
}

using namespace std::chrono_literals;

namespace porter_esp32_bridge
{

class Esp32SensorBridge : public rclcpp::Node
{
public:
  Esp32SensorBridge()
  : Node("esp32_sensor_bridge")
  {
    // --- Declare parameters ---
    this->declare_parameter<std::string>("port", "/dev/esp32_sensors");
    this->declare_parameter<int>("baudrate", 115200);
    this->declare_parameter<double>("reconnect_interval", 3.0);
    this->declare_parameter<std::string>("frame_id", "sensor_frame");
    this->declare_parameter<double>("fov", 0.44);
    this->declare_parameter<double>("min_range", 0.02);
    this->declare_parameter<double>("max_range", 4.0);

    port_ = this->get_parameter("port").as_string();
    baudrate_ = this->get_parameter("baudrate").as_int();
    reconnect_interval_ = this->get_parameter("reconnect_interval").as_double();
    frame_id_ = this->get_parameter("frame_id").as_string();
    fov_ = this->get_parameter("fov").as_double();
    min_range_ = this->get_parameter("min_range").as_double();
    max_range_ = this->get_parameter("max_range").as_double();

    // --- Publishers ---
    range_pub_ = this->create_publisher<sensor_msgs::msg::Range>(
      "environment", rclcpp::SensorDataQoS().reliable());
    sensor_status_pub_ = this->create_publisher<std_msgs::msg::String>(
      "sensor_status", 10);
    diag_pub_ = this->create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
      "/diagnostics", 10);

    // --- Initialize parser ---
    protocol_parser_init(&parser_);

    // --- Connect ---
    connect();

    // --- Timers ---
    serial_read_timer_ = this->create_wall_timer(
      10ms, std::bind(&Esp32SensorBridge::serial_read_callback, this));

    status_poll_timer_ = this->create_wall_timer(
      2s, std::bind(&Esp32SensorBridge::status_poll_callback, this));

    reconnect_timer_ = this->create_wall_timer(
      std::chrono::duration<double>(reconnect_interval_),
      std::bind(&Esp32SensorBridge::reconnect_callback, this));

    diag_timer_ = this->create_wall_timer(
      1s, std::bind(&Esp32SensorBridge::publish_diagnostics, this));

    RCLCPP_INFO(this->get_logger(), "ESP32 Sensor Bridge started — port: %s, baud: %d",
      port_.c_str(), baudrate_);
  }

private:
  // --- Serial ---
  SerialPort serial_;
  std::string port_;
  int baudrate_;
  protocol_parser_t parser_;
  bool connected_ = false;

  // --- Parameters ---
  double reconnect_interval_;
  std::string frame_id_;
  double fov_;
  double min_range_;
  double max_range_;

  // --- Stats ---
  uint32_t packets_received_ = 0;
  uint32_t parse_errors_ = 0;
  uint32_t serial_errors_ = 0;
  uint32_t fused_readings_ = 0;

  // --- Latest readings ---
  float last_tof_mm_ = 0.0f;
  float last_ultrasonic_mm_ = 0.0f;
  float last_fused_mm_ = 0.0f;
  uint8_t last_confidence_ = 0;
  bool motion_detected_ = false;

  // --- ROS interfaces ---
  rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr range_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr sensor_status_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diag_pub_;

  // --- Timers ---
  rclcpp::TimerBase::SharedPtr serial_read_timer_;
  rclcpp::TimerBase::SharedPtr status_poll_timer_;
  rclcpp::TimerBase::SharedPtr reconnect_timer_;
  rclcpp::TimerBase::SharedPtr diag_timer_;

  // --- Connection ---
  void connect()
  {
    if (serial_.open(port_, baudrate_)) {
      connected_ = true;
      RCLCPP_INFO(this->get_logger(), "Connected to ESP32 sensors on %s", port_.c_str());
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

  // --- Serial reading (100 Hz poll) ---
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

  // --- Status poll ---
  void status_poll_callback()
  {
    if (!connected_) {
      return;
    }
    send_command(CMD_SENSOR_STATUS, nullptr, 0);
  }

  // --- Packet handler ---
  void handle_packet(const protocol_packet_t & pkt)
  {
    switch (pkt.command) {
      case CMD_SENSOR_FUSED:
        handle_fused_data(pkt);
        break;
      case CMD_SENSOR_TOF:
        handle_tof_data(pkt);
        break;
      case CMD_SENSOR_ULTRASONIC:
        handle_ultrasonic_data(pkt);
        break;
      case CMD_SENSOR_MICROWAVE:
        handle_microwave_data(pkt);
        break;
      case CMD_SENSOR_STATUS:
        handle_sensor_status(pkt);
        break;
      case CMD_ACK:
        RCLCPP_DEBUG(this->get_logger(), "ACK for cmd 0x%02X",
          pkt.length > 0 ? pkt.payload[0] : 0);
        break;
      case CMD_NACK:
        RCLCPP_WARN(this->get_logger(), "NACK: cmd=0x%02X reason=0x%02X",
          pkt.length > 0 ? pkt.payload[0] : 0,
          pkt.length > 1 ? pkt.payload[1] : 0);
        break;
      default:
        RCLCPP_DEBUG(this->get_logger(), "Unknown cmd 0x%02X", pkt.command);
        break;
    }
  }

  void handle_fused_data(const protocol_packet_t & pkt)
  {
    // Fused payload: [distance_mm:u16][confidence:u8][motion:u8]
    if (pkt.length < 4) {
      return;
    }

    uint16_t distance_mm;
    std::memcpy(&distance_mm, &pkt.payload[0], 2);
    last_confidence_ = pkt.payload[2];
    motion_detected_ = pkt.payload[3] != 0;
    last_fused_mm_ = static_cast<float>(distance_mm);
    fused_readings_++;

    // Publish as sensor_msgs/Range
    auto msg = sensor_msgs::msg::Range();
    msg.header.stamp = this->now();
    msg.header.frame_id = frame_id_;
    msg.radiation_type = sensor_msgs::msg::Range::INFRARED;
    msg.field_of_view = static_cast<float>(fov_);
    msg.min_range = static_cast<float>(min_range_);
    msg.max_range = static_cast<float>(max_range_);
    msg.range = static_cast<float>(distance_mm) / 1000.0f;  // mm → m

    // Clamp to valid range
    if (msg.range < msg.min_range) {
      msg.range = msg.min_range;
    } else if (msg.range > msg.max_range) {
      msg.range = std::numeric_limits<float>::infinity();
    }

    range_pub_->publish(msg);
  }

  void handle_tof_data(const protocol_packet_t & pkt)
  {
    if (pkt.length < 2) {
      return;
    }
    uint16_t mm;
    std::memcpy(&mm, &pkt.payload[0], 2);
    last_tof_mm_ = static_cast<float>(mm);
    RCLCPP_DEBUG(this->get_logger(), "ToF: %u mm", mm);
  }

  void handle_ultrasonic_data(const protocol_packet_t & pkt)
  {
    if (pkt.length < 2) {
      return;
    }
    uint16_t mm;
    std::memcpy(&mm, &pkt.payload[0], 2);
    last_ultrasonic_mm_ = static_cast<float>(mm);
    RCLCPP_DEBUG(this->get_logger(), "Ultrasonic: %u mm", mm);
  }

  void handle_microwave_data(const protocol_packet_t & pkt)
  {
    if (pkt.length < 1) {
      return;
    }
    motion_detected_ = pkt.payload[0] != 0;
    RCLCPP_DEBUG(this->get_logger(), "Microwave motion: %s",
      motion_detected_ ? "detected" : "clear");
  }

  void handle_sensor_status(const protocol_packet_t & pkt)
  {
    // Status payload: [state:u8][tof_health:u8][us_health:u8][mw_health:u8]
    if (pkt.length < 4) {
      return;
    }

    static const char * health_names[] = {"OK", "DEGRADED", "FAULT", "NOT_PRESENT"};
    auto clamp_idx = [](uint8_t v) -> uint8_t {return v < 4 ? v : 3;};

    char json[256];
    std::snprintf(json, sizeof(json),
      R"({"state":%d,"tof":"%s","ultrasonic":"%s","microwave":"%s"})",
      pkt.payload[0],
      health_names[clamp_idx(pkt.payload[1])],
      health_names[clamp_idx(pkt.payload[2])],
      health_names[clamp_idx(pkt.payload[3])]);

    auto msg = std_msgs::msg::String();
    msg.data = json;
    sensor_status_pub_->publish(msg);
  }

  // --- Send command ---
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
    }
  }

  // --- Diagnostics ---
  void publish_diagnostics()
  {
    auto diag_msg = diagnostic_msgs::msg::DiagnosticArray();
    diag_msg.header.stamp = this->now();

    auto status = diagnostic_msgs::msg::DiagnosticStatus();
    status.name = "esp32_sensor_bridge";
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
    add_kv("packets_received", std::to_string(packets_received_));
    add_kv("fused_readings", std::to_string(fused_readings_));
    add_kv("parse_errors", std::to_string(parse_errors_));
    add_kv("serial_errors", std::to_string(serial_errors_));
    add_kv("last_fused_mm", std::to_string(last_fused_mm_));
    add_kv("last_tof_mm", std::to_string(last_tof_mm_));
    add_kv("last_ultrasonic_mm", std::to_string(last_ultrasonic_mm_));
    add_kv("confidence", std::to_string(last_confidence_));
    add_kv("motion_detected", motion_detected_ ? "true" : "false");

    diag_msg.status.push_back(status);
    diag_pub_->publish(diag_msg);
  }
};

}  // namespace porter_esp32_bridge

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<porter_esp32_bridge::Esp32SensorBridge>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}

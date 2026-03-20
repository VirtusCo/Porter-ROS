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

#ifndef PORTER_ESP32_BRIDGE__SERIAL_PORT_HPP_
#define PORTER_ESP32_BRIDGE__SERIAL_PORT_HPP_

#include <string>
#include <cstdint>
#include <cstddef>

namespace porter_esp32_bridge
{

class SerialPort
{
public:
  SerialPort() = default;
  ~SerialPort();

  // Non-copyable
  SerialPort(const SerialPort &) = delete;
  SerialPort & operator=(const SerialPort &) = delete;

  /**
   * @brief Open and configure the serial port
   * @param device Path to serial device (e.g. "/dev/esp32_motors")
   * @param baudrate Baud rate (e.g. 115200)
   * @return true on success
   */
  bool open(const std::string & device, int baudrate);

  /**
   * @brief Close the serial port
   */
  void close();

  /**
   * @brief Check if port is open
   */
  bool is_open() const;

  /**
   * @brief Read up to max_len bytes (non-blocking)
   * @param buf Output buffer
   * @param max_len Maximum bytes to read
   * @return Number of bytes read (0 if nothing available), -1 on error
   */
  int read(uint8_t * buf, size_t max_len);

  /**
   * @brief Write data to port (blocking until all written or error)
   * @param data Data buffer
   * @param len Number of bytes to write
   * @return Number of bytes written, -1 on error
   */
  int write(const uint8_t * data, size_t len);

  /**
   * @brief Flush both input and output buffers
   */
  void flush();

  /**
   * @brief Get the file descriptor (for poll/select if needed)
   */
  int fd() const {return fd_;}

private:
  int fd_ = -1;

  static int baudrate_to_speed(int baudrate);
};

}  // namespace porter_esp32_bridge

#endif  // PORTER_ESP32_BRIDGE__SERIAL_PORT_HPP_

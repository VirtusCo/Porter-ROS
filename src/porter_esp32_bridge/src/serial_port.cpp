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

#include "porter_esp32_bridge/serial_port.hpp"

#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>

namespace porter_esp32_bridge
{

SerialPort::~SerialPort()
{
  close();
}

bool SerialPort::open(const std::string & device, int baudrate)
{
  if (fd_ >= 0) {
    close();
  }

  fd_ = ::open(device.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
  if (fd_ < 0) {
    return false;
  }

  // Configure termios
  struct termios tty;
  std::memset(&tty, 0, sizeof(tty));

  if (tcgetattr(fd_, &tty) != 0) {
    ::close(fd_);
    fd_ = -1;
    return false;
  }

  speed_t speed = baudrate_to_speed(baudrate);
  cfsetispeed(&tty, speed);
  cfsetospeed(&tty, speed);

  // 8N1, no flow control
  tty.c_cflag &= ~PARENB;          // No parity
  tty.c_cflag &= ~CSTOPB;          // 1 stop bit
  tty.c_cflag &= ~CSIZE;
  tty.c_cflag |= CS8;              // 8 data bits
  tty.c_cflag &= ~CRTSCTS;         // No hardware flow control
  tty.c_cflag |= CREAD | CLOCAL;   // Enable receiver, ignore modem controls

  // Raw mode — no canonical processing, no echo, no signals
  tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);

  // No software flow control
  tty.c_iflag &= ~(IXON | IXOFF | IXANY);

  // Raw output
  tty.c_oflag &= ~OPOST;

  // Non-blocking: VMIN=0, VTIME=0 → return immediately
  tty.c_cc[VMIN] = 0;
  tty.c_cc[VTIME] = 0;

  if (tcsetattr(fd_, TCSANOW, &tty) != 0) {
    ::close(fd_);
    fd_ = -1;
    return false;
  }

  // Flush any stale data
  tcflush(fd_, TCIOFLUSH);

  return true;
}

void SerialPort::close()
{
  if (fd_ >= 0) {
    ::close(fd_);
    fd_ = -1;
  }
}

bool SerialPort::is_open() const
{
  return fd_ >= 0;
}

int SerialPort::read(uint8_t * buf, size_t max_len)
{
  if (fd_ < 0 || buf == nullptr || max_len == 0) {
    return 0;
  }

  ssize_t n = ::read(fd_, buf, max_len);
  if (n < 0) {
    if (errno == EAGAIN || errno == EWOULDBLOCK) {
      return 0;  // No data available (non-blocking)
    }
    return -1;  // Real error
  }
  return static_cast<int>(n);
}

int SerialPort::write(const uint8_t * data, size_t len)
{
  if (fd_ < 0 || data == nullptr || len == 0) {
    return 0;
  }

  size_t total = 0;
  while (total < len) {
    ssize_t n = ::write(fd_, data + total, len - total);
    if (n < 0) {
      if (errno == EAGAIN || errno == EWOULDBLOCK) {
        // Brief pause then retry
        usleep(1000);
        continue;
      }
      return -1;  // Real error
    }
    total += static_cast<size_t>(n);
  }
  return static_cast<int>(total);
}

void SerialPort::flush()
{
  if (fd_ >= 0) {
    tcflush(fd_, TCIOFLUSH);
  }
}

int SerialPort::baudrate_to_speed(int baudrate)
{
  switch (baudrate) {
    case 9600:    return B9600;
    case 19200:   return B19200;
    case 38400:   return B38400;
    case 57600:   return B57600;
    case 115200:  return B115200;
    case 230400:  return B230400;
    case 460800:  return B460800;
    case 921600:  return B921600;
    default:      return B115200;
  }
}

}  // namespace porter_esp32_bridge

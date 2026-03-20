cmake_minimum_required(VERSION 3.16)
project(porter_esp32_bridge)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)

# ==========================================================================
# Shared protocol library (from esp32_firmware/common/)
# ==========================================================================
set(COMMON_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../esp32_firmware/common)

add_library(porter_protocol STATIC
  ${COMMON_DIR}/src/protocol.cpp
  ${COMMON_DIR}/src/crc16.cpp
)
target_include_directories(porter_protocol PUBLIC
  ${COMMON_DIR}/include
)
# Not a Zephyr build — use host mock transport (excluded from protocol lib)
target_compile_definitions(porter_protocol PRIVATE)

# ==========================================================================
# Serial port helper (POSIX termios)
# ==========================================================================
add_library(serial_port STATIC
  src/serial_port.cpp
)
target_include_directories(serial_port PUBLIC
  include
)

# ==========================================================================
# Motor bridge node
# ==========================================================================
add_executable(esp32_motor_bridge
  src/esp32_motor_bridge.cpp
)
target_include_directories(esp32_motor_bridge PRIVATE include)
target_link_libraries(esp32_motor_bridge porter_protocol serial_port)
ament_target_dependencies(esp32_motor_bridge
  rclcpp geometry_msgs std_msgs diagnostic_msgs
)

# ==========================================================================
# Sensor bridge node
# ==========================================================================
add_executable(esp32_sensor_bridge
  src/esp32_sensor_bridge.cpp
)
target_include_directories(esp32_sensor_bridge PRIVATE include)
target_link_libraries(esp32_sensor_bridge porter_protocol serial_port)
ament_target_dependencies(esp32_sensor_bridge
  rclcpp sensor_msgs std_msgs diagnostic_msgs
)

# ==========================================================================
# Install
# ==========================================================================
install(TARGETS
  esp32_motor_bridge
  esp32_sensor_bridge
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

# ==========================================================================
# Testing
# ==========================================================================
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()

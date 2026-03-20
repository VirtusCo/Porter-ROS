# Copyright 2026 VirtusCo. All rights reserved.
# Proprietary and confidential.

cmake_minimum_required(VERSION 3.16)
project(porter_lidar_processor_cpp)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)

# Filter library (no ROS dependency — pure functions, unit-testable in isolation)
add_library(lidar_filters STATIC
  src/filters.cpp
)
target_include_directories(lidar_filters PUBLIC include)

# Processor node executable
add_executable(lidar_processor_node
  src/processor_node.cpp
  src/main.cpp
)
target_link_libraries(lidar_processor_node lidar_filters)
ament_target_dependencies(lidar_processor_node rclcpp sensor_msgs diagnostic_msgs)
target_include_directories(lidar_processor_node PUBLIC include)

install(TARGETS lidar_processor_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_filters test/test_filters.cpp)
  target_link_libraries(test_filters lidar_filters)
  target_include_directories(test_filters PRIVATE include)
endif()

ament_package()

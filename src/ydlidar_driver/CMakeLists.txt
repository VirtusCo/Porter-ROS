cmake_minimum_required(VERSION 3.16)
project(ydlidar_driver)

# ── C++ standard ─────────────────────────────────────────────────────────────
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── ROS 2 dependencies ──────────────────────────────────────────────────────
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)

# ── YDLidar SDK (installed system-wide) ─────────────────────────────────────
find_package(ydlidar_sdk REQUIRED)

# ── Include directories ─────────────────────────────────────────────────────
include_directories(
  include
  ${YDLIDAR_SDK_INCLUDE_DIRS}
)

# ── ydlidar_node executable ─────────────────────────────────────────────────
add_executable(ydlidar_node
  src/ydlidar_node.cpp
  src/sdk_adapter.cpp
  src/health_monitor.cpp
)

ament_target_dependencies(ydlidar_node
  rclcpp
  sensor_msgs
  std_msgs
  diagnostic_msgs
)

target_link_libraries(ydlidar_node
  ${YDLIDAR_SDK_LIBRARIES}
)

# ── Install targets ─────────────────────────────────────────────────────────
install(TARGETS ydlidar_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include/${PROJECT_NAME}
)

# ── Testing ─────────────────────────────────────────────────────────────────
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)

  # ── Health Monitor Unit Tests ──
  ament_add_gtest(test_health_monitor tests/test_health_monitor.cpp src/health_monitor.cpp)
  ament_target_dependencies(test_health_monitor rclcpp sensor_msgs diagnostic_msgs)
  target_include_directories(test_health_monitor PRIVATE include)

  # ── Adapter Config Unit Tests ──
  ament_add_gtest(test_adapter_config tests/test_adapter_config.cpp)
  target_include_directories(test_adapter_config PRIVATE
    include
    ${YDLIDAR_SDK_INCLUDE_DIRS}
  )
  target_link_libraries(test_adapter_config ${YDLIDAR_SDK_LIBRARIES})

  # ── Scan Conversion Integration Tests ──
  ament_add_gtest(test_scan_conversion tests/test_scan_conversion.cpp)
  target_include_directories(test_scan_conversion PRIVATE
    include
    ${YDLIDAR_SDK_INCLUDE_DIRS}
  )
  target_link_libraries(test_scan_conversion ${YDLIDAR_SDK_LIBRARIES})
endif()

ament_package()

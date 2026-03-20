# ROS 2 How-To Guides — Skill File

> Source: https://docs.ros.org/en/jazzy/How-To-Guides.html
> Distro: Jazzy Jalisco

---

## Overview

How-To Guides provide direct answers to specific "How do I...?" questions. Not for learning concepts — see Tutorials instead.

---

## Guide Index

### Package Development
1. **Installation troubleshooting** — Common install issues and fixes
2. **Developing a ROS 2 package** — Development workflow, building, testing
3. **Documenting a ROS 2 package** — rosdoc2, API docs, package-level docs

### Build System
4. **ament_cmake user documentation** — CMake macros, targets, dependencies, installing
5. **ament_cmake_python user documentation** — Python bindings in CMake packages

### Migration
6. **Migrating from ROS 1 to ROS 2** — Message, service, parameter, launch migration

### Launch
7. **Using XML, YAML, and Python for ROS 2 Launch Files** — Format comparison and examples
8. **Using ROS 2 launch to launch composable nodes** — Load components via launch
9. **Passing ROS arguments to nodes via the command-line** — `--ros-args`, remappings, parameters

### Communication
10. **Synchronous vs. asynchronous service clients** — When to use each pattern
11. **DDS tuning information** — Network buffer sizes, shared memory, multicast
12. **rosbag2: Overriding QoS Policies** — Record/play with custom QoS
13. **Working with multiple ROS 2 middleware implementations** — Switch RMW at runtime
14. **Configure Zero Copy Loaned Messages** — Shared memory zero-copy transport

### Deployment
15. **Cross-compilation** — Build for ARM/embedded targets
16. **Releasing a Package** — bloom-release workflow for distribution
17. **Using Python Packages with ROS 2** — pip packages in ROS workspace
18. **Running ROS 2 nodes in Docker** — Container setup and networking
19. **ROS 2 on Raspberry Pi** — ARM deployment guide

### Tools & Debugging
20. **Visualizing ROS 2 data with Foxglove Studio** — Web-based visualization
21. **ROS 2 Core Maintainer Guide** — Maintainer responsibilities
22. **Building a custom deb package** — bloom + debhelper
23. **Building ROS 2 with tracing** — LTTng tracing setup
24. **Topics vs Services vs Actions** — When to use each communication type
25. **Using variants** — Meta-packages for install groups
26. **Using the ros2 param command-line tool** — Full param CLI reference
27. **Using ros1_bridge with upstream ROS** — Bridge between ROS 1 and 2
28. **Using Callback Groups** — Thread-safe callback execution
29. **Getting Backtraces in ROS 2** — GDB, AddressSanitizer, core dumps
30. **IDEs and Debugging** — VSCode, CLion, Eclipse setup
31. **Setup ROS 2 with VSCode and Docker** — Dev container configuration
32. **Using Custom Rosdistro Version** — Custom distribution index

---

## Key How-To Details

### ament_cmake Essentials

```cmake
cmake_minimum_required(VERSION 3.14)
project(my_package)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)

add_executable(my_node src/my_node.cpp)
ament_target_dependencies(my_node rclcpp sensor_msgs)

install(TARGETS my_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
```

### Topics vs Services vs Actions

| Communication | Pattern | Use When |
|---|---|---|
| **Topics** | Pub/Sub (1-to-many) | Continuous data streams (sensors, state) |
| **Services** | Request/Response (1-to-1) | Quick computations, queries |
| **Actions** | Goal/Feedback/Result | Long-running tasks with cancellation |

### DDS Tuning

```bash
# Increase UDP receive buffer (Linux)
sudo sysctl -w net.core.rmem_max=8388608
sudo sysctl -w net.core.rmem_default=8388608

# Fast DDS shared memory (high throughput, same machine)
export FASTRTPS_DEFAULT_PROFILES_FILE=my_fastdds_profile.xml
```

### Callback Groups

```cpp
// Mutually exclusive — callbacks never run in parallel
auto group1 = this->create_callback_group(
  rclcpp::CallbackGroupType::MutuallyExclusive);

// Reentrant — callbacks CAN run in parallel
auto group2 = this->create_callback_group(
  rclcpp::CallbackGroupType::Reentrant);

rclcpp::SubscriptionOptions options;
options.callback_group = group1;

subscription_ = this->create_subscription<Msg>(
  "topic", 10, callback, options);
```

### Synchronous vs Async Service Clients

```cpp
// ASYNC (recommended — non-blocking)
auto future = client->async_send_request(request);
// Process response in callback or spin_until_future_complete

// SYNC (blocks — use ONLY in simple scripts, never in callbacks)
auto response = client->async_send_request(request);
rclcpp::spin_until_future_complete(node, response);
```

**Rule**: Never call a synchronous service from within a callback — it will deadlock.

### Running in Docker

```bash
# Basic
docker run -it --rm \
  --network=host \
  osrf/ros:jazzy-desktop \
  bash -c "source /opt/ros/jazzy/setup.bash && ros2 run demo_nodes_cpp talker"

# With device access (e.g., LIDAR)
docker run -it --rm \
  --network=host \
  --privileged \
  --device=/dev/ttyUSB0 \
  -v /dev:/dev \
  my_ros2_image
```

### VSCode + Docker Setup

```json
// .devcontainer/devcontainer.json
{
  "name": "ROS 2 Jazzy",
  "image": "osrf/ros:jazzy-desktop",
  "runArgs": ["--network=host", "--privileged"],
  "extensions": [
    "ms-vscode.cpptools",
    "ms-python.python",
    "ms-iot.vscode-ros"
  ],
  "postCreateCommand": "sudo apt-get update && rosdep update"
}
```

### Getting Backtraces

```bash
# With GDB
ros2 run --prefix 'gdb -ex run --args' my_package my_node

# With AddressSanitizer
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_FLAGS="-fsanitize=address" \
  -DCMAKE_C_FLAGS="-fsanitize=address"

# Enable core dumps
ulimit -c unlimited
```

# ROS 2 Tutorials: Advanced — Skill File

> Source: https://docs.ros.org/en/jazzy/Tutorials/Advanced.html
> Distro: Jazzy Jalisco

---

## Sub-Documents

1. **Supplementing custom rosdep keys** — Custom system dependency mappings
2. **Enabling topic statistics (C++)** — Built-in subscription statistics
3. **Using Fast DDS Discovery Server** — Centralized discovery protocol
4. **Implementing a custom memory allocator** — TLSF or custom allocators for real-time
5. **Ament Lint CLI Utilities** — Running linters from command line
6. **Unlocking the potential of Fast DDS middleware** — XML profiles, tuning
7. **Improved Dynamic Discovery** — Simple Discovery Protocol improvements
8. **Recording a bag from a node (C++)** — Programmatic rosbag2 recording
9. **Recording a bag from a node (Python)** — Programmatic rosbag2 recording
10. **Reading from a bag file (C++)** — Programmatic rosbag2 reading
11. **How to use ros2_tracing** — Trace and analyze application performance
12. **Creating an RMW implementation** — Custom middleware integration
13. **Simulators** — Gazebo integration and setup
14. **Security** — Setting up ROS 2 security enclaves

---

## Topic Statistics

### Enable in C++
```cpp
auto options = rclcpp::SubscriptionOptions();
options.topic_stats_options.state = rclcpp::TopicStatisticsState::Enable;
options.topic_stats_options.publish_period = std::chrono::seconds(1);

subscription_ = this->create_subscription<sensor_msgs::msg::LaserScan>(
  "scan", 10,
  std::bind(&MyNode::callback, this, _1),
  options);
```

Statistics published to: `/statistics` (configurable)

---

## Fast DDS Discovery Server

### Why?
- Default Simple Discovery Protocol generates multicast traffic.
- Discovery Server: centralized, reduces network overhead.
- Better for large systems or restricted networks.

### Start Discovery Server
```bash
fastdds discovery -i 0 -l 127.0.0.1 -p 11811
```

### Configure Nodes
```bash
export ROS_DISCOVERY_SERVER=127.0.0.1:11811
ros2 run my_package my_node
```

---

## Custom Memory Allocators

### Purpose
- Real-time systems need deterministic memory allocation.
- TLSF (Two-Level Segregate Fit) provides O(1) allocation.

### Usage Pattern
```cpp
#include "rclcpp/allocator/allocator_common.hpp"
#include "tlsf_cpp/tlsf.hpp"

using TLSFAllocator = tlsf_heap_allocator<void>;

auto alloc = std::make_shared<TLSFAllocator>();
auto publisher = node->create_publisher<std_msgs::msg::String>(
  "topic", 10, rclcpp::PublisherOptionsWithAllocator<TLSFAllocator>(alloc));
```

---

## Ament Lint CLI

### Run All Linters
```bash
# In package directory after building with tests
colcon test --packages-select <package_name>
colcon test-result --verbose

# Individual linters
ament_cpplint src/
ament_uncrustify src/
ament_cppcheck src/
ament_clang_format src/
ament_flake8 my_package/
ament_pep257 my_package/
ament_pycodestyle my_package/
```

### Auto-fix Formatting
```bash
ament_uncrustify --reformat src/
ament_clang_format --reformat src/
```

---

## Recording/Reading Bags Programmatically

### C++ Recording
```cpp
#include "rosbag2_cpp/writer.hpp"

auto writer = std::make_unique<rosbag2_cpp::Writer>();
writer->open("my_bag");

auto serialized_msg = /* ... */;
writer->write(serialized_msg, "topic_name", "msg_type", timestamp);
```

### C++ Reading
```cpp
#include "rosbag2_cpp/reader.hpp"

auto reader = std::make_unique<rosbag2_cpp::Reader>();
reader->open("my_bag");

while (reader->has_next()) {
  auto msg = reader->read_next();
  // process msg
}
```

---

## ros2_tracing

### Purpose
Low-overhead tracing for performance analysis (uses LTTng on Linux).

### Record a Trace
```bash
ros2 trace --session-name my_session --list  # List available tracepoints
ros2 trace --session-name my_session         # Start tracing
```

### Analyze
```python
import tracetools_analysis
# Use tracetools_analysis to load and analyze trace data
```

---

## Security

### Setup Security Enclaves
```bash
# Generate keystore
ros2 security create_keystore ~/sros2_keystore

# Create enclave for a node
ros2 security create_enclave ~/sros2_keystore /my_node

# Enable security
export ROS_SECURITY_KEYSTORE=~/sros2_keystore
export ROS_SECURITY_ENABLE=true
export ROS_SECURITY_STRATEGY=Enforce  # or Permissive
```

---

## Simulators (Gazebo)

### Launching with Gazebo (Ignition)
```bash
# Install
sudo apt install ros-jazzy-ros-gz

# Launch
ros2 launch ros_gz_sim gz_sim.launch.py gz_args:='empty.sdf'

# Bridge ROS 2 ↔ Gazebo topics
ros2 run ros_gz_bridge parameter_bridge /scan@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan
```

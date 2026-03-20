# ROS 2 Tutorials: Demos — Skill File

> Source: https://docs.ros.org/en/jazzy/Tutorials/Demos.html
> Distro: Jazzy Jalisco

---

## Sub-Documents

1. **Using quality-of-service settings for lossy networks** — QoS reliability/durability
2. **Managing nodes with managed lifecycles** — Lifecycle node state machine
3. **Setting up efficient intra-process communication** — Zero-copy within single process
4. **Recording and playing back data with rosbag using ROS 1 bridge** — Cross-generation bridge
5. **Understanding real-time programming** — RT kernel, scheduling, memory locking
6. **Experimenting with a dummy robot** — Demo robot simulation
7. **Logging** — Logger configuration and output control
8. **Creating a content filtering subscription** — Filter messages at DDS level
9. **Configure service introspection** — Hidden service events for debugging
10. **Wait for acknowledgment** — Publisher wait for subscriber acknowledgment

---

## Quality of Service (QoS) Demo

### Key QoS Policies

| Policy | Options | Use Case |
|---|---|---|
| **Reliability** | `RELIABLE` / `BEST_EFFORT` | Reliable for commands, best-effort for sensor streams |
| **Durability** | `TRANSIENT_LOCAL` / `VOLATILE` | Transient for late-joining subscribers to get last value |
| **History** | `KEEP_LAST(N)` / `KEEP_ALL` | Keep last N messages or all |
| **Deadline** | Duration | Expected maximum time between messages |
| **Lifespan** | Duration | Message expiry time |
| **Liveliness** | `AUTOMATIC` / `MANUAL` | Node/topic liveness assertion |

### Setting QoS in Code (C++)
```cpp
rclcpp::QoS qos(10);  // depth = 10
qos.reliability(rclcpp::ReliabilityPolicy::BestEffort);
qos.durability(rclcpp::DurabilityPolicy::Volatile);
qos.history(rclcpp::HistoryPolicy::KeepLast);

auto pub = this->create_publisher<sensor_msgs::msg::LaserScan>("/scan", qos);
```

### Predefined QoS Profiles
```cpp
rclcpp::SensorDataQoS()   // BEST_EFFORT + VOLATILE + KEEP_LAST(5)
rclcpp::SystemDefaultsQoS()
rclcpp::ServicesQoS()
rclcpp::ParametersQoS()
```

---

## Lifecycle Nodes

### State Machine
```
       [Unconfigured]
            │ configure()
       [Inactive]
            │ activate()
       [Active]
            │ deactivate()
       [Inactive]
            │ cleanup()
       [Unconfigured]
            │ shutdown()
       [Finalized]
```

### Error transitions available from any primary state → [ErrorProcessing] → [Unconfigured] or [Finalized]

### C++ Implementation
```cpp
#include "rclcpp_lifecycle/lifecycle_node.hpp"

class MyLifecycleNode : public rclcpp_lifecycle::LifecycleNode
{
  CallbackReturn on_configure(const rclcpp_lifecycle::State &) override;
  CallbackReturn on_activate(const rclcpp_lifecycle::State &) override;
  CallbackReturn on_deactivate(const rclcpp_lifecycle::State &) override;
  CallbackReturn on_cleanup(const rclcpp_lifecycle::State &) override;
  CallbackReturn on_shutdown(const rclcpp_lifecycle::State &) override;
};
```

### CLI Control
```bash
ros2 lifecycle list /my_lifecycle_node
ros2 lifecycle set /my_lifecycle_node configure
ros2 lifecycle set /my_lifecycle_node activate
ros2 lifecycle set /my_lifecycle_node deactivate
ros2 lifecycle set /my_lifecycle_node cleanup
ros2 lifecycle set /my_lifecycle_node shutdown
ros2 lifecycle get /my_lifecycle_node
```

---

## Intra-Process Communication

### Purpose
Zero-copy message passing between nodes in the same process — dramatically reduces latency.

### Enable
```cpp
auto options = rclcpp::NodeOptions().use_intra_process_comms(true);
auto node = std::make_shared<rclcpp::Node>("my_node", options);
```

### Requirements
- Nodes must be in the same process (composition).
- Use `std::unique_ptr<T>` for published messages to enable zero-copy.

```cpp
auto msg = std::make_unique<sensor_msgs::msg::LaserScan>();
// fill msg
publisher_->publish(std::move(msg));
```

---

## Logging Configuration

### Logger Levels
```bash
# Set at runtime
ros2 run my_package my_node --ros-args --log-level debug
ros2 run my_package my_node --ros-args --log-level my_node:=debug

# Set via service
ros2 service call /my_node/set_logger_level \
  rcl_interfaces/srv/SetLoggerLevel "{name: '', level: 10}"
```

### C++ Logging Macros
```cpp
RCLCPP_DEBUG(this->get_logger(), "Debug message: %d", value);
RCLCPP_INFO(this->get_logger(), "Info message");
RCLCPP_WARN(this->get_logger(), "Warning message");
RCLCPP_ERROR(this->get_logger(), "Error message");
RCLCPP_FATAL(this->get_logger(), "Fatal message");

// Conditional and throttled variants
RCLCPP_INFO_ONCE(this->get_logger(), "Only once");
RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000, "Every 5s");
RCLCPP_DEBUG_EXPRESSION(this->get_logger(), condition, "Conditional");
```

---

## Content Filtering Subscription

### Filter messages at the DDS level (reduces bandwidth)
```cpp
rclcpp::SubscriptionOptions options;
options.content_filter_options.filter_expression = "data > %0";
options.content_filter_options.expression_parameters = {"5.0"};

auto sub = this->create_subscription<std_msgs::msg::Float64>(
  "topic", 10, callback, options);
```

---

## Service Introspection

### Enable hidden service events for debugging
```cpp
auto service = this->create_service<MySrv>(
  "my_service", callback,
  rmw_qos_profile_services_default,
  /* group */ nullptr);

// Enable introspection
service->configure_introspection(
  this->get_clock(),
  rclcpp::SystemDefaultsQoS(),
  rclcpp::ServiceIntrospectionState::Contents);
```

### Observe via CLI
```bash
ros2 service echo /my_service
```

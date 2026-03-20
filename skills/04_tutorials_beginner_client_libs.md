# ROS 2 Tutorials: Beginner Client Libraries — Skill File

> Source: https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries.html
> Distro: Jazzy Jalisco

---

## Sub-Documents

1. **Using colcon to build packages** — `colcon build`, `colcon test`, workspace overlay
2. **Creating a workspace** — `mkdir -p ~/ros2_ws/src`, overlay vs underlay
3. **Creating a package** — `ros2 pkg create`, `ament_cmake` vs `ament_python`
4. **Writing a simple publisher and subscriber (C++)** — rclcpp pub/sub pattern
5. **Writing a simple publisher and subscriber (Python)** — rclpy pub/sub pattern
6. **Writing a simple service and client (C++)** — rclcpp service pattern
7. **Writing a simple service and client (Python)** — rclpy service pattern
8. **Creating custom msg and srv files** — `.msg`/`.srv` definition, `rosidl_generate_interfaces`
9. **Implementing custom interfaces** — Single package define and use interface
10. **Using parameters in a class (C++)** — `declare_parameter<T>()`, `get_parameter()`
11. **Using parameters in a class (Python)** — `declare_parameter()`, `get_parameter()`
12. **Using ros2doctor to identify issues** — `ros2 doctor`, `ros2 doctor --report`
13. **Creating and using plugins (C++)** — pluginlib, plugin descriptors, class loading

---

## colcon Build System

### Essential Commands
```bash
# Build entire workspace
colcon build

# Build specific packages
colcon build --packages-select <pkg1> <pkg2>

# Build with dependencies
colcon build --packages-up-to <pkg>

# Build with compiler options
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release

# Run tests
colcon test
colcon test --packages-select <pkg>

# View test results
colcon test-result --all
colcon test-result --verbose
```

### Workspace Structure
```
ros2_ws/
├── src/           # Source packages
├── build/         # Build artifacts (per-package)
├── install/       # Install space (per-package)
└── log/           # Build and test logs
```

### Overlay vs Underlay
- **Underlay**: base ROS 2 install (`/opt/ros/jazzy/setup.bash`)
- **Overlay**: workspace-specific install (`~/ros2_ws/install/setup.bash`)
- Source underlay first, then overlay.

---

## Creating Packages

### CMake Package (C++)
```bash
ros2 pkg create --build-type ament_cmake --license Apache-2.0 <package_name>
ros2 pkg create --build-type ament_cmake --license Apache-2.0 \
  --node-name my_node --dependencies rclcpp std_msgs <package_name>
```

### Python Package
```bash
ros2 pkg create --build-type ament_python --license Apache-2.0 <package_name>
ros2 pkg create --build-type ament_python --license Apache-2.0 \
  --node-name my_node --dependencies rclpy std_msgs <package_name>
```

### Package Structure (ament_cmake)
```
my_package/
├── CMakeLists.txt
├── package.xml
├── include/my_package/
├── src/
├── launch/
├── config/
└── test/
```

### Package Structure (ament_python)
```
my_package/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/my_package
├── my_package/
│   └── __init__.py
├── launch/
├── config/
└── test/
```

---

## Publisher/Subscriber Pattern

### C++ (rclcpp)
```cpp
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

class MyPublisher : public rclcpp::Node
{
public:
  MyPublisher() : Node("my_publisher")
  {
    publisher_ = this->create_publisher<std_msgs::msg::String>("topic", 10);
    timer_ = this->create_wall_timer(
      std::chrono::milliseconds(500),
      std::bind(&MyPublisher::timer_callback, this));
  }

private:
  void timer_callback()
  {
    auto msg = std_msgs::msg::String();
    msg.data = "Hello, world!";
    publisher_->publish(msg);
  }
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};
```

### Python (rclpy)
```python
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class MyPublisher(Node):
    def __init__(self):
        super().__init__('my_publisher')
        self.publisher_ = self.create_publisher(String, 'topic', 10)
        self.timer = self.create_timer(0.5, self.timer_callback)

    def timer_callback(self):
        msg = String()
        msg.data = 'Hello, world!'
        self.publisher_.publish(msg)
```

---

## Parameters in Code

### C++ — Always declare with type and default!
```cpp
// CORRECT (Jazzy requires typed declaration)
this->declare_parameter<double>("frequency", 10.0);
this->declare_parameter<std::string>("port", "/dev/ttyUSB0");
this->declare_parameter<int>("baud_rate", 115200);

// Get parameter
double freq = this->get_parameter("frequency").as_double();

// Set callback for parameter changes
auto callback = [this](const std::vector<rclcpp::Parameter> & params) {
  // handle changes
  rcl_interfaces::msg::SetParametersResult result;
  result.successful = true;
  return result;
};
this->add_on_set_parameters_callback(callback);
```

### Python
```python
self.declare_parameter('frequency', 10.0)
self.declare_parameter('port', '/dev/ttyUSB0')

freq = self.get_parameter('frequency').get_parameter_value().double_value
```

---

## Custom Interfaces

### Define message (msg/MyMsg.msg)
```
uint32 id
string name
float64[] values
```

### CMakeLists.txt additions
```cmake
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/MyMsg.msg"
  "srv/MySrv.srv"
  "action/MyAction.action"
)
```

### package.xml additions
```xml
<buildtool_depend>rosidl_default_generators</buildtool_depend>
<exec_depend>rosidl_default_runtime</exec_depend>
<member_of_group>rosidl_interface_packages</member_of_group>
```

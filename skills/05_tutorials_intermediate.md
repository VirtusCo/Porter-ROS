# ROS 2 Tutorials: Intermediate — Skill File

> Source: https://docs.ros.org/en/jazzy/Tutorials/Intermediate.html
> Distro: Jazzy Jalisco

---

## Sub-Documents

1. **Managing Dependencies with rosdep** — `rosdep install`, system dependency resolution
2. **Creating an action** — `.action` file definition
3. **Writing an action server and client (C++)** — rclcpp_action patterns
4. **Writing an action server and client (Python)** — rclpy action patterns
5. **Writing a Composable Node (C++)** — Component-style node for composition
6. **Composing multiple nodes in a single process** — Runtime composition, shared process
7. **Using the Node Interfaces Template Class (C++)** — Generic node interface access
8. **Monitoring for parameter changes (C++)** — Parameter event subscriber
9. **Monitoring for parameter changes (Python)** — Parameter event subscriber
10. **Launch** (sub-tutorials):
    - Creating launch files
    - Integrating launch files into packages
    - Using substitutions
    - Using event handlers
    - Managing large projects
11. **tf2** (sub-tutorials):
    - Static/dynamic broadcaster
    - Listener
    - Adding a frame
    - Time travel
    - Debugging
12. **Testing** — Unit, integration, and system testing patterns
13. **URDF** — Robot description format and tools
14. **RViz** — 3D visualization setup and markers

---

## rosdep

### Purpose
Resolves and installs system dependencies declared in `package.xml`.

### Commands
```bash
# Initialize (first time only)
sudo rosdep init
rosdep update

# Install all dependencies for workspace
rosdep install --from-paths src --ignore-src -r -y

# Check what would be installed
rosdep check --from-paths src --ignore-src
```

### package.xml dependency tags
```xml
<depend>rclcpp</depend>                 <!-- build + exec dependency -->
<build_depend>rosidl_default_generators</build_depend>
<exec_depend>rosidl_default_runtime</exec_depend>
<test_depend>ament_lint_auto</test_depend>
```

---

## Actions

### Defining an Action
```
# MyAction.action
int32 order          # Goal
---
int32[] sequence     # Result
---
int32[] sequence     # Feedback
```

### C++ Action Server Pattern
```cpp
#include "rclcpp_action/rclcpp_action.hpp"

rclcpp_action::Server<MyAction>::SharedPtr action_server_;

action_server_ = rclcpp_action::create_server<MyAction>(
  this, "my_action",
  std::bind(&MyNode::handle_goal, this, _1, _2),
  std::bind(&MyNode::handle_cancel, this, _1),
  std::bind(&MyNode::handle_accepted, this, _1));
```

### C++ Action Client Pattern
```cpp
auto client = rclcpp_action::create_client<MyAction>(this, "my_action");
auto goal_msg = MyAction::Goal();
goal_msg.order = 10;
auto send_goal_options = rclcpp_action::Client<MyAction>::SendGoalOptions();
send_goal_options.feedback_callback = ...;
send_goal_options.result_callback = ...;
client->async_send_goal(goal_msg, send_goal_options);
```

---

## Composable Nodes

### Why Compose?
- Run multiple nodes in a single process.
- Enables **intra-process communication** (zero-copy).
- Reduces latency and overhead.

### Writing a Composable Node
```cpp
#include "rclcpp_components/register_node_macro.hpp"

class MyComponent : public rclcpp::Node {
public:
  explicit MyComponent(const rclcpp::NodeOptions & options)
  : Node("my_component", options) { /* ... */ }
};

RCLCPP_COMPONENTS_REGISTER_NODE(MyComponent)
```

### CMakeLists.txt for Component
```cmake
add_library(my_component SHARED src/my_component.cpp)
target_compile_definitions(my_component PRIVATE "COMPOSITION_BUILDING_DLL")
ament_target_dependencies(my_component rclcpp rclcpp_components)

rclcpp_components_register_nodes(my_component "my_package::MyComponent")
```

### Runtime Composition
```bash
# Start component container
ros2 run rclcpp_components component_container

# Load components
ros2 component load /ComponentManager my_package my_package::MyComponent
```

---

## Launch System

### Python Launch File
```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='my_package',
            executable='my_node',
            name='custom_name',
            parameters=[{'param1': 'value1'}],
            remappings=[('/old_topic', '/new_topic')],
            output='screen',
        ),
    ])
```

### XML Launch File
```xml
<launch>
  <node pkg="my_package" exec="my_node" name="custom_name" output="screen">
    <param name="param1" value="value1"/>
    <remap from="/old_topic" to="/new_topic"/>
  </node>
</launch>
```

### YAML Launch File
```yaml
launch:
  - node:
      pkg: my_package
      exec: my_node
      name: custom_name
      param:
        - name: param1
          value: value1
```

---

## tf2 (Transform Library)

### Static Transform Broadcaster
```bash
ros2 run tf2_ros static_transform_publisher --x 1 --y 0 --z 0 \
  --roll 0 --pitch 0 --yaw 0 --frame-id base_link --child-frame-id laser
```

### Dynamic Transform Broadcaster (C++)
```cpp
#include "tf2_ros/transform_broadcaster.h"

tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(*this);

geometry_msgs::msg::TransformStamped t;
t.header.stamp = this->get_clock()->now();
t.header.frame_id = "base_link";
t.child_frame_id = "laser";
t.transform.translation.x = 0.1;
tf_broadcaster_->sendTransform(t);
```

### Transform Listener (C++)
```cpp
#include "tf2_ros/buffer.h"
#include "tf2_ros/transform_listener.h"

tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());
tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);

auto transform = tf_buffer_->lookupTransform("target_frame", "source_frame", tf2::TimePointZero);
```

---

## Testing

### Test Types
| Type | Scope | Location |
|---|---|---|
| Unit tests | Single function/class | Same package |
| Integration tests | Component interactions | Same package |
| System tests | End-to-end | Separate package |

### C++ Testing (GTest)
```cmake
if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(my_test test/test_my_node.cpp)
  target_link_libraries(my_test my_library)
endif()
```

### Python Testing (pytest)
```python
# test/test_my_module.py
import pytest
from my_package.my_module import MyClass

def test_something():
    obj = MyClass()
    assert obj.method() == expected_value
```

### Launch Testing
```python
import launch_testing
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_test_description():
    return LaunchDescription([
        Node(package='my_package', executable='my_node'),
        launch_testing.actions.ReadyToTest(),
    ])

class TestMyNode(unittest.TestCase):
    def test_node_running(self, proc_info):
        proc_info.assertWaitForShutdown(process=..., timeout=10)
```

---

## URDF (Unified Robot Description Format)

### Basic Structure
```xml
<?xml version="1.0"?>
<robot name="my_robot">
  <link name="base_link">
    <visual>
      <geometry><box size="0.5 0.3 0.1"/></geometry>
    </visual>
    <collision>
      <geometry><box size="0.5 0.3 0.1"/></geometry>
    </collision>
  </link>

  <joint name="laser_joint" type="fixed">
    <parent link="base_link"/>
    <child link="laser_link"/>
    <origin xyz="0.1 0 0.05" rpy="0 0 0"/>
  </joint>

  <link name="laser_link"/>
</robot>
```

### Using xacro
```bash
xacro model.urdf.xacro > model.urdf
```

### Publishing robot state
```bash
ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:="$(xacro model.urdf.xacro)"
```

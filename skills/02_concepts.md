# ROS 2 Concepts — Skill File

> Source: https://docs.ros.org/en/jazzy/Concepts.html (Basic, Intermediate, Advanced)
> Distro: Jazzy Jalisco

---

## BASIC CONCEPTS

ROS 2 is a middleware based on a **strongly-typed, anonymous publish/subscribe** mechanism for message passing between processes.

### Nodes

- A **node** is a participant in the ROS 2 graph using a client library to communicate.
- Nodes can be in the same process, different processes, or different machines.
- Each node should do **one logical thing** (unit of computation).
- A node can simultaneously be: publisher, subscriber, service server, service client, action server, action client.
- Connections established through distributed **discovery**.

### Discovery

1. When started, a node advertises its presence to others on the same **ROS domain** (`ROS_DOMAIN_ID`).
2. Other nodes respond with their info so connections can be made.
3. Nodes periodically re-advertise to connect with new entities.
4. Nodes advertise when going offline.
5. Connections only established with **compatible QoS settings**.

### Interfaces (IDL)

ROS 2 uses a simplified **Interface Definition Language** for describing communication types.

#### Message Types (.msg)
- Simple text files describing fields of a ROS message.
- Located in `msg/` directory.
- Composed of **fields** and **constants**.

**Built-in types**: `bool`, `byte`, `char`, `float32`, `float64`, `int8`, `uint8`, `int16`, `uint16`, `int32`, `uint32`, `int64`, `uint64`, `string`, `wstring`

**Arrays**: static `T[N]`, unbounded dynamic `T[]`, bounded dynamic `T[<=N]`, bounded string `string<=N`

```
int32 my_int
string my_string
uint8 x 42
int32[] samples [-200, -100, 0, 100, 200]
int32 X=123          # constant (UPPERCASE)
```

- Field names: lowercase alphanumeric + underscores, start with letter.
- Constants: UPPERCASE names, use `=` sign.

#### Service Types (.srv)
- Located in `srv/` directory.
- Request and response separated by `---`.

```
string str
---
string str
```

#### Action Types (.action)
- Located in `action/` directory.
- Goal, result, and feedback separated by `---`.

```
int32 order
---
int32[] sequence
---
int32[] sequence
```

### Topics

- For **continuous data streams** (sensor data, robot state, etc.).
- **Publish/subscribe** pattern: publishers produce, subscribers consume via named topics.
- **Zero or more** publishers and subscribers per topic.
- **Anonymous**: subscriber doesn't know/care which publisher sent data.
- **Strongly-typed**: field types enforced; semantics well-defined (e.g., IMU angular velocity in rad/s).

### Services

- **Remote procedure calls** — request/response pattern.
- Expected to return **quickly** — not for long-running processes.
- **One service server** per service name (undefined behavior with multiple).
- **Multiple service clients** allowed per service name.

```
uint32 a
uint32 b
---
uint32 sum
```

### Actions

- **Long-running** remote procedure calls with **feedback** and **cancellation**.
- Use for operations taking seconds/minutes (e.g., navigate to waypoint).
- **One action server** per action name.
- **Multiple action clients** allowed.
- Overhead in setup — use services for short RPCs instead.

```
int32 order     # goal
---
int32[] sequence  # result
---
int32[] sequence  # feedback
```

### Parameters

- Associated with individual **nodes** (lifetime tied to node).
- Addressed by: node name, node namespace, parameter name, parameter namespace.
- **Types**: `bool`, `int64`, `float64`, `string`, `byte[]`, `bool[]`, `int64[]`, `float64[]`, `string[]`
- Nodes must **declare** parameters at startup (unless `allow_undeclared_parameters=true`).
- `dynamic_typing` in `ParameterDescriptor` allows type changes at runtime.

#### Parameter Callbacks
1. **Pre-set** (`add_pre_set_parameters_callback`): can modify parameter list before setting.
2. **Set** (`add_on_set_parameters_callback`): can reject changes (no side-effects!).
3. **Post-set** (`add_post_set_parameters_callback`): react to successful changes.

#### Parameter Services (auto-created per node)
- `/node_name/describe_parameters`
- `/node_name/get_parameter_types`
- `/node_name/get_parameters`
- `/node_name/list_parameters`
- `/node_name/set_parameters`
- `/node_name/set_parameters_atomically`

#### Setting Parameters
- **CLI**: `ros2 run <pkg> <node> --ros-args -p param:=value`
- **YAML file**: `ros2 run <pkg> <node> --ros-args --params-file params.yaml`
- **Launch file**: via launch parameter directives
- **Runtime**: `ros2 param set /node_name param_name value`

### Launch

- Automates running many nodes with a single command.
- Describes system configuration: programs, locations, arguments, ROS conventions.
- Monitors process state and reacts to changes.
- Written in **XML**, **YAML**, or **Python**.
- Run with: `ros2 launch <package> <launch_file>`

### Client Libraries

- **rclcpp**: C++ client library
- **rclpy**: Python client library
- Both built on top of `rcl` (C library)
- Other language bindings available

---

## INTERMEDIATE CONCEPTS

### ROS_DOMAIN_ID
- Environment variable to partition ROS 2 communication.
- Nodes only discover peers with the same domain ID.
- Default: 0. Range: 0–101 (recommended 0–101 for DDS compatibility).

### Different ROS 2 Middleware Vendors
- ROS 2 abstracts DDS via RMW layer.
- Supported: Fast DDS, Cyclone DDS, Connext DDS.
- Cross-vendor communication within same distro: **NOT guaranteed**.

### Logging
- Severity levels: DEBUG, INFO, WARN, ERROR, FATAL.
- Configurable per-node and per-logger.
- Output to console, log files, `/rosout` topic.

### Quality of Service (QoS)
- Configure communication reliability and behavior.
- **Key policies**: Reliability (RELIABLE/BEST_EFFORT), Durability (TRANSIENT_LOCAL/VOLATILE), History (KEEP_LAST/KEEP_ALL), Depth, Deadline, Lifespan, Liveliness.
- Predefined profiles: `sensor_data`, `parameters`, `services`, `system_default`.
- Publishers and subscribers must have **compatible** QoS to connect.

### Executors
- Coordinate execution of callbacks (subscriptions, timers, services, actions).
- **SingleThreadedExecutor**: one callback at a time.
- **MultiThreadedExecutor**: multiple callbacks in parallel.
- **StaticSingleThreadedExecutor**: optimized for unchanging callback sets.

### Topic Statistics
- Built-in statistics for subscription callbacks: message age, message period.
- Published automatically to `/statistics` topics.

### RQt
- Qt-based GUI framework for ROS 2 tools and visualization.
- Plugin-based architecture (introspection, plotting, logging).

### Composition
- Run multiple nodes in a **single process** for efficiency.
- Reduces overhead of inter-process communication.
- Nodes must be written as "composable" (component-style).

### Cross-Compilation
- Build ROS 2 packages for a different target architecture.
- Common for embedded/ARM targets.

### Security
- ROS 2 supports **DDS Security** for encrypted communication.
- Authentication, access control, and cryptographic operations.
- Configured via security enclaves and keystores.

### Tf2
- Transform library for tracking coordinate frames over time.
- Maintains transform tree: relationships between frames.
- Core components: `tf2_ros`, `tf2_geometry_msgs`.
- Broadcasters publish transforms; listeners query transforms.

---

## ADVANCED CONCEPTS

### The Build System
- **ament**: the build system for ROS 2.
- **ament_cmake**: CMake-based build for C/C++ packages.
- **ament_python**: setuptools-based build for Python packages.
- **colcon**: the build tool that orchestrates building packages in a workspace.

### Internal ROS 2 Interfaces
- **rcl**: C library implementing core ROS 2 functionality.
- **rmw**: ROS Middleware interface — abstract API for DDS implementations.
- **rosidl**: Interface generation pipeline (IDL → language-specific code).

### ROS 2 Middleware Implementations
- RMW layer provides abstraction over DDS.
- Each implementation (Fast DDS, Cyclone DDS, Connext) has different performance characteristics.
- Selected at runtime via `RMW_IMPLEMENTATION` environment variable.

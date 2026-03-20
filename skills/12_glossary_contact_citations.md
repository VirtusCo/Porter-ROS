# ROS 2 Glossary, Contact & Citations — Skill File

> Source: https://docs.ros.org/en/jazzy/ (Glossary, Contact, Citations, Related Projects, Package Docs)
> Distro: Jazzy Jalisco

---

## Key ROS 2 Terminology

| Term | Definition |
|---|---|
| **Node** | A process that performs computation; communicates via topics, services, actions |
| **Topic** | Named bus for pub/sub message passing |
| **Service** | Synchronous request/response RPC |
| **Action** | Asynchronous long-running RPC with feedback and cancellation |
| **Parameter** | Runtime-configurable key-value pair associated with a node |
| **Package** | Unit of organization for ROS code, with build metadata |
| **Workspace** | Directory containing one or more packages being built together |
| **Underlay** | Base workspace (e.g., `/opt/ros/jazzy`) |
| **Overlay** | Workspace built on top of an underlay |
| **QoS** | Quality of Service — configures communication reliability/durability |
| **RMW** | ROS Middleware — abstraction layer over DDS implementations |
| **DDS** | Data Distribution Service — underlying pub/sub protocol |
| **IDL** | Interface Definition Language — describes msg/srv/action types |
| **colcon** | Collective construction — the build tool for ROS 2 workspaces |
| **ament** | Build system for ROS 2 (ament_cmake, ament_python) |
| **rosdep** | Tool to install system dependencies declared in package.xml |
| **bloom** | Release automation tool for ROS packages |
| **REP** | ROS Enhancement Proposal — formal design documents |
| **tf2** | Transform library — tracks coordinate frame relationships |
| **URDF** | Unified Robot Description Format — XML robot model |
| **xacro** | XML macro language for URDF files |
| **Launch** | System for starting multiple nodes with configuration |
| **Lifecycle Node** | Node with managed state transitions (configure/activate/deactivate) |
| **Composition** | Running multiple nodes in a single process |
| **Component** | A node designed for composition (loaded at runtime) |
| **ROS_DOMAIN_ID** | Environment variable partitioning ROS 2 communication |
| **Executor** | Coordinates callback execution in a node |
| **Callback Group** | Controls concurrency of callbacks (mutually exclusive or reentrant) |

---

## Contact & Community

| Resource | URL |
|---|---|
| **ROS Discourse** (primary forum) | https://discourse.ros.org |
| **ROS Answers** (Q&A) | https://answers.ros.org |
| **GitHub** (source + issues) | https://github.com/ros2 |
| **ROSCon** (annual conference) | https://roscon.ros.org |
| **ROS Wiki** (legacy) | https://wiki.ros.org |
| **Package Index** | https://index.ros.org |
| **API Docs** | https://docs.ros.org/en/jazzy/p/ |

---

## Related Projects

| Project | Description |
|---|---|
| **Gazebo (Ignition)** | Physics-based robot simulator |
| **MoveIt** | Motion planning framework |
| **Nav2** | Navigation stack (path planning, obstacle avoidance) |
| **micro-ROS** | ROS 2 for microcontrollers |
| **rosbridge** | WebSocket interface to ROS |
| **Foxglove** | Web-based visualization and debugging |
| **PlotJuggler** | Time-series data visualization |
| **ros1_bridge** | Communication bridge between ROS 1 and ROS 2 |
| **rosbag2** | Data recording and playback |
| **robot_localization** | State estimation (EKF/UKF) |

---

## Package Documentation

All released ROS 2 package API docs: https://docs.ros.org/en/jazzy/p/

Search packages at: https://index.ros.org/

---

## Citations

When citing ROS 2 in academic work:

```bibtex
@article{ros2,
  title={Robot Operating System 2: Design, architecture, and uses in the wild},
  author={Macenski, Steven and Foote, Tully and Gerkey, Brian and Lalancette, Chris and Woodall, William},
  journal={Science Robotics},
  year={2022}
}
```

---

## Key REPs (ROS Enhancement Proposals)

| REP | Title | Relevance |
|---|---|---|
| REP-0103 | Standard Units of Measure and Coordinate Conventions | Units (SI), coordinate frames (right-hand, ENU) |
| REP-0117 | Informational Distance Measurements | "too close" / "too far" conventions |
| REP-0140 | Package Manifest Format | `package.xml` format specification |
| REP-0144 | ROS Package Naming Conventions | Package naming rules |
| REP-0149 | Package Manifest Format 3 | Updated package.xml format |
| REP-2000 | ROS 2 Releases and Target Platforms | Platform support, dependency versions per distro |
| REP-2002 | Rolling Distribution | Rolling Ridley specification |
| REP-2004 | Package Quality Categories | Quality levels 1–5 for packages |

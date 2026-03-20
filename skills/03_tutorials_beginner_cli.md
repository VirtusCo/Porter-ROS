# ROS 2 Tutorials: Beginner CLI Tools — Skill File

> Source: https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools.html
> Distro: Jazzy Jalisco

---

## Sub-Documents

1. **Configuring environment** — Setup `ROS_DOMAIN_ID`, source setup files
2. **Using turtlesim, ros2, and rqt** — Interactive intro to ROS 2 basics
3. **Understanding nodes** — `ros2 node list`, `ros2 node info`
4. **Understanding topics** — `ros2 topic list/echo/info/pub`, `rqt_graph`
5. **Understanding services** — `ros2 service list/type/call`
6. **Understanding parameters** — `ros2 param list/get/set/dump/load`
7. **Understanding actions** — `ros2 action list/info/send_goal`
8. **Using rqt_console** — View and filter log messages
9. **Launching nodes** — `ros2 launch` with launch files
10. **Recording and playing back data** — `ros2 bag record/play`

---

## Key CLI Commands Reference

### Environment Setup
```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=<your_domain_id>   # default: 0
export ROS_LOCALHOST_ONLY=1             # restrict to localhost only
```

### Node Commands
```bash
ros2 run <package> <executable>           # Run a node
ros2 node list                            # List active nodes
ros2 node info /node_name                 # Get node details (pubs, subs, services, actions)
```

### Topic Commands
```bash
ros2 topic list                           # List all topics
ros2 topic list -t                        # List with types
ros2 topic echo /topic_name               # Print topic data
ros2 topic info /topic_name               # Show pub/sub count
ros2 topic pub /topic <msg_type> '{data}' # Publish to topic
ros2 topic hz /topic_name                 # Show publish rate
ros2 topic bw /topic_name                 # Show bandwidth
```

### Service Commands
```bash
ros2 service list                         # List all services
ros2 service list -t                      # List with types
ros2 service type /service_name           # Show service type
ros2 service find <type>                  # Find services by type
ros2 service call /srv <type> '{data}'    # Call a service
```

### Parameter Commands
```bash
ros2 param list                           # List all parameters
ros2 param get /node param_name           # Get parameter value
ros2 param set /node param_name value     # Set parameter value
ros2 param dump /node                     # Dump all params to stdout
ros2 param load /node params.yaml         # Load params from file
```

### Action Commands
```bash
ros2 action list                          # List all actions
ros2 action list -t                       # List with types
ros2 action info /action_name             # Show action servers/clients
ros2 action send_goal /action <type> '{data}'           # Send goal
ros2 action send_goal /action <type> '{data}' --feedback # With feedback
```

### Launch
```bash
ros2 launch <package> <launch_file>       # Run launch file
```

### Bag (Recording/Playback)
```bash
ros2 bag record /topic1 /topic2           # Record specific topics
ros2 bag record -a                        # Record all topics
ros2 bag record -o my_bag /topic          # Specify output name
ros2 bag info my_bag                      # Show bag metadata
ros2 bag play my_bag                      # Play back recorded data
```

### Introspection
```bash
ros2 interface show <msg/srv/action_type> # Show interface definition
ros2 interface list                       # List all interfaces
ros2 interface package <package>          # List interfaces in package
```

---

## rqt_graph

Visual tool to see the ROS 2 computation graph:
```bash
rqt_graph
```

Shows nodes as ovals and topics as rectangles with arrows for pub/sub connections.

---

## rqt_console

Log viewer with severity filtering:
```bash
ros2 run rqt_console rqt_console
```

Severity levels: Debug → Info → Warn → Error → Fatal

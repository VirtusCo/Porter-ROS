# virtus_msgs/IncidentEvent
# Single event in incident recording buffer
# Published on /incident/events

builtin_interfaces/Time stamp
uint8  severity                  # 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR, 4=FATAL
string source_node               # ROS 2 node name that generated this event
string event_type                # Machine-readable type e.g. "FSM_TRANSITION"
string description               # Human-readable description
string payload_json              # Optional JSON with structured event data

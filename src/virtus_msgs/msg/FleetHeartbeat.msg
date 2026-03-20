# virtus_msgs/FleetHeartbeat
# Robot to fleet backend heartbeat — sent every 30s

builtin_interfaces/Time stamp
string robot_id                  # Robot identifier
uint8  fsm_state                 # Current FSM state
uint8  battery_pct               # Battery percentage 0-100
float32 pos_x                    # Map position X (meters)
float32 pos_y                    # Map position Y (meters)
bool   is_serving                # True if actively serving a passenger
uint32 tasks_today               # Tasks completed today

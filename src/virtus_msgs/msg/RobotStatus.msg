# virtus_msgs/RobotStatus
# Complete robot status snapshot — published at 1Hz on /robot/status

builtin_interfaces/Time stamp
string robot_id                  # e.g. "virtus-cial-001"
string robot_name                # e.g. "CIAL Porter #1"

# Position
geometry_msgs/Pose2D pose        # x, y in meters (map frame), theta in radians
string current_zone              # Semantic zone name e.g. "Gate B"

# State
uint8  fsm_state                 # Current FSM state (see OrchestratorState constants)
string current_task              # Active task description

# Hardware health
float32 battery_voltage          # Volts
uint8   battery_pct              # 0-100 percent
float32 rail_12v                 # 12V rail voltage
float32 rail_5v                  # 5V rail voltage
float32 rail_33v                 # 3.3V rail voltage
uint16  motor_left_ma            # Left motor current (milliamps)
uint16  motor_right_ma           # Right motor current (milliamps)

# Compute health
uint8   cpu_pct                  # CPU usage percent
uint8   ram_pct                  # RAM usage percent
float32 cpu_temp_c               # CPU temperature (Celsius)
float32 disk_free_gb             # Free disk space (GB)

# Software versions
string ros_pkg_version           # semver e.g. "0.4.2"
string firmware_version          # semver e.g. "1.2.0"
string ai_model_version          # e.g. "qwen2.5-1.5b-virtus-v4"

# Session metrics
uint32 tasks_completed           # Tasks completed today
float32 distance_m               # Distance traveled today (meters)
uint16 errors_today              # Error count today
uint32 uptime_today_s            # Uptime today (seconds)

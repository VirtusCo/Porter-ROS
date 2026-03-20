# virtus_msgs/OrchestratorState
# Porter orchestrator FSM state — published at 5Hz on /orchestrator/state

builtin_interfaces/Time stamp

# Current FSM state
uint8 state
uint8 STATE_BOOT                = 0
uint8 STATE_HEALTH_CHECK        = 1
uint8 STATE_IDLE                = 2
uint8 STATE_PASSENGER_DETECTED  = 3
uint8 STATE_FOLLOWING           = 4
uint8 STATE_NAVIGATING          = 5
uint8 STATE_OBSTACLE_AVOIDANCE  = 6
uint8 STATE_ERROR               = 7
uint8 STATE_RECOVERY            = 8

# Transition info
string last_trigger              # Event that caused last transition
builtin_interfaces/Time state_entered_at  # When current state was entered
uint32 state_duration_ms         # How long in current state (ms)

# Active task
string current_task              # e.g. "Escorting passenger to Gate C5" or ""

# Recovery info
uint8 recovery_attempt           # 0 if not in recovery
uint8 recovery_max_attempts      # Configured max (default: 3)

# Error info
string error_code                # Machine-readable error code e.g. "STUCK_TIMEOUT"
string error_detail              # Human-readable detail

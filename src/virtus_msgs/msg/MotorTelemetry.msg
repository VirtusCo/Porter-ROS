# virtus_msgs/MotorTelemetry
# Motor driver telemetry — published at 10Hz on /hardware/motors

builtin_interfaces/Time stamp
uint8   left_rpwm_pct            # Left RPWM duty cycle 0-100 percent
uint8   left_lpwm_pct            # Left LPWM duty cycle 0-100 percent
bool    left_en                  # Left enable pin state
uint16  left_current_ma          # Left motor current (milliamps)
float32 left_temp_est_c          # Left estimated die temperature (Celsius)

uint8   right_rpwm_pct           # Right RPWM duty cycle 0-100 percent
uint8   right_lpwm_pct           # Right LPWM duty cycle 0-100 percent
bool    right_en                 # Right enable pin state
uint16  right_current_ma         # Right motor current (milliamps)
float32 right_temp_est_c         # Right estimated die temperature (Celsius)

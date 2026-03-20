# virtus_msgs/BridgeFrame
# Decoded ESP32 bridge protocol frame
# Raw binary: [0xAA][MSG_TYPE:1B][LENGTH:2B LE][PAYLOAD:NB][CRC16:2B LE]

builtin_interfaces/Time stamp
uint8  source                    # 0=ESP32_1 (motor), 1=ESP32_2 (sensors)
uint8  msg_type                  # Frame type constants below
bool   crc_valid                 # False if CRC16-CCITT check failed

uint8 TYPE_MOTOR_CMD     = 1     # RPi to ESP32 #1
uint8 TYPE_SENSOR_DATA   = 2     # ESP32 #2 to RPi
uint8 TYPE_MOTOR_STATUS  = 3     # ESP32 #1 to RPi
uint8 TYPE_HEARTBEAT     = 4     # Either direction
uint8 TYPE_ERROR_FRAME   = 255   # Error report

# TYPE_MOTOR_CMD payload
int16  motor_left_speed          # RPWM duty percent (-100 to +100)
int16  motor_right_speed         # RPWM duty percent (-100 to +100)
uint8  lift_cmd                  # 0=STOP, 1=UP, 2=DOWN

# TYPE_SENSOR_DATA payload
uint16 tof_mm                    # Time-of-Flight distance (mm)
uint16 ultrasonic_cm             # Ultrasonic distance (cm)
bool   microwave_detected        # Motion presence
float32 kalman_cm                # Kalman estimate (cm)

# TYPE_MOTOR_STATUS payload
uint16 left_current_ma           # Left motor current (mA)
uint16 right_current_ma          # Right motor current (mA)
bool   left_en                   # Left enable pin state
bool   right_en                  # Right enable pin state

# TYPE_HEARTBEAT payload
uint32 uptime_ms                 # ESP32 uptime (milliseconds)
uint8  error_flags               # Error bitmask

# TYPE_ERROR_FRAME payload
uint8  error_code                # Error code enum
uint16 error_context             # Additional context

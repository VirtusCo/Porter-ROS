# virtus_msgs/SensorFusion
# ESP32 #2 sensor fusion output — Kalman-filtered obstacle estimate
# Published at 50Hz on /sensor_fusion
# Source: porter_esp32_bridge, decoded from BridgeFrame type 0x02

builtin_interfaces/Time stamp
string frame_id                  # Always "base_link"

# Raw sensor readings (before fusion)
uint16 tof_mm                    # VL53L0X Time-of-Flight distance (mm). 0 = no reading.
uint16 ultrasonic_cm             # HC-SR04 ultrasonic distance (cm). 0 = no reading.
bool   microwave_detected        # RCWL-0516 motion presence (true = motion detected)

# Kalman filter output
float32 kalman_estimate_cm       # Fused distance estimate (cm)
float32 kalman_variance          # Estimate uncertainty — low = confident, high = uncertain

# Obstacle classification
uint8 obstacle_class             # 0=CLEAR, 1=NEAR(<50cm), 2=MEDIUM(50-150cm), 3=FAR(>150cm)
uint8 OBSTACLE_CLEAR   = 0
uint8 OBSTACLE_NEAR    = 1
uint8 OBSTACLE_MEDIUM  = 2
uint8 OBSTACLE_FAR     = 3

# Health flags (bitmask)
uint8 health_flags               # Bit 0: ToF OK, Bit 1: Ultrasonic OK, Bit 2: Microwave OK

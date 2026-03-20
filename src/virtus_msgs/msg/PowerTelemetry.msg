# virtus_msgs/PowerTelemetry
# Power management board telemetry — published at 10Hz on /hardware/power

builtin_interfaces/Time stamp
float32 v12                      # 12V rail voltage (Volts)
float32 v5                       # 5V rail voltage (Volts)
float32 v33                      # 3.3V rail voltage (Volts)
uint16  i12_ma                   # 12V rail current (milliamps)
uint16  i5_ma                    # 5V rail current (milliamps)
bool[4] relay_states             # K1-K4 relay states (true = energized)

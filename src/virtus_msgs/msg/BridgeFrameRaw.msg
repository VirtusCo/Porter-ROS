# virtus_msgs/BridgeFrameRaw
# Raw binary frame before decoding — for bridge debugger

builtin_interfaces/Time stamp
uint8[] raw_bytes                # Complete frame bytes including header and CRC
uint8  source                    # 0=ESP32_1 (motor), 1=ESP32_2 (sensors)

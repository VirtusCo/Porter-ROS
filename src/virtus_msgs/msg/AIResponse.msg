# virtus_msgs/AIResponse
# Virtue AI text response to passenger
# Published on /ai_assistant/response

builtin_interfaces/Time stamp
string session_id                # Passenger session
string text                      # Response text in passenger language
string language                  # ISO 639-1 language code
float32 inference_time_ms        # Time to generate response (ms)
string model_version             # Model/adapter that produced this
bool   used_tool                 # True if a ROS 2 tool was called
string tool_called               # Tool name if used_tool is true

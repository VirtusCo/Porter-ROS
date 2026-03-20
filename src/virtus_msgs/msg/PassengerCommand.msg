# virtus_msgs/PassengerCommand
# Structured command parsed from passenger speech/text by Virtue AI
# Published on /ai_assistant/command

builtin_interfaces/Time stamp
string session_id                # Passenger session identifier

# Intent classification
uint8  intent                    # See constants below
uint8  INTENT_NAVIGATE     = 1   # Go to a location
uint8  INTENT_FOLLOW       = 2   # Follow the passenger
uint8  INTENT_STOP         = 3   # Stop movement
uint8  INTENT_WAIT         = 4   # Wait at current location
uint8  INTENT_INFO_QUERY   = 5   # Question (no movement)
uint8  INTENT_WEIGH        = 6   # Weigh luggage
uint8  INTENT_ASSIST       = 7   # Call human assistance

# Navigation target (for INTENT_NAVIGATE)
string destination_id            # Semantic ID e.g. "gate_c5"
string destination_label         # Human-readable e.g. "Gate C5"

# Confidence
float32 confidence               # 0.0-1.0

# Original utterance
string raw_text                  # Original passenger text
string language                  # ISO 639-1: "en", "ml", "hi", "ta"

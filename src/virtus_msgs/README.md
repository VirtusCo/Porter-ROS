# virtus_msgs — Virtus Message Definition Library (VDL)

Single source of truth for all custom ROS 2 message, service, and action types in the Virtusco stack.

## Messages (11)

| Message | Topic | Hz | Publisher |
|---------|-------|----|-----------|
| SensorFusion | /sensor_fusion | 50 | porter_esp32_bridge |
| OrchestratorState | /orchestrator/state | 5 | porter_orchestrator |
| BridgeFrame | /esp32_bridge/rx, /tx | 50 | porter_esp32_bridge |
| BridgeFrameRaw | /esp32_bridge/raw | 50 | porter_esp32_bridge |
| RobotStatus | /robot/status | 1 | porter_telemetry |
| PassengerCommand | /ai_assistant/command | on-demand | porter_ai_assistant |
| AIResponse | /ai_assistant/response | on-demand | porter_ai_assistant |
| PowerTelemetry | /hardware/power | 10 | porter_telemetry |
| MotorTelemetry | /hardware/motors | 10 | porter_telemetry |
| FleetHeartbeat | /fleet/heartbeat | 0.033 | porter_telemetry |
| IncidentEvent | /incident/events | on-demand | all nodes |

## Services (5)

| Service | Purpose |
|---------|---------|
| GetFlightInfo | Query airport flight database |
| NavigateTo | Request robot navigation |
| ManualOverride | Operator override (stop/resume/estop) |
| GetRobotStatus | Full status snapshot |
| UpdateConfig | Dynamic configuration update |

## Actions (1)

| Action | Purpose |
|--------|---------|
| EscortPassenger | Full passenger escort lifecycle |

## Usage

Python:
```python
from virtus_msgs.msg import SensorFusion, OrchestratorState
from virtus_msgs.srv import NavigateTo
from virtus_msgs.action import EscortPassenger
```

C++:
```cpp
#include "virtus_msgs/msg/sensor_fusion.hpp"
#include "virtus_msgs/srv/navigate_to.hpp"
```

## Build

```bash
colcon build --packages-select virtus_msgs
```

# Changelog — virtus_msgs

## [1.0.0] — 2026-03-20

### Added
- SensorFusion.msg — ESP32 #2 Kalman-filtered obstacle estimate
- OrchestratorState.msg — 9-state FSM with transition history
- BridgeFrame.msg — Decoded ESP32 serial protocol frame
- BridgeFrameRaw.msg — Raw binary frame for debugger
- RobotStatus.msg — Complete robot health snapshot
- PassengerCommand.msg — AI-parsed passenger intent
- AIResponse.msg — Virtue AI text response
- PowerTelemetry.msg — Power rail voltages and currents
- MotorTelemetry.msg — BTS7960 motor driver telemetry
- FleetHeartbeat.msg — Robot-to-fleet heartbeat
- IncidentEvent.msg — Incident buffer event
- GetFlightInfo.srv — Flight information query
- NavigateTo.srv — Navigation request
- ManualOverride.srv — Operator override
- GetRobotStatus.srv — Status snapshot request
- UpdateConfig.srv — Dynamic config update
- EscortPassenger.action — Full escort lifecycle

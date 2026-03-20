cmake_minimum_required(VERSION 3.8)
project(virtus_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/SensorFusion.msg"
  "msg/OrchestratorState.msg"
  "msg/BridgeFrame.msg"
  "msg/BridgeFrameRaw.msg"
  "msg/RobotStatus.msg"
  "msg/PassengerCommand.msg"
  "msg/AIResponse.msg"
  "msg/PowerTelemetry.msg"
  "msg/MotorTelemetry.msg"
  "msg/FleetHeartbeat.msg"
  "msg/IncidentEvent.msg"
  "srv/GetFlightInfo.srv"
  "srv/NavigateTo.srv"
  "srv/ManualOverride.srv"
  "srv/GetRobotStatus.srv"
  "srv/UpdateConfig.srv"
  "action/EscortPassenger.action"
  DEPENDENCIES std_msgs geometry_msgs builtin_interfaces
)

ament_package()

// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

// Data models for the Porter Robot GUI.

/// Chat message from user or AI assistant (Virtue).
class ChatMessage {
  /// Visible text — updated progressively during streaming.
  String text;
  final bool isUser;
  final DateTime timestamp;

  /// Whether this message is currently being streamed in.
  bool isStreaming;

  /// Extracted tool_call / tool_response blocks (AI messages only).
  final List<String> toolCalls;

  ChatMessage.now({
    required this.text,
    required this.isUser,
    this.isStreaming = false,
    List<String>? toolCalls,
  })  : toolCalls = toolCalls ?? [],
        timestamp = DateTime.now();
}

/// ROS node health status.
enum HealthLevel { ok, warn, error, stale, unknown }

/// Diagnostic status for a single ROS node or subsystem.
class DiagnosticStatus {
  final String name;
  final HealthLevel level;
  final String message;
  final DateTime timestamp;
  final Map<String, String> values;

  const DiagnosticStatus({
    required this.name,
    required this.level,
    this.message = '',
    required this.timestamp,
    this.values = const {},
  });

  factory DiagnosticStatus.unknown(String name) {
    return DiagnosticStatus(
      name: name,
      level: HealthLevel.unknown,
      message: 'No data',
      timestamp: DateTime.now(),
    );
  }
}

/// Robot operational state (matches porter_orchestrator states).
enum RobotState {
  booting,
  idle,
  followMe,
  navigating,
  error,
  emergencyStop,
}

/// Flight information for display panel.
class FlightInfo {
  final String flightNumber;
  final String airline;
  final String destination;
  final String gate;
  final String terminal;
  final String status; // "On Time", "Delayed", "Boarding", "Departed"
  final DateTime scheduledTime;
  final DateTime? estimatedTime;

  const FlightInfo({
    required this.flightNumber,
    required this.airline,
    required this.destination,
    required this.gate,
    required this.terminal,
    required this.status,
    required this.scheduledTime,
    this.estimatedTime,
  });
}

/// Map waypoint / point of interest.
class MapPoi {
  final String name;
  final String category; // "gate", "restroom", "restaurant", "shop", "service"
  final double x;
  final double y;
  final String? description;

  const MapPoi({
    required this.name,
    required this.category,
    required this.x,
    required this.y,
    this.description,
  });
}

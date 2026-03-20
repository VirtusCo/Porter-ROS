// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import '../models/models.dart';
import '../services/ai_service.dart';
import '../services/ros_bridge_service.dart';

/// Manages connection to rosbridge and exposes connection state.
class ConnectionProvider extends ChangeNotifier {
  final RosBridgeService _ros;
  StreamSubscription<bool>? _sub;

  bool _connected = false;
  bool get connected => _connected;

  ConnectionProvider(this._ros) {
    _sub = _ros.connectionStream.listen((state) {
      _connected = state;
      notifyListeners();
    });
  }

  Future<void> connect() async {
    await _ros.connect();
  }

  void disconnect() {
    _ros.disconnect();
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}

/// AI Chat provider — sends queries to Virtue and receives responses.
///
/// Uses direct HTTP to the AI server (preferred) with fallback to rosbridge.
class ChatProvider extends ChangeNotifier {
  final RosBridgeService _ros;
  final AiService _aiService;
  final List<ChatMessage> _messages = [];
  bool _isResponding = false;
  bool _aiServerAvailable = false;
  Timer? _healthCheckTimer;
  Timer? _streamTimer;
  String? _streamingFullText;
  StreamSubscription<StreamEvent>? _sseSubscription;

  /// Maximum number of messages to keep in memory.
  static const int _maxMessages = 100;

  /// Cached unmodifiable view — invalidated on mutation.
  List<ChatMessage>? _cachedMessages;

  List<ChatMessage> get messages {
    _cachedMessages ??= List.unmodifiable(_messages);
    return _cachedMessages!;
  }

  /// Invalidate cache and notify listeners.
  void _mutated() {
    _cachedMessages = null;
    notifyListeners();
  }

  bool get isResponding => _isResponding;
  bool get aiServerAvailable => _aiServerAvailable;

  ChatProvider(this._ros, this._aiService) {
    // Subscribe to AI response topic (rosbridge fallback).
    _ros.subscribe(
      '/porter/ai_response',
      'std_msgs/msg/String',
      _onAiResponse,
    );

    // Check AI server availability periodically (30s to reduce overhead).
    _checkAiServer();
    _healthCheckTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _checkAiServer(),
    );
  }

  Future<void> _checkAiServer() async {
    final available = await _aiService.checkHealth();
    if (available != _aiServerAvailable) {
      _aiServerAvailable = available;
      debugPrint(
        '[ChatProvider] AI server ${available ? "available" : "unavailable"}',
      );
      notifyListeners();
    }
  }

  /// Send a user query to the AI assistant.
  void sendMessage(String text) {
    if (text.trim().isEmpty) return;

    // Cancel any active streaming.
    _cancelStreaming();

    // Add user message.
    _messages.add(ChatMessage.now(text: text, isUser: true));
    _trimMessages();
    _isResponding = true;
    _mutated();

    // Use direct AI server if available, otherwise rosbridge.
    if (_aiServerAvailable) {
      _sendDirectQuery(text);
    } else {
      _sendViRosbridge(text);
    }
  }

  /// Send query directly to the AI HTTP server via SSE streaming.
  Future<void> _sendDirectQuery(String text) async {
    // Create AI message immediately for streaming into.
    final msg = ChatMessage.now(
      text: '',
      isUser: false,
      isStreaming: true,
    );
    _messages.add(msg);
    _trimMessages();
    _isResponding = false;
    _mutated();

    try {
      _sseSubscription?.cancel();
      _sseSubscription = _aiService.chatStream(text).listen(
        (event) {
          switch (event.type) {
            case 'adapter':
              // Adapter info — can be used for UI hints.
              break;
            case 'tool_call':
              // Add tool call to the message to trigger shimmer.
              final tcData = event.data['tool_call'];
              final tcStr = tcData is String ? tcData : jsonEncode(tcData);
              msg.toolCalls.add(tcStr);
              _mutated();
              break;
            case 'tool_result':
              // Tool result arrived — shimmer will stop when tokens flow.
              break;
            case 'token':
              final token = event.data['token'] as String? ?? '';
              msg.text += token;
              _mutated();
              break;
            case 'done':
              msg.isStreaming = false;
              _sseSubscription = null;
              _mutated();
              break;
            case 'error':
              final error = event.data['error'] as String? ?? 'Unknown error';
              if (msg.text.isEmpty) {
                msg.text = 'Sorry, I encountered an error: $error';
              }
              msg.isStreaming = false;
              _sseSubscription = null;
              _mutated();
              break;
          }
        },
        onError: (e) {
          if (msg.text.isEmpty) {
            msg.text = 'Connection error: $e';
          }
          msg.isStreaming = false;
          _sseSubscription = null;
          _mutated();
        },
        onDone: () {
          msg.isStreaming = false;
          _sseSubscription = null;
          _mutated();
        },
      );
    } catch (e) {
      msg.text = 'Connection error: $e';
      msg.isStreaming = false;
      _mutated();
    }
  }

  /// Cancel any active text streaming.
  void _cancelStreaming() {
    _streamTimer?.cancel();
    _streamTimer = null;
    _sseSubscription?.cancel();
    _sseSubscription = null;
    if (_messages.isNotEmpty && _messages.last.isStreaming) {
      _messages.last.isStreaming = false;
    }
    _streamingFullText = null;
  }

  /// Send query via rosbridge (fallback when AI server is not running).
  void _sendViRosbridge(String text) {
    _ros.publish(
      '/porter/ai_query',
      'std_msgs/msg/String',
      {'data': text},
    );

    // Add timeout — if no response in 15s, show error.
    Future.delayed(const Duration(seconds: 15), () {
      if (_isResponding) {
        _messages.add(ChatMessage.now(
          text: 'No response received. Make sure the AI server is running:\n'
              'source .venv-finetune/bin/activate && '
              'python src/porter_ai_assistant/scripts/ai_server.py',
          isUser: false,
        ));
        _isResponding = false;
        _mutated();
      }
    });
  }

  void _onAiResponse(Map<String, dynamic> msg) {
    final rawData = msg['data'] as String? ?? '';
    if (rawData.isEmpty) return;

    // Parse JSON response from the AI assistant node.
    String displayText;
    try {
      final data = jsonDecode(rawData) as Map<String, dynamic>;
      displayText = data['response'] as String? ?? rawData;
    } catch (_) {
      // Not JSON — use raw text.
      displayText = rawData;
    }

    // Rosbridge fallback: add complete message (no real streaming).
    _messages.add(ChatMessage.now(text: displayText, isUser: false));
    _trimMessages();
    _isResponding = false;
    _mutated();
  }

  /// Trim messages to stay under memory cap.
  void _trimMessages() {
    while (_messages.length > _maxMessages) {
      _messages.removeAt(0);
    }
  }

  void clearMessages() {
    _cancelStreaming();
    _messages.clear();
    _mutated();
  }

  /// Regenerate the last AI response by re-sending the last user query.
  void regenerateLastResponse() {
    // Find the last user message.
    String? lastUserText;
    int removeFrom = _messages.length;
    for (int i = _messages.length - 1; i >= 0; i--) {
      if (_messages[i].isUser) {
        lastUserText = _messages[i].text;
        // Remove everything from this user message onward.
        removeFrom = i;
        break;
      }
    }
    if (lastUserText == null) return;

    _cancelStreaming();
    _messages.removeRange(removeFrom, _messages.length);
    _mutated();

    // Re-send.
    sendMessage(lastUserText);
  }

  @override
  void dispose() {
    _healthCheckTimer?.cancel();
    _streamTimer?.cancel();
    _sseSubscription?.cancel();
    super.dispose();
  }
}

/// System status provider — monitors all subsystem diagnostics.
class SystemStatusProvider extends ChangeNotifier {
  final RosBridgeService _ros;
  final Map<String, DiagnosticStatus> _diagnostics = {};
  RobotState _robotState = RobotState.booting;
  double _batteryPercent = -1; // -1 = unknown
  double _cpuTemp = -1;

  Map<String, DiagnosticStatus> get diagnostics =>
      Map.unmodifiable(_diagnostics);
  RobotState get robotState => _robotState;
  double get batteryPercent => _batteryPercent;
  double get cpuTemp => _cpuTemp;

  HealthLevel get overallHealth {
    if (_diagnostics.isEmpty) return HealthLevel.unknown;
    if (_diagnostics.values.any((d) => d.level == HealthLevel.error)) {
      return HealthLevel.error;
    }
    if (_diagnostics.values.any((d) => d.level == HealthLevel.warn)) {
      return HealthLevel.warn;
    }
    if (_diagnostics.values.any((d) => d.level == HealthLevel.stale)) {
      return HealthLevel.stale;
    }
    return HealthLevel.ok;
  }

  SystemStatusProvider(this._ros) {
    // Subscribe to diagnostics.
    _ros.subscribe(
      '/diagnostics',
      'diagnostic_msgs/msg/DiagnosticArray',
      _onDiagnostics,
      throttleRate: 500, // Max 2 Hz to GUI
    );

    // Subscribe to robot state.
    _ros.subscribe(
      '/porter/state',
      'std_msgs/msg/String',
      _onRobotState,
    );
  }

  void _onDiagnostics(Map<String, dynamic> msg) {
    final statusList = msg['status'] as List<dynamic>? ?? [];
    for (final statusMap in statusList) {
      final s = statusMap as Map<String, dynamic>;
      final name = s['name'] as String? ?? 'unknown';
      final levelByte = s['level'] as int? ?? 3;
      final message = s['message'] as String? ?? '';

      // Parse key-value pairs.
      final values = <String, String>{};
      final kvList = s['values'] as List<dynamic>? ?? [];
      for (final kv in kvList) {
        final kvMap = kv as Map<String, dynamic>;
        values[kvMap['key'] as String] = kvMap['value'] as String;
      }

      HealthLevel level;
      switch (levelByte) {
        case 0:
          level = HealthLevel.ok;
          break;
        case 1:
          level = HealthLevel.warn;
          break;
        case 2:
          level = HealthLevel.error;
          break;
        case 3:
          level = HealthLevel.stale;
          break;
        default:
          level = HealthLevel.unknown;
      }

      _diagnostics[name] = DiagnosticStatus(
        name: name,
        level: level,
        message: message,
        timestamp: DateTime.now(),
        values: values,
      );

      // Extract battery and CPU temp if present.
      if (values.containsKey('battery_percent')) {
        _batteryPercent =
            double.tryParse(values['battery_percent']!) ?? _batteryPercent;
      }
      if (values.containsKey('cpu_temperature')) {
        _cpuTemp =
            double.tryParse(values['cpu_temperature']!) ?? _cpuTemp;
      }
    }
    notifyListeners();
  }

  void _onRobotState(Map<String, dynamic> msg) {
    final stateStr = msg['data'] as String? ?? '';
    switch (stateStr.toUpperCase()) {
      case 'IDLE':
        _robotState = RobotState.idle;
        break;
      case 'FOLLOW_ME':
        _robotState = RobotState.followMe;
        break;
      case 'NAVIGATING':
        _robotState = RobotState.navigating;
        break;
      case 'ERROR':
        _robotState = RobotState.error;
        break;
      case 'EMERGENCY_STOP':
      case 'ESTOP':
        _robotState = RobotState.emergencyStop;
        break;
      default:
        _robotState = RobotState.booting;
    }
    notifyListeners();
  }
}

/// Emergency stop provider — handles E-stop toggle.
class EmergencyStopProvider extends ChangeNotifier {
  final RosBridgeService _ros;
  bool _isEngaged = false;

  bool get isEngaged => _isEngaged;

  EmergencyStopProvider(this._ros);

  /// Engage emergency stop.
  void engage() {
    _isEngaged = true;
    _ros.publish(
      '/porter/emergency_stop',
      'std_msgs/msg/Bool',
      {'data': true},
    );
    notifyListeners();
  }

  /// Disengage emergency stop (requires confirmation).
  void disengage() {
    _isEngaged = false;
    _ros.publish(
      '/porter/emergency_stop',
      'std_msgs/msg/Bool',
      {'data': false},
    );
    notifyListeners();
  }
}

/// Follow-Me mode provider.
class FollowMeProvider extends ChangeNotifier {
  final RosBridgeService _ros;
  bool _isActive = false;
  final double _distance = 0.0;

  bool get isActive => _isActive;
  double get distance => _distance;

  FollowMeProvider(this._ros) {
    // Subscribe to follow-me status.
    _ros.subscribe(
      '/porter/follow_me/status',
      'std_msgs/msg/String',
      _onStatus,
    );
  }

  void toggle() {
    _isActive = !_isActive;
    _ros.publish(
      '/porter/follow_me/command',
      'std_msgs/msg/Bool',
      {'data': _isActive},
    );
    notifyListeners();
  }

  void _onStatus(Map<String, dynamic> msg) {
    final data = msg['data'] as String? ?? '';
    if (data == 'ACTIVE') {
      _isActive = true;
    } else if (data == 'INACTIVE') {
      _isActive = false;
    }
    notifyListeners();
  }
}

/// Flight information provider — demo data + subscribes to flight topic.
class FlightInfoProvider extends ChangeNotifier {
  final RosBridgeService _ros;
  List<FlightInfo> _flights = [];

  List<FlightInfo> get flights => List.unmodifiable(_flights);

  FlightInfoProvider(this._ros) {
    // Load demo data initially.
    _loadDemoFlights();

    // Subscribe to flight updates (for future integration).
    _ros.subscribe(
      '/porter/flight_info',
      'std_msgs/msg/String',
      _onFlightUpdate,
    );
  }

  void _loadDemoFlights() {
    final now = DateTime.now();
    _flights = [
      FlightInfo(
        flightNumber: 'AI-101',
        airline: 'Air India',
        destination: 'Mumbai (BOM)',
        gate: 'A12',
        terminal: 'T3',
        status: 'Boarding',
        scheduledTime: now.add(const Duration(minutes: 30)),
      ),
      FlightInfo(
        flightNumber: '6E-302',
        airline: 'IndiGo',
        destination: 'Delhi (DEL)',
        gate: 'B7',
        terminal: 'T2',
        status: 'On Time',
        scheduledTime: now.add(const Duration(hours: 1, minutes: 15)),
      ),
      FlightInfo(
        flightNumber: 'SG-450',
        airline: 'SpiceJet',
        destination: 'Goa (GOI)',
        gate: 'C3',
        terminal: 'T1',
        status: 'Delayed',
        scheduledTime: now.add(const Duration(hours: 2)),
        estimatedTime: now.add(const Duration(hours: 2, minutes: 45)),
      ),
      FlightInfo(
        flightNumber: 'UK-835',
        airline: 'Vistara',
        destination: 'Bangalore (BLR)',
        gate: 'A5',
        terminal: 'T3',
        status: 'On Time',
        scheduledTime: now.add(const Duration(hours: 3)),
      ),
      FlightInfo(
        flightNumber: 'EK-505',
        airline: 'Emirates',
        destination: 'Dubai (DXB)',
        gate: 'D1',
        terminal: 'T3',
        status: 'On Time',
        scheduledTime: now.add(const Duration(hours: 4)),
      ),
      FlightInfo(
        flightNumber: 'SQ-423',
        airline: 'Singapore Airlines',
        destination: 'Singapore (SIN)',
        gate: 'D8',
        terminal: 'T3',
        status: 'On Time',
        scheduledTime: now.add(const Duration(hours: 5, minutes: 30)),
      ),
    ];
    notifyListeners();
  }

  void _onFlightUpdate(Map<String, dynamic> msg) {
    // Future: parse JSON flight update from ROS topic.
    debugPrint('[FlightInfo] Received update: $msg');
  }

  void refresh() {
    _loadDemoFlights();
  }
}

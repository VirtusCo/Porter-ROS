// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// rosbridge v2.0 protocol client for ROS 2 communication.
///
/// Connects to rosbridge_server WebSocket (default ws://localhost:9090).
/// Handles topic subscribe/publish, service calls, and reconnection.
class RosBridgeService {
  final String url;
  final Duration reconnectDelay;
  final int maxReconnectAttempts;

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;
  bool _disposed = false;
  String _idCounter = 'porter_gui_0';
  int _idNum = 0;

  /// Callbacks keyed by topic name.
  final Map<String, List<void Function(Map<String, dynamic>)>>
      _topicCallbacks = {};

  /// Callbacks keyed by service call ID (one-shot).
  final Map<String, Completer<Map<String, dynamic>>> _serviceCallbacks = {};

  final StreamController<bool> _connectionController =
      StreamController<bool>.broadcast();

  /// Stream of connection state changes.
  Stream<bool> get connectionStream => _connectionController.stream;

  bool _connected = false;
  bool get isConnected => _connected;

  RosBridgeService({
    this.url = 'ws://localhost:9090',
    this.reconnectDelay = const Duration(seconds: 3),
    this.maxReconnectAttempts = 20, // Stop after 20 to avoid resource waste
  });

  /// Generate a unique message ID.
  String _nextId() {
    _idNum++;
    _idCounter = 'porter_gui_$_idNum';
    return _idCounter;
  }

  /// Connect to rosbridge WebSocket server.
  Future<void> connect() async {
    if (_disposed) return;

    try {
      debugPrint('[RosBridge] Connecting to $url');
      _channel = WebSocketChannel.connect(Uri.parse(url));

      // Wait for connection to be ready.
      await _channel!.ready;

      _connected = true;
      _reconnectAttempts = 0;
      _connectionController.add(true);
      debugPrint('[RosBridge] Connected to $url');

      _subscription = _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDone,
      );

      // Re-subscribe to any topics that were subscribed before reconnect.
      for (final topic in _topicCallbacks.keys) {
        _sendSubscribe(topic);
      }
    } catch (e) {
      debugPrint('[RosBridge] Connection failed: $e');
      _connected = false;
      _connectionController.add(false);
      _scheduleReconnect();
    }
  }

  /// Disconnect from rosbridge.
  void disconnect() {
    _reconnectTimer?.cancel();
    _subscription?.cancel();
    _channel?.sink.close();
    _channel = null;
    _connected = false;
    _connectionController.add(false);
    debugPrint('[RosBridge] Disconnected');
  }

  /// Subscribe to a ROS topic.
  void subscribe(
    String topic,
    String type,
    void Function(Map<String, dynamic>) callback, {
    int throttleRate = 0,
    int queueLength = 1,
  }) {
    _topicCallbacks.putIfAbsent(topic, () => []);
    _topicCallbacks[topic]!.add(callback);

    if (_connected) {
      _sendSubscribe(topic, type: type, throttleRate: throttleRate,
          queueLength: queueLength);
    }
  }

  /// Unsubscribe from a ROS topic.
  void unsubscribe(String topic) {
    _topicCallbacks.remove(topic);
    if (_connected) {
      _send({
        'op': 'unsubscribe',
        'topic': topic,
      });
    }
  }

  /// Publish a message to a ROS topic.
  void publish(String topic, String type, Map<String, dynamic> msg) {
    if (!_connected) {
      debugPrint('[RosBridge] Cannot publish to $topic: not connected');
      return;
    }
    _send({
      'op': 'publish',
      'topic': topic,
      'type': type,
      'msg': msg,
    });
  }

  /// Call a ROS service and wait for response.
  Future<Map<String, dynamic>> callService(
    String service,
    String type, {
    Map<String, dynamic>? args,
    Duration timeout = const Duration(seconds: 10),
  }) async {
    if (!_connected) {
      throw Exception('Not connected to rosbridge');
    }

    final id = _nextId();
    final completer = Completer<Map<String, dynamic>>();
    _serviceCallbacks[id] = completer;

    _send({
      'op': 'call_service',
      'id': id,
      'service': service,
      'type': type,
      'args': ?args,
    });

    // Timeout handling.
    return completer.future.timeout(
      timeout,
      onTimeout: () {
        _serviceCallbacks.remove(id);
        throw TimeoutException('Service call to $service timed out');
      },
    );
  }

  void _sendSubscribe(
    String topic, {
    String? type,
    int throttleRate = 0,
    int queueLength = 1,
  }) {
    final msg = <String, dynamic>{
      'op': 'subscribe',
      'topic': topic,
      'type': ?type,
      'throttle_rate': throttleRate,
      'queue_length': queueLength,
    };
    _send(msg);
  }

  void _send(Map<String, dynamic> msg) {
    if (_channel == null) return;
    try {
      _channel!.sink.add(jsonEncode(msg));
    } catch (e) {
      debugPrint('[RosBridge] Send error: $e');
    }
  }

  void _onMessage(dynamic rawMessage) {
    try {
      final msg = jsonDecode(rawMessage as String) as Map<String, dynamic>;
      final op = msg['op'] as String?;

      switch (op) {
        case 'publish':
          // Topic message.
          final topic = msg['topic'] as String?;
          final data = msg['msg'] as Map<String, dynamic>?;
          if (topic != null && data != null) {
            final callbacks = _topicCallbacks[topic];
            if (callbacks != null) {
              for (final cb in callbacks) {
                cb(data);
              }
            }
          }
          break;

        case 'service_response':
          // Service call response.
          final id = msg['id'] as String?;
          if (id != null && _serviceCallbacks.containsKey(id)) {
            final completer = _serviceCallbacks.remove(id)!;
            final success = msg['result'] as bool? ?? true;
            if (success) {
              completer.complete(
                  msg['values'] as Map<String, dynamic>? ?? {});
            } else {
              completer.completeError(
                  Exception('Service call failed: ${msg['values']}'));
            }
          }
          break;

        default:
          break;
      }
    } catch (e) {
      debugPrint('[RosBridge] Message parse error: $e');
    }
  }

  void _onError(dynamic error) {
    debugPrint('[RosBridge] WebSocket error: $error');
    _connected = false;
    _connectionController.add(false);
    _scheduleReconnect();
  }

  void _onDone() {
    debugPrint('[RosBridge] WebSocket closed');
    _connected = false;
    _connectionController.add(false);
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    if (maxReconnectAttempts >= 0 &&
        _reconnectAttempts >= maxReconnectAttempts) {
      debugPrint('[RosBridge] Max reconnect attempts reached');
      return;
    }

    // Exponential backoff: 3s, 6s, 12s, 24s, 48s, 60s (capped).
    final backoffMs = (reconnectDelay.inMilliseconds *
            (1 << _reconnectAttempts.clamp(0, 5)))
        .clamp(0, 60000);
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(milliseconds: backoffMs), () {
      _reconnectAttempts++;
      debugPrint(
          '[RosBridge] Reconnect attempt $_reconnectAttempts'
          ' (backoff ${backoffMs}ms)');
      connect();
    });
  }

  /// Dispose all resources.
  void dispose() {
    _disposed = true;
    disconnect();
    _connectionController.close();
    _topicCallbacks.clear();
    _serviceCallbacks.clear();
  }
}

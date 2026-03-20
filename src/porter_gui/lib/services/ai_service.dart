// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// Direct HTTP client for the Porter AI server.
///
/// Connects to the standalone Python AI HTTP server (ai_server.py)
/// running on localhost:8085. Provides chat queries and health checks
/// without requiring ROS 2 or rosbridge.
class AiService {
  final String baseUrl;
  final HttpClient _client;
  final Duration timeout;

  bool _serverAvailable = false;

  /// Whether the AI server is reachable.
  bool get isAvailable => _serverAvailable;

  AiService({
    this.baseUrl = 'http://localhost:8085',
    this.timeout = const Duration(seconds: 30),
  }) : _client = HttpClient() {
    _client.connectionTimeout = const Duration(seconds: 5);
  }

  /// Check if the AI server is reachable and model is loaded.
  Future<bool> checkHealth() async {
    try {
      final uri = Uri.parse('$baseUrl/api/status');
      final request = await _client.getUrl(uri);
      final response = await request.close().timeout(
        const Duration(seconds: 3),
      );

      if (response.statusCode == 200) {
        final body = await response.transform(utf8.decoder).join();
        final data = jsonDecode(body) as Map<String, dynamic>;
        _serverAvailable = data['model_loaded'] == true;
        return _serverAvailable;
      }
    } catch (e) {
      debugPrint('[AiService] Health check failed: $e');
    }
    _serverAvailable = false;
    return false;
  }

  /// Send a chat query to the AI server and return the response text.
  ///
  /// [history] is an optional list of previous messages, each a map with
  /// 'role' ('user' or 'assistant') and 'content' keys. The server uses
  /// these for multi-turn context so follow-up replies are coherent.
  Future<ChatResponse> chat(
    String query, {
    List<Map<String, String>>? history,
  }) async {
    final uri = Uri.parse('$baseUrl/api/chat');

    try {
      final request = await _client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      // Encode body to bytes first, then set explicit Content-Length
      // to avoid chunked transfer encoding (Python's BaseHTTPRequestHandler
      // doesn't handle chunked encoding).
      final payload = <String, dynamic>{'query': query};
      if (history != null && history.isNotEmpty) {
        payload['history'] = history;
      }
      final bodyBytes = utf8.encode(jsonEncode(payload));
      request.contentLength = bodyBytes.length;
      request.add(bodyBytes);

      final response = await request.close().timeout(timeout);
      final body = await response.transform(utf8.decoder).join();
      final data = jsonDecode(body) as Map<String, dynamic>;

      if (response.statusCode == 200) {
        _serverAvailable = true;
        // Extract tool_calls from server response (orchestrator provides them).
        final rawToolCalls = data['tool_calls'] as List<dynamic>? ?? [];
        final toolCalls = rawToolCalls
            .map((tc) => tc is String ? tc : jsonEncode(tc))
            .toList();
        return ChatResponse(
          text: data['response'] as String? ?? '',
          query: data['query'] as String? ?? query,
          latencyMs: (data['latency_ms'] as num?)?.toDouble() ?? 0.0,
          adapter: data['adapter'] as String? ?? 'unknown',
          success: true,
          toolCalls: toolCalls,
        );
      } else {
        final error = data['error'] as String? ?? 'Unknown error';
        return ChatResponse(
          text: '',
          query: query,
          error: error,
          success: false,
        );
      }
    } on TimeoutException {
      return ChatResponse(
        text: '',
        query: query,
        error: 'Request timed out — the AI is taking too long to respond.',
        success: false,
      );
    } on SocketException catch (e) {
      _serverAvailable = false;
      return ChatResponse(
        text: '',
        query: query,
        error: 'AI server not reachable: ${e.message}',
        success: false,
      );
    } catch (e) {
      return ChatResponse(
        text: '',
        query: query,
        error: 'Unexpected error: $e',
        success: false,
      );
    }
  }

  /// Get detailed health stats from the AI server.
  Future<Map<String, dynamic>?> getHealth() async {
    try {
      final uri = Uri.parse('$baseUrl/api/health');
      final request = await _client.getUrl(uri);
      final response = await request.close().timeout(
        const Duration(seconds: 5),
      );

      if (response.statusCode == 200) {
        final body = await response.transform(utf8.decoder).join();
        return jsonDecode(body) as Map<String, dynamic>;
      }
    } catch (e) {
      debugPrint('[AiService] Health request failed: $e');
    }
    return null;
  }

  void dispose() {
    _client.close();
  }

  /// Stream a chat response via Server-Sent Events.
  ///
  /// Returns a [Stream] of [StreamEvent] objects that arrive as the model
  /// generates tokens. Event types: adapter, tool_call, tool_result, token,
  /// done, error.
  Stream<StreamEvent> chatStream(
    String query, {
    String sessionId = 'gui_default',
  }) async* {
    final uri = Uri.parse('$baseUrl/api/chat/stream');

    try {
      final request = await _client.postUrl(uri);
      request.headers.contentType = ContentType.json;
      final payload = {'query': query, 'session_id': sessionId};
      final bodyBytes = utf8.encode(jsonEncode(payload));
      request.contentLength = bodyBytes.length;
      request.add(bodyBytes);

      final response = await request.close().timeout(timeout);

      if (response.statusCode != 200) {
        final body = await response.transform(utf8.decoder).join();
        yield StreamEvent('error', {'error': 'HTTP ${response.statusCode}: $body'});
        return;
      }

      _serverAvailable = true;

      // Parse SSE: lines like "event: <type>\ndata: <json>\n\n"
      String buffer = '';
      String? currentEvent;

      await for (final chunk in response.transform(utf8.decoder)) {
        buffer += chunk;

        // Process complete SSE blocks (terminated by double newline)
        while (buffer.contains('\n\n')) {
          final blockEnd = buffer.indexOf('\n\n');
          final block = buffer.substring(0, blockEnd);
          buffer = buffer.substring(blockEnd + 2);

          for (final line in block.split('\n')) {
            if (line.startsWith('event: ')) {
              currentEvent = line.substring(7).trim();
            } else if (line.startsWith('data: ') && currentEvent != null) {
              try {
                final data = jsonDecode(line.substring(6)) as Map<String, dynamic>;
                yield StreamEvent(currentEvent!, data);
              } catch (e) {
                debugPrint('[AiService] SSE parse error: $e');
              }
              currentEvent = null;
            }
          }
        }
      }
    } on TimeoutException {
      yield StreamEvent('error', {'error': 'Stream timed out'});
    } on SocketException catch (e) {
      _serverAvailable = false;
      yield StreamEvent('error', {'error': 'AI server not reachable: ${e.message}'});
    } catch (e) {
      yield StreamEvent('error', {'error': 'Unexpected error: $e'});
    }
  }
}

/// A single Server-Sent Event from the streaming chat endpoint.
class StreamEvent {
  final String type;
  final Map<String, dynamic> data;
  const StreamEvent(this.type, this.data);
}

/// Response from the AI chat endpoint.
class ChatResponse {
  final String text;
  final String query;
  final double latencyMs;
  final String adapter;
  final bool success;
  final String error;

  /// Tool calls executed server-side (list of JSON-encoded tool call strings).
  final List<String> toolCalls;

  const ChatResponse({
    required this.text,
    required this.query,
    this.latencyMs = 0.0,
    this.adapter = '',
    required this.success,
    this.error = '',
    this.toolCalls = const [],
  });
}

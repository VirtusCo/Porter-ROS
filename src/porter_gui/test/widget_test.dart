// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'package:flutter_test/flutter_test.dart';
import 'package:porter_gui/models/models.dart';
import 'package:porter_gui/services/ai_service.dart';

void main() {
  group('ChatMessage', () {
    test('creates with current timestamp', () {
      final msg = ChatMessage.now(text: 'Hello', isUser: true);
      expect(msg.text, 'Hello');
      expect(msg.isUser, true);
      expect(msg.isStreaming, false);
      expect(msg.timestamp.isBefore(DateTime.now().add(const Duration(seconds: 1))), true);
    });
  });

  group('DiagnosticStatus', () {
    test('creates unknown status', () {
      final status = DiagnosticStatus.unknown('test');
      expect(status.name, 'test');
      expect(status.level, HealthLevel.unknown);
      expect(status.message, 'No data');
    });

    test('creates with values', () {
      final status = DiagnosticStatus(
        name: 'lidar',
        level: HealthLevel.ok,
        message: 'Running',
        timestamp: DateTime.now(),
        values: {'rate': '10.0'},
      );
      expect(status.level, HealthLevel.ok);
      expect(status.values['rate'], '10.0');
    });
  });

  group('FlightInfo', () {
    test('creates with required fields', () {
      final flight = FlightInfo(
        flightNumber: 'AI-101',
        airline: 'Air India',
        destination: 'Mumbai',
        gate: 'A12',
        terminal: 'T3',
        status: 'On Time',
        scheduledTime: DateTime.now(),
      );
      expect(flight.flightNumber, 'AI-101');
      expect(flight.estimatedTime, isNull);
    });
  });

  group('MapPoi', () {
    test('creates with position', () {
      const poi = MapPoi(
        name: 'Gate A1',
        category: 'gate',
        x: 0.5,
        y: 0.3,
      );
      expect(poi.name, 'Gate A1');
      expect(poi.description, isNull);
    });
  });

  group('AiService', () {
    test('creates with default URL', () {
      final service = AiService();
      expect(service.baseUrl, 'http://localhost:8085');
      expect(service.isAvailable, false);
      service.dispose();
    });

    test('creates with custom URL', () {
      final service = AiService(baseUrl: 'http://10.0.0.1:9000');
      expect(service.baseUrl, 'http://10.0.0.1:9000');
      service.dispose();
    });
  });

  group('ChatResponse', () {
    test('creates successful response', () {
      const response = ChatResponse(
        text: 'Gate A12 is in Terminal 3',
        query: 'Where is Gate A12?',
        latencyMs: 350.0,
        adapter: 'conversational',
        success: true,
      );
      expect(response.success, true);
      expect(response.text, 'Gate A12 is in Terminal 3');
      expect(response.error, '');
    });

    test('creates error response', () {
      const response = ChatResponse(
        text: '',
        query: 'test',
        success: false,
        error: 'Model not loaded',
      );
      expect(response.success, false);
      expect(response.error, 'Model not loaded');
    });
  });
}

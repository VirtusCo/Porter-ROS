"""Tests for log_bridge regex pattern extraction.

Validates that structured fields are correctly extracted from log messages
covering FSM transitions, scan quality, motor overcurrent, sensor faults,
battery levels, navigation goals, LIDAR timeouts, and ESP32 CRC errors.
"""

import pytest

from porter_observability.patterns import extract_patterns


class TestFsmTransition:
    """Test FSM state transition pattern extraction."""

    def test_arrow_syntax(self):
        result = extract_patterns('FSM transition: IDLE -> SERVING')
        assert 'fsm_transition' in result
        assert result['fsm_transition']['from_state'] == 'IDLE'
        assert result['fsm_transition']['to_state'] == 'SERVING'

    def test_unicode_arrow(self):
        result = extract_patterns('state change: SERVING \u2192 NAVIGATING')
        assert 'fsm_transition' in result
        assert result['fsm_transition']['from_state'] == 'SERVING'
        assert result['fsm_transition']['to_state'] == 'NAVIGATING'

    def test_to_keyword(self):
        result = extract_patterns('State transition NAVIGATING to ERROR')
        assert 'fsm_transition' in result
        assert result['fsm_transition']['from_state'] == 'NAVIGATING'
        assert result['fsm_transition']['to_state'] == 'ERROR'

    def test_lowercase(self):
        result = extract_patterns('fsm transition: idle -> serving')
        assert 'fsm_transition' in result
        assert result['fsm_transition']['from_state'] == 'idle'
        assert result['fsm_transition']['to_state'] == 'serving'


class TestScanQuality:
    """Test LIDAR scan quality pattern extraction."""

    def test_percentage(self):
        result = extract_patterns('scan quality: 87.5%')
        assert 'scan_quality' in result
        assert result['scan_quality']['quality'] == '87.5'

    def test_without_percent_sign(self):
        result = extract_patterns('Scan quality: 92')
        assert 'scan_quality' in result
        assert result['scan_quality']['quality'] == '92'


class TestMotorOvercurrent:
    """Test motor overcurrent pattern extraction."""

    def test_with_motor_name(self):
        result = extract_patterns('Motor overcurrent: left 2.5A')
        assert 'motor_overcurrent' in result
        assert result['motor_overcurrent']['motor'] == 'left'
        assert result['motor_overcurrent']['current'] == '2.5'

    def test_without_motor_name(self):
        result = extract_patterns('motor over-current: 3.1 mA')
        assert 'motor_overcurrent' in result
        assert result['motor_overcurrent']['current'] == '3.1'

    def test_underscore_variant(self):
        result = extract_patterns('Motor over_current: right 1800mA')
        assert 'motor_overcurrent' in result
        assert result['motor_overcurrent']['current'] == '1800'


class TestSensorFault:
    """Test sensor fault pattern extraction."""

    def test_basic(self):
        result = extract_patterns('Sensor fault: ultrasonic')
        assert 'sensor_fault' in result
        assert result['sensor_fault']['sensor'] == 'ultrasonic'

    def test_failure_variant(self):
        result = extract_patterns('sensor failure: tof_front')
        assert 'sensor_fault' in result
        assert result['sensor_fault']['sensor'] == 'tof_front'

    def test_error_variant(self):
        result = extract_patterns('Sensor error: microwave')
        assert 'sensor_fault' in result
        assert result['sensor_fault']['sensor'] == 'microwave'


class TestBatteryLevel:
    """Test battery level pattern extraction."""

    def test_integer(self):
        result = extract_patterns('Battery: 75%')
        assert 'battery_level' in result
        assert result['battery_level']['level'] == '75'

    def test_decimal(self):
        result = extract_patterns('battery: 42.3%')
        assert 'battery_level' in result
        assert result['battery_level']['level'] == '42.3'


class TestNavigationGoal:
    """Test navigation goal coordinate extraction."""

    def test_parenthesized(self):
        result = extract_patterns('Nav goal: (3.5, -2.1)')
        assert 'navigation_goal' in result
        assert result['navigation_goal']['x'] == '3.5'
        assert result['navigation_goal']['y'] == '-2.1'

    def test_without_parens(self):
        result = extract_patterns('navigation goal: 1.0, 4.5')
        assert 'navigation_goal' in result
        assert result['navigation_goal']['x'] == '1.0'
        assert result['navigation_goal']['y'] == '4.5'


class TestLidarTimeout:
    """Test LIDAR timeout pattern extraction."""

    def test_lidar_timeout(self):
        result = extract_patterns('LIDAR timeout detected')
        assert 'lidar_timeout' in result

    def test_ydlidar_timed_out(self):
        result = extract_patterns('ydlidar timed out waiting for scan')
        assert 'lidar_timeout' in result


class TestEsp32CrcError:
    """Test ESP32 CRC error pattern extraction."""

    def test_crc_error(self):
        result = extract_patterns('CRC error on motor frame')
        assert 'esp32_crc_error' in result

    def test_crc_mismatch(self):
        result = extract_patterns('CRC mismatch: expected 0xA3B2')
        assert 'esp32_crc_error' in result


class TestNoMatch:
    """Test that unrelated messages produce no extractions."""

    def test_empty_string(self):
        assert extract_patterns('') == {}

    def test_irrelevant_message(self):
        assert extract_patterns('Node started successfully') == {}

    def test_partial_keyword(self):
        # Should not match partial words
        result = extract_patterns('The scanner is running')
        assert 'scan_quality' not in result


class TestMultiplePatterns:
    """Test messages that match multiple patterns simultaneously."""

    def test_sensor_fault_with_battery(self):
        result = extract_patterns(
            'Sensor fault: tof_front, battery: 15%'
        )
        assert 'sensor_fault' in result
        assert 'battery_level' in result
        assert result['sensor_fault']['sensor'] == 'tof_front'
        assert result['battery_level']['level'] == '15'

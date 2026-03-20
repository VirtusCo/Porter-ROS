"""Regex patterns for structured log field extraction.

Separated from log_bridge.py so patterns can be tested independently
without requiring rclpy or any ROS 2 dependencies.
"""

import re


# ---------------------------------------------------------------------------
# Regex patterns for structured field extraction
# ---------------------------------------------------------------------------

PATTERNS = {
    'fsm_transition': re.compile(
        r'(?:FSM|state)\s+(?:transition|change)\s*[:\-]?\s*'
        r'(?P<from_state>\w+)\s*(?:->|→|to)\s*(?P<to_state>\w+)',
        re.IGNORECASE,
    ),
    'scan_quality': re.compile(
        r'scan\s+quality\s*[:\-]?\s*(?P<quality>\d+(?:\.\d+)?)\s*%?',
        re.IGNORECASE,
    ),
    'motor_overcurrent': re.compile(
        r'motor\s+(?:overcurrent|over[_\- ]?current)\s*[:\-]?\s*'
        r'(?:(?P<motor>\w+)\s+)?(?P<current>\d+(?:\.\d+)?)\s*(?:m?A)?',
        re.IGNORECASE,
    ),
    'sensor_fault': re.compile(
        r'sensor\s+(?:fault|failure|error)\s*[:\-]?\s*(?P<sensor>\w+)',
        re.IGNORECASE,
    ),
    'battery_level': re.compile(
        r'battery\s*[:\-]?\s*(?P<level>\d+(?:\.\d+)?)\s*%',
        re.IGNORECASE,
    ),
    'navigation_goal': re.compile(
        r'(?:nav|navigation)\s+goal\s*[:\-]?\s*'
        r'\(?\s*(?P<x>-?\d+(?:\.\d+)?)\s*,\s*(?P<y>-?\d+(?:\.\d+)?)\s*\)?',
        re.IGNORECASE,
    ),
    'lidar_timeout': re.compile(
        r'(?:lidar|ydlidar)\s+(?:timeout|timed?\s*out)',
        re.IGNORECASE,
    ),
    'esp32_crc_error': re.compile(
        r'CRC\s+(?:error|mismatch|fail)',
        re.IGNORECASE,
    ),
}


def extract_patterns(message: str) -> dict:
    """Extract structured fields from a log message using regex patterns.

    Args:
        message: The raw log message text.

    Returns:
        A dict mapping pattern name to captured groups.  Only patterns
        that matched are included.
    """
    extracted = {}
    for name, pattern in PATTERNS.items():
        match = pattern.search(message)
        if match:
            extracted[name] = {
                k: v for k, v in match.groupdict().items() if v is not None
            }
    return extracted

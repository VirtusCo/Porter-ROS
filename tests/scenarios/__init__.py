"""Reusable test scenarios for integration and system tests.

Each TestScenario bundles a mock scenario name, a set of assertions,
and timing parameters. Scenarios can be used by integration and system
test runners to execute deterministic, repeatable tests.
"""

from dataclasses import dataclass, field
from typing import List, Callable, Any, Optional


@dataclass
class Assertion:
    """A single named assertion to evaluate against test results."""
    name: str
    check: Callable[[Any], bool]
    description: str


@dataclass
class TestScenario:
    """A complete test scenario specification."""
    name: str
    description: str
    mock_scenario: str  # MockESP32Bridge scenario name
    assertions: List[Assertion]
    timeout_s: float = 30.0
    setup_delay_s: float = 3.0


def _check_fsm_reaches_idle(result: Any) -> bool:
    """Assert FSM reaches IDLE within the timeout."""
    states = getattr(result, 'states_visited', [])
    return 'IDLE' in states


def _check_sensor_fusion_rate(result: Any) -> bool:
    """Assert sensor_fusion publishes at >45 Hz."""
    rate = getattr(result, 'sensor_fusion_hz', 0.0)
    return rate > 45.0


def _check_obstacle_avoidance_transition(result: Any) -> bool:
    """Assert FSM transitions through OBSTACLE_AVOIDANCE."""
    transitions = getattr(result, 'state_transitions', [])
    saw_navigating = False
    saw_obstacle = False
    saw_resume = False
    for old_state, new_state in transitions:
        if new_state == 'NAVIGATING' and not saw_navigating:
            saw_navigating = True
        elif old_state == 'NAVIGATING' and new_state == 'OBSTACLE_AVOIDANCE':
            saw_obstacle = True
        elif old_state == 'OBSTACLE_AVOIDANCE' and new_state == 'NAVIGATING':
            saw_resume = True
    return saw_obstacle and saw_resume


def _check_diagnostics_warn(result: Any) -> bool:
    """Assert diagnostics published a warning (not error)."""
    diag_levels = getattr(result, 'diagnostics_levels', [])
    # Level 1 = WARN in diagnostic_msgs
    return 1 in diag_levels and 2 not in diag_levels


def _check_fsm_stays_navigating(result: Any) -> bool:
    """Assert FSM does NOT transition to ERROR on sensor degradation."""
    states = getattr(result, 'states_visited', [])
    return 'NAVIGATING' in states and 'ERROR' not in states


def _check_motor_stall_current(result: Any) -> bool:
    """Assert motor current exceeded 6A (stall threshold)."""
    max_current = getattr(result, 'max_motor_current_a', 0.0)
    return max_current > 6.0


def _check_fsm_reaches_error(result: Any) -> bool:
    """Assert FSM transitions to ERROR state."""
    states = getattr(result, 'states_visited', [])
    return 'ERROR' in states


def _check_cmd_vel_zeroed(result: Any) -> bool:
    """Assert /cmd_vel was set to zero (robot stopped)."""
    last_cmd = getattr(result, 'last_cmd_vel_linear_x', None)
    return last_cmd is not None and abs(last_cmd) < 0.01


# ──────────────────────────────────────────────────────────────
# Standard test scenarios
# ──────────────────────────────────────────────────────────────

SCENARIOS = {
    'nominal_idle': TestScenario(
        name='Nominal Idle',
        description='Robot in IDLE state with all sensors nominal',
        mock_scenario='clear',
        assertions=[
            Assertion(
                name='fsm_reaches_idle',
                check=_check_fsm_reaches_idle,
                description='FSM reaches IDLE within 5s',
            ),
            Assertion(
                name='sensor_fusion_rate',
                check=_check_sensor_fusion_rate,
                description='sensor_fusion publishes at >45 Hz',
            ),
        ],
        timeout_s=15.0,
    ),

    'obstacle_recovery': TestScenario(
        name='Obstacle Recovery',
        description='Obstacle approaches, robot stops, clears, resumes',
        mock_scenario='obstacle_50',
        assertions=[
            Assertion(
                name='obstacle_avoidance_transition',
                check=_check_obstacle_avoidance_transition,
                description='FSM transitions NAVIGATING -> OBSTACLE_AVOIDANCE -> NAVIGATING',
            ),
            Assertion(
                name='cmd_vel_zeroed_during_obstacle',
                check=_check_cmd_vel_zeroed,
                description='/cmd_vel zeroed when obstacle detected',
            ),
        ],
        timeout_s=30.0,
    ),

    'sensor_degradation': TestScenario(
        name='ToF Sensor Failure',
        description='ToF fails mid-run, robot continues on ultrasonic',
        mock_scenario='sensor_fail',
        assertions=[
            Assertion(
                name='diagnostics_warn',
                check=_check_diagnostics_warn,
                description='Diagnostics published warning (not error)',
            ),
            Assertion(
                name='fsm_stays_navigating',
                check=_check_fsm_stays_navigating,
                description='FSM stays NAVIGATING (not ERROR) during sensor degradation',
            ),
        ],
        timeout_s=20.0,
    ),

    'motor_stall': TestScenario(
        name='Motor Stall',
        description='Motor stall detected, robot stops safely',
        mock_scenario='stall',
        assertions=[
            Assertion(
                name='motor_stall_current',
                check=_check_motor_stall_current,
                description='Motor current > 6A detected',
            ),
            Assertion(
                name='fsm_reaches_error',
                check=_check_fsm_reaches_error,
                description='FSM transitions to ERROR state',
            ),
            Assertion(
                name='cmd_vel_zeroed',
                check=_check_cmd_vel_zeroed,
                description='/cmd_vel zeroed after stall',
            ),
        ],
        timeout_s=15.0,
    ),
}

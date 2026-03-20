"""Unit tests for the Porter orchestrator FSM.

Tests all 14 valid transitions and invalid transition handling.
Can run WITHOUT ROS 2 — pure Python state machine logic.
"""

import pytest


class OrchestratorFSM:
    """Minimal FSM for testing — mirrors porter_orchestrator logic.

    Implements the Porter robot's 9-state finite state machine with
    14 valid transitions, recovery attempt tracking, and state history.
    """

    STATES = [
        'BOOT', 'HEALTH_CHECK', 'IDLE', 'PASSENGER_DETECTED',
        'FOLLOWING', 'NAVIGATING', 'OBSTACLE_AVOIDANCE', 'ERROR', 'RECOVERY',
    ]

    TRANSITIONS = {
        ('BOOT', 'system_ready'): 'HEALTH_CHECK',
        ('HEALTH_CHECK', 'all_healthy'): 'IDLE',
        ('HEALTH_CHECK', 'health_fail'): 'ERROR',
        ('IDLE', 'passenger_detected'): 'PASSENGER_DETECTED',
        ('PASSENGER_DETECTED', 'confirmed'): 'FOLLOWING',
        ('PASSENGER_DETECTED', 'timeout'): 'IDLE',
        ('FOLLOWING', 'gate_requested'): 'NAVIGATING',
        ('FOLLOWING', 'obstacle_detected'): 'OBSTACLE_AVOIDANCE',
        ('NAVIGATING', 'arrived'): 'IDLE',
        ('NAVIGATING', 'obstacle_detected'): 'OBSTACLE_AVOIDANCE',
        ('OBSTACLE_AVOIDANCE', 'clear'): 'NAVIGATING',
        ('OBSTACLE_AVOIDANCE', 'stuck'): 'ERROR',
        ('ERROR', 'recovery_triggered'): 'RECOVERY',
        ('RECOVERY', 'reset'): 'HEALTH_CHECK',
    }

    def __init__(self, max_recovery=3):
        self.state = 'BOOT'
        self.recovery_attempt = 0
        self.max_recovery = max_recovery
        self.history = []

    def trigger(self, event):
        """Attempt a state transition. Invalid transitions are silently ignored."""
        key = (self.state, event)
        if key in self.TRANSITIONS:
            old = self.state
            self.state = self.TRANSITIONS[key]
            self.history.append((old, event, self.state))
            if self.state == 'RECOVERY':
                self.recovery_attempt += 1
            if self.state == 'IDLE':
                self.recovery_attempt = 0

    def force_state(self, state):
        """Force FSM into a specific state (for test setup)."""
        assert state in self.STATES, f"Invalid state: {state}"
        self.state = state

    def is_max_recovery_reached(self):
        """Check if maximum recovery attempts have been exceeded."""
        return self.recovery_attempt >= self.max_recovery


class TestFSMInitialization:
    """Tests for FSM initial state."""

    def test_initial_state_is_boot(self):
        """FSM starts in BOOT state."""
        fsm = OrchestratorFSM()
        assert fsm.state == 'BOOT'

    def test_initial_recovery_count_is_zero(self):
        """Recovery attempt counter starts at zero."""
        fsm = OrchestratorFSM()
        assert fsm.recovery_attempt == 0

    def test_initial_history_is_empty(self):
        """Transition history starts empty."""
        fsm = OrchestratorFSM()
        assert fsm.history == []

    def test_all_states_are_valid(self):
        """All 9 states are defined."""
        fsm = OrchestratorFSM()
        assert len(fsm.STATES) == 9
        expected = {
            'BOOT', 'HEALTH_CHECK', 'IDLE', 'PASSENGER_DETECTED',
            'FOLLOWING', 'NAVIGATING', 'OBSTACLE_AVOIDANCE', 'ERROR', 'RECOVERY',
        }
        assert set(fsm.STATES) == expected

    def test_all_transitions_are_defined(self):
        """All 14 transitions are defined."""
        fsm = OrchestratorFSM()
        assert len(fsm.TRANSITIONS) == 14


class TestValidTransitions:
    """Tests for all 14 valid FSM transitions."""

    def test_boot_to_health_check(self):
        """Transition 1: BOOT --system_ready--> HEALTH_CHECK"""
        fsm = OrchestratorFSM()
        fsm.trigger('system_ready')
        assert fsm.state == 'HEALTH_CHECK'

    def test_health_check_to_idle(self):
        """Transition 2: HEALTH_CHECK --all_healthy--> IDLE"""
        fsm = OrchestratorFSM()
        fsm.force_state('HEALTH_CHECK')
        fsm.trigger('all_healthy')
        assert fsm.state == 'IDLE'

    def test_health_check_to_error(self):
        """Transition 3: HEALTH_CHECK --health_fail--> ERROR"""
        fsm = OrchestratorFSM()
        fsm.force_state('HEALTH_CHECK')
        fsm.trigger('health_fail')
        assert fsm.state == 'ERROR'

    def test_idle_to_passenger_detected(self):
        """Transition 4: IDLE --passenger_detected--> PASSENGER_DETECTED"""
        fsm = OrchestratorFSM()
        fsm.force_state('IDLE')
        fsm.trigger('passenger_detected')
        assert fsm.state == 'PASSENGER_DETECTED'

    def test_passenger_detected_to_following(self):
        """Transition 5: PASSENGER_DETECTED --confirmed--> FOLLOWING"""
        fsm = OrchestratorFSM()
        fsm.force_state('PASSENGER_DETECTED')
        fsm.trigger('confirmed')
        assert fsm.state == 'FOLLOWING'

    def test_passenger_detected_timeout_to_idle(self):
        """Transition 6: PASSENGER_DETECTED --timeout--> IDLE"""
        fsm = OrchestratorFSM()
        fsm.force_state('PASSENGER_DETECTED')
        fsm.trigger('timeout')
        assert fsm.state == 'IDLE'

    def test_following_to_navigating(self):
        """Transition 7: FOLLOWING --gate_requested--> NAVIGATING"""
        fsm = OrchestratorFSM()
        fsm.force_state('FOLLOWING')
        fsm.trigger('gate_requested')
        assert fsm.state == 'NAVIGATING'

    def test_following_to_obstacle_avoidance(self):
        """Transition 8: FOLLOWING --obstacle_detected--> OBSTACLE_AVOIDANCE"""
        fsm = OrchestratorFSM()
        fsm.force_state('FOLLOWING')
        fsm.trigger('obstacle_detected')
        assert fsm.state == 'OBSTACLE_AVOIDANCE'

    def test_navigating_to_idle_on_arrival(self):
        """Transition 9: NAVIGATING --arrived--> IDLE"""
        fsm = OrchestratorFSM()
        fsm.force_state('NAVIGATING')
        fsm.trigger('arrived')
        assert fsm.state == 'IDLE'

    def test_navigating_to_obstacle_avoidance(self):
        """Transition 10: NAVIGATING --obstacle_detected--> OBSTACLE_AVOIDANCE"""
        fsm = OrchestratorFSM()
        fsm.force_state('NAVIGATING')
        fsm.trigger('obstacle_detected')
        assert fsm.state == 'OBSTACLE_AVOIDANCE'

    def test_obstacle_avoidance_to_navigating(self):
        """Transition 11: OBSTACLE_AVOIDANCE --clear--> NAVIGATING"""
        fsm = OrchestratorFSM()
        fsm.force_state('OBSTACLE_AVOIDANCE')
        fsm.trigger('clear')
        assert fsm.state == 'NAVIGATING'

    def test_obstacle_avoidance_stuck_to_error(self):
        """Transition 12: OBSTACLE_AVOIDANCE --stuck--> ERROR"""
        fsm = OrchestratorFSM()
        fsm.force_state('OBSTACLE_AVOIDANCE')
        fsm.trigger('stuck')
        assert fsm.state == 'ERROR'

    def test_error_to_recovery(self):
        """Transition 13: ERROR --recovery_triggered--> RECOVERY"""
        fsm = OrchestratorFSM()
        fsm.force_state('ERROR')
        fsm.trigger('recovery_triggered')
        assert fsm.state == 'RECOVERY'

    def test_recovery_to_health_check(self):
        """Transition 14: RECOVERY --reset--> HEALTH_CHECK"""
        fsm = OrchestratorFSM()
        fsm.force_state('RECOVERY')
        fsm.trigger('reset')
        assert fsm.state == 'HEALTH_CHECK'


class TestInvalidTransitions:
    """Tests that invalid transitions are silently ignored."""

    def test_boot_ignores_unknown_event(self):
        """BOOT ignores events other than system_ready."""
        fsm = OrchestratorFSM()
        fsm.trigger('all_healthy')
        assert fsm.state == 'BOOT'

    def test_idle_ignores_system_ready(self):
        """IDLE ignores system_ready (only valid from BOOT)."""
        fsm = OrchestratorFSM()
        fsm.force_state('IDLE')
        fsm.trigger('system_ready')
        assert fsm.state == 'IDLE'

    def test_navigating_ignores_passenger_detected(self):
        """NAVIGATING ignores passenger_detected."""
        fsm = OrchestratorFSM()
        fsm.force_state('NAVIGATING')
        fsm.trigger('passenger_detected')
        assert fsm.state == 'NAVIGATING'

    def test_error_ignores_clear(self):
        """ERROR ignores clear (only valid from OBSTACLE_AVOIDANCE)."""
        fsm = OrchestratorFSM()
        fsm.force_state('ERROR')
        fsm.trigger('clear')
        assert fsm.state == 'ERROR'

    def test_recovery_ignores_all_healthy(self):
        """RECOVERY ignores all_healthy (must reset first)."""
        fsm = OrchestratorFSM()
        fsm.force_state('RECOVERY')
        fsm.trigger('all_healthy')
        assert fsm.state == 'RECOVERY'

    def test_following_ignores_arrived(self):
        """FOLLOWING ignores arrived (only valid from NAVIGATING)."""
        fsm = OrchestratorFSM()
        fsm.force_state('FOLLOWING')
        fsm.trigger('arrived')
        assert fsm.state == 'FOLLOWING'

    def test_boot_ignores_completely_bogus_event(self):
        """FSM ignores events that don't exist anywhere in transition table."""
        fsm = OrchestratorFSM()
        fsm.trigger('this_event_does_not_exist')
        assert fsm.state == 'BOOT'

    def test_invalid_transition_does_not_add_history(self):
        """Invalid transitions should not be recorded in history."""
        fsm = OrchestratorFSM()
        fsm.trigger('all_healthy')  # invalid from BOOT
        assert len(fsm.history) == 0


class TestRecoveryCounter:
    """Tests for recovery attempt tracking."""

    def test_recovery_increments_counter(self):
        """Entering RECOVERY increments recovery_attempt."""
        fsm = OrchestratorFSM()
        fsm.force_state('ERROR')
        fsm.trigger('recovery_triggered')
        assert fsm.recovery_attempt == 1

    def test_multiple_recoveries_increment(self):
        """Multiple recovery cycles increment the counter."""
        fsm = OrchestratorFSM()
        for _ in range(3):
            fsm.force_state('ERROR')
            fsm.trigger('recovery_triggered')
            assert fsm.state == 'RECOVERY'
            fsm.trigger('reset')
            assert fsm.state == 'HEALTH_CHECK'
        assert fsm.recovery_attempt == 3

    def test_reaching_idle_resets_recovery_counter(self):
        """Reaching IDLE resets recovery_attempt to zero."""
        fsm = OrchestratorFSM()
        fsm.force_state('ERROR')
        fsm.trigger('recovery_triggered')
        assert fsm.recovery_attempt == 1
        fsm.trigger('reset')
        fsm.trigger('all_healthy')
        assert fsm.state == 'IDLE'
        assert fsm.recovery_attempt == 0

    def test_max_recovery_reached(self):
        """is_max_recovery_reached returns True after max attempts."""
        fsm = OrchestratorFSM(max_recovery=2)
        assert not fsm.is_max_recovery_reached()
        fsm.force_state('ERROR')
        fsm.trigger('recovery_triggered')
        assert not fsm.is_max_recovery_reached()
        fsm.trigger('reset')
        fsm.force_state('ERROR')
        fsm.trigger('recovery_triggered')
        assert fsm.is_max_recovery_reached()

    def test_max_recovery_default_is_three(self):
        """Default max recovery is 3."""
        fsm = OrchestratorFSM()
        assert fsm.max_recovery == 3


class TestStateHistory:
    """Tests for transition history recording."""

    def test_valid_transition_recorded_in_history(self):
        """Valid transitions are recorded as (old, event, new) tuples."""
        fsm = OrchestratorFSM()
        fsm.trigger('system_ready')
        assert len(fsm.history) == 1
        assert fsm.history[0] == ('BOOT', 'system_ready', 'HEALTH_CHECK')

    def test_full_history_for_multi_step(self):
        """Multiple transitions build up the history list."""
        fsm = OrchestratorFSM()
        fsm.trigger('system_ready')
        fsm.trigger('all_healthy')
        fsm.trigger('passenger_detected')
        assert len(fsm.history) == 3
        assert fsm.history[0] == ('BOOT', 'system_ready', 'HEALTH_CHECK')
        assert fsm.history[1] == ('HEALTH_CHECK', 'all_healthy', 'IDLE')
        assert fsm.history[2] == ('IDLE', 'passenger_detected', 'PASSENGER_DETECTED')


class TestForceState:
    """Tests for force_state helper method."""

    def test_force_state_sets_state(self):
        """force_state changes state directly."""
        fsm = OrchestratorFSM()
        fsm.force_state('NAVIGATING')
        assert fsm.state == 'NAVIGATING'

    def test_force_state_rejects_invalid(self):
        """force_state raises AssertionError for unknown states."""
        fsm = OrchestratorFSM()
        with pytest.raises(AssertionError):
            fsm.force_state('NONEXISTENT_STATE')


class TestHappyPath:
    """End-to-end happy path through the FSM."""

    def test_full_happy_path(self):
        """BOOT -> HEALTH_CHECK -> IDLE -> PASSENGER_DETECTED -> FOLLOWING
        -> NAVIGATING -> IDLE (complete journey)."""
        fsm = OrchestratorFSM()
        assert fsm.state == 'BOOT'

        fsm.trigger('system_ready')
        assert fsm.state == 'HEALTH_CHECK'

        fsm.trigger('all_healthy')
        assert fsm.state == 'IDLE'

        fsm.trigger('passenger_detected')
        assert fsm.state == 'PASSENGER_DETECTED'

        fsm.trigger('confirmed')
        assert fsm.state == 'FOLLOWING'

        fsm.trigger('gate_requested')
        assert fsm.state == 'NAVIGATING'

        fsm.trigger('arrived')
        assert fsm.state == 'IDLE'

        # Verify full history
        assert len(fsm.history) == 6
        assert fsm.recovery_attempt == 0

    def test_obstacle_detour_during_navigation(self):
        """NAVIGATING -> OBSTACLE_AVOIDANCE -> NAVIGATING -> IDLE
        (obstacle encountered and cleared during navigation)."""
        fsm = OrchestratorFSM()
        fsm.force_state('NAVIGATING')

        fsm.trigger('obstacle_detected')
        assert fsm.state == 'OBSTACLE_AVOIDANCE'

        fsm.trigger('clear')
        assert fsm.state == 'NAVIGATING'

        fsm.trigger('arrived')
        assert fsm.state == 'IDLE'

    def test_error_recovery_path(self):
        """ERROR -> RECOVERY -> HEALTH_CHECK -> IDLE
        (successful recovery from error)."""
        fsm = OrchestratorFSM()
        fsm.force_state('ERROR')

        fsm.trigger('recovery_triggered')
        assert fsm.state == 'RECOVERY'
        assert fsm.recovery_attempt == 1

        fsm.trigger('reset')
        assert fsm.state == 'HEALTH_CHECK'

        fsm.trigger('all_healthy')
        assert fsm.state == 'IDLE'
        assert fsm.recovery_attempt == 0

    def test_passenger_timeout_then_retry(self):
        """IDLE -> PASSENGER_DETECTED -> IDLE (timeout) -> PASSENGER_DETECTED
        -> FOLLOWING (confirmed on second attempt)."""
        fsm = OrchestratorFSM()
        fsm.force_state('IDLE')

        fsm.trigger('passenger_detected')
        assert fsm.state == 'PASSENGER_DETECTED'

        fsm.trigger('timeout')
        assert fsm.state == 'IDLE'

        fsm.trigger('passenger_detected')
        assert fsm.state == 'PASSENGER_DETECTED'

        fsm.trigger('confirmed')
        assert fsm.state == 'FOLLOWING'

    def test_obstacle_stuck_leads_to_error_and_recovery(self):
        """OBSTACLE_AVOIDANCE -> ERROR -> RECOVERY -> HEALTH_CHECK -> IDLE
        (stuck scenario with full recovery)."""
        fsm = OrchestratorFSM()
        fsm.force_state('OBSTACLE_AVOIDANCE')

        fsm.trigger('stuck')
        assert fsm.state == 'ERROR'

        fsm.trigger('recovery_triggered')
        assert fsm.state == 'RECOVERY'

        fsm.trigger('reset')
        assert fsm.state == 'HEALTH_CHECK'

        fsm.trigger('all_healthy')
        assert fsm.state == 'IDLE'

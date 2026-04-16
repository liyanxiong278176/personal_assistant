"""Tests for SlotStateMachine - TDD approach."""
import pytest
from app.core.intent.state_machine import (
    SlotStateMachine,
    SlotState,
    SlotStateType,
)


@pytest.fixture
def state_machine():
    return SlotStateMachine()


class TestSlotStateMachineInit:
    """Test state initialization."""

    def test_init_state_itinerary(self, state_machine):
        state = state_machine.init_state("conv1", "itinerary")
        assert state.intent == "itinerary"
        assert state.missing == ["destination", "days"]

    def test_init_state_hotel(self, state_machine):
        state = state_machine.init_state("conv2", "hotel")
        assert state.intent == "hotel"
        assert state.missing == ["destination", "dates"]

    def test_init_state_food(self, state_machine):
        state = state_machine.init_state("conv3", "food")
        assert state.intent == "food"
        assert state.missing == ["destination"]

    def test_init_state_query(self, state_machine):
        state = state_machine.init_state("conv4", "query")
        assert state.missing == []
        assert state.state_type == SlotStateType.COMPLETE

    def test_init_state_chat(self, state_machine):
        state = state_machine.init_state("conv5", "chat")
        assert state.missing == []
        assert state.state_type == SlotStateType.COMPLETE

    def test_get_state_returns_initialized(self, state_machine):
        state = state_machine.init_state("conv1", "itinerary")
        retrieved = state_machine.get_state("conv1")
        assert retrieved is not None
        assert retrieved.intent == "itinerary"

    def test_get_state_returns_none_for_unknown(self, state_machine):
        result = state_machine.get_state("unknown_conv")
        assert result is None

    def test_reinit_clears_previous(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state_machine.update_state("conv1", {"destination": "北京"})
        state = state_machine.init_state("conv1", "hotel")
        assert state.intent == "hotel"
        assert state.collected == {}


class TestSlotStateMachineUpdate:
    """Test slot update logic."""

    def test_update_partial_slots(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state = state_machine.update_state("conv1", {"destination": "北京"})
        assert state.collected["destination"] == "北京"
        assert "destination" not in state.missing
        assert state.missing == ["days"]

    def test_update_multiple_slots(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state = state_machine.update_state("conv1", {"destination": "北京", "days": 3})
        assert state.collected["destination"] == "北京"
        assert state.collected["days"] == 3
        assert state.missing == []

    def test_update_complete_transitions(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state_machine.update_state("conv1", {"destination": "北京"})
        state = state_machine.update_state("conv1", {"days": 3})
        assert state.state_type == SlotStateType.COMPLETE

    def test_update_unknown_conv_returns_none(self, state_machine):
        result = state_machine.update_state("unknown_conv", {"destination": "北京"})
        assert result is None

    def test_update_preserves_previous_collected(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state_machine.update_state("conv1", {"destination": "北京"})
        state = state_machine.update_state("conv1", {"days": 5})
        assert state.collected["destination"] == "北京"
        assert state.collected["days"] == 5


class TestSlotStateMachineRound:
    """Test clarification round tracking."""

    def test_round_increments(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state = state_machine.increment_round("conv1")
        assert state.round == 1

    def test_round_increments_multiple_times(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state_machine.increment_round("conv1")
        state = state_machine.increment_round("conv1")
        assert state.round == 2

    def test_round_timeout_after_max(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        for _ in range(3):
            state = state_machine.increment_round("conv1")
        assert state.state_type == SlotStateType.TIMEOUT


class TestSlotStateMachineClarification:
    """Test clarification question generation."""

    def test_generate_clarification_first_missing(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        question = state_machine.generate_clarification(
            state_machine.get_state("conv1")
        )
        assert question is not None
        assert "目的地" in question or "城市" in question

    def test_generate_clarification_with_context(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state_machine.update_state("conv1", {"destination": "北京"})
        question = state_machine.generate_clarification(
            state_machine.get_state("conv1")
        )
        assert "北京" in question

    def test_generate_clarification_omits_collected(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state_machine.update_state("conv1", {"destination": "北京"})
        question = state_machine.generate_clarification(
            state_machine.get_state("conv1")
        )
        assert "北京" in question

    def test_generate_clarification_none_for_complete(self, state_machine):
        state_machine.init_state("conv1", "query")
        question = state_machine.generate_clarification(
            state_machine.get_state("conv1")
        )
        assert question is None

    def test_generate_clarification_none_for_timeout(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        for _ in range(3):
            state_machine.increment_round("conv1")
        state = state_machine.get_state("conv1")
        question = state_machine.generate_clarification(state)
        assert question is None

    def test_generate_clarification_timeout_message(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        for _ in range(3):
            state_machine.increment_round("conv1")
        state = state_machine.get_state("conv1")
        assert state.state_type == SlotStateType.TIMEOUT


class TestSlotStateMachineClear:
    """Test state cleanup."""

    def test_clear_removes_state(self, state_machine):
        state_machine.init_state("conv1", "itinerary")
        state_machine.clear_state("conv1")
        assert state_machine.get_state("conv1") is None

    def test_clear_unknown_is_noop(self, state_machine):
        state_machine.clear_state("unknown_conv")  # should not raise


class TestSlotStateDataclass:
    """Test SlotState dataclass methods."""

    def test_is_complete_true(self):
        state = SlotState(intent="query", state_type=SlotStateType.COMPLETE)
        assert state.is_complete() is True

    def test_is_complete_false(self):
        state = SlotState(intent="itinerary", state_type=SlotStateType.COLLECTING)
        assert state.is_complete() is False

    def test_needs_clarification_true(self):
        state = SlotState(
            intent="itinerary",
            state_type=SlotStateType.COLLECTING,
            missing=["destination"],
        )
        assert state.needs_clarification() is True

    def test_needs_clarification_false_complete(self):
        state = SlotState(intent="query", state_type=SlotStateType.COMPLETE)
        assert state.needs_clarification() is False

    def test_needs_clarification_false_timeout(self):
        state = SlotState(intent="itinerary", state_type=SlotStateType.TIMEOUT)
        assert state.needs_clarification() is False

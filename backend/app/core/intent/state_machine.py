"""Slot state machine for multi-turn clarification.

Tracks collected/missing slots per conversation and generates
clarification questions one at a time with context.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SlotStateType(Enum):
    """Slot collection state types."""

    COLLECTING = "collecting"  # Missing required slots
    COMPLETE = "complete"  # All required slots collected
    TIMEOUT = "timeout"  # Exceeded max clarification rounds


@dataclass
class SlotState:
    """Represents the slot collection state for a conversation turn."""

    intent: str
    collected: Dict[str, Any] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    round: int = 0
    max_rounds: int = 3
    state_type: SlotStateType = SlotStateType.COLLECTING

    def is_complete(self) -> bool:
        """Check if all required slots are collected."""
        return self.state_type == SlotStateType.COMPLETE

    def needs_clarification(self) -> bool:
        """Check if clarification is still needed."""
        return self.state_type == SlotStateType.COLLECTING and bool(self.missing)


class SlotStateMachine:
    """Manages slot collection state across conversation turns."""

    # Required slots per intent type
    REQUIRED_SLOTS: Dict[str, List[str]] = {
        "itinerary": ["destination", "days"],
        "hotel": ["destination", "dates"],
        "food": ["destination"],
        "query": [],
        "chat": [],
    }

    # Clarification questions keyed by slot name
    SLOT_QUESTIONS: Dict[str, str] = {
        "destination": "您想去哪个城市？",
        "days": "计划玩几天？",
        "dates": "大概什么时候出发？",
    }

    def __init__(self) -> None:
        self._states: Dict[str, SlotState] = {}

    def get_state(self, conversation_id: str) -> Optional[SlotState]:
        """Retrieve the current state for a conversation."""
        return self._states.get(conversation_id)

    def init_state(self, conversation_id: str, intent: str) -> SlotState:
        """Initialize a new state for a conversation with the given intent."""
        required = self.REQUIRED_SLOTS.get(intent, [])
        state = SlotState(
            intent=intent,
            collected={},
            missing=list(required),
            round=0,
            max_rounds=3,
            state_type=SlotStateType.COMPLETE if not required else SlotStateType.COLLECTING,
        )
        self._states[conversation_id] = state
        return state

    def update_state(
        self, conversation_id: str, new_slots: Dict[str, Any]
    ) -> Optional[SlotState]:
        """Merge new slots into the conversation state.

        Args:
            conversation_id: The conversation identifier.
            new_slots: Dictionary of slot names to values.

        Returns:
            Updated SlotState, or None if conversation not found.
        """
        state = self._states.get(conversation_id)
        if state is None:
            return None

        # Merge new slots into collected
        state.collected.update(new_slots)

        # Remove newly filled slots from missing list
        state.missing = [s for s in state.missing if s not in new_slots]

        # Transition to COMPLETE if all required slots are collected
        if not state.missing:
            state.state_type = SlotStateType.COMPLETE

        return state

    def increment_round(self, conversation_id: str) -> Optional[SlotState]:
        """Increment the clarification round counter.

        Transitions to TIMEOUT if max_rounds exceeded.
        """
        state = self._states.get(conversation_id)
        if state is None:
            return None

        state.round += 1
        if state.round >= state.max_rounds:
            state.state_type = SlotStateType.TIMEOUT

        return state

    def clear_state(self, conversation_id: str) -> None:
        """Remove the state for a conversation."""
        self._states.pop(conversation_id, None)

    def generate_clarification(self, state: Optional[SlotState]) -> Optional[str]:
        """Generate the next clarification question.

        Asks for the first missing slot only, showing collected context.

        Args:
            state: Current slot state.

        Returns:
            Clarification question string, or None if complete/timeout.
        """
        if state is None:
            return None

        if state.state_type != SlotStateType.COLLECTING:
            return None

        if not state.missing:
            return None

        # Ask the first missing slot only
        slot_name = state.missing[0]
        base_question = self.SLOT_QUESTIONS.get(slot_name, f"请提供您的{slot_name}？")

        # Build context from already-collected slots
        context_parts = []
        for key, value in state.collected.items():
            if key != slot_name:
                context_parts.append(f"{key}={value}")

        if context_parts:
            context_str = "（已了解：" + "，".join(context_parts) + "）"
            return base_question + context_str

        return base_question

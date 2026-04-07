"""Tests for ICacheStore interface."""

import pytest
from abc import ABC

from app.core.cache.base import ICacheStore


def test_icache_store_cannot_be_instantiated():
    """Test that ICacheStore cannot be instantiated directly."""
    with pytest.raises(TypeError) as exc_info:
        ICacheStore()

    assert "abstract" in str(exc_info.value).lower()


def test_icache_store_requires_abstract_methods():
    """Test that ICacheStore defines all required abstract methods."""
    # Verify the class is an ABC
    assert issubclass(ICacheStore, ABC)

    # Verify all 10 abstract methods are defined
    abstract_methods = {
        "get_session",
        "set_session",
        "delete_session",
        "get_slots",
        "set_slots",
        "delete_slots",
        "get_user_prefs",
        "set_user_prefs",
        "delete_user_prefs",
        "health_check",
    }
    assert ICacheStore.__abstractmethods__ == abstract_methods


def test_complete_implementation():
    """Test a concrete implementation satisfies the ICacheStore contract."""

    class ConcreteCacheStore(ICacheStore):
        """Minimal concrete implementation for testing."""

        def __init__(self):
            self._sessions = {}
            self._slots = {}
            self._user_prefs = {}
            self._healthy = True

        def get_session(self, conversation_id: str):
            return self._sessions.get(conversation_id)

        def set_session(self, conversation_id: str, data: dict, ttl: int):
            self._sessions[conversation_id] = data

        def delete_session(self, conversation_id: str):
            return self._sessions.pop(conversation_id, None) is not None

        def get_slots(self, conversation_id: str):
            return self._slots.get(conversation_id)

        def set_slots(self, conversation_id: str, slots: dict, ttl: int):
            self._slots[conversation_id] = slots

        def delete_slots(self, conversation_id: str):
            return self._slots.pop(conversation_id, None) is not None

        def get_user_prefs(self, user_id: str):
            return self._user_prefs.get(user_id)

        def set_user_prefs(self, user_id: str, prefs: dict, ttl: int):
            self._user_prefs[user_id] = prefs

        def delete_user_prefs(self, user_id: str):
            return self._user_prefs.pop(user_id, None) is not None

        def health_check(self):
            return self._healthy

    # Instantiation succeeds
    store = ConcreteCacheStore()
    assert isinstance(store, ICacheStore)

    # Session operations
    store.set_session("conv1", {"messages": ["hello"]}, ttl=300)
    assert store.get_session("conv1") == {"messages": ["hello"]}
    assert store.delete_session("conv1") is True
    assert store.get_session("conv1") is None

    # Slots operations
    store.set_slots("conv1", {"origin": "Beijing", "destination": "Shanghai"}, ttl=600)
    assert store.get_slots("conv1") == {"origin": "Beijing", "destination": "Shanghai"}
    assert store.delete_slots("conv1") is True
    assert store.get_slots("conv1") is None

    # User prefs operations
    store.set_user_prefs("user1", {"language": "zh", "currency": "CNY"}, ttl=3600)
    assert store.get_user_prefs("user1") == {"language": "zh", "currency": "CNY"}
    assert store.delete_user_prefs("user1") is True
    assert store.get_user_prefs("user1") is None

    # Health check
    assert store.health_check() is True
    store._healthy = False
    assert store.health_check() is False

    # Delete non-existent returns False
    assert store.delete_session("nonexistent") is False
    assert store.delete_slots("nonexistent") is False
    assert store.delete_user_prefs("nonexistent") is False

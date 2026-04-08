"""Tests for ICacheStore interface."""
import pytest
from app.core.cache.base import ICacheStore


def test_icache_store_cannot_be_instantiated():
    """Interface cannot be directly instantiated."""
    with pytest.raises(TypeError):
        ICacheStore()


def test_icache_store_requires_abstract_methods():
    """Subclass must implement all abstract methods."""
    class IncompleteStore(ICacheStore):
        pass  # Intentionally not implementing any method

    with pytest.raises(TypeError):
        IncompleteStore()


@pytest.mark.asyncio
async def test_complete_implementation_can_be_instantiated():
    """Complete implementation can be instantiated."""
    from typing import Optional, Dict

    class DummyStore(ICacheStore):
        async def get_session(self, conversation_id: str) -> Optional[Dict]:
            return None

        async def set_session(self, conversation_id: str, data: Dict, ttl: int) -> None:
            pass

        async def delete_session(self, conversation_id: str) -> bool:
            return False

        async def get_slots(self, conversation_id: str) -> Optional[Dict]:
            return None

        async def set_slots(self, conversation_id: str, slots: Dict, ttl: int) -> None:
            pass

        async def delete_slots(self, conversation_id: str) -> bool:
            return False

        async def get_user_prefs(self, user_id: str) -> Optional[Dict]:
            return None

        async def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int) -> None:
            pass

        async def delete_user_prefs(self, user_id: str) -> bool:
            return False

        async def health_check(self) -> bool:
            return True

    store = DummyStore()
    assert await store.health_check() is True
    assert await store.get_session("test") is None

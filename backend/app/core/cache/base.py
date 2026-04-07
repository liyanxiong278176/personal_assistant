"""ICacheStore abstract interface for cache operations."""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class ICacheStore(ABC):
    """Abstract interface for cache store implementations.

    Defines the contract for session, slot, and user preferences caching
    operations across different storage backends (Redis, memory, etc.).
    """

    @abstractmethod
    def get_session(self, conversation_id: str) -> Optional[Dict]:
        """Retrieve session data for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            Session data dict if found, None otherwise.
        """
        ...

    @abstractmethod
    def set_session(self, conversation_id: str, data: Dict, ttl: int) -> None:
        """Store session data for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.
            data: Session data dictionary to store.
            ttl: Time-to-live in seconds.
        """
        ...

    @abstractmethod
    def delete_session(self, conversation_id: str) -> bool:
        """Delete session data for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    def get_slots(self, conversation_id: str) -> Optional[Dict]:
        """Retrieve slots (conversation state) for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            Slots dict if found, None otherwise.
        """
        ...

    @abstractmethod
    def set_slots(self, conversation_id: str, slots: Dict, ttl: int) -> None:
        """Store slots (conversation state) for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.
            slots: Slots dictionary to store.
            ttl: Time-to-live in seconds.
        """
        ...

    @abstractmethod
    def delete_slots(self, conversation_id: str) -> bool:
        """Delete slots for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    def get_user_prefs(self, user_id: str) -> Optional[Dict]:
        """Retrieve user preferences.

        Args:
            user_id: Unique identifier for the user.

        Returns:
            User preferences dict if found, None otherwise.
        """
        ...

    @abstractmethod
    def set_user_prefs(self, user_id: str, prefs: Dict, ttl: int) -> None:
        """Store user preferences.

        Args:
            user_id: Unique identifier for the user.
            prefs: Preferences dictionary to store.
            ttl: Time-to-live in seconds.
        """
        ...

    @abstractmethod
    def delete_user_prefs(self, user_id: str) -> bool:
        """Delete user preferences.

        Args:
            user_id: Unique identifier for the user.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the cache store is healthy and accessible.

        Returns:
            True if healthy, False otherwise.
        """
        ...

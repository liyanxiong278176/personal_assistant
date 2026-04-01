"""Conversation service layer.

Handles business logic for conversation management including CRUD operations,
search, filtering, and tag management.
"""

import logging
from typing import Optional
from uuid import UUID

from app.db.postgres import (
    Database,
    create_conversation,
    get_conversation,
    update_conversation,
    list_user_conversations,
    search_conversations,
    add_conversation_tag,
    remove_conversation_tag,
    get_conversation_tags,
    get_all_user_tags,
)

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing conversations.

    Provides methods for CRUD operations, search, filtering,
    and tag management with proper permission checks.
    """

    async def create_conversation(
        self, user_id: str, title: str = "新对话"
    ) -> dict:
        """Create a new conversation for a user.

        Args:
            user_id: User ID
            title: Conversation title (default: "新对话")

        Returns:
            Created conversation dict
        """
        conv_id = await create_conversation(title)

        # Associate with user
        conn = await Database.get_connection()
        try:
            await conn.execute(
                "UPDATE conversations SET user_id = $1 WHERE id = $2",
                user_id,
                conv_id,
            )
        finally:
            await Database.release_connection(conn)

        # Return the conversation
        conv = await get_conversation(conv_id)
        return conv

    async def get_conversation(
        self, conversation_id: UUID, user_id: str
    ) -> Optional[dict]:
        """Get a conversation by ID with permission check.

        Args:
            conversation_id: Conversation UUID
            user_id: User ID for permission check

        Returns:
            Conversation dict or None if not found

        Raises:
            PermissionError: If user doesn't own the conversation
        """
        conv = await get_conversation(conversation_id)
        if not conv:
            return None

        # Permission check: user_id must match or conversation must be public
        if conv.get("user_id") and str(conv["user_id"]) != user_id:
            logger.warning(
                f"Permission denied: user {user_id} tried to access conversation {conversation_id}"
            )
            raise PermissionError("You do not have access to this conversation")

        # Add tags to response
        tags = await get_conversation_tags(conversation_id)
        conv["tags"] = [tag["tag_name"] for tag in tags]

        return conv

    async def update_conversation(
        self,
        conversation_id: UUID,
        user_id: str,
        title: Optional[str] = None,
        is_archived: Optional[bool] = None,
        pinned: Optional[bool] = None,
        sync_enabled: Optional[bool] = None,
    ) -> Optional[dict]:
        """Update conversation properties with permission check.

        Args:
            conversation_id: Conversation UUID
            user_id: User ID for permission check
            title: New title (optional)
            is_archived: Archive status (optional)
            pinned: Pin status (optional)
            sync_enabled: Sync status (optional)

        Returns:
            Updated conversation dict or None if not found

        Raises:
            PermissionError: If user doesn't own the conversation
        """
        # Verify ownership first
        conv = await get_conversation(conversation_id)
        if not conv:
            return None

        if conv.get("user_id") and str(conv["user_id"]) != user_id:
            raise PermissionError("You do not have access to this conversation")

        # Perform update
        success = await update_conversation(
            conversation_id,
            title=title,
            is_archived=is_archived,
            pinned=pinned,
            sync_enabled=sync_enabled,
        )

        if success:
            # Return updated conversation
            return await self.get_conversation(conversation_id, user_id)
        return None

    async def list_conversations(
        self,
        user_id: str,
        include_archived: bool = False,
        archived_only: bool = False,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """List conversations for a user with filters.

        Args:
            user_id: User ID
            include_archived: Whether to include archived conversations
            archived_only: Whether to only return archived conversations
            limit: Maximum number of conversations to return

        Returns:
            Tuple of (conversations list, total count)
        """
        # If archived_only is True, we need to filter for archived only
        # Otherwise use include_archived flag
        if archived_only:
            conversations = await list_user_conversations(
                user_id, include_archived=True, limit=limit
            )
            conversations = [c for c in conversations if c.get("is_archived")]
        else:
            conversations = await list_user_conversations(
                user_id, include_archived=include_archived, limit=limit
            )

        # Add tags to each conversation
        for conv in conversations:
            tags = await get_conversation_tags(conv["id"])
            conv["tags"] = [tag["tag_name"] for tag in tags]

        # Get total count
        total = len(conversations)
        return conversations, total

    async def search_conversations(
        self, user_id: str, query: str, limit: int = 20
    ) -> list[dict]:
        """Search conversations by title or message content.

        Args:
            user_id: User ID (required for permission filtering)
            query: Search query string
            limit: Maximum results

        Returns:
            List of matching conversations
        """
        conversations = await search_conversations(user_id, query, limit)

        # Add tags to each conversation
        for conv in conversations:
            tags = await get_conversation_tags(conv["id"])
            conv["tags"] = [tag["tag_name"] for tag in tags]

        return conversations

    async def delete_conversation(
        self, conversation_id: UUID, user_id: str
    ) -> bool:
        """Delete a conversation with permission check.

        Args:
            conversation_id: Conversation UUID
            user_id: User ID for permission check

        Returns:
            True if deleted, False if not found

        Raises:
            PermissionError: If user doesn't own the conversation
        """
        # Verify ownership first
        conv = await get_conversation(conversation_id)
        if not conv:
            return False

        if conv.get("user_id") and str(conv["user_id"]) != user_id:
            raise PermissionError("You do not have access to this conversation")

        # Perform delete
        conn = await Database.get_connection()
        try:
            result = await conn.execute(
                "DELETE FROM conversations WHERE id = $1", conversation_id
            )
            return result == "DELETE 1"
        finally:
            await Database.release_connection(conn)

    async def add_tag(
        self, conversation_id: UUID, user_id: str, tag_name: str, color: str = "#6366f1"
    ) -> dict:
        """Add a tag to a conversation.

        Args:
            conversation_id: Conversation UUID
            user_id: User ID for permission check
            tag_name: Tag name
            color: Tag color (hex)

        Returns:
            Created tag dict

        Raises:
            PermissionError: If user doesn't own the conversation
        """
        # Verify ownership
        conv = await get_conversation(conversation_id)
        if not conv:
            raise ValueError("Conversation not found")

        if conv.get("user_id") and str(conv["user_id"]) != user_id:
            raise PermissionError("You do not have access to this conversation")

        tag_id = await add_conversation_tag(conversation_id, tag_name, color)
        return {
            "id": tag_id,
            "conversation_id": str(conversation_id),
            "tag_name": tag_name,
            "color": color,
        }

    async def remove_tag(self, conversation_id: UUID, user_id: str, tag_name: str) -> bool:
        """Remove a tag from a conversation.

        Args:
            conversation_id: Conversation UUID
            user_id: User ID for permission check
            tag_name: Tag name to remove

        Returns:
            True if removed, False if not found

        Raises:
            PermissionError: If user doesn't own the conversation
        """
        # Verify ownership
        conv = await get_conversation(conversation_id)
        if not conv:
            return False

        if conv.get("user_id") and str(conv["user_id"]) != user_id:
            raise PermissionError("You do not have access to this conversation")

        return await remove_conversation_tag(conversation_id, tag_name)

    async def get_tags(self, conversation_id: UUID, user_id: str) -> list[dict]:
        """Get all tags for a conversation.

        Args:
            conversation_id: Conversation UUID
            user_id: User ID for permission check

        Returns:
            List of tag dicts

        Raises:
            PermissionError: If user doesn't own the conversation
        """
        # Verify ownership
        conv = await get_conversation(conversation_id)
        if not conv:
            return []

        if conv.get("user_id") and str(conv["user_id"]) != user_id:
            raise PermissionError("You do not have access to this conversation")

        return await get_conversation_tags(conversation_id)

    async def get_all_tags(self, user_id: str) -> list[str]:
        """Get all unique tag names for a user.

        Args:
            user_id: User ID

        Returns:
            List of unique tag names
        """
        return await get_all_user_tags(user_id)


# Singleton instance
_conversation_service: Optional[ConversationService] = None


def get_conversation_service() -> ConversationService:
    """Get or create the conversation service singleton.

    Returns:
        ConversationService instance
    """
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService()
    return _conversation_service

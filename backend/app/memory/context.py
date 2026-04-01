"""Context builder - integrates all three memory layers."""

import logging
from uuid import UUID

from .base import MemoryContext
from .working_memory import WorkingMemory
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .prompts import SYSTEM_PROMPT_WITH_MEMORY

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Builds complete LLM context from all memory layers.

    Combines:
    1. System prompt
    2. Long-term memory (user profile from semantic memory)
    3. Short-term memory (current conversation from episodic memory)
    4. Working memory (recent messages)
    5. Current message
    """

    def __init__(self):
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()

    async def build_context(
        self,
        user_id: str | None,
        conversation_id: UUID,
        working_memory: WorkingMemory,
        current_message: str,
        system_prompt: str | None = None,
    ) -> MemoryContext:
        """Build complete context for LLM request.

        Args:
            user_id: Optional user ID for personalized memories
            conversation_id: Current conversation UUID
            working_memory: Working memory with recent messages
            current_message: Current user message
            system_prompt: Optional custom system prompt

        Returns:
            Complete MemoryContext ready for LLM
        """
        # Use default or custom system prompt
        sys_prompt = system_prompt or SYSTEM_PROMPT_WITH_MEMORY

        context = MemoryContext(
            system_prompt=sys_prompt,
            working_memory=working_memory.to_llm_format(),
            current_message=current_message,
        )

        # Add long-term memory if user is authenticated
        if user_id:
            try:
                # Get user profile
                profile = await self.semantic.get_user_profile(user_id)

                # Search relevant memories based on current message
                relevant_memories = await self.semantic.search_memories(
                    user_id=user_id,
                    query=current_message,
                    n_results=3,
                )

                # Build long-term memory context
                long_term = []

                # Add preferences
                if profile.get("travel_preferences"):
                    prefs = profile["travel_preferences"]
                    for key, value in prefs.items():
                        if value:  # Only include non-empty values
                            long_term.append({
                                "content": f"{key}: {value}",
                                "type": "preference",
                            })

                # Add relevant semantic memories
                for mem in relevant_memories:
                    long_term.append({
                        "content": mem["content"],
                        "type": mem.get("metadata", {}).get("memory_type", "memory"),
                    })

                context.long_term_memory = long_term[:5]  # Limit to 5 items

            except Exception as e:
                logger.error(f"[ContextBuilder] Failed to load long-term memory: {e}")

        # Add short-term memory from current conversation
        try:
            episodic_memories = await self.episodic.get_by_conversation(
                conversation_id=conversation_id,
            )

            context.short_term_memory = [
                {
                    "content": m["content"],
                    "type": m["memory_type"],
                }
                for m in episodic_memories[:10]  # Limit to 10 items
            ]

        except Exception as e:
            logger.error(f"[ContextBuilder] Failed to load short-term memory: {e}")

        logger.info(
            f"[ContextBuilder] Built context: "
            f"long_term={len(context.long_term_memory)}, "
            f"short_term={len(context.short_term_memory)}, "
            f"working={len(context.working_memory)}"
        )

        return context

    async def extract_and_store_memory(
        self,
        user_id: str | None,
        conversation_id: UUID,
        message_content: str,
        message_role: str,
        llm_complete_fn,
    ) -> None:
        """Extract memory from message and store appropriately.

        Args:
            user_id: Optional user ID
            conversation_id: Current conversation UUID
            message_content: Message content
            message_role: Message role (user/assistant)
            llm_complete_fn: Async function for non-streaming LLM calls
        """
        if message_role != "user":
            return  # Only extract from user messages

        # TODO: Implement LLM-based extraction
        # This would call the extractor with the conversation context
        pass

    async def promote_memories(
        self,
        user_id: str,
        conversation_id: UUID,
        llm_complete_fn,
    ) -> None:
        """Promote important episodic memories to long-term.

        Args:
            user_id: User UUID
            conversation_id: Conversation UUID
            llm_complete_fn: Async function for non-streaming LLM calls
        """
        # Get unpromoted memories above importance threshold
        unpromoted = await self.episodic.get_unpromoted(
            conversation_id=conversation_id,
            min_importance=0.7,
        )

        if not unpromoted:
            return

        # Get user profile for context
        profile = await self.semantic.get_user_profile(user_id)

        for memory in unpromoted:
            try:
                # TODO: Use LLM to evaluate promotion
                # For now, auto-promote high-importance memories

                # Add to semantic memory
                await self.semantic.add_memory(
                    user_id=user_id,
                    content=memory["content"],
                    memory_type=memory["memory_type"],
                    metadata={"importance": memory["importance"]},
                )

                # Update user profile if it's a preference
                if memory["memory_type"] == "preference":
                    await self.semantic.update_user_profile(
                        user_id=user_id,
                        preferences=memory.get("structured_data", {}),
                    )

                # Mark as promoted
                await self.episodic.mark_promoted(memory["id"])

                logger.info(
                    f"[ContextBuilder] Promoted memory: {memory['memory_type']} - "
                    f"{memory['content'][:50]}"
                )

            except Exception as e:
                logger.error(f"[ContextBuilder] Failed to promote memory {memory['id']}: {e}")

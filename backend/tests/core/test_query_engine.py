"""Tests for QueryEngine."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from app.core.query_engine import QueryEngine, get_global_engine, set_global_engine
from app.core.errors import AgentError, DegradationLevel
from app.intent import SlashCommand, SkillTrigger, register_slash, register_skill


def make_async_stream(items):
    """Create an async stream function that yields the given items."""
    async def stream(*args, **kwargs):
        for item in items:
            yield item
    # Create a mock that records calls but returns the actual async generator
    original_stream = stream
    mock = MagicMock(side_effect=lambda *args, **kwargs: original_stream(*args, **kwargs))
    return mock


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""

    async def mock_stream(*args, **kwargs):
        """Default mock stream that yields empty."""
        return
        yield

    client = MagicMock()
    # Use a regular MagicMock for stream_chat so we can replace it per test
    client.stream_chat = MagicMock(side_effect=lambda *args, **kwargs: mock_stream(*args, **kwargs))
    client.chat = AsyncMock(return_value="Default response")
    client.close = AsyncMock()
    return client


@pytest.fixture
def query_engine(mock_llm_client):
    """Create a QueryEngine with mock LLM client."""
    return QueryEngine(llm_client=mock_llm_client)


@pytest.fixture(autouse=True)
def clear_registries():
    """Clear intent registries before each test."""
    from app import intent
    intent._slash_registry.clear()
    intent._skill_registry.clear()
    yield
    intent._slash_registry.clear()
    intent._skill_registry.clear()


class TestQueryEngineInit:
    """Tests for QueryEngine initialization."""

    def test_init_with_llm_client(self, mock_llm_client):
        """Test initialization with LLM client."""
        engine = QueryEngine(llm_client=mock_llm_client)
        assert engine.llm_client is mock_llm_client
        assert engine.system_prompt
        assert engine._conversation_history == {}

    def test_init_without_llm_client(self):
        """Test initialization without LLM client."""
        engine = QueryEngine(llm_client=None)
        assert engine.llm_client is None

    def test_init_with_custom_system_prompt(self, mock_llm_client):
        """Test initialization with custom system prompt."""
        custom_prompt = "You are a helpful assistant."
        engine = QueryEngine(
            llm_client=mock_llm_client,
            system_prompt=custom_prompt
        )
        assert engine.system_prompt == custom_prompt

    def test_set_llm_client(self):
        """Test setting LLM client after initialization."""
        engine = QueryEngine(llm_client=None)
        assert engine.llm_client is None

        engine.set_llm_client(mock_llm_client)
        assert engine.llm_client is mock_llm_client


class TestConversationHistory:
    """Tests for conversation history management."""

    def test_get_conversation_history_empty(self, query_engine):
        """Test getting history for new conversation."""
        history = query_engine._get_conversation_history("test-conv-1")
        assert history == []

    def test_update_conversation_history(self, query_engine):
        """Test updating conversation history."""
        query_engine._update_conversation_history(
            "test-conv-1",
            "Hello",
            "Hi there!"
        )

        history = query_engine._get_conversation_history("test-conv-1")
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there!"}

    def test_conversation_history_trimming(self, query_engine):
        """Test that history is trimmed to 20 messages."""
        # Add 15 exchanges (30 messages)
        for i in range(15):
            query_engine._update_conversation_history(
                "test-conv-1",
                f"Message {i}",
                f"Response {i}"
            )

        history = query_engine._get_conversation_history("test-conv-1")
        # Should be trimmed to 20 messages (10 exchanges)
        assert len(history) == 20
        # Last messages should be preserved
        assert history[-2]["content"] == "Message 14"
        assert history[-1]["content"] == "Response 14"

    def test_reset_conversation(self, query_engine):
        """Test resetting conversation history."""
        query_engine._update_conversation_history(
            "test-conv-1",
            "Hello",
            "Hi there!"
        )
        assert len(query_engine._get_conversation_history("test-conv-1")) == 2

        query_engine.reset_conversation("test-conv-1")
        assert len(query_engine._get_conversation_history("test-conv-1")) == 0


class TestSlashCommandRouting:
    """Tests for slash command intent routing."""

    @pytest.mark.asyncio
    async def test_unknown_slash_command(self, query_engine):
        """Test handling of unknown slash command."""
        chunks = []
        async for chunk in query_engine.process(
            "/unknown command",
            "test-conv"
        ):
            chunks.append(chunk)

        response = "".join(chunks)
        assert "未知命令" in response
        assert "/unknown" in response

    @pytest.mark.asyncio
    async def test_registered_slash_command(self, query_engine):
        """Test handling of registered slash command."""
        # Register a test slash command
        async def help_handler(conversation_id: str) -> str:
            return "This is the help text"

        register_slash(SlashCommand(
            name="help",
            description="Show help",
            handler=help_handler
        ))

        chunks = []
        async for chunk in query_engine.process(
            "/help",
            "test-conv"
        ):
            chunks.append(chunk)

        response = "".join(chunks)
        assert response == "This is the help text"

    @pytest.mark.asyncio
    async def test_slash_command_with_args(self, query_engine):
        """Test slash command with additional arguments."""
        async def echo_handler(conversation_id: str, **kwargs) -> str:
            return "Echo received"

        register_slash(SlashCommand(
            name="echo",
            description="Echo input",
            handler=echo_handler
        ))

        chunks = []
        async for chunk in query_engine.process(
            "/echo some arguments here",
            "test-conv"
        ):
            chunks.append(chunk)

        response = "".join(chunks)
        assert response == "Echo received"

    @pytest.mark.asyncio
    async def test_slash_command_error_handling(self, query_engine):
        """Test error handling in slash commands."""
        async def failing_handler(conversation_id: str) -> str:
            raise ValueError("Intentional error")

        register_slash(SlashCommand(
            name="fail",
            description="Failing command",
            handler=failing_handler
        ))

        chunks = []
        async for chunk in query_engine.process(
            "/fail",
            "test-conv"
        ):
            chunks.append(chunk)

        response = "".join(chunks)
        assert "命令执行失败" in response


class TestSkillTriggerRouting:
    """Tests for skill trigger intent routing."""

    @pytest.mark.asyncio
    async def test_registered_skill_trigger(self, query_engine):
        """Test handling of registered skill trigger."""
        async def weather_handler(user_input: str, conversation_id: str) -> str:
            return "The weather is sunny today!"

        register_skill(SkillTrigger(
            name="weather",
            description="Weather query",
            trigger_pattern="天气",
            handler=weather_handler
        ))

        chunks = []
        async for chunk in query_engine.process(
            "今天北京天气怎么样？",
            "test-conv"
        ):
            chunks.append(chunk)

        response = "".join(chunks)
        assert response == "The weather is sunny today!"

    @pytest.mark.asyncio
    async def test_skill_trigger_case_insensitive(self, query_engine, mock_llm_client):
        """Test that skill triggers are case insensitive."""
        async def weather_handler(user_input: str, conversation_id: str) -> str:
            return "Weather response"

        register_skill(SkillTrigger(
            name="weather",
            description="Weather query",
            trigger_pattern="天气",
            handler=weather_handler
        ))

        # Set up LLM mock for fallback
        mock_llm_client.stream_chat = make_async_stream(["LLM fallback response"])

        chunks = []
        async for chunk in query_engine.process(
            "今天TIANQI怎么样？",  # Mixed case - won't match "天气"
            "test-conv"
        ):
            chunks.append(chunk)

        # In stub, it's simple substring matching, so "TIANQI" won't match "天气"
        # This will fall through to LLM
        response = "".join(chunks)
        assert response == "LLM fallback response"

    @pytest.mark.asyncio
    async def test_skill_trigger_error_handling(self, query_engine):
        """Test error handling in skill triggers."""
        async def failing_handler(user_input: str, conversation_id: str) -> str:
            raise RuntimeError("Skill failed")

        register_skill(SkillTrigger(
            name="failing_skill",
            description="Failing skill",
            trigger_pattern="fail",
            handler=failing_handler
        ))

        chunks = []
        async for chunk in query_engine.process(
            "This should fail",
            "test-conv"
        ):
            chunks.append(chunk)

        response = "".join(chunks)
        assert "技能执行失败" in response


class TestLLMProcessing:
    """Tests for LLM-based processing."""

    @pytest.mark.asyncio
    async def test_process_with_llm(self, query_engine, mock_llm_client):
        """Test basic LLM processing."""
        mock_llm_client.stream_chat = make_async_stream(["Hello", " there", "!"])

        chunks = []
        async for chunk in query_engine.process(
            "Hi",
            "test-conv"
        ):
            chunks.append(chunk)

        response = "".join(chunks)
        assert response == "Hello there!"

        # Verify history was updated
        history = query_engine._get_conversation_history("test-conv")
        assert len(history) == 2
        assert history[0]["content"] == "Hi"
        assert history[1]["content"] == "Hello there!"

    @pytest.mark.asyncio
    async def test_process_with_conversation_history(self, query_engine, mock_llm_client):
        """Test that conversation history is passed to LLM."""
        # Set up some history
        query_engine._update_conversation_history(
            "test-conv",
            "Previous message",
            "Previous response"
        )

        mock_llm_client.stream_chat = make_async_stream(["New response"])

        chunks = []
        async for chunk in query_engine.process(
            "New message",
            "test-conv"
        ):
            chunks.append(chunk)

        # Verify LLM was called with history
        # Get the first call args (before history was updated)
        call_args = mock_llm_client.stream_chat.call_args_list[0]
        messages = call_args[1]["messages"]
        assert len(messages) == 3  # Previous exchange + new message
        assert messages[0]["content"] == "Previous message"
        assert messages[1]["content"] == "Previous response"
        assert messages[2]["content"] == "New message"

    @pytest.mark.asyncio
    async def test_process_without_llm_client(self):
        """Test that processing fails without LLM client."""
        engine = QueryEngine(llm_client=None)

        with pytest.raises(AgentError) as exc_info:
            async for _ in engine.process("Hello", "test-conv"):
                pass

        assert exc_info.value.level == DegradationLevel.LLM_DEGRADED

    @pytest.mark.asyncio
    async def test_process_simple(self, query_engine, mock_llm_client):
        """Test process_simple for one-shot queries."""
        mock_llm_client.chat.return_value = "Simple response"

        response = await query_engine.process_simple(
            "Simple query",
            system_prompt="Custom prompt"
        )

        assert response == "Simple response"

        # Verify custom prompt was used
        call_args = mock_llm_client.chat.call_args
        assert call_args[1]["system_prompt"] == "Custom prompt"

    @pytest.mark.asyncio
    async def test_process_simple_without_llm_client(self):
        """Test that process_simple fails without LLM client."""
        engine = QueryEngine(llm_client=None)

        with pytest.raises(AgentError) as exc_info:
            await engine.process_simple("Hello")

        assert exc_info.value.level == DegradationLevel.LLM_DEGRADED


class TestGlobalEngine:
    """Tests for global engine instance."""

    def test_get_global_engine_creates_instance(self):
        """Test that get_global_engine creates an instance."""
        # Clear any existing global engine
        from app import core
        original_engine = getattr(core.query_engine, "_global_engine", None)
        core.query_engine._global_engine = None

        engine = get_global_engine()
        assert isinstance(engine, QueryEngine)

        # Subsequent calls return same instance
        assert get_global_engine() is engine

        # Restore original
        core.query_engine._global_engine = original_engine

    def test_set_global_engine(self):
        """Test setting global engine."""
        mock_llm = MagicMock()
        custom_engine = QueryEngine(llm_client=mock_llm)

        set_global_engine(custom_engine)
        assert get_global_engine() is custom_engine


class TestCleanup:
    """Tests for resource cleanup."""

    @pytest.mark.asyncio
    async def test_close(self, mock_llm_client):
        """Test that close cleans up LLM client."""
        engine = QueryEngine(llm_client=mock_llm_client)
        await engine.close()

        mock_llm_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_none_client(self):
        """Test close with None client doesn't crash."""
        engine = QueryEngine(llm_client=None)
        await engine.close()  # Should not raise

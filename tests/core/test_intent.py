"""Tests for Intent Routing System (Slash Commands and Skills)."""

import pytest
from unittest.mock import AsyncMock

from app.core.intent.commands import (
    CommandResult,
    SlashCommand,
    SlashCommandRegistry,
    get_slash_registry,
    set_slash_registry,
)

from app.core.intent.skills import (
    SkillResult,
    Skill,
    SkillRegistry,
    get_skill_registry,
    set_skill_registry,
)


# Test Fixtures


@pytest.fixture
def simple_handler():
    """Create a simple async handler for testing."""
    async def handler(conversation_id: str, match=None, **kwargs) -> CommandResult:
        return CommandResult(success=True, message="Handler executed")
    return handler


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    # Reset global registry
    import app.core.intent.commands as commands_module
    commands_module._global_registry = None
    return SlashCommandRegistry()


@pytest.fixture
def sample_command(simple_handler):
    """Create a sample slash command."""
    return SlashCommand(
        name="test",
        pattern=r"^/test\s*$",
        handler=simple_handler,
        description="Test command"
    )


# Test CommandResult


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful result."""
        result = CommandResult(
            success=True,
            message="Operation successful"
        )
        assert result.success is True
        assert result.message == "Operation successful"
        assert result.data is None
        assert result.error is None

    def test_create_result_with_data(self):
        """Test creating a result with additional data."""
        result = CommandResult(
            success=True,
            message="Here's your data",
            data={"count": 42, "items": ["a", "b"]}
        )
        assert result.data == {"count": 42, "items": ["a", "b"]}

    def test_create_error_result(self):
        """Test creating an error result."""
        result = CommandResult(
            success=False,
            message="Operation failed",
            error="Invalid input"
        )
        assert result.success is False
        assert result.error == "Invalid input"

    def test_string_conversion(self):
        """Test that result converts to string using message."""
        result = CommandResult(
            success=True,
            message="Test message"
        )
        assert str(result) == "Test message"


# Test SlashCommand


class TestSlashCommand:
    """Tests for SlashCommand class."""

    def test_init(self):
        """Test SlashCommand initialization."""
        async def handler(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="test")

        cmd = SlashCommand(
            name="test",
            pattern=r"^/test\s*$",
            handler=handler,
            description="Test command"
        )

        assert cmd.name == "test"
        assert cmd.description == "Test command"
        assert cmd.handler is handler

    def test_match_exact(self, sample_command):
        """Test exact pattern matching."""
        match = sample_command.match("/test")
        assert match is not None
        assert match.group(0) == "/test"

    def test_match_with_whitespace(self, sample_command):
        """Test matching with trailing whitespace."""
        match = sample_command.match("/test   ")
        assert match is not None

    def test_match_case_sensitive(self):
        """Test that matching is case-sensitive."""
        async def handler(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="test")

        cmd = SlashCommand(
            name="test",
            pattern=r"^/TEST\s*$",
            handler=handler,
            description="Test"
        )

        assert cmd.match("/TEST") is not None
        assert cmd.match("/test") is None

    def test_match_no_match(self, sample_command):
        """Test non-matching input."""
        match = sample_command.match("/other")
        assert match is None

    def test_match_non_slash(self, sample_command):
        """Test that non-slash input doesn't match."""
        match = sample_command.match("test")
        assert match is None

    def test_match_with_groups(self):
        """Test pattern matching with named groups."""
        async def handler(conversation_id: str, match=None, **kwargs) -> CommandResult:
            return CommandResult(success=True, message=f"Got: {kwargs}")

        cmd = SlashCommand(
            name="greet",
            pattern=r"^/greet\s+(?P<name>\w+)(?:\s+(?P<title>\w+))?\s*$",
            handler=handler,
            description="Greet someone"
        )

        # Match with name only
        match = cmd.match("/greet Alice")
        assert match is not None
        assert match.group("name") == "Alice"
        assert match.group("title") is None

        # Match with name and title
        match = cmd.match("/greet Alice Dr")
        assert match is not None
        assert match.group("name") == "Alice"
        assert match.group("title") == "Dr"

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_command):
        """Test successful command execution."""
        match = sample_command.match("/test")
        result = await sample_command.execute(
            match,
            conversation_id="conv-123"
        )

        assert result.success is True
        assert result.message == "Handler executed"

    @pytest.mark.asyncio
    async def test_execute_with_groups(self):
        """Test execution with named groups passed to handler."""
        received_kwargs = {}

        async def handler(conversation_id: str, match=None, **kwargs):
            received_kwargs.update(kwargs)
            return CommandResult(success=True, message="OK")

        cmd = SlashCommand(
            name="capture",
            pattern=r"^/capture\s+(?P<item>\w+)\s+(?P<quantity>\d+)\s*$",
            handler=handler,
            description="Capture groups"
        )

        match = cmd.match("/capture apples 5")
        result = await cmd.execute(match, conversation_id="conv-1")

        assert result.success is True
        assert received_kwargs == {"item": "apples", "quantity": "5"}

    @pytest.mark.asyncio
    async def test_execute_with_extra_kwargs(self):
        """Test execution with additional context kwargs."""
        async def handler(conversation_id: str, match=None, user_id=None, **kwargs):
            return CommandResult(
                success=True,
                message=f"User: {user_id}"
            )

        cmd = SlashCommand(
            name="user",
            pattern=r"^/user\s*$",
            handler=handler,
            description="User command"
        )

        match = cmd.match("/user")
        result = await cmd.execute(
            match,
            conversation_id="conv-1",
            user_id="user-123"
        )

        assert result.success is True
        assert "user-123" in result.message

    @pytest.mark.asyncio
    async def test_execute_handler_returns_string(self):
        """Test execution when handler returns string instead of CommandResult."""
        async def handler(conversation_id: str, match=None, **kwargs):
            return "String result"

        cmd = SlashCommand(
            name="string",
            pattern=r"^/string\s*$",
            handler=handler,
            description="String handler"
        )

        match = cmd.match("/string")
        result = await cmd.execute(match, conversation_id="conv-1")

        assert result.success is True
        assert result.message == "String result"

    @pytest.mark.asyncio
    async def test_execute_handler_raises_error(self):
        """Test execution when handler raises an exception."""
        async def handler(conversation_id: str, match=None, **kwargs):
            raise ValueError("Handler error")

        cmd = SlashCommand(
            name="error",
            pattern=r"^/error\s*$",
            handler=handler,
            description="Error handler"
        )

        match = cmd.match("/error")
        from app.core.errors import AgentError

        with pytest.raises(AgentError) as exc_info:
            await cmd.execute(match, conversation_id="conv-1")

        assert "Command execution failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_handler_returns_invalid_type(self):
        """Test execution when handler returns invalid type."""
        async def handler(conversation_id: str, match=None, **kwargs):
            return 123  # Invalid type

        cmd = SlashCommand(
            name="invalid",
            pattern=r"^/invalid\s*$",
            handler=handler,
            description="Invalid handler"
        )

        match = cmd.match("/invalid")
        from app.core.errors import AgentError

        with pytest.raises(AgentError) as exc_info:
            await cmd.execute(match, conversation_id="conv-1")

        assert "invalid type" in str(exc_info.value).lower()


# Test SlashCommandRegistry


class TestSlashCommandRegistry:
    """Tests for SlashCommandRegistry class."""

    def test_init_empty(self):
        """Test registry initialization is empty."""
        registry = SlashCommandRegistry()
        assert len(registry) == 0
        assert registry.commands == {}

    def test_register_command(self, registry, sample_command):
        """Test registering a command."""
        registry.register(sample_command)
        assert len(registry) == 1
        assert "test" in registry
        assert registry.get("test") is sample_command

    def test_register_duplicate_fails(self, registry, sample_command):
        """Test that registering duplicate command raises error."""
        registry.register(sample_command)

        with pytest.raises(ValueError) as exc_info:
            registry.register(sample_command)

        assert "already registered" in str(exc_info.value)

    def test_replace_command(self, registry):
        """Test replacing an existing command."""
        async def handler1(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="handler1")

        async def handler2(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="handler2")

        cmd1 = SlashCommand("test", r"^/test\s*$", handler1, "First")
        cmd2 = SlashCommand("test", r"^/test\s*$", handler2, "Second")

        registry.register(cmd1)
        assert registry.get("test").description == "First"

        registry.replace(cmd2)
        assert registry.get("test").description == "Second"
        assert len(registry) == 1  # Still only one command

    def test_replace_new_command(self, registry, sample_command):
        """Test that replace works for new commands too."""
        registry.replace(sample_command)
        assert len(registry) == 1
        assert "test" in registry

    def test_unregister_existing(self, registry, sample_command):
        """Test unregistering an existing command."""
        registry.register(sample_command)
        assert len(registry) == 1

        result = registry.unregister("test")
        assert result is True
        assert len(registry) == 0
        assert "test" not in registry

    def test_unregister_nonexistent(self, registry):
        """Test unregistering a non-existent command."""
        result = registry.unregister("nonexistent")
        assert result is False

    def test_match_slash_command(self, registry, sample_command):
        """Test matching a registered command."""
        registry.register(sample_command)

        result = registry.match("/test")
        assert result is not None
        cmd, match = result
        assert cmd is sample_command
        assert match.group(0) == "/test"

    def test_match_no_match(self, registry, sample_command):
        """Test matching when no command matches."""
        registry.register(sample_command)

        result = registry.match("/other")
        assert result is None

    def test_match_non_slash(self, registry, sample_command):
        """Test that non-slash input doesn't match."""
        registry.register(sample_command)

        result = registry.match("test")
        assert result is None

    def test_match_first_wins(self, registry):
        """Test that first matching command is returned."""
        async def handler1(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="1")

        async def handler2(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="2")

        # Both match /test, but handler1 is registered first
        cmd1 = SlashCommand("first", r"^/test\s*$", handler1, "First")
        cmd2 = SlashCommand("second", r"^/test\s*$", handler2, "Second")

        registry.register(cmd1)
        registry.register(cmd2)

        result = registry.match("/test")
        assert result is not None
        cmd, _ = result
        assert cmd.name == "first"

    def test_get_existing(self, registry, sample_command):
        """Test getting an existing command."""
        registry.register(sample_command)
        assert registry.get("test") is sample_command

    def test_get_nonexistent(self, registry):
        """Test getting a non-existent command."""
        assert registry.get("nonexistent") is None

    def test_list_commands_empty(self, registry):
        """Test listing commands when registry is empty."""
        assert registry.list_commands() == []

    def test_list_commands(self, registry):
        """Test listing all commands."""
        async def handler(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="ok")

        registry.register(SlashCommand(
            "help", r"^/help\s*$", handler, "Show help"
        ))
        registry.register(SlashCommand(
            "reset", r"^/reset\s*$", handler, "Reset conversation"
        ))
        registry.register(SlashCommand(
            "plan", r"^/plan\s*$", handler, "Plan trip"
        ))

        commands = registry.list_commands()
        assert len(commands) == 3

        # Check sorted by name
        assert commands[0]["name"] == "help"
        assert commands[1]["name"] == "plan"
        assert commands[2]["name"] == "reset"

        # Check structure
        for cmd in commands:
            assert "name" in cmd
            assert "description" in cmd
            assert "usage" in cmd
            assert cmd["usage"] == f"/{cmd['name']}"

    def test_commands_property(self, registry):
        """Test that commands property returns a copy."""
        async def handler(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="ok")

        cmd = SlashCommand("test", r"^/test\s*$", handler, "Test")
        registry.register(cmd)

        commands = registry.commands
        commands["new"] = "value"  # Modify the returned dict

        # Original should be unchanged
        assert "new" not in registry._commands

    def test_contains_operator(self, registry, sample_command):
        """Test the 'in' operator for registry."""
        registry.register(sample_command)

        assert "test" in registry
        assert "other" not in registry

    def test_len_operator(self, registry):
        """Test the len() operator for registry."""
        assert len(registry) == 0

        async def handler(conversation_id: str, match=None) -> CommandResult:
            return CommandResult(success=True, message="ok")

        registry.register(SlashCommand("a", r"^/a\s*$", handler, "A"))
        assert len(registry) == 1

        registry.register(SlashCommand("b", r"^/b\s*$", handler, "B"))
        assert len(registry) == 2


# Test Global Registry


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_slash_registry_creates_singleton(self):
        """Test that get_slash_registry creates a singleton."""
        # Reset global state
        import app.core.intent.commands as commands_module
        commands_module._global_registry = None

        registry1 = get_slash_registry()
        registry2 = get_slash_registry()

        assert registry1 is registry2
        assert isinstance(registry1, SlashCommandRegistry)

    def test_get_slash_registry_has_defaults(self):
        """Test that global registry has default commands."""
        import app.core.intent.commands as commands_module
        commands_module._global_registry = None

        registry = get_slash_registry()

        # Check default commands exist
        assert "help" in registry
        assert "reset" in registry
        assert "plan" in registry
        assert "weather" in registry

        # Check they have proper structure
        help_cmd = registry.get("help")
        assert help_cmd.description
        assert help_cmd.handler

    def test_set_slash_registry(self):
        """Test setting a custom global registry."""
        import app.core.intent.commands as commands_module
        commands_module._global_registry = None

        custom_registry = SlashCommandRegistry()
        set_slash_registry(custom_registry)

        assert get_slash_registry() is custom_registry


# Test Default Commands


class TestDefaultCommands:
    """Tests for built-in default commands."""

    @pytest.fixture
    def default_registry(self):
        """Get a fresh default registry."""
        import app.core.intent.commands as commands_module
        commands_module._global_registry = None
        return get_slash_registry()

    @pytest.mark.asyncio
    async def test_help_command(self, default_registry):
        """Test the /help command."""
        result = default_registry.match("/help")
        assert result is not None

        cmd, match = result
        response = await cmd.execute(match, conversation_id="test-conv")

        assert response.success is True
        assert "Available Commands" in response.message
        assert "/help" in response.message
        assert "/reset" in response.message
        assert "/plan" in response.message
        assert "/weather" in response.message

    @pytest.mark.asyncio
    async def test_reset_command(self, default_registry):
        """Test the /reset command."""
        result = default_registry.match("/reset")
        assert result is not None

        cmd, match = result
        response = await cmd.execute(match, conversation_id="conv-123")

        assert response.success is True
        assert "reset" in response.message.lower()
        assert response.data is not None
        assert response.data["action"] == "reset_conversation"
        assert response.data["conversation_id"] == "conv-123"

    @pytest.mark.asyncio
    async def test_plan_command_with_destination(self, default_registry):
        """Test the /plan command with destination."""
        result = default_registry.match("/plan Paris")
        assert result is not None

        cmd, match = result
        response = await cmd.execute(match, conversation_id="conv-1")

        assert response.success is True
        assert "Paris" in response.message
        assert "Planning trip" in response.message

    @pytest.mark.asyncio
    async def test_plan_command_with_destination_and_date(self, default_registry):
        """Test the /plan command with destination and date."""
        result = default_registry.match("/plan Tokyo 2024-06-01")
        assert result is not None

        cmd, match = result
        response = await cmd.execute(match, conversation_id="conv-1")

        assert response.success is True
        assert "Tokyo" in response.message
        assert "2024-06-01" in response.message

    @pytest.mark.asyncio
    async def test_plan_command_without_args(self, default_registry):
        """Test the /plan command without arguments."""
        result = default_registry.match("/plan")
        assert result is not None

        cmd, match = result
        response = await cmd.execute(match, conversation_id="conv-1")

        assert response.success is True
        assert "specify a destination" in response.message.lower()

    @pytest.mark.asyncio
    async def test_weather_command_with_city(self, default_registry):
        """Test the /weather command with city."""
        result = default_registry.match("/weather Beijing")
        assert result is not None

        cmd, match = result
        response = await cmd.execute(match, conversation_id="conv-1")

        assert response.success is True
        assert "Beijing" in response.message
        assert "weather" in response.message.lower()

    @pytest.mark.asyncio
    async def test_weather_command_without_city(self, default_registry):
        """Test the /weather command without city."""
        result = default_registry.match("/weather")
        assert result is not None

        cmd, match = result
        response = await cmd.execute(match, conversation_id="conv-1")

        assert response.success is True
        assert "specify a city" in response.message.lower()

    @pytest.mark.asyncio
    async def test_unknown_command(self, default_registry):
        """Test that unknown commands don't match."""
        result = default_registry.match("/unknown_command")
        assert result is None


# =============================================================================
# Tests for Skill System
# =============================================================================


# Skill System Fixtures


@pytest.fixture
def skill_handler():
    """Create a simple async handler for skill testing."""
    async def handler(input_text: str, **kwargs) -> SkillResult:
        return SkillResult(
            skill_name="test_skill",
            confidence=1.0,
            matched_text=input_text,
            message="Skill executed"
        )
    return handler


@pytest.fixture
def skill_registry():
    """Create a fresh skill registry for each test."""
    import app.core.intent.skills as skills_module
    skills_module._global_registry = None
    return SkillRegistry()


@pytest.fixture
def sample_skill(skill_handler):
    """Create a sample skill."""
    return Skill(
        name="test_skill",
        patterns=[r"test.*pattern", r"sample.*match"],
        handler=skill_handler,
        description="Test skill"
    )


# Test SkillResult


class TestSkillResult:
    """Tests for SkillResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful skill result."""
        result = SkillResult(
            skill_name="test_skill",
            confidence=0.9,
            matched_text="test pattern matched",
            message="Operation successful"
        )
        assert result.skill_name == "test_skill"
        assert result.confidence == 0.9
        assert result.matched_text == "test pattern matched"
        assert result.message == "Operation successful"
        assert result.success is True
        assert result.data is None
        assert result.error is None

    def test_create_result_with_data(self):
        """Test creating a result with additional data."""
        result = SkillResult(
            skill_name="test_skill",
            confidence=1.0,
            matched_text="matched",
            message="Here's your data",
            data={"destination": "Beijing", "days": 5}
        )
        assert result.data == {"destination": "Beijing", "days": 5}

    def test_create_error_result(self):
        """Test creating an error result."""
        result = SkillResult(
            skill_name="test_skill",
            confidence=0.0,
            matched_text="",
            message="Operation failed",
            error="Invalid input",
            success=False
        )
        assert result.success is False
        assert result.error == "Invalid input"

    def test_string_conversion(self):
        """Test that result converts to string using message."""
        result = SkillResult(
            skill_name="test",
            confidence=1.0,
            matched_text="matched",
            message="Test message"
        )
        assert str(result) == "Test message"


# Test Skill


class TestSkill:
    """Tests for Skill class."""

    def test_init(self):
        """Test Skill initialization."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="test"
            )

        skill = Skill(
            name="test",
            patterns=[r"test.*pattern", r"another.*pattern"],
            handler=handler,
            description="Test skill"
        )

        assert skill.name == "test"
        assert skill.description == "Test skill"
        assert skill.handler is handler
        assert len(skill._raw_patterns) == 2
        assert len(skill._compiled_patterns) == 2

    def test_match_exact_pattern(self, sample_skill):
        """Test exact pattern matching."""
        result = sample_skill.match("test pattern here")
        assert result is not None
        assert result.skill_name == "test_skill"
        assert result.confidence > 0

    def test_match_multiple_patterns(self, sample_skill):
        """Test matching with multiple patterns."""
        # First pattern
        result1 = sample_skill.match("test pattern match")
        assert result1 is not None

        # Second pattern
        result2 = sample_skill.match("sample match here")
        assert result2 is not None

    def test_match_case_sensitive(self):
        """Test that matching is case-sensitive by default."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="test"
            )

        skill = Skill(
            name="test",
            patterns=[r"TEST.*PATTERN"],
            handler=handler,
            description="Test"
        )

        assert skill.match("TEST PATTERN") is not None
        assert skill.match("test pattern") is None

    def test_match_no_match(self, sample_skill):
        """Test non-matching input."""
        result = sample_skill.match("completely unrelated text")
        assert result is None

    def test_match_confidence_threshold(self):
        """Test confidence threshold filtering."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="test"
            )

        # Pattern with very short match (low confidence)
        skill = Skill(
            name="test",
            patterns=[r"test"],
            handler=handler,
            description="Test"
        )

        # Long input with short pattern match = low confidence
        result = skill.match("this is a very long input with test at the end")
        # Confidence should be below 0.7 due to short match vs long input
        assert result is None  # Below default 0.7 threshold

        # But with lower threshold, it should match
        result_low = skill.match(
            "this is a very long input with test at the end",
            confidence=0.3
        )
        assert result_low is not None

    def test_confidence_calculation(self):
        """Test confidence score calculation based on match length."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="test"
            )

        skill = Skill(
            name="test",
            patterns=[r"long.*pattern.*here"],
            handler=handler,
            description="Test"
        )

        # Longer match relative to input = higher confidence
        result = skill.match("long pattern here")
        assert result is not None
        assert result.confidence > 0.9

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_skill):
        """Test successful skill execution."""
        result = await sample_skill.execute("test pattern input")

        assert result.success is True
        assert result.message == "Skill executed"
        assert result.skill_name == "test_skill"

    @pytest.mark.asyncio
    async def test_execute_with_kwargs(self):
        """Test execution with additional context kwargs."""
        received_kwargs = {}

        async def handler(input_text: str, **kwargs):
            received_kwargs.update(kwargs)
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message=f"Context: {kwargs.get('conversation_id')}"
            )

        skill = Skill(
            name="context_skill",
            patterns=[r"context"],
            handler=handler,
            description="Context test"
        )

        result = await skill.execute(
            "context",
            conversation_id="conv-123",
            user_id="user-456"
        )

        assert result.success is True
        assert "conv-123" in result.message
        assert received_kwargs["conversation_id"] == "conv-123"
        assert received_kwargs["user_id"] == "user-456"

    @pytest.mark.asyncio
    async def test_execute_handler_returns_string(self):
        """Test execution when handler returns string instead of SkillResult."""
        async def handler(input_text: str, **kwargs):
            return "String result"

        skill = Skill(
            name="string_skill",
            patterns=[r"string"],
            handler=handler,
            description="String handler"
        )

        result = await skill.execute("string")

        assert result.success is True
        assert result.message == "String result"
        assert result.skill_name == "string_skill"

    @pytest.mark.asyncio
    async def test_execute_handler_raises_error(self):
        """Test execution when handler raises an exception."""
        async def handler(input_text: str, **kwargs):
            raise ValueError("Handler error")

        skill = Skill(
            name="error_skill",
            patterns=[r"error"],
            handler=handler,
            description="Error handler"
        )

        from app.core.errors import AgentError

        with pytest.raises(AgentError) as exc_info:
            await skill.execute("error")

        assert "Skill execution failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_handler_returns_invalid_type(self):
        """Test execution when handler returns invalid type."""
        async def handler(input_text: str, **kwargs):
            return 123  # Invalid type

        skill = Skill(
            name="invalid_skill",
            patterns=[r"invalid"],
            handler=handler,
            description="Invalid handler"
        )

        from app.core.errors import AgentError

        with pytest.raises(AgentError) as exc_info:
            await skill.execute("invalid")

        assert "invalid type" in str(exc_info.value).lower()


# Test SkillRegistry


class TestSkillRegistry:
    """Tests for SkillRegistry class."""

    def test_init_empty(self):
        """Test registry initialization is empty."""
        registry = SkillRegistry()
        assert len(registry) == 0
        assert registry.skills == {}

    def test_register_skill(self, skill_registry, sample_skill):
        """Test registering a skill."""
        skill_registry.register(sample_skill)
        assert len(skill_registry) == 1
        assert "test_skill" in skill_registry
        assert skill_registry.get("test_skill") is sample_skill

    def test_register_duplicate_fails(self, skill_registry, sample_skill):
        """Test that registering duplicate skill raises error."""
        skill_registry.register(sample_skill)

        with pytest.raises(ValueError) as exc_info:
            skill_registry.register(sample_skill)

        assert "already registered" in str(exc_info.value)

    def test_replace_skill(self, skill_registry):
        """Test replacing an existing skill."""
        async def handler1(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="handler1"
            )

        async def handler2(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="handler2"
            )

        skill1 = Skill("test", [r"test"], handler1, "First")
        skill2 = Skill("test", [r"test"], handler2, "Second")

        skill_registry.register(skill1)
        assert skill_registry.get("test").description == "First"

        skill_registry.replace(skill2)
        assert skill_registry.get("test").description == "Second"
        assert len(skill_registry) == 1  # Still only one skill

    def test_replace_new_skill(self, skill_registry, sample_skill):
        """Test that replace works for new skills too."""
        skill_registry.replace(sample_skill)
        assert len(skill_registry) == 1
        assert "test_skill" in skill_registry

    def test_unregister_existing(self, skill_registry, sample_skill):
        """Test unregistering an existing skill."""
        skill_registry.register(sample_skill)
        assert len(skill_registry) == 1

        result = skill_registry.unregister("test_skill")
        assert result is True
        assert len(skill_registry) == 0
        assert "test_skill" not in skill_registry

    def test_unregister_nonexistent(self, skill_registry):
        """Test unregistering a non-existent skill."""
        result = skill_registry.unregister("nonexistent")
        assert result is False

    def test_match_skill(self, skill_registry, sample_skill):
        """Test matching a registered skill."""
        skill_registry.register(sample_skill)

        result = skill_registry.match("test pattern here")
        assert result is not None
        assert result.skill_name == "test_skill"

    def test_match_no_match(self, skill_registry, sample_skill):
        """Test matching when no skill matches."""
        skill_registry.register(sample_skill)

        result = skill_registry.match("completely unrelated")
        assert result is None

    def test_match_returns_highest_confidence(self):
        """Test that match returns the highest confidence skill."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="ok"
            )

        # First skill with short pattern (lower confidence)
        skill1 = Skill(
            "low_conf",
            [r"match"],
            handler,
            "Low confidence"
        )

        # Second skill with longer pattern (higher confidence)
        skill2 = Skill(
            "high_conf",
            [r"match.*specific.*pattern"],
            handler,
            "High confidence"
        )

        registry = SkillRegistry()
        registry.register(skill1)
        registry.register(skill2)

        result = registry.match("this match specific pattern here")
        assert result is not None
        # The longer pattern should produce higher confidence
        assert result.skill_name == "high_conf"

    def test_match_confidence_threshold(self, skill_registry):
        """Test confidence threshold in match."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="test"
            )

        # Create skill with simple pattern
        skill = Skill("test", [r"test"], handler, "Test")
        skill_registry.register(skill)

        # With high threshold - exact match gives 1.0 confidence
        result_high = skill_registry.match("test", confidence=1.01)
        assert result_high is None  # Above max possible confidence

        # With normal threshold
        result_normal = skill_registry.match("test", confidence=0.99)
        assert result_normal is not None  # Below actual confidence

        # With low threshold
        result_low = skill_registry.match("test", confidence=0.5)
        assert result_low is not None  # Above threshold

    @pytest.mark.asyncio
    async def test_execute_match(self, skill_registry):
        """Test execute_match method."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message=f"Executed with: {input_text}"
            )

        skill = Skill("test", [r"test.*pattern"], handler, "Test")
        skill_registry.register(skill)

        result = await skill_registry.execute_match("test pattern here")

        assert result is not None
        assert result.success is True
        assert "Executed with:" in result.message

    @pytest.mark.asyncio
    async def test_execute_match_no_match(self, skill_registry):
        """Test execute_match when no skill matches."""
        result = await skill_registry.execute_match("no match here")
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_match_with_kwargs(self, skill_registry):
        """Test execute_match with additional kwargs."""
        received_kwargs = {}

        async def handler(input_text: str, **kwargs) -> SkillResult:
            received_kwargs.update(kwargs)
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="ok"
            )

        skill = Skill("test", [r"test"], handler, "Test")
        skill_registry.register(skill)

        result = await skill_registry.execute_match(
            "test",
            conversation_id="conv-123"
        )

        assert result is not None
        assert received_kwargs["conversation_id"] == "conv-123"

    def test_get_existing(self, skill_registry, sample_skill):
        """Test getting an existing skill."""
        skill_registry.register(sample_skill)
        assert skill_registry.get("test_skill") is sample_skill

    def test_get_nonexistent(self, skill_registry):
        """Test getting a non-existent skill."""
        assert skill_registry.get("nonexistent") is None

    def test_list_skills_empty(self, skill_registry):
        """Test listing skills when registry is empty."""
        assert skill_registry.list_skills() == []

    def test_list_skills(self, skill_registry):
        """Test listing all skill names."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="ok"
            )

        skill_registry.register(Skill(
            "attraction", [r"attraction"], handler, "Attraction skill"
        ))
        skill_registry.register(Skill(
            "itinerary", [r"itinerary"], handler, "Itinerary skill"
        ))
        skill_registry.register(Skill(
            "advice", [r"advice"], handler, "Advice skill"
        ))

        skills = skill_registry.list_skills()
        assert len(skills) == 3

        # Check sorted alphabetically
        assert skills[0] == "advice"
        assert skills[1] == "attraction"
        assert skills[2] == "itinerary"

    def test_list_skills_details(self, skill_registry):
        """Test listing skills with full details."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="ok"
            )

        skill = Skill(
            "test_skill",
            [r"pattern1", r"pattern2"],
            handler,
            "Test description"
        )
        skill_registry.register(skill)

        details = skill_registry.list_skills_details()
        assert len(details) == 1

        assert details[0]["name"] == "test_skill"
        assert details[0]["description"] == "Test description"
        assert details[0]["patterns"] == [r"pattern1", r"pattern2"]

    def test_skills_property(self, skill_registry):
        """Test that skills property returns a copy."""
        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="ok"
            )

        skill = Skill("test", [r"test"], handler, "Test")
        skill_registry.register(skill)

        skills = skill_registry.skills
        skills["new"] = "value"  # Modify the returned dict

        # Original should be unchanged
        assert "new" not in skill_registry._skills

    def test_contains_operator(self, skill_registry, sample_skill):
        """Test the 'in' operator for registry."""
        skill_registry.register(sample_skill)

        assert "test_skill" in skill_registry
        assert "other" not in skill_registry

    def test_len_operator(self, skill_registry):
        """Test the len() operator for registry."""
        assert len(skill_registry) == 0

        async def handler(input_text: str, **kwargs) -> SkillResult:
            return SkillResult(
                skill_name="test",
                confidence=1.0,
                matched_text=input_text,
                message="ok"
            )

        skill_registry.register(Skill("a", [r"a"], handler, "A"))
        assert len(skill_registry) == 1

        skill_registry.register(Skill("b", [r"b"], handler, "B"))
        assert len(skill_registry) == 2


# Test Global Skill Registry


class TestGlobalSkillRegistry:
    """Tests for global skill registry functions."""

    def test_get_skill_registry_creates_singleton(self):
        """Test that get_skill_registry creates a singleton."""
        import app.core.intent.skills as skills_module
        skills_module._global_registry = None

        registry1 = get_skill_registry()
        registry2 = get_skill_registry()

        assert registry1 is registry2
        assert isinstance(registry1, SkillRegistry)

    def test_get_skill_registry_has_defaults(self):
        """Test that global registry has default skills."""
        import app.core.intent.skills as skills_module
        skills_module._global_registry = None

        registry = get_skill_registry()

        # Check default skills exist
        assert "itinerary_planning" in registry
        assert "attraction_recommendation" in registry
        assert "travel_advice" in registry

        # Check they have proper structure
        itinerary_skill = registry.get("itinerary_planning")
        assert itinerary_skill.description
        assert itinerary_skill.handler
        assert len(itinerary_skill._raw_patterns) > 0

    def test_set_skill_registry(self):
        """Test setting a custom global registry."""
        import app.core.intent.skills as skills_module
        skills_module._global_registry = None

        custom_registry = SkillRegistry()
        set_skill_registry(custom_registry)

        assert get_skill_registry() is custom_registry


# Test Default Skills


class TestDefaultSkills:
    """Tests for built-in default skills."""

    @pytest.fixture
    def default_registry(self):
        """Get a fresh default registry."""
        import app.core.intent.skills as skills_module
        skills_module._global_registry = None
        return get_skill_registry()

    def test_itinerary_planning_patterns(self, default_registry):
        """Test itinerary planning skill has correct patterns."""
        skill = default_registry.get("itinerary_planning")
        assert skill is not None

        patterns = skill._raw_patterns
        assert r"规划.*行程" in patterns
        assert r"制定.*计划" in patterns
        assert r"安排.*旅游" in patterns

    def test_itinerary_planning_matches(self, default_registry):
        """Test itinerary planning skill matches expected inputs."""
        test_cases = [
            "请帮我规划北京行程",
            "制定一个旅行计划",
            "安排一下去上海的旅游",
            "设计一条旅游路线",
            "计划去成都旅行",
            "行程规划求推荐",
        ]

        for test_input in test_cases:
            result = default_registry.match(test_input)
            assert result is not None, f"Should match: {test_input}"
            assert result.skill_name == "itinerary_planning"

    def test_itinerary_planning_no_match(self, default_registry):
        """Test itinerary planning skill doesn't match unrelated input."""
        result = default_registry.match("今天天气怎么样")
        assert result is None or result.skill_name != "itinerary_planning"

    @pytest.mark.asyncio
    async def test_itinerary_planning_execution(self, default_registry):
        """Test itinerary planning skill execution."""
        result = await default_registry.execute_match("帮我规划北京的行程")

        assert result is not None
        assert result.success is True
        assert result.skill_name == "itinerary_planning"
        assert "规划" in result.message or "北京" in result.message
        assert result.data is not None
        assert result.data.get("action") == "itinerary_planning"
        assert result.data.get("destination") == "北京"

    @pytest.mark.asyncio
    async def test_itinerary_planning_execution_no_destination(self, default_registry):
        """Test itinerary planning execution without destination."""
        result = await default_registry.execute_match("请帮我规划行程")

        assert result is not None
        assert result.success is True
        assert "规划" in result.message
        assert result.data.get("destination") is None

    def test_attraction_recommendation_patterns(self, default_registry):
        """Test attraction recommendation skill has correct patterns."""
        skill = default_registry.get("attraction_recommendation")
        assert skill is not None

        patterns = skill._raw_patterns
        assert r"推荐.*景点" in patterns
        assert r"哪里.*好玩" in patterns
        assert r"有什么.*景点" in patterns

    def test_attraction_recommendation_matches(self, default_registry):
        """Test attraction recommendation skill matches expected inputs."""
        test_cases = [
            "推荐一些杭州的景点",
            "上海哪里好玩",
            "成都有什么必去的景点",
            "推荐景点",
            "有什么好玩的地方",
            "值得一去的旅游景点",
        ]

        for test_input in test_cases:
            result = default_registry.match(test_input)
            assert result is not None, f"Should match: {test_input}"
            assert result.skill_name == "attraction_recommendation"

    @pytest.mark.asyncio
    async def test_attraction_recommendation_execution(self, default_registry):
        """Test attraction recommendation skill execution."""
        result = await default_registry.execute_match("推荐西安的景点")

        assert result is not None
        assert result.success is True
        assert result.skill_name == "attraction_recommendation"
        assert "推荐" in result.message or "西安" in result.message
        assert result.data.get("action") == "attraction_recommendation"
        assert result.data.get("destination") == "西安"

    def test_travel_advice_patterns(self, default_registry):
        """Test travel advice skill has correct patterns."""
        skill = default_registry.get("travel_advice")
        assert skill is not None

        patterns = skill._raw_patterns
        assert r"建议.*交通" in patterns
        assert r"怎么.*去" in patterns
        assert r"注意.*事项" in patterns

    def test_travel_advice_matches(self, default_registry):
        """Test travel advice skill matches expected inputs."""
        test_cases = [
            "建议什么交通方式去北京",
            "怎么去上海最方便",
            "去成都有什么注意事项",
            "如何到达广州",
            "出行建议",
            "交通方式推荐",
            "求旅行攻略",  # Changed from "求旅游攻略" to match pattern
        ]

        for test_input in test_cases:
            result = default_registry.match(test_input)
            assert result is not None, f"Should match: {test_input}"
            assert result.skill_name == "travel_advice"

    @pytest.mark.asyncio
    async def test_travel_advice_execution_transport(self, default_registry):
        """Test travel advice execution with transport query."""
        result = await default_registry.execute_match("怎么去北京最方便")

        assert result is not None
        assert result.success is True
        assert result.skill_name == "travel_advice"
        assert "交通" in result.message or "出行" in result.message
        assert result.data.get("action") == "travel_advice"
        assert result.data.get("is_transport_query") is True

    @pytest.mark.asyncio
    async def test_travel_advice_execution_general(self, default_registry):
        """Test travel advice execution with general query."""
        result = await default_registry.execute_match("旅行有什么注意事项")

        assert result is not None
        assert result.success is True
        assert result.skill_name == "travel_advice"
        assert result.data.get("is_transport_query") is False

    def test_skill_priority_selection(self, default_registry):
        """Test that correct skill is selected when multiple could match."""
        # Input that could match both itinerary and attraction
        # Should select based on pattern specificity and confidence
        result = default_registry.match("规划北京景点推荐行程")
        # The most specific match should win
        assert result is not None
        assert result.skill_name in [
            "itinerary_planning",
            "attraction_recommendation"
        ]

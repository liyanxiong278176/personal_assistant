"""Tests for Slash Command System (Intent Routing)."""

import pytest
from unittest.mock import AsyncMock

from app.core.intent.commands import (
    CommandResult,
    SlashCommand,
    SlashCommandRegistry,
    get_slash_registry,
    set_slash_registry,
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

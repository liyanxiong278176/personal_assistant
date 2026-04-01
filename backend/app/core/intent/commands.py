"""Slash Command System

Provides fast command entry points for common actions.
Slash commands are the first layer of intent routing in QueryEngine.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, List, Dict, Any

from app.core.errors import AgentError

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a slash command execution.

    Attributes:
        success: Whether the command executed successfully
        message: The response message to display to the user
        data: Optional additional data (e.g., structured results)
        error: Optional error message if execution failed
    """
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def __str__(self) -> str:
        """Return the message as string representation."""
        return self.message


class SlashCommand:
    """Slash command definition with pattern matching.

    A slash command represents a quick action that users can trigger
    by typing a command prefix (e.g., /help, /reset).

    Example:
        ```python
        async def handle_help(conversation_id: str) -> CommandResult:
            return CommandResult(
                success=True,
                message="Available commands: /help, /reset"
            )

        cmd = SlashCommand(
            name="help",
            pattern=r"^/help\s*$",
            handler=handle_help,
            description="Show available commands"
        )
        ```
    """

    def __init__(
        self,
        name: str,
        pattern: str,
        handler: Callable[..., Awaitable[CommandResult]],
        description: str
    ):
        """Initialize a SlashCommand.

        Args:
            name: Command name (without the / prefix)
            pattern: Regex pattern to match input text
            handler: Async function that returns CommandResult
            description: Human-readable description of the command
        """
        self.name = name
        self._pattern = pattern
        self._compiled_pattern = re.compile(pattern)
        self.handler = handler
        self.description = description

    def match(self, input_text: str) -> Optional[re.Match]:
        """Check if input text matches this command's pattern.

        Args:
            input_text: User input text to match against

        Returns:
            re.Match object if matched, None otherwise
        """
        return self._compiled_pattern.match(input_text.strip())

    async def execute(
        self,
        match: re.Match,
        conversation_id: str,
        **kwargs
    ) -> CommandResult:
        """Execute the command with the given match context.

        Args:
            match: The regex match object from pattern matching
            conversation_id: Current conversation identifier
            **kwargs: Additional context (user_id, etc.)

        Returns:
            CommandResult with the execution outcome

        Raises:
            AgentError: If command execution fails
        """
        try:
            # Extract named groups from match if available
            groups = match.groupdict() if match.re.groupindex else {}

            # Call handler with conversation_id and any matched groups
            result = await self.handler(
                conversation_id=conversation_id,
                match=match,
                **groups,
                **kwargs
            )

            if not isinstance(result, CommandResult):
                logger.warning(
                    f"[SlashCommand] Handler for '{self.name}' "
                    f"returned non-CommandResult: {type(result)}"
                )
                # Convert to CommandResult if possible
                if isinstance(result, str):
                    result = CommandResult(success=True, message=result)
                else:
                    raise AgentError(
                        f"Command handler returned invalid type: {type(result)}"
                    )

            return result

        except AgentError:
            raise
        except Exception as e:
            logger.error(f"[SlashCommand] Execution failed for '{self.name}': {e}")
            raise AgentError(f"Command execution failed: {e}")


class SlashCommandRegistry:
    """Registry for managing slash commands.

    The registry maintains a collection of slash commands and provides
    methods for registration, matching, and listing.

    Example:
        ```python
        registry = SlashCommandRegistry()

        registry.register(SlashCommand(
            name="help",
            pattern=r"^/help\s*$",
            handler=handle_help,
            description="Show help"
        ))

        command = registry.match("/help")
        if command:
            result = await command.execute(match, conversation_id="conv-1")
        ```
    """

    def __init__(self):
        """Initialize an empty SlashCommandRegistry."""
        self._commands: Dict[str, SlashCommand] = {}

    def register(self, command: SlashCommand) -> None:
        """Register a slash command.

        Args:
            command: SlashCommand instance to register

        Raises:
            ValueError: If a command with the same name already exists
        """
        if command.name in self._commands:
            raise ValueError(
                f"Command '{command.name}' is already registered. "
                f"Use replace() to override."
            )

        self._commands[command.name] = command
        logger.info(f"[SlashCommandRegistry] Registered command: /{command.name}")

    def replace(self, command: SlashCommand) -> None:
        """Replace an existing command or register if new.

        Args:
            command: SlashCommand instance to register/replace
        """
        if command.name in self._commands:
            logger.info(f"[SlashCommandRegistry] Replacing command: /{command.name}")
        else:
            logger.info(f"[SlashCommandRegistry] Registering command: /{command.name}")

        self._commands[command.name] = command

    def unregister(self, name: str) -> bool:
        """Unregister a slash command.

        Args:
            name: Command name to unregister

        Returns:
            True if command was removed, False if not found
        """
        if name in self._commands:
            del self._commands[name]
            logger.info(f"[SlashCommandRegistry] Unregistered command: /{name}")
            return True
        return False

    def match(self, input_text: str) -> Optional[tuple[SlashCommand, re.Match]]:
        """Find a command that matches the input text.

        Args:
            input_text: User input text to match

        Returns:
            Tuple of (SlashCommand, re.Match) if matched, None otherwise
        """
        # Only process if it starts with /
        if not input_text.strip().startswith("/"):
            return None

        for command in self._commands.values():
            match = command.match(input_text)
            if match:
                return command, match

        return None

    def get(self, name: str) -> Optional[SlashCommand]:
        """Get a command by name.

        Args:
            name: Command name (without / prefix)

        Returns:
            SlashCommand if found, None otherwise
        """
        return self._commands.get(name)

    def list_commands(self) -> List[Dict[str, str]]:
        """List all registered commands.

        Returns:
            List of dicts with 'name', 'description', and 'usage' keys
        """
        return [
            {
                "name": cmd.name,
                "description": cmd.description,
                "usage": f"/{cmd.name}"
            }
            for cmd in sorted(self._commands.values(), key=lambda c: c.name)
        ]

    @property
    def commands(self) -> Dict[str, SlashCommand]:
        """Get all registered commands."""
        return self._commands.copy()

    def __len__(self) -> int:
        """Return the number of registered commands."""
        return len(self._commands)

    def __contains__(self, name: str) -> bool:
        """Check if a command is registered."""
        return name in self._commands


# Global registry instance
_global_registry: Optional[SlashCommandRegistry] = None


def get_slash_registry() -> SlashCommandRegistry:
    """Get the global slash command registry.

    Creates the registry on first call and registers default commands.

    Returns:
        The global SlashCommandRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = SlashCommandRegistry()
        _register_default_commands(_global_registry)
        logger.info("[SlashCommandRegistry] Created global registry with defaults")
    return _global_registry


def set_slash_registry(registry: SlashCommandRegistry) -> None:
    """Set a custom global slash command registry.

    Args:
        registry: SlashCommandRegistry to use as global
    """
    global _global_registry
    _global_registry = registry
    logger.info("[SlashCommandRegistry] Set custom global registry")


def _register_default_commands(registry: SlashCommandRegistry) -> None:
    """Register default slash commands.

    Args:
        registry: The registry to register commands into
    """
    # /help - Show available commands
    async def handle_help(
        conversation_id: str,
        match: re.Match,
        **kwargs
    ) -> CommandResult:
        commands = registry.list_commands()
        help_lines = [
            "**Available Commands:**",
            ""
        ]
        for cmd in commands:
            help_lines.append(f"  `{cmd['usage']}` - {cmd['description']}")
        help_lines.append("")
        help_lines.append("Type a command to execute it.")

        return CommandResult(
            success=True,
            message="\n".join(help_lines)
        )

    registry.register(SlashCommand(
        name="help",
        pattern=r"^/help\s*$",
        handler=handle_help,
        description="Show available commands"
    ))

    # /plan - Quick trip planning
    async def handle_plan(
        conversation_id: str,
        match: re.Match,
        destination: Optional[str] = None,
        date: Optional[str] = None,
        **kwargs
    ) -> CommandResult:
        if destination:
            msg = f"Planning trip to {destination}"
            if date:
                msg += f" on {date}"
            msg += ". Please provide more details about your preferences."
        else:
            msg = "Please specify a destination for trip planning. Usage: /plan [destination] [date]"

        return CommandResult(
            success=True,
            message=msg
        )

    registry.register(SlashCommand(
        name="plan",
        pattern=r"^/plan(?:\s+(?P<destination>[^\s]+))?(?:\s+(?P<date>[^\s]+))?\s*$",
        handler=handle_plan,
        description="Quick trip planning. Usage: /plan [destination] [date]"
    ))

    # /weather - Query weather
    async def handle_weather(
        conversation_id: str,
        match: re.Match,
        city: Optional[str] = None,
        **kwargs
    ) -> CommandResult:
        if city:
            msg = f"Checking weather for {city}..."
            # In a real implementation, this would call the weather service
            msg += "\n\nWeather integration will be available in Phase 3."
        else:
            msg = "Please specify a city. Usage: /weather [city]"

        return CommandResult(
            success=True,
            message=msg
        )

    registry.register(SlashCommand(
        name="weather",
        pattern=r"^/weather(?:\s+(?P<city>[^\s]+))?\s*$",
        handler=handle_weather,
        description="Query weather. Usage: /weather [city]"
    ))

    # /reset - Reset conversation
    async def handle_reset(
        conversation_id: str,
        match: re.Match,
        **kwargs
    ) -> CommandResult:
        # This would integrate with QueryEngine's reset_conversation
        # For now, return a message indicating the reset
        return CommandResult(
            success=True,
            message="Conversation has been reset. Starting fresh!",
            data={"action": "reset_conversation", "conversation_id": conversation_id}
        )

    registry.register(SlashCommand(
        name="reset",
        pattern=r"^/reset\s*$",
        handler=handle_reset,
        description="Reset the current conversation"
    ))


__all__ = [
    "CommandResult",
    "SlashCommand",
    "SlashCommandRegistry",
    "get_slash_registry",
    "set_slash_registry",
]

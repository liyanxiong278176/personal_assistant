"""Intent routing module

Provides stub registries for Slash commands and Skills.
Will be fully implemented in Phase 2.
"""

from typing import Optional, Callable, Awaitable, Dict, Any
from dataclasses import dataclass


@dataclass
class SlashCommand:
    """Slash command definition."""

    name: str
    description: str
    handler: Callable[..., Awaitable[str]]


@dataclass
class SkillTrigger:
    """Skill trigger definition."""

    name: str
    description: str
    trigger_pattern: str  # Will be regex or keyword pattern in Phase 2
    handler: Callable[..., Awaitable[str]]


# Stub registries - will be populated in Phase 2
_slash_registry: Dict[str, SlashCommand] = {}
_skill_registry: Dict[str, SkillTrigger] = {}


def register_slash(command: SlashCommand) -> None:
    """Register a slash command.

    Args:
        command: SlashCommand instance to register
    """
    _slash_registry[command.name] = command


def register_skill(skill: SkillTrigger) -> None:
    """Register a skill trigger.

    Args:
        skill: SkillTrigger instance to register
    """
    _skill_registry[skill.name] = skill


def get_slash_registry() -> Dict[str, SlashCommand]:
    """Get the slash command registry.

    Returns:
        Dict mapping command names to SlashCommand instances
    """
    return _slash_registry.copy()


def get_skill_registry() -> Dict[str, SkillTrigger]:
    """Get the skill trigger registry.

    Returns:
        Dict mapping skill names to SkillTrigger instances
    """
    return _skill_registry.copy()


def get_slash_command(name: str) -> Optional[SlashCommand]:
    """Get a specific slash command by name.

    Args:
        name: Command name (without the / prefix)

    Returns:
        SlashCommand if found, None otherwise
    """
    return _slash_registry.get(name)


def get_skill(name: str) -> Optional[SkillTrigger]:
    """Get a specific skill by name.

    Args:
        name: Skill name

    Returns:
        SkillTrigger if found, None otherwise
    """
    return _skill_registry.get(name)


__all__ = [
    "SlashCommand",
    "SkillTrigger",
    "register_slash",
    "register_skill",
    "get_slash_registry",
    "get_skill_registry",
    "get_slash_command",
    "get_skill",
]

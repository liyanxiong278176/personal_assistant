"""Intent routing module for Agent Core.

This module provides the first layer of intent routing through:
- Slash commands: Fast command entry points
- Skill triggers: Pattern-based action triggers (Phase 2.3)

The intent routing system is integrated with QueryEngine to provide
quick access to common actions before falling back to LLM processing.
"""

from .commands import (
    CommandResult,
    SlashCommand,
    SlashCommandRegistry,
    get_slash_registry,
    set_slash_registry,
)

from .skills import (
    SkillResult,
    Skill,
    SkillRegistry,
    get_skill_registry,
    set_skill_registry,
)

__all__ = [
    # Slash Commands
    "CommandResult",
    "SlashCommand",
    "SlashCommandRegistry",
    "get_slash_registry",
    "set_slash_registry",
    # Skills
    "SkillResult",
    "Skill",
    "SkillRegistry",
    "get_skill_registry",
    "set_skill_registry",
]

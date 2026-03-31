"""Base agent class with common functionality.

References:
- D-09: Main agent coordinates, subagents execute tasks
- 03-RESEARCH.md: Subagents pattern with structured communication
"""

import logging
from typing import Optional
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class AgentResponse(BaseModel):
    """Structured agent response.

    Per D-11: Agents communicate through structured messages.
    """

    success: bool
    data: dict = {}
    error: Optional[str] = None
    metadata: dict = {}


class BaseAgent:
    """Base class for specialized agents.

    Provides common functionality for all subagents.
    """

    def __init__(self, name: str):
        """Initialize agent.

        Args:
            name: Agent name for logging
        """
        self.name = name
        self.logger = logging.getLogger(f"agent.{name}")

    def _log_request(self, method: str, **kwargs) -> None:
        """Log incoming request."""
        self.logger.info(f"[{self.name}] {method} called with: {kwargs}")

    def _log_response(self, method: str, success: bool, **kwargs) -> None:
        """Log response."""
        status = "SUCCESS" if success else "ERROR"
        self.logger.info(f"[{self.name}] {method} {status}: {kwargs}")

    def _success_response(self, data: dict, metadata: dict = None) -> AgentResponse:
        """Create success response."""
        return AgentResponse(
            success=True,
            data=data,
            metadata=metadata or {}
        )

    def _error_response(self, error: str, data: dict = None) -> AgentResponse:
        """Create error response."""
        return AgentResponse(
            success=False,
            data=data or {},
            error=error
        )

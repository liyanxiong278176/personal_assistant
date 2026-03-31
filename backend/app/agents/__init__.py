"""Multi-agent system for travel planning.

References:
- AI-02: Multi-agent collaboration architecture
- D-08, D-09, D-10: Master-Orchestrator pattern with specialized subagents
"""

from app.agents.base import BaseAgent, AgentResponse
from app.agents.weather_agent import WeatherAgent
from app.agents.map_agent import MapAgent
from app.agents.itinerary_agent import ItineraryAgent

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "WeatherAgent",
    "MapAgent",
    "ItineraryAgent",
]

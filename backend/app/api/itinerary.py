"""Itinerary API endpoints.

References:
- ITIN-01: User inputs destination, dates, preferences -> AI generates detailed daily itinerary
- ITIN-05: User can modify itinerary, AI adjusts based on feedback
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.models import (
    ItineraryCreate, ItineraryResponse, ItineraryDay
)
from app.db.postgres import (
    create_itinerary, get_itinerary, update_itinerary,
    get_conversation_itineraries
)
from app.services.agent_service import itinerary_agent

router = APIRouter(prefix="/api/itineraries", tags=["itineraries"])
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=dict)
async def generate_itinerary(request: ItineraryCreate) -> dict:
    """Generate a new itinerary using AI agent.

    Args:
        request: Itinerary creation request with destination, dates, preferences

    Returns:
        Generated itinerary with daily plans
    """
    try:
        logger.info(f"Generating itinerary for {request.destination}")

        # Generate itinerary using agent
        itinerary_data = await itinerary_agent.generate_itinerary(
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            preferences=request.preferences,
            travelers=request.travelers,
            budget=request.budget,
            conversation_id=str(request.conversation_id)
        )

        # Save to database
        itinerary_id = await create_itinerary(
            conversation_id=request.conversation_id,
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            preferences=request.preferences,
            travelers=request.travelers,
            budget=request.budget,
            days=itinerary_data.get("days", [])
        )

        return {
            "id": str(itinerary_id),
            **itinerary_data
        }

    except Exception as e:
        logger.error(f"Itinerary generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{itinerary_id}", response_model=dict)
async def get_itinerary_by_id(itinerary_id: UUID) -> dict:
    """Get an itinerary by ID.

    Args:
        itinerary_id: Itinerary UUID

    Returns:
        Itinerary details
    """
    itinerary = await get_itinerary(itinerary_id)

    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    return itinerary


@router.get("/conversation/{conversation_id}", response_model=list)
async def list_conversation_itineraries(
    conversation_id: UUID,
    limit: int = 10
) -> list:
    """List all itineraries for a conversation.

    Args:
        conversation_id: Conversation UUID
        limit: Maximum number of itineraries to return

    Returns:
        List of itineraries
    """
    return await get_conversation_itineraries(conversation_id, limit)


@router.post("/{itinerary_id}/refine", response_model=dict)
async def refine_itinerary(
    itinerary_id: UUID,
    feedback: str,
    conversation_id: UUID = None
) -> dict:
    """Refine an existing itinerary based on user feedback.

    Args:
        itinerary_id: Itinerary UUID to refine
        feedback: User's modification request
        conversation_id: Conversation ID for context (optional)

    Returns:
        Updated itinerary
    """
    try:
        logger.info(f"Refining itinerary {itinerary_id}")

        refined = await itinerary_agent.refine_itinerary(
            itinerary_id=itinerary_id,
            feedback=feedback,
            conversation_id=str(conversation_id) if conversation_id else None
        )

        return refined

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Itinerary refinement error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{itinerary_id}", response_model=dict)
async def update_itinerary_manual(
    itinerary_id: UUID,
    days: list[ItineraryDay]
) -> dict:
    """Manually update itinerary days.

    Args:
        itinerary_id: Itinerary UUID
        days: Updated daily plans

    Returns:
        Success confirmation
    """
    success = await update_itinerary(
        itinerary_id,
        [day.model_dump() for day in days]
    )

    if not success:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    return {"success": True, "message": "Itinerary updated"}

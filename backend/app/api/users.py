"""User management and preference API endpoints.

References:
- PERS-01: Store user preferences
- PERS-04: Cross-session preference persistence
- D-01, D-02, D-03: Simplified user system (UUID, no password, localStorage)
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.postgres import create_user, get_user, update_preferences, get_preferences
from app.models import UserResponse, PreferenceCreate, PreferenceResponse
from app.services.preference_service import preference_service

logger = logging.getLogger(__name__)

users_router = APIRouter(prefix="/api/users", tags=["users"])


class ExtractPreferencesRequest(BaseModel):
    """Request to extract preferences from conversation."""

    conversation_text: str = Field(..., min_length=1, max_length=2000)
    auto_confirm: bool = Field(False, description="Auto-confirm low-confidence extractions")


@users_router.post("", response_model=UserResponse)
async def create_new_user() -> dict:
    """Create a new user with auto-generated UUID.

    Per D-01: UUID as user identifier.
    Per D-02: No password required.

    Returns:
        Created user with UUID
    """
    try:
        from datetime import datetime
        user_id = await create_user()
        user = await get_user(user_id)
        return {
            "id": user["id"],
            "created_at": user["created_at"],
            "updated_at": user["updated_at"]
        }
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@users_router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(user_id: str) -> dict:
    """Get a user by ID.

    Args:
        user_id: User UUID

    Returns:
        User information
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user["id"],
        "created_at": user["created_at"],
        "updated_at": user["updated_at"]
    }


@users_router.get("/{user_id}/preferences", response_model=dict)
async def get_user_preferences(user_id: str) -> dict:
    """Get user preferences.

    Args:
        user_id: User UUID

    Returns:
        User preferences
    """
    prefs = await get_preferences(user_id)
    if not prefs:
        raise HTTPException(status_code=404, detail="User not found")
    return prefs


@users_router.put("/{user_id}/preferences")
async def update_user_preferences(
    user_id: str,
    preferences: PreferenceCreate
) -> dict:
    """Update user preferences.

    Per D-07: Supports partial updates (merge with existing).

    Args:
        user_id: User UUID
        preferences: Preferences to update

    Returns:
        Updated preferences
    """
    success = await update_preferences(user_id, preferences.model_dump(exclude_unset=True))
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    updated = await get_preferences(user_id)
    return {
        "user_id": user_id,
        "preferences": updated,
        "updated_at": updated.get("updated_at")
    }


@users_router.post("/{user_id}/preferences/extract")
async def extract_and_sync_preferences(
    user_id: str,
    request: ExtractPreferencesRequest
) -> dict:
    """Extract preferences from conversation and sync to database.

    Per D-07: AI extraction with confirmation for low confidence.

    Args:
        user_id: User UUID
        request: Extraction request with conversation text

    Returns:
        Extraction result with status
    """
    # Get current preferences for context
    current = await get_preferences(user_id)
    if not current:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Extract preferences
        extracted = await preference_service.extract_preferences(
            request.conversation_text,
            current
        )

        # Sync to database
        result = await preference_service.sync_preferences(
            user_id,
            extracted,
            auto_confirm=request.auto_confirm
        )

        return {
            "user_id": user_id,
            **result
        }
    except Exception as e:
        logger.error(f"Failed to extract preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@users_router.get("/health")
async def health_check() -> dict:
    """Health check for users service."""
    return {"status": "healthy", "service": "users"}

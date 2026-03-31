"""FastAPI dependencies for authentication.

Provides dependency injection functions for extracting and validating
JWT tokens from Authorization headers and cookies.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .models import UserInfo
from .service import AuthService, get_auth_service


# Optional auth - returns None if no token provided
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
) -> Optional[UserInfo]:
    """Get current user from Authorization header (optional).

    If no valid token is provided, returns None instead of raising an error.
    Use this for routes that work for both authenticated and anonymous users.

    Args:
        credentials: HTTP Bearer token credentials (optional)
        auth_service: Authentication service instance

    Returns:
        UserInfo if token is valid, None otherwise
    """
    if credentials is None:
        return None

    token = credentials.credentials
    try:
        user = await auth_service.get_current_user(token)
        return user
    except (ValueError, Exception):
        return None


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserInfo:
    """Require authentication - raises 401 if no valid token.

    Use this for routes that require authenticated users.

    Args:
        credentials: HTTP Bearer token credentials
        auth_service: Authentication service instance

    Returns:
        UserInfo for authenticated user

    Raises:
        HTTPException: 401 if no valid token provided
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        user = await auth_service.get_current_user(token)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_refresh_token_jti(
    refresh_jti: Optional[str] = None,
) -> Optional[str]:
    """Get JTI from refresh token cookie.

    The refresh token JTI is stored in an httpOnly cookie
    named 'refresh_jti'. This dependency extracts that value.

    Args:
        refresh_jti: JTI from cookie (injected by FastAPI)

    Returns:
        JTI string if present, None otherwise
    """
    return refresh_jti

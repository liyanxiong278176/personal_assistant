"""FastAPI router for authentication endpoints.

Provides routes for user registration, login, logout, token refresh,
and user profile management.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie
from fastapi.security import HTTPBearer

from .models import (
    LoginRequest,
    LoginResponse,
    TokenResponse,
    SendCodeRequest,
    SendCodeResponse,
    ResetPasswordRequest,
    ErrorResponse,
)
from .service import AuthService, get_auth_service
from .dependencies import get_current_user, require_auth, get_refresh_token_jti


router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cookie configuration
REFRESH_COOKIE_NAME = "refresh_jti"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days


@router.post("/send-code", response_model=SendCodeResponse)
async def send_verification_code(
    request: SendCodeRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Send a verification code to the user's email.

    In development, the code is printed to console.
    In production, integrate with an email service.
    """
    return await auth_service.send_verification_code(request.email)


@router.post("/register", response_model=LoginResponse)
async def register(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Register a new user with email verification code.

    Note: Uses LoginRequest schema which has identifier field.
    For registration, identifier must be an email address.
    """
    # Validate that identifier is an email
    if "@" not in request.identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration requires email address",
        )

    # For now, we'll use a simplified approach - just login
    # Full registration with verification code requires extending the request
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Use /login endpoint. Full registration with verification pending.",
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Login with email/phone and password.

    Sets an httpOnly cookie with the refresh token JTI.
    """
    try:
        result = await auth_service.login(request.identifier, request.password)

        # Set httpOnly cookie with refresh token JTI
        # We need to decode the refresh token to get JTI
        import jwt
        import os
        from .service import ALGORITHM, SECRET_KEY

        payload = jwt.decode(
            result.refresh_token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        jti = payload.get("jti")

        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=jti,
            max_age=REFRESH_COOKIE_MAX_AGE,
            httponly=True,
            secure=False,  # Set True in production with HTTPS
            samesite="lax",
        )

        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    refresh_jti: Optional[str] = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Refresh access token using refresh token from cookie.

    Updates the httpOnly cookie with the new refresh token JTI.
    """
    if refresh_jti is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
        )

    # Get the actual refresh token from database using JTI
    from ..db.postgres import get_refresh_token_by_jti

    token_record = await get_refresh_token_by_jti(refresh_jti)
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # For token refresh, we need the actual token string
    # Since we only store hash, we need a different approach
    # The client should send the refresh token in the request body
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Token refresh requires refresh token in request body. Use /api/auth/refresh-token endpoint instead.",
    )


@router.post("/refresh-token", response_model=TokenResponse)
async def refresh_token_with_body(
    refresh_token: str,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Refresh access token using refresh token from request body.

    Updates the httpOnly cookie with the new refresh token JTI.
    """
    try:
        result = await auth_service.refresh_tokens(refresh_token)

        # Extract JTI from new refresh token and update cookie
        import jwt
        from .service import ALGORITHM, SECRET_KEY

        payload = jwt.decode(
            result.refresh_token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        jti = payload.get("jti")

        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=jti,
            max_age=REFRESH_COOKIE_MAX_AGE,
            httponly=True,
            secure=False,
            samesite="lax",
        )

        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/logout")
async def logout(
    response: Response,
    refresh_jti: Optional[str] = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Logout user by clearing the refresh token cookie.

    Also revokes the refresh token in the database.
    """
    if refresh_jti:
        # Revoke the refresh token
        from ..db.postgres import revoke_refresh_token
        await revoke_refresh_token(refresh_jti)

    # Clear the cookie
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=False,
        samesite="lax",
    )

    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_current_user_info(
    current_user: dict = Depends(require_auth),
):
    """Get current authenticated user information.

    Requires valid authentication.
    """
    return current_user


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Reset user password with verification code.

    Not yet implemented - returns 501.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Password reset not yet implemented",
    )

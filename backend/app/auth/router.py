"""FastAPI router for authentication endpoints.

Provides routes for user registration, login, logout, token refresh,
and user profile management.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie, Body
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from .models import (
    LoginRequest,
    LoginResponse,
    TokenResponse,
    RegisterRequest,
    ErrorResponse,
    UserInfo,
)


class RefreshTokenRequest(BaseModel):
    refresh_token: str
from .service import AuthService, get_auth_service
from .dependencies import get_current_user, require_auth, get_refresh_token_jti


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Cookie configuration
REFRESH_COOKIE_NAME = "refresh_jti"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days


@router.post("/register", response_model=LoginResponse)
async def register(
    request: RegisterRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Register a new user with email and password.

    Simple registration without email verification for development.
    """
    try:
        result = await auth_service.register(
            email=request.email,
            password=request.password,
            username=request.username,
        )

        # Set httpOnly cookie with refresh token JTI
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
            secure=False,  # Set True in production with HTTPS
            samesite="lax",
        )

        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Login with email and password.

    Sets an httpOnly cookie with the refresh token JTI.
    """
    try:
        result = await auth_service.login(request.email, request.password)

        # Set httpOnly cookie with refresh token JTI
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
    request: RefreshTokenRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Refresh access token using refresh token from request body.

    Updates the httpOnly cookie with the new refresh token JTI.
    """
    try:
        result = await auth_service.refresh_tokens(request.refresh_token)

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


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/logout")
async def logout(
    request: Optional[LogoutRequest] = None,
    response: Response = None,
    refresh_jti: Optional[str] = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Logout user by revoking the refresh token.

    Supports both cookie-based and request body refresh tokens.
    """
    jti_to_revoke = None

    # Try to get JTI from request body first
    if request and request.refresh_token:
        import jwt
        from .service import ALGORITHM, SECRET_KEY

        try:
            payload = jwt.decode(
                request.refresh_token,
                SECRET_KEY,
                algorithms=[ALGORITHM]
            )
            jti_to_revoke = payload.get("jti")
        except Exception:
            pass

    # Fall back to cookie
    if not jti_to_revoke and refresh_jti:
        jti_to_revoke = refresh_jti

    # Revoke the refresh token
    if jti_to_revoke:
        from ..db.postgres import revoke_refresh_token
        await revoke_refresh_token(jti_to_revoke)

    # Clear the cookie if response is provided
    if response:
        response.delete_cookie(
            key=REFRESH_COOKIE_NAME,
            httponly=True,
            secure=False,
            samesite="lax",
        )

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: UserInfo = Depends(require_auth),
):
    """Get current authenticated user information.

    Requires valid authentication.
    """
    return current_user

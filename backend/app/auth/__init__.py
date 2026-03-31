"""Authentication module for travel assistant.

Provides user registration, login, token management, and verification codes.
"""

from .models import (
    RegisterRequest,
    LoginRequest,
    LoginResponse,
    TokenResponse,
    SendCodeRequest,
    SendCodeResponse,
    ResetPasswordRequest,
    UserInfo,
    ErrorResponse,
)
from .service import AuthService, get_auth_service
from .dependencies import get_current_user, require_auth, get_refresh_token_jti
from .router import router as auth_router

__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "LoginResponse",
    "TokenResponse",
    "SendCodeRequest",
    "SendCodeResponse",
    "ResetPasswordRequest",
    "UserInfo",
    "ErrorResponse",
    "AuthService",
    "get_auth_service",
    "get_current_user",
    "require_auth",
    "get_refresh_token_jti",
    "auth_router",
]

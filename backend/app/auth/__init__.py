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
]

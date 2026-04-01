"""Pydantic models for authentication requests and responses."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, max_length=100, description="Password (min 6 characters)")
    username: Optional[str] = Field(None, min_length=2, max_length=50, description="Username (optional)")


class LoginRequest(BaseModel):
    """User login request."""

    email: str = Field(..., description="Email address")
    password: str = Field(..., description="User password")


class LoginResponse(BaseModel):
    """Login response with tokens."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration time in seconds")
    user: "UserInfo" = Field(..., description="User information")


class TokenResponse(BaseModel):
    """Token refresh response."""

    access_token: str = Field(..., description="New JWT access token")
    refresh_token: str = Field(..., description="New JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration time in seconds")


class SendCodeRequest(BaseModel):
    """Request to send verification code."""

    email: EmailStr = Field(..., description="Email address to send code to")


class SendCodeResponse(BaseModel):
    """Response for verification code request."""

    message: str = Field(..., description="Success message")
    expires_in: int = Field(..., description="Code expiration time in seconds")


class ResetPasswordRequest(BaseModel):
    """Password reset request."""

    email: EmailStr = Field(..., description="User email")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password")
    verification_code: str = Field(..., min_length=6, max_length=6, description="Verification code")


class UserInfo(BaseModel):
    """User information response."""

    user_id: str = Field(..., description="User unique identifier (UUID)")
    email: Optional[str] = Field(None, description="User email")
    username: Optional[str] = Field(None, description="Username")
    email_verified: bool = Field(default=False, description="Email verification status")
    phone: Optional[str] = Field(None, description="User phone number")
    phone_verified: bool = Field(default=False, description="Phone verification status")
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error details")

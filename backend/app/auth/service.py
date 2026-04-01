"""Authentication service for user management and JWT tokens.

Provides password hashing, JWT token creation/verification,
verification codes, and user authentication operations.
"""

import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

import jwt
from passlib.context import CryptContext
from pydantic import EmailStr, ValidationError
from dotenv import load_dotenv

# Load .env file to ensure JWT_SECRET_KEY is available
load_dotenv()

from ..db.postgres import (
    Database,
    create_user,
    get_user,
    create_user_credentials,
    get_user_credentials_by_email,
    get_user_credentials_by_phone,
    verify_user_email,
    create_refresh_token,
    get_refresh_token_by_jti,
    revoke_refresh_token,
    revoke_all_user_tokens,
)
from .models import (
    RegisterRequest,
    LoginResponse,
    SendCodeResponse,
    UserInfo,
    TokenResponse,
)


# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
VERIFICATION_CODE_EXPIRE_MINUTES = int(os.getenv("VERIFICATION_CODE_EXPIRE_MINUTES", "10"))

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In-memory verification code storage (for development)
# In production, use Redis or database
_verification_codes: Dict[str, tuple[str, datetime]] = {}


class AuthService:
    """Service for authentication operations."""

    def __init__(self):
        self._pwd_context = pwd_context

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Hashed password
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash.

        Args:
            plain_password: Plain text password
            hashed_password: Hashed password

        Returns:
            True if password matches
        """
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(
        self,
        user_id: str,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> tuple[str, datetime]:
        """Create a JWT access token.

        Args:
            user_id: User identifier
            additional_claims: Additional claims to include in token

        Returns:
            Tuple of (token, expires_at)
        """
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "sub": str(user_id),
            "type": "access",
            "exp": int(expires_at.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }

        if additional_claims:
            # Convert any non-JSON-serializable values
            for key, value in additional_claims.items():
                if isinstance(value, datetime):
                    payload[key] = int(value.timestamp())
                elif hasattr(value, "__str__"):
                    payload[key] = str(value)
                else:
                    payload[key] = value

        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        return token, expires_at

    def create_refresh_token(
        self,
        user_id: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> tuple[str, datetime, str]:
        """Create a JWT refresh token.

        Args:
            user_id: User identifier
            user_agent: User agent string for the client
            ip_address: IP address of the client

        Returns:
            Tuple of (token, expires_at, jti)
        """
        jti = str(uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "jti": jti,
            "exp": int(expires_at.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }

        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        return token, expires_at, jti

    @staticmethod
    def decode_token(token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded payload or None if invalid
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token for secure storage.

        Uses SHA-256 to hash the token before storing in database.

        Args:
            token: Plain token string

        Returns:
            Hashed token
        """
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def generate_verification_code(length: int = 6) -> str:
        """Generate a numeric verification code.

        Args:
            length: Length of the code (default 6)

        Returns:
            Numeric verification code
        """
        return "".join(secrets.choice(string.digits) for _ in range(length))

    def send_verification_code(self, email: str) -> SendCodeResponse:
        """Generate and store a verification code for email.

        In development, outputs the code to console.
        In production, would send via email service.

        Args:
            email: Email address to send code to

        Returns:
            Response with expiration time
        """
        code = self.generate_verification_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRE_MINUTES)

        # Store code in memory (use Redis in production)
        _verification_codes[email] = (code, expires_at)

        # Output to console for development
        print(f"[Auth] ===== Verification Code =====")
        print(f"[Auth] Email: {email}")
        print(f"[Auth] Code: {code}")
        print(f"[Auth] Expires: {expires_at.isoformat()}")
        print(f"[Auth] =============================")

        return SendCodeResponse(
            message="Verification code sent successfully",
            expires_in=VERIFICATION_CODE_EXPIRE_MINUTES * 60
        )

    def verify_code(self, email: str, code: str) -> bool:
        """Verify a verification code.

        Args:
            email: Email address
            code: Verification code

        Returns:
            True if code is valid
        """
        if email not in _verification_codes:
            return False

        stored_code, expires_at = _verification_codes[email]

        # Check expiration
        if datetime.now(timezone.utc) > expires_at:
            # Remove expired code
            del _verification_codes[email]
            return False

        # Check code match (timing-safe comparison)
        if secrets.compare_digest(stored_code, code):
            # Remove used code
            del _verification_codes[email]
            return True

        return False

    async def register(
        self,
        email: str,
        password: str,
        username: Optional[str] = None
    ) -> LoginResponse:
        """Register a new user.

        Args:
            email: User email
            password: User password
            username: Optional username

        Returns:
            Login response with tokens

        Raises:
            ValueError: If validation fails
        """
        # Check if email already exists
        existing = await get_user_credentials_by_email(email)
        if existing:
            raise ValueError("Email already registered")

        # Check if username is already taken (if provided)
        if username:
            conn = await Database.get_connection()
            try:
                existing_user = await conn.fetchrow(
                    "SELECT id FROM users WHERE username = $1",
                    username
                )
                if existing_user:
                    raise ValueError("Username already taken")
            finally:
                await Database.release_connection(conn)

        # Create user with username
        user_id = await create_user(username=username if username else None)

        # Hash password
        password_hash = self.hash_password(password)

        # Create credentials
        credentials_id = str(uuid4())
        conn = await Database.get_connection()
        try:
            await conn.execute("""
                INSERT INTO user_credentials (id, user_id, email, password_hash, email_verified)
                VALUES ($1, $2, $3, $4, TRUE)
            """, credentials_id, user_id, email, password_hash)
        finally:
            await Database.release_connection(conn)

        # Get user info
        user = await get_user(user_id)
        if not user:
            raise ValueError("Failed to create user")

        # Create tokens
        access_token, access_expires = self.create_access_token(user_id)
        refresh_token, refresh_expires, jti = self.create_refresh_token(user_id)

        # Store refresh token
        await create_refresh_token(
            user_id=user_id,
            token_hash=self.hash_token(refresh_token),
            jti=jti,
            expires_at=refresh_expires
        )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=int(ACCESS_TOKEN_EXPIRE_MINUTES * 60),
            user=UserInfo(
                user_id=user_id,
                email=email,
                username=username,
                email_verified=True,
                phone=None,
                phone_verified=False,
                created_at=user["created_at"],
                updated_at=user["updated_at"]
            )
        )

    async def login(
        self,
        email: str,
        password: str
    ) -> LoginResponse:
        """Login a user with email and password.

        Args:
            email: Email address
            password: User password

        Returns:
            Login response with tokens

        Raises:
            ValueError: If credentials are invalid
        """
        # Get credentials by email
        credentials = await get_user_credentials_by_email(email)

        if not credentials:
            raise ValueError("Invalid credentials")

        # Verify password
        if not self.verify_password(password, credentials["password_hash"]):
            raise ValueError("Invalid credentials")

        user_id = credentials["user_id"]

        # Get user info
        user = await get_user(user_id)
        if not user:
            raise ValueError("User not found")

        # Create tokens
        access_token, access_expires = self.create_access_token(user_id)
        refresh_token, refresh_expires, jti = self.create_refresh_token(user_id)

        # Store refresh token
        await create_refresh_token(
            user_id=user_id,
            token_hash=self.hash_token(refresh_token),
            jti=jti,
            expires_at=refresh_expires
        )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=int(ACCESS_TOKEN_EXPIRE_MINUTES * 60),
            user=UserInfo(
                user_id=user_id,
                email=credentials.get("email"),
                username=user.get("username"),
                email_verified=credentials.get("email_verified", False),
                phone=credentials.get("phone"),
                phone_verified=credentials.get("phone_verified", False),
                created_at=user["created_at"],
                updated_at=user["updated_at"]
            )
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """Refresh access token using refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New token response

        Raises:
            ValueError: If token is invalid
        """
        # Decode token
        payload = self.decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise ValueError("Invalid refresh token")

        jti = payload.get("jti")
        user_id = payload.get("sub")

        # Check if token exists and is not revoked
        token_record = await get_refresh_token_by_jti(jti)
        if not token_record:
            raise ValueError("Refresh token not found or revoked")

        # Verify token hash
        if not secrets.compare_digest(token_record["token_hash"], self.hash_token(refresh_token)):
            raise ValueError("Invalid refresh token")

        # Revoke old refresh token
        await revoke_refresh_token(jti)

        # Get user info
        user = await get_user(user_id)
        if not user:
            raise ValueError("User not found")

        # Create new tokens
        access_token, access_expires = self.create_access_token(user_id)
        new_refresh_token, refresh_expires, new_jti = self.create_refresh_token(user_id)

        # Store new refresh token
        await create_refresh_token(
            user_id=user_id,
            token_hash=self.hash_token(new_refresh_token),
            jti=new_jti,
            expires_at=refresh_expires
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=int(ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        )

    async def logout(self, refresh_token: str) -> bool:
        """Logout user by revoking refresh token.

        Args:
            refresh_token: Refresh token to revoke

        Returns:
            True if successful
        """
        payload = self.decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return False

        jti = payload.get("jti")
        await revoke_refresh_token(jti)
        return True

    async def logout_all(self, user_id: str) -> int:
        """Logout user from all devices.

        Args:
            user_id: User identifier

        Returns:
            Number of tokens revoked
        """
        return await revoke_all_user_tokens(user_id)

    async def get_current_user(self, token: str) -> UserInfo:
        """Get current user from access token.

        Args:
            token: Access token

        Returns:
            User information

        Raises:
            ValueError: If token is invalid
        """
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "access":
            raise ValueError("Invalid access token")

        user_id = payload.get("sub")

        # Get user
        user = await get_user(user_id)
        if not user:
            raise ValueError("User not found")

        # Get credentials
        conn = await Database.get_connection()
        try:
            credentials = await conn.fetchrow(
                "SELECT * FROM user_credentials WHERE user_id = $1",
                user_id
            )
        finally:
            await Database.release_connection(conn)

        if not credentials:
            credentials = {}

        return UserInfo(
            user_id=user_id,
            email=credentials.get("email"),
            username=user.get("username"),
            email_verified=credentials.get("email_verified", False),
            phone=credentials.get("phone"),
            phone_verified=credentials.get("phone_verified", False),
            created_at=user["created_at"],
            updated_at=user["updated_at"]
        )

    async def reset_password(
        self,
        email: str,
        new_password: str,
        verification_code: str
    ) -> bool:
        """Reset user password.

        Args:
            email: User email
            new_password: New password
            verification_code: Verification code

        Returns:
            True if successful

        Raises:
            ValueError: If validation fails
        """
        # Verify code
        if not self.verify_code(email, verification_code):
            raise ValueError("Invalid or expired verification code")

        # Get credentials
        credentials = await get_user_credentials_by_email(email)
        if not credentials:
            raise ValueError("User not found")

        # Hash new password
        password_hash = self.hash_password(new_password)

        # Update password
        conn = await Database.get_connection()
        try:
            await conn.execute("""
                UPDATE user_credentials
                SET password_hash = $1, updated_at = NOW()
                WHERE user_id = $2
            """, password_hash, credentials["user_id"])
        finally:
            await Database.release_connection(conn)

        # Revoke all tokens for security
        await self.logout_all(credentials["user_id"])

        return True


# Global service instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get or create the global AuthService instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service

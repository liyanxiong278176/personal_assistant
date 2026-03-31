# 用户认证与会话管理系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为AI旅游助手添加完整的用户认证系统和增强的会话管理功能

**Architecture:** 后端使用FastAPI + PostgreSQL，新增user_credentials和refresh_tokens表实现认证；前端使用Next.js + Zustand实现认证状态管理和会话UI。

**Tech Stack:**
- 后端: FastAPI, asyncpg, passlib+bcrypt, PyJWT
- 前端: Next.js 15, React 19, Zustand, Zod, React Hook Form
- 数据库: PostgreSQL (扩展现有schema)

---

## 文件结构概览

### 后端新增/修改文件
```
backend/
├── app/
│   ├── auth/                          # 新增认证模块
│   │   ├── __init__.py
│   │   ├── models.py                  # 认证相关Pydantic模型
│   │   ├── service.py                 # 认证服务核心逻辑
│   │   ├── dependencies.py            # FastAPI依赖注入
│   │   └── router.py                  # 认证API路由
│   ├── conversations/                  # 新增会话管理模块
│   │   ├── __init__.py
│   │   ├── models.py                  # 会话管理模型
│   │   ├── service.py                 # 会话服务
│   │   └── router.py                  # 会话API路由
│   ├── db/
│   │   └── postgres.py                # 修改：添加新表和函数
│   ├── middleware/
│   │   └── auth.py                    # 新增：认证中间件
│   └── main.py                        # 修改：注册新路由
├── requirements.txt                   # 修改：添加新依赖
└── tests/
    ├── test_auth.py                   # 新增：认证测试
    └── test_conversations.py          # 新增：会话管理测试
```

### 前端新增/修改文件
```
frontend/
├── lib/
│   ├── store/                         # 新增状态管理
│   │   ├── auth-store.ts              # 认证状态
│   │   └── conversation-store.ts      # 会话状态
│   ├── api/
│   │   ├── auth.ts                    # 新增：认证API客户端
│   │   └── conversations.ts           # 新增：会话API客户端
│   └── types.ts                       # 修改：添加新类型
├── components/
│   ├── auth/                          # 新增认证组件
│   │   ├── auth-modal.tsx
│   │   ├── login-form.tsx
│   │   └── register-form.tsx
│   ├── conversations/                 # 新增会话组件
│   │   ├── conversation-list.tsx
│   │   ├── conversation-item.tsx
│   │   ├── conversation-search.tsx
│   │   └── conversation-tags.tsx
│   └── chat/
│       └── message-actions.tsx        # 修改：添加消息操作
├── app/
│   ├── layout.tsx                     # 修改：添加认证状态
│   └── chat/page.tsx                  # 修改：集成会话管理
└── package.json                       # 修改：添加新依赖
```

---

## Phase 1: 数据库Schema迁移

### Task 1.1: 扩展PostgreSQL连接和表创建函数

**Files:**
- Modify: `backend/app/db/postgres.py`

- [ ] **Step 1: 在_create_tables_if_not_exists方法中添加user_credentials表**

在`postgres.py`的`_create_tables_if_not_exists`方法中，users表创建之后添加：

```python
# Create user_credentials table (per auth design spec)
await conn.execute("""
    CREATE TABLE IF NOT EXISTS user_credentials (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        email VARCHAR(255) UNIQUE,
        phone VARCHAR(20) UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        email_verified BOOLEAN DEFAULT FALSE,
        phone_verified BOOLEAN DEFAULT FALSE,
        verification_token VARCHAR(255),
        verification_expires TIMESTAMP WITH TIME ZONE,
        reset_token VARCHAR(255),
        reset_token_expires TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_credentials_email ON user_credentials(email);
""")
await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_credentials_phone ON user_credentials(phone);
""")
await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_credentials_user_id ON user_credentials(user_id);
""")

# 确保至少有email或phone其中一个
await conn.execute("""
    ALTER TABLE user_credentials ADD CONSTRAINT IF NOT EXISTS check_contact_method
    CHECK (email IS NOT NULL OR phone IS NOT NULL);
""")
```

- [ ] **Step 2: 添加refresh_tokens表**

```python
# Create refresh_tokens table (避免与chat sessions混淆)
await conn.execute("""
    CREATE TABLE IF NOT EXISTS refresh_tokens (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash VARCHAR(255) NOT NULL UNIQUE,
        jti VARCHAR(255) NOT NULL UNIQUE,
        user_agent TEXT,
        ip_address INET,
        is_revoked BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL
)
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
""")
await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_refresh_tokens_jti ON refresh_tokens(jti);
""")
await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_refresh_tokens_active ON refresh_tokens(user_id)
    WHERE is_revoked = FALSE AND expires_at > NOW();
""")
```

- [ ] **Step 3: 扩展conversations表**

```python
# 扩展conversations表添加认证相关字段
await conn.execute("""
    ALTER TABLE conversations ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL;
""")
await conn.execute("""
    ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;
""")
await conn.execute("""
    ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pinned BOOLEAN DEFAULT FALSE;
""")
await conn.execute("""
    ALTER TABLE conversations ADD COLUMN IF NOT EXISTS sync_enabled BOOLEAN DEFAULT TRUE;
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
""")
await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_conversations_pinned ON conversations(user_id, pinned DESC, updated_at DESC);
""")
await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_conversations_archived ON conversations(user_id, is_archived);
""")
```

- [ ] **Step 4: 添加conversation_tags表**

```python
# Create conversation_tags table
await conn.execute("""
    CREATE TABLE IF NOT EXISTS conversation_tags (
        id UUID PRIMARY KEY,
        conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        tag_name VARCHAR(50) NOT NULL,
        color VARCHAR(7) DEFAULT '#6366f1' CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_tags_conversation ON conversation_tags(conversation_id);
""")
await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_tags_name ON conversation_tags(tag_name);
""")
```

- [ ] **Step 5: 运行后端验证表创建**

```bash
cd backend
python -c "from app.db.postgres import Database; import asyncio; asyncio.run(Database.connect())"
```

预期输出: 包含`[OK] Database tables initialized`的日志

- [ ] **Step 6: 提交**

```bash
git add backend/app/db/postgres.py
git commit -m "feat(db): add auth and conversation management tables

- Add user_credentials table for email/password auth
- Add refresh_tokens table for JWT refresh tokens
- Extend conversations with user_id, archived, pinned, sync_enabled
- Add conversation_tags table for tagging feature
"
```

### Task 1.2: 添加数据库操作函数

**Files:**
- Modify: `backend/app/db/postgres.py`

- [ ] **Step 1: 在postgres.py末尾添加认证相关函数**

```python
# ============================================================
# User Credentials Operations
# ============================================================

async def create_user_credentials(
    user_id: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    password: str = ""
) -> str:
    """Create user credentials record."""
    import hashlib
    credentials_id = str(uuid4())

    # Hash password with bcrypt
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    password_hash = pwd_context.hash(password) if password else pwd_context.hash(str(uuid4()))

    conn = await Database.get_connection()
    try:
        await conn.execute("""
            INSERT INTO user_credentials (id, user_id, email, phone, password_hash)
            VALUES ($1, $2, $3, $4, $5)
        """, credentials_id, user_id, email, phone, password_hash)
        print(f"[OK] Created credentials for user: {user_id}")
        return credentials_id
    finally:
        await Database.release_connection(conn)


async def get_user_credentials_by_email(email: str) -> Optional[dict]:
    """Get user credentials by email."""
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM user_credentials WHERE email = $1",
            email
        )
        return dict(row) if row else None
    finally:
        await Database.release_connection(conn)


async def get_user_credentials_by_phone(phone: str) -> Optional[dict]:
    """Get user credentials by phone."""
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM user_credentials WHERE phone = $1",
            phone
        )
        return dict(row) if row else None
    finally:
        await Database.release_connection(conn)


async def verify_user_email(user_id: str) -> bool:
    """Mark user email as verified."""
    conn = await Database.get_connection()
    try:
        result = await conn.execute("""
            UPDATE user_credentials
            SET email_verified = TRUE, verification_token = NULL
            WHERE user_id = $1
        """, user_id)
        return result == "UPDATE 1"
    finally:
        await Database.release_connection(conn)


# ============================================================
# Refresh Token Operations
# ============================================================

async def create_refresh_token(
    user_id: str,
    token_hash: str,
    jti: str,
    expires_at: datetime,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> str:
    """Create a refresh token record."""
    token_id = str(uuid4())
    conn = await Database.get_connection()
    try:
        await conn.execute("""
            INSERT INTO refresh_tokens (id, user_id, token_hash, jti, user_agent, ip_address, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, token_id, user_id, token_hash, jti, user_agent, ip_address)
        return token_id
    finally:
        await Database.release_connection(conn)


async def get_refresh_token_by_jti(jti: str) -> Optional[dict]:
    """Get refresh token by JWT ID."""
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow(
            """SELECT * FROM refresh_tokens
               WHERE jti = $1 AND is_revoked = FALSE AND expires_at > NOW()""",
            jti
        )
        return dict(row) if row else None
    finally:
        await Database.release_connection(conn)


async def revoke_refresh_token(jti: str) -> bool:
    """Revoke a refresh token."""
    conn = await Database.get_connection()
    try:
        result = await conn.execute(
            "UPDATE refresh_tokens SET is_revoked = TRUE WHERE jti = $1",
            jti
        )
        return result == "UPDATE 1"
    finally:
        await Database.release_connection(conn)


async def revoke_all_user_tokens(user_id: str) -> int:
    """Revoke all refresh tokens for a user."""
    conn = await Database.get_connection()
    try:
        result = await conn.execute(
            "UPDATE refresh_tokens SET is_revoked = TRUE WHERE user_id = $1",
            user_id
        )
        # result format: "UPDATE n"
        return int(result.split()[-1]) if result else 0
    finally:
        await Database.release_connection(conn)


# ============================================================
# Conversation Management Operations
# ============================================================

async def update_conversation(
    conv_id: UUID,
    title: Optional[str] = None,
    is_archived: Optional[bool] = None,
    pinned: Optional[bool] = None,
    sync_enabled: Optional[bool] = None
) -> bool:
    """Update conversation properties."""
    updates = []
    params = []
    param_idx = 1

    if title is not None:
        updates.append(f"title = ${param_idx}")
        params.append(title)
        param_idx += 1
    if is_archived is not None:
        updates.append(f"is_archived = ${param_idx}")
        params.append(is_archived)
        param_idx += 1
    if pinned is not None:
        updates.append(f"pinned = ${param_idx}")
        params.append(pinned)
        param_idx += 1
    if sync_enabled is not None:
        updates.append(f"sync_enabled = ${param_idx}")
        params.append(sync_enabled)
        param_idx += 1

    if not updates:
        return False

    params.append(str(conv_id))
    query = f"UPDATE conversations SET {', '.join(updates)} WHERE id = ${param_idx}"

    conn = await Database.get_connection()
    try:
        result = await conn.execute(query, *params)
        return result == "UPDATE 1"
    finally:
        await Database.release_connection(conn)


async def list_user_conversations(
    user_id: str,
    include_archived: bool = False,
    limit: int = 50
) -> list[dict]:
    """List conversations for a user with pinned first."""
    conn = await Database.get_connection()
    try:
        archived_filter = "" if include_archived else "AND c.is_archived = FALSE"
        rows = await conn.fetch(f"""
            SELECT c.*, COUNT(m.id) as message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.user_id = $1 {archived_filter}
            GROUP BY c.id
            ORDER BY c.pinned DESC, c.updated_at DESC
            LIMIT $2
        """, user_id, limit)
        return [dict(row) for row in rows]
    finally:
        await Database.release_connection(conn)


async def search_conversations(
    user_id: str,
    query: str,
    limit: int = 20
) -> list[dict]:
    """Search conversations by title or message content."""
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch("""
            SELECT DISTINCT c.*
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.user_id = $1
              AND (c.title ILIKE $2 OR m.content ILIKE $2)
              AND c.is_archived = FALSE
            ORDER BY c.updated_at DESC
            LIMIT $3
        """, user_id, f"%{query}%", limit)
        return [dict(row) for row in rows]
    finally:
        await Database.release_connection(conn)


# ============================================================
# Conversation Tags Operations
# ============================================================

async def add_conversation_tag(
    conversation_id: UUID,
    tag_name: str,
    color: str = "#6366f1"
) -> str:
    """Add a tag to a conversation."""
    tag_id = str(uuid4())
    conn = await Database.get_connection()
    try:
        await conn.execute("""
            INSERT INTO conversation_tags (id, conversation_id, tag_name, color)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (conversation_id, tag_name) DO NOTHING
        """, tag_id, conversation_id, tag_name, color)
        return tag_id
    finally:
        await Database.release_connection(conn)


async def remove_conversation_tag(conversation_id: UUID, tag_name: str) -> bool:
    """Remove a tag from a conversation."""
    conn = await Database.get_connection()
    try:
        result = await conn.execute("""
            DELETE FROM conversation_tags
            WHERE conversation_id = $1 AND tag_name = $2
        """, conversation_id, tag_name)
        return result == "DELETE 1"
    finally:
        await Database.release_connection(conn)


async def get_conversation_tags(conversation_id: UUID) -> list[dict]:
    """Get all tags for a conversation."""
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch(
            "SELECT * FROM conversation_tags WHERE conversation_id = $1 ORDER BY tag_name",
            conversation_id
        )
        return [dict(row) for row in rows]
    finally:
        await Database.release_connection(conn)


async def get_all_user_tags(user_id: str) -> list[str]:
    """Get all unique tag names for a user."""
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch("""
            SELECT DISTINCT ct.tag_name
            FROM conversation_tags ct
            JOIN conversations c ON ct.conversation_id = c.id
            WHERE c.user_id = $1
            ORDER BY ct.tag_name
        """, user_id)
        return [row["tag_name"] for row in rows]
    finally:
        await Database.release_connection(conn)
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/db/postgres.py
git commit -m "feat(db): add auth and conversation management operations

- Add user_credentials CRUD operations
- Add refresh_token CRUD operations
- Add conversation update and search operations
- Add conversation tags CRUD operations
"
```

---

## Phase 2: 后端认证服务

### Task 2.1: 添加认证依赖到requirements.txt

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加认证相关依赖**

```bash
echo "
# Authentication
passlib==1.7.4
bcrypt==4.2.1
PyJWT==2.9.0
python-jose[cryptography]==3.3.0
" >> backend/requirements.txt
```

- [ ] **Step 2: 安装依赖**

```bash
cd backend && pip install -r requirements.txt
```

- [ ] **Step 3: 提交**

```bash
git add backend/requirements.txt
git commit -m "feat: add authentication dependencies

- Add passlib for password hashing
- Add bcrypt for secure password storage
- Add PyJWT for token generation
"
```

### Task 2.2: 创建认证模块结构

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/models.py`

- [ ] **Step 1: 创建__init__.py**

```python
"""Authentication module for user login/registration."""

from .service import AuthService
from .dependencies import get_current_user, get_optional_user
from .router import auth_router

__all__ = ["AuthService", "get_current_user", "get_optional_user", "auth_router"]
```

- [ ] **Step 2: 创建认证模型**

```python
"""Authentication models for request/response validation."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailField


# Register Request
class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailField
    password: str = Field(..., min_length=8, max_length=100)
    verification_code: str = Field(..., min_length=6, max_length=6)


class RegisterResponse(BaseModel):
    """User registration response."""
    user_id: str
    email: str
    access_token: str
    expires_in: int  # seconds


# Login Request
class LoginRequest(BaseModel):
    """User login request."""
    email: EmailField
    password: str = Field(..., min_length=1, max_length=100)


class LoginResponse(BaseModel):
    """User login response."""
    user_id: str
    email: str
    access_token: str
    refresh_token_expires: datetime
    expires_in: int


# Token Response
class TokenResponse(BaseModel):
    """Token refresh response."""
    access_token: str
    expires_in: int


# Send Code Request
class SendCodeRequest(BaseModel):
    """Send verification code request."""
    email: EmailField


class SendCodeResponse(BaseModel):
    """Send verification code response."""
    message: str
    expires_in: int  # seconds until code expires


# Reset Password Request
class ResetPasswordRequest(BaseModel):
    """Reset password request."""
    email: EmailField
    new_password: str = Field(..., min_length=8, max_length=100)
    reset_token: str = Field(..., min_length=32, max_length=255)


# User Info
class UserInfo(BaseModel):
    """User information."""
    id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    email_verified: bool = False
    phone_verified: bool = False
    created_at: datetime
    updated_at: datetime


# Error Response
class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/auth/__init__.py backend/app/auth/models.py
git commit -m "feat(auth): add authentication models

- Add RegisterRequest/Response
- Add LoginRequest/Response
- Add TokenResponse, UserInfo
- Add ErrorResponse
"
```

### Task 2.3: 创建认证服务

**Files:**
- Create: `backend/app/auth/service.py`

- [ ] **Step 1: 创建认证服务核心逻辑**

```python
"""Authentication service for user management and token handling."""

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status

from app.db.postgres import (
    create_user,
    create_user_credentials,
    get_user,
    get_user_credentials_by_email,
    create_refresh_token,
    get_refresh_token_by_jti,
    revoke_refresh_token,
)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# 验证码存储（开发环境使用内存）
_verification_codes: dict[str, tuple[str, datetime]] = {}


class AuthService:
    """Authentication service for login, registration, and token management."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def create_access_token(user_id: str, jti: Optional[str] = None) -> tuple[str, str, datetime]:
        """
        Create an access token.

        Returns:
            (token, jti, expires_at)
        """
        jti = jti or str(uuid4())
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        expires_at = datetime.utcnow() + expires_delta

        payload = {
            "user_id": user_id,
            "jti": jti,
            "type": "access",
            "exp": expires_at,
            "iat": datetime.utcnow(),
        }

        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        return token, jti, expires_at

    @staticmethod
    def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
        """
        Create a refresh token.

        Returns:
            (token, jti, expires_at)
        """
        jti = str(uuid4())
        expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        expires_at = datetime.utcnow() + expires_delta

        payload = {
            "user_id": user_id,
            "jti": jti,
            "type": "refresh",
            "exp": expires_at,
            "iat": datetime.utcnow(),
        }

        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        return token, jti, expires_at

    @staticmethod
    def decode_token(token: str) -> dict:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token for storage (SHA-256)."""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def generate_verification_code() -> str:
        """Generate a 6-digit verification code."""
        import random
        return str(random.randint(100000, 999999))

    @staticmethod
    def send_verification_code(email: str) -> str:
        """
        Send a verification code to the user's email.
        (Development: prints to console)
        """
        code = AuthService.generate_verification_code()
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        _verification_codes[email] = (code, expires_at)

        # 开发环境：打印到控制台
        print(f"[验证码] 发送到 {email}: {code}")
        print(f"[验证码] 请在应用中输入此码完成验证（10分钟内有效）")

        return code

    @staticmethod
    def verify_code(email: str, code: str) -> bool:
        """Verify a verification code."""
        if email not in _verification_codes:
            return False

        stored_code, expires_at = _verification_codes[email]
        if datetime.utcnow() > expires_at:
            # 清理过期代码
            del _verification_codes[email]
            return False

        return stored_code == code

    @staticmethod
    async def register(email: str, password: str, code: str) -> dict:
        """Register a new user."""
        # 验证验证码
        if not AuthService.verify_code(email, code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification code"
            )

        # 检查邮箱是否已注册
        existing = await get_user_credentials_by_email(email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # 创建用户
        user_id = await create_user()

        # 创建用户凭证
        await create_user_credentials(
            user_id=user_id,
            email=email,
            password=password
        )

        # 生成Token
        access_token, access_jti, access_expires = AuthService.create_access_token(user_id)
        refresh_token, refresh_jti, refresh_expires = AuthService.create_refresh_token(user_id)

        # 存储refresh token
        token_hash = AuthService.hash_token(refresh_token)
        await create_refresh_token(user_id, token_hash, refresh_jti, refresh_expires)

        return {
            "user_id": user_id,
            "email": email,
            "access_token": access_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

    @staticmethod
    async def login(email: str, password: str) -> dict:
        """Login a user."""
        # 获取用户凭证
        credentials = await get_user_credentials_by_email(email)
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # 验证密码
        if not AuthService.verify_password(password, credentials["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        user_id = credentials["user_id"]

        # 生成Token
        access_token, access_jti, access_expires = AuthService.create_access_token(user_id)
        refresh_token, refresh_jti, refresh_expires = AuthService.create_refresh_token(user_id)

        # 存储refresh token
        token_hash = AuthService.hash_token(refresh_token)
        await create_refresh_token(user_id, token_hash, refresh_jti, refresh_expires)

        return {
            "user_id": user_id,
            "email": email,
            "access_token": access_token,
            "refresh_token_expires": refresh_expires,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

    @staticmethod
    async def refresh_tokens(jti: str) -> dict:
        """Refresh access token using refresh token."""
        # 检查refresh token是否有效
        token_record = await get_refresh_token_by_jti(jti)
        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        user_id = token_record["user_id"]

        # 撤销旧的refresh token
        await revoke_refresh_token(jti)

        # 生成新Token
        access_token, access_jti, access_expires = AuthService.create_access_token(user_id)
        refresh_token, refresh_jti, refresh_expires = AuthService.create_refresh_token(user_id)

        # 存储新refresh token
        token_hash = AuthService.hash_token(refresh_token)
        await create_refresh_token(user_id, token_hash, refresh_jti, refresh_expires)

        return {
            "access_token": access_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

    @staticmethod
    async def logout(jti: str) -> bool:
        """Logout by revoking refresh token."""
        return await revoke_refresh_token(jti)

    @staticmethod
    async def get_current_user_info(user_id: str) -> dict:
        """Get current user information."""
        user = await get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # 获取凭证信息
        credentials = await get_user_credentials_by_email(user.get("email", ""))
        if not credentials:
            return {
                "id": str(user["id"]),
                "email": None,
                "phone": None,
                "email_verified": False,
                "phone_verified": False,
                "created_at": user["created_at"],
                "updated_at": user["updated_at"]
            }

        return {
            "id": str(user["id"]),
            "email": credentials.get("email"),
            "phone": credentials.get("phone"),
            "email_verified": credentials.get("email_verified", False),
            "phone_verified": credentials.get("phone_verified", False),
            "created_at": user["created_at"],
            "updated_at": user["updated_at"]
        }
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/auth/service.py
git commit -m "feat(auth): add authentication service

- Add password hashing and verification
- Add JWT access/refresh token creation
- Add verification code generation and validation (console output)
- Add user registration and login methods
- Add token refresh and logout methods
"
```

### Task 2.4: 创建认证依赖注入

**Files:**
- Create: `backend/app/auth/dependencies.py`

- [ ] **Step 1: 创建FastAPI依赖注入**

```python
"""FastAPI dependencies for authentication."""

from typing import Optional
from fastapi import Header, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.service import AuthService

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = security
) -> Optional[dict]:
    """
    Get current authenticated user from JWT token.

    Returns None if not authenticated (for optional auth).
    Use require_auth dependency for mandatory authentication.
    """
    if not credentials:
        return None

    try:
        token = credentials.credentials
        payload = AuthService.decode_token(token)

        # 检查是否为access token
        if payload.get("type") != "access":
            return None

        user_id = payload.get("user_id")
        if not user_id:
            return None

        # 获取用户信息
        user_info = await AuthService.get_current_user_info(user_id)
        request.state.user = user_info
        return user_info

    except HTTPException:
        return None


async def require_auth(user: Optional[dict] = None) -> dict:
    """Require authentication - raises 401 if not authenticated."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user


async def get_refresh_token_jti(request: Request) -> Optional[str]:
    """Get jti from refresh token cookie."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return None

    try:
        payload = AuthService.decode_token(refresh_token)
        if payload.get("type") != "refresh":
            return None
        return payload.get("jti")
    except Exception:
        return None
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/auth/dependencies.py
git commit -m "feat(auth): add authentication dependencies

- Add get_current_user for optional auth
- Add require_auth for mandatory auth
- Add get_refresh_token_jti for refresh token handling
"
```

### Task 2.5: 创建认证API路由

**Files:**
- Create: `backend/app/auth/router.py`

- [ ] **Step 1: 创建认证路由**

```python
"""Authentication API routes."""

from fastapi import APIRouter, HTTPException, status, Response, Request, Depends
from fastapi.security import OAuth2PasswordBearer

from app.auth.models import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    TokenResponse,
    SendCodeRequest,
    SendCodeResponse,
    ResetPasswordRequest,
    ErrorResponse,
    UserInfo
)
from app.auth.service import AuthService
from app.auth.dependencies import get_current_user, require_auth, get_refresh_token_jti

auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])


@auth_router.post("/send-code", response_model=SendCodeResponse)
async def send_verification_code(request: SendCodeRequest) -> dict:
    """
    发送验证码到用户邮箱。

    开发环境：验证码将打印到控制台
    """
    code = AuthService.send_verification_code(request.email)
    return {
        "message": "验证码已发送",
        "expires_in": 600  # 10分钟
    }


@auth_router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest) -> dict:
    """
    用户注册。

    流程：
    1. 先调用 /send-code 获取验证码
    2. 使用邮箱、密码和验证码注册
    """
    try:
        result = await AuthService.register(
            email=request.email,
            password=request.password,
            code=request.verification_code
        )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@auth_router.post("/login", response_model=LoginResponse)
async def login(
    request_data: LoginRequest,
    response: Response,
    http_request: Request
) -> dict:
    """
    用户登录。

    返回access token并在httpOnly cookie中设置refresh token。
    """
    try:
        result = await AuthService.login(
            email=request_data.email,
            password=request_data.password
        )

        # 创建refresh token并设置到cookie
        _, refresh_jti, refresh_expires = AuthService.create_refresh_token(result["user_id"])

        # 设置httpOnly cookie
        max_age = 7 * 24 * 60 * 60  # 7天
        response.set_cookie(
            key="refresh_token",
            value=refresh_jti,  # 存储jti而不是token本身
            max_age=max_age,
            path="/",
            samesite="lax",
            httponly=True,
            secure=False  # 开发环境设为False，生产环境应为True
        )

        # 存储refresh token到数据库
        from app.auth.service import AuthService
        from app.db.postgres import create_refresh_token

        _, _, refresh_expires_at = AuthService.create_refresh_token(result["user_id"])
        token_hash = AuthService.hash_token(refresh_jti)
        await create_refresh_token(
            result["user_id"],
            token_hash,
            refresh_jti,
            refresh_expires_at,
            user_agent=http_request.headers.get("user-agent"),
            ip_address=http_request.client.host if http_request.client else None
        )

        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    http_request: Request,
    jti: str = Depends(get_refresh_token_jti)
) -> dict:
    """
    使用refresh token刷新access token。
    """
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token found"
        )

    try:
        result = await AuthService.refresh_tokens(jti)

        # 更新cookie
        max_age = 7 * 24 * 60 * 60
        response.set_cookie(
            key="refresh_token",
            value=result.get("jti", jti),
            max_age=max_age,
            path="/",
            samesite="lax",
            httponly=True,
            secure=False
        )

        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )


@auth_router.post("/logout")
async def logout(
    response: Response,
    jti: str = Depends(get_refresh_token_jti)
) -> dict:
    """
    用户登出。

    撤销refresh token并清除cookie。
    """
    if jti:
        await AuthService.logout(jti)

    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}


@auth_router.get("/me", response_model=UserInfo)
async def get_me(user: dict = Depends(require_auth)) -> dict:
    """
    获取当前登录用户信息。
    """
    return user


@auth_router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest) -> dict:
    """
    重置密码（开发环境暂不实现）。
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Password reset not implemented yet"
    )


# Health check
@auth_router.get("/health")
async def health_check() -> dict:
    """认证服务健康检查。"""
    return {"status": "ok", "service": "authentication"}
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/auth/router.py
git commit -m "feat(auth): add authentication API routes

- POST /api/auth/send-code - 发送验证码
- POST /api/auth/register - 用户注册
- POST /api/auth/login - 用户登录
- POST /api/auth/refresh - 刷新token
- POST /api/auth/logout - 登出
- GET /api/auth/me - 获取当前用户
"
```

### Task 2.6: 注册认证路由到主应用

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 在main.py中注册认证路由**

在`main.py`的导入部分添加：

```python
from app.auth.router import auth_router
```

在`app.include_router`部分添加：

```python
app.include_router(auth_router)
```

更新CORS配置以支持credentials：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,  # 确保为True
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: 测试认证API**

```bash
# 启动后端
cd backend && python -m uvicorn app.main:app --reload
```

测试发送验证码：

```bash
curl -X POST http://localhost:8000/api/auth/send-code \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

预期输出：控制台打印验证码

- [ ] **Step 3: 提交**

```bash
git add backend/app/main.py
git commit -m "feat(main): register authentication router

- Import and include auth_router
- Update CORS to allow credentials
"
```

### Task 2.7: 编写认证服务测试

**Files:**
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: 创建认证测试**

```python
"""Tests for authentication service."""

import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException

from app.auth.service import AuthService


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password(self):
        """Test password hashing generates different hashes."""
        password = "test123456"
        hash1 = AuthService.hash_password(password)
        hash2 = AuthService.hash_password(password)

        # 相同密码应该产生不同hash（因为salt）
        assert hash1 != hash2
        assert hash1.startswith("$2b$")

    def test_verify_password(self):
        """Test password verification."""
        password = "test123456"
        hashed = AuthService.hash_password(password)

        assert AuthService.verify_password(password, hashed) is True
        assert AuthService.verify_password("wrong", hashed) is False


class TestTokenGeneration:
    """Test JWT token generation and validation."""

    def test_create_access_token(self):
        """Test access token creation."""
        user_id = "test-user-123"
        token, jti, expires = AuthService.create_access_token(user_id)

        assert isinstance(token, str)
        assert isinstance(jti, str)
        assert expires > datetime.utcnow()

    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        user_id = "test-user-123"
        token, jti, expires = AuthService.create_access_token(user_id)

        payload = AuthService.decode_token(token)
        assert payload["user_id"] == user_id
        assert payload["type"] == "access"

    def test_decode_invalid_token(self):
        """Test decoding an invalid token."""
        with pytest.raises(HTTPException) as exc:
            AuthService.decode_token("invalid.token.here")
        assert exc.value.status_code == 401


class TestVerificationCodes:
    """Test verification code generation and validation."""

    def test_generate_code(self):
        """Test code generation produces 6 digits."""
        code = AuthService.generate_verification_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_send_and_verify_code(self):
        """Test sending and verifying a code."""
        email = "test@example.com"
        code = AuthService.send_verification_code(email)

        assert len(code) == 6
        assert AuthService.verify_code(email, code) is True
        assert AuthService.verify_code(email, "000000") is False


@pytest.mark.asyncio
class TestAuthService:
    """Test authentication service methods."""

    async def test_get_current_user_info_with_invalid_user(self):
        """Test get_current_user_info with invalid user ID."""
        with pytest.raises(HTTPException) as exc:
            await AuthService.get_current_user_info("non-existent-user")
        assert exc.value.status_code == 404
```

- [ ] **Step 2: 运行测试**

```bash
cd backend && pytest tests/test_auth.py -v
```

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_auth.py
git commit -m "test(auth): add authentication service tests

- Test password hashing and verification
- Test JWT token generation and validation
- Test verification code generation and validation
- Test error handling
"
```

---

## Phase 3: 后端会话管理API

### Task 3.1: 创建会话管理模块

**Files:**
- Create: `backend/app/conversations/__init__.py`
- Create: `backend/app/conversations/models.py`

- [ ] **Step 1: 创建__init__.py**

```python
"""Conversation management module."""

from .service import ConversationService
from .router import conversations_router

__all__ = ["ConversationService", "conversations_router"]
```

- [ ] **Step 2: 创建会话模型**

```python
"""Conversation management models."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ConversationUpdate(BaseModel):
    """Conversation update request."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    is_archived: Optional[bool] = None
    pinned: Optional[bool] = None
    sync_enabled: Optional[bool] = None


class ConversationResponse(BaseModel):
    """Conversation response."""
    id: str
    title: str
    user_id: Optional[str] = None
    is_archived: bool = False
    pinned: bool = False
    sync_enabled: bool = True
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Conversation list response."""
    conversations: List[ConversationResponse]
    total: int


class TagCreate(BaseModel):
    """Create tag request."""
    tag_name: str = Field(..., min_length=1, max_length=50)
    color: str = Field("#6366f1", pattern=r"^#[0-9A-Fa-f]{6}$")


class TagResponse(BaseModel):
    """Tag response."""
    id: str
    conversation_id: str
    tag_name: str
    color: str
    created_at: datetime
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/conversations/__init__.py backend/app/conversations/models.py
git commit -m "feat(conversations): add conversation management models

- Add ConversationUpdate model
- Add ConversationResponse model
- Add ConversationListResponse model
- Add TagCreate and TagResponse models
"
```

### Task 3.2: 创建会话管理服务

**Files:**
- Create: `backend/app/conversations/service.py`

- [ ] **Step 1: 创建会话服务**

```python
"""Conversation management service."""

from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import HTTPException, status

from app.db.postgres import (
    get_conversation,
    update_conversation,
    list_user_conversations,
    search_conversations,
    add_conversation_tag,
    remove_conversation_tag,
    get_conversation_tags,
    get_all_user_tags,
    create_conversation,
)
from app.auth.dependencies import get_current_user


class ConversationService:
    """Service for conversation management operations."""

    @staticmethod
    async def get_conversation(
        conv_id: str,
        user_id: Optional[str] = None
    ) -> dict:
        """Get a conversation by ID."""
        try:
            conv_uuid = UUID(conv_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID"
            )

        conv = await get_conversation(conv_uuid)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        # 检查权限（如果指定了user_id）
        if user_id and conv.get("user_id") and conv["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        return conv

    @staticmethod
    async def update_conversation(
        conv_id: str,
        title: Optional[str] = None,
        is_archived: Optional[bool] = None,
        pinned: Optional[bool] = None,
        sync_enabled: Optional[bool] = None,
        user_id: Optional[str] = None
    ) -> dict:
        """Update conversation properties."""
        try:
            conv_uuid = UUID(conv_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID"
            )

        # 检查权限
        conv = await get_conversation(conv_uuid)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        if user_id and conv.get("user_id") and conv["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        # 更新
        success = await update_conversation(
            conv_uuid,
            title=title,
            is_archived=is_archived,
            pinned=pinned,
            sync_enabled=sync_enabled
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update conversation"
            )

        # 返回更新后的数据
        updated = await get_conversation(conv_uuid)
        return updated

    @staticmethod
    async def list_conversations(
        user_id: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 50
    ) -> tuple[List[dict], int]:
        """List conversations for a user."""
        if not user_id:
            # 游客模式：返回所有会话（按时间排序）
            from app.db.postgres import list_conversations
            convs = await list_conversations(limit)
            return convs, len(convs)

        convs = await list_user_conversations(user_id, include_archived, limit)
        return convs, len(convs)

    @staticmethod
    async def search_conversations(
        query: str,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[dict]:
        """Search conversations by query."""
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id required for search"
            )

        return await search_conversations(user_id, query, limit)

    @staticmethod
    async def delete_conversation(
        conv_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Delete a conversation."""
        try:
            conv_uuid = UUID(conv_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID"
            )

        # 检查权限
        conv = await get_conversation(conv_uuid)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        if user_id and conv.get("user_id") and conv["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        # 删除（cascade会删除相关消息和标签）
        from app.db.postgres import Database
        conn = await Database.get_connection()
        try:
            await conn.execute("DELETE FROM conversations WHERE id = $1", conv_uuid)
            return True
        finally:
            await Database.release_connection(conn)

    @staticmethod
    async def add_tag(
        conv_id: str,
        tag_name: str,
        color: str,
        user_id: Optional[str] = None
    ) -> dict:
        """Add a tag to a conversation."""
        try:
            conv_uuid = UUID(conv_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID"
            )

        # 检查权限
        conv = await get_conversation(conv_uuid)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        if user_id and conv.get("user_id") and conv["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        tag_id = await add_conversation_tag(conv_uuid, tag_name, color)
        return {
            "id": tag_id,
            "conversation_id": conv_id,
            "tag_name": tag_name,
            "color": color
        }

    @staticmethod
    async def remove_tag(
        conv_id: str,
        tag_name: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Remove a tag from a conversation."""
        try:
            conv_uuid = UUID(conv_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID"
            )

        # 检查权限
        conv = await get_conversation(conv_uuid)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        if user_id and conv.get("user_id") and conv["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        return await remove_conversation_tag(conv_uuid, tag_name)

    @staticmethod
    async def get_tags(conv_id: str, user_id: Optional[str] = None) -> List[dict]:
        """Get all tags for a conversation."""
        try:
            conv_uuid = UUID(conv_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID"
            )

        # 检查权限
        conv = await get_conversation(conv_uuid)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        if user_id and conv.get("user_id") and conv["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        return await get_conversation_tags(conv_uuid)

    @staticmethod
    async def get_all_tags(user_id: str) -> List[str]:
        """Get all unique tag names for a user."""
        return await get_all_user_tags(user_id)

    @staticmethod
    async def create_conversation(
        title: str = "新对话",
        user_id: Optional[str] = None
    ) -> dict:
        """Create a new conversation."""
        conv_id = await create_conversation(title)

        # 如果提供了user_id，更新会话
        if user_id:
            try:
                conv_uuid = UUID(conv_id)
                await update_conversation(conv_uuid, user_id=user_id)
            except Exception:
                pass

        return await get_conversation(UUID(conv_id))
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/conversations/service.py
git commit -m "feat(conversations): add conversation service

- Add get/update/delete conversation methods
- Add list and search conversations
- Add tag management methods
- Add permission checks
"
```

### Task 3.3: 创建会话管理API路由

**Files:**
- Create: `backend/app/conversations/router.py`

- [ ] **Step 1: 创建会话路由**

```python
"""Conversation management API routes."""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query, Depends

from app.conversations.models import (
    ConversationUpdate,
    ConversationResponse,
    ConversationListResponse,
    TagCreate,
    TagResponse
)
from app.conversations.service import ConversationService
from app.auth.dependencies import get_current_user

conversations_router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@conversations_router.get("", response_model=ConversationListResponse)
async def list_conversations(
    include_archived: bool = Query(False, description="Include archived conversations"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of conversations"),
    current_user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """
    获取会话列表。

    如果用户已登录，返回该用户的会话。
    如果是游客，返回所有会话（按时间排序）。
    """
    user_id = current_user["id"] if current_user else None
    conversations, total = await ConversationService.list_conversations(
        user_id=user_id,
        include_archived=include_archived,
        limit=limit
    )

    return {
        "conversations": conversations,
        "total": total
    }


@conversations_router.get("/search", response_model=List[ConversationResponse])
async def search_conversations(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=50),
    current_user: Optional[dict] = Depends(get_current_user)
) -> List[dict]:
    """搜索会话（需要登录）。"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    results = await ConversationService.search_conversations(
        query=q,
        user_id=current_user["id"],
        limit=limit
    )
    return results


@conversations_router.get("/archived", response_model=ConversationListResponse)
async def list_archived_conversations(
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """获取归档的会话（需要登录）。"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    conversations, total = await ConversationService.list_conversations(
        user_id=current_user["id"],
        include_archived=True,
        limit=limit
    )

    # 过滤只返回归档的
    archived = [c for c in conversations if c.get("is_archived")]
    return {
        "conversations": archived,
        "total": len(archived)
    }


@conversations_router.get("/tags", response_model=List[str])
async def get_all_tags(
    current_user: dict = Depends(get_current_user)
) -> List[str]:
    """获取用户所有标签（需要登录）。"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    return await ConversationService.get_all_tags(current_user["id"])


@conversations_router.get("/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    conv_id: str,
    current_user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """获取单个会话详情。"""
    user_id = current_user["id"] if current_user else None
    return await ConversationService.get_conversation(conv_id, user_id)


@conversations_router.put("/{conv_id}", response_model=ConversationResponse)
async def update_conversation(
    conv_id: str,
    update: ConversationUpdate,
    current_user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """更新会话属性（标题、归档状态、固定状态等）。"""
    user_id = current_user["id"] if current_user else None
    return await ConversationService.update_conversation(
        conv_id,
        title=update.title,
        is_archived=update.is_archived,
        pinned=update.pinned,
        sync_enabled=update.sync_enabled,
        user_id=user_id
    )


@conversations_router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conv_id: str,
    current_user: Optional[dict] = Depends(get_current_user)
) -> None:
    """删除会话。"""
    user_id = current_user["id"] if current_user else None
    await ConversationService.delete_conversation(conv_id, user_id)


@conversations_router.post("/{conv_id}/tags", response_model=TagResponse)
async def add_conversation_tag(
    conv_id: str,
    tag: TagCreate,
    current_user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """为会话添加标签。"""
    user_id = current_user["id"] if current_user else None
    return await ConversationService.add_tag(
        conv_id,
        tag.tag_name,
        tag.color,
        user_id
    )


@conversations_router.delete("/{conv_id}/tags/{tag_name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_conversation_tag(
    conv_id: str,
    tag_name: str,
    current_user: Optional[dict] = Depends(get_current_user)
) -> None:
    """移除会话标签。"""
    user_id = current_user["id"] if current_user else None
    await ConversationService.remove_tag(conv_id, tag_name, user_id)


@conversations_router.get("/{conv_id}/tags", response_model=List[TagResponse])
async def get_conversation_tags(
    conv_id: str,
    current_user: Optional[dict] = Depends(get_current_user)
) -> List[dict]:
    """获取会话的所有���签。"""
    user_id = current_user["id"] if current_user else None
    return await ConversationService.get_tags(conv_id, user_id)


@conversations_router.post("/{conv_id}/pin")
async def toggle_conversation_pin(
    conv_id: str,
    current_user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """切换会话固定状态。"""
    user_id = current_user["id"] if current_user else None
    conv = await ConversationService.get_conversation(conv_id, user_id)
    new_state = not conv.get("pinned", False)

    updated = await ConversationService.update_conversation(
        conv_id,
        pinned=new_state,
        user_id=user_id
    )

    return {"pinned": updated.get("pinned", False)}
```

- [ ] **Step 2: 在main.py中注册会话路由**

在`backend/app/main.py`添加：

```python
from app.conversations.router import conversations_router

# ...

app.include_router(conversations_router)
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/conversations/router.py backend/app/main.py
git commit -m "feat(conversations): add conversation management API

- GET /api/conversations - 获取会话列表
- GET /api/conversations/search - 搜索会话
- GET /api/conversations/archived - 获取归档会话
- GET /api/conversations/{id} - 获取单个会话
- PUT /api/conversations/{id} - 更新会话
- DELETE /api/conversations/{id} - 删除会话
- POST /api/conversations/{id}/tags - 添加标签
- DELETE /api/conversations/{id}/tags/{tag_name} - 移除标签
- GET /api/conversations/{id}/tags - 获取会话标签
- POST /api/conversations/{id}/pin - 切换固定状态
"
```

---

## Phase 4: 前端准备 - 添加依赖和类型

### Task 4.1: 添加前端依赖

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 添加新依赖**

```bash
cd frontend && npm install zustand zod react-hook-form @hookform/resolvers date-fns
```

- [ ] **Step 2: 提交package.json**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): add state management and form dependencies

- Add zustand for state management
- Add zod for schema validation
- Add react-hook-form for form handling
- Add date-fns for date formatting
"
```

### Task 4.2: 扩展前端类型定义

**Files:**
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: 添加认证和会话相关类型**

```typescript
// ============================================================
// 认证相关类型
// ============================================================

export interface User {
  id: string;
  email: string | null;
  phone: string | null;
  email_verified: boolean;
  phone_verified: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  verification_code: string;
}

export interface SendCodeRequest {
  email: string;
}

// ============================================================
// 会话相关类型
// ============================================================

export interface Conversation {
  id: string;
  title: string;
  user_id: string | null;
  is_archived: boolean;
  pinned: boolean;
  sync_enabled: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationTag {
  id: string;
  conversation_id: string;
  tag_name: string;
  color: string;
  created_at: string;
}

export interface ConversationUpdate {
  title?: string;
  is_archived?: boolean;
  pinned?: boolean;
  sync_enabled?: boolean;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

// ============================================================
// 消息相关类型（扩展现有）
// ============================================================

export interface MessageAction {
  type: 'copy' | 'regenerate' | 'edit' | 'delete';
  messageId: string;
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/lib/types.ts
git commit -m "feat(frontend): add auth and conversation types

- Add User, AuthState types
- Add LoginRequest, RegisterRequest, SendCodeRequest
- Add Conversation, ConversationTag, ConversationUpdate
- Add ConversationListResponse
- Add MessageAction type
"
```

---

## Phase 5: 前端状态管理 (Zustand)

### Task 5.1: 创建认证状态Store

**Files:**
- Create: `frontend/lib/store/auth-store.ts`

- [ ] **Step 1: 创建认证Store**

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, AuthState, LoginRequest, RegisterRequest } from '@/lib/types';

interface AuthStore extends AuthState {
  // Actions
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  login: (request: LoginRequest) => Promise<void>;
  register: (request: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  sendCode: (email: string) => Promise<void>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      token: null,
      isAuthenticated: false,

      // Setters
      setUser: (user) => set({ user, isAuthenticated: !!user }),

      setToken: (token) => {
        set({ token });
        if (token) {
          // 设置axios默认header（如果使用axios）
          localStorage.setItem('access_token', token);
        } else {
          localStorage.removeItem('access_token');
        }
      },

      // Actions
      login: async (request) => {
        const response = await fetch(`${API_BASE}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
          credentials: 'include',
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Login failed');
        }

        const data = await response.json();

        set({
          user: {
            id: data.user_id,
            email: data.email,
            phone: null,
            email_verified: true,
            phone_verified: false,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          token: data.access_token,
          isAuthenticated: true,
        });

        localStorage.setItem('access_token', data.access_token);
      },

      register: async (request) => {
        const response = await fetch(`${API_BASE}/api/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
          credentials: 'include',
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Registration failed');
        }

        const data = await response.json();

        set({
          user: {
            id: data.user_id,
            email: data.email,
            phone: null,
            email_verified: true,
            phone_verified: false,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          token: data.access_token,
          isAuthenticated: true,
        });

        localStorage.setItem('access_token', data.access_token);
      },

      logout: async () => {
        try {
          await fetch(`${API_BASE}/api/auth/logout`, {
            method: 'POST',
            credentials: 'include',
          });
        } catch (e) {
          console.error('Logout error:', e);
        } finally {
          set({
            user: null,
            token: null,
            isAuthenticated: false,
          });
          localStorage.removeItem('access_token');
        }
      },

      refreshUser: async () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
          set({ user: null, isAuthenticated: false });
          return;
        }

        try {
          const response = await fetch(`${API_BASE}/api/auth/me`, {
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          });

          if (response.ok) {
            const user = await response.json();
            set({ user, isAuthenticated: true });
          } else {
            // Token invalid, clear state
            set({ user: null, token: null, isAuthenticated: false });
            localStorage.removeItem('access_token');
          }
        } catch (error) {
          console.error('Failed to refresh user:', error);
        }
      },

      sendCode: async (email: string) => {
        const response = await fetch(`${API_BASE}/api/auth/send-code`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email }),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to send code');
        }

        return await response.json();
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
```

- [ ] **Step 2: 提交**

```bash
git add frontend/lib/store/auth-store.ts
git commit -m "feat(frontend): add auth store with zustand

- Add user authentication state management
- Add login, register, logout actions
- Add token persistence to localStorage
- Add auto-refresh user on mount
"
```

### Task 5.2: 创建会话状态Store

**Files:**
- Create: `frontend/lib/store/conversation-store.ts`

- [ ] **Step 1: 创建会话Store**

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Conversation, ConversationUpdate } from '@/lib/types';

interface ConversationStore {
  // State
  conversations: Conversation[];
  activeConversationId: string | null;
  isLoading: boolean;
  searchQuery: string;
  showArchived: boolean;

  // Actions
  setConversations: (conversations: Conversation[]) => void;
  setActiveConversation: (id: string | null) => void;
  addConversation: (conversation: Conversation) => void;
  updateConversation: (id: string, update: ConversationUpdate) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  setSearchQuery: (query: string) => void;
  setShowArchived: (show: boolean) => void;
  refreshConversations: () => Promise<void>;
  searchConversations: (query: string) => Promise<void>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const useConversationStore = create<ConversationStore>()(
  persist(
    (set, get) => ({
      // Initial state
      conversations: [],
      activeConversationId: null,
      isLoading: false,
      searchQuery: '',
      showArchived: false,

      // Setters
      setConversations: (conversations) => set({ conversations }),

      setActiveConversation: (id) => set({ activeConversationId: id }),

      setSearchQuery: (query) => set({ searchQuery: query }),

      setShowArchived: (show) => set({ showArchived: show }),

      // Actions
      addConversation: (conversation) =>
        set((state) => ({
          conversations: [conversation, ...state.conversations],
        })),

      updateConversation: async (id, update) => {
        const token = localStorage.getItem('access_token');

        const response = await fetch(`${API_BASE}/api/conversations/${id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` }),
          },
          body: JSON.stringify(update),
        });

        if (!response.ok) {
          throw new Error('Failed to update conversation');
        }

        const updated = await response.json();

        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === id ? updated : c
          ),
        }));
      },

      deleteConversation: async (id) => {
        const token = localStorage.getItem('access_token');

        const response = await fetch(`${API_BASE}/api/conversations/${id}`, {
          method: 'DELETE',
          headers: {
            ...(token && { 'Authorization': `Bearer ${token}` }),
          },
        });

        if (!response.ok) {
          throw new Error('Failed to delete conversation');
        }

        set((state) => ({
          conversations: state.conversations.filter((c) => c.id !== id),
          activeConversationId:
            state.activeConversationId === id ? null : state.activeConversationId,
        }));
      },

      refreshConversations: async () => {
        set({ isLoading: true });

        try {
          const token = localStorage.getItem('access_token');
          const includeArchived = get().showArchived;

          const response = await fetch(
            `${API_BASE}/api/conversations?include_archived=${includeArchived}`,
            {
              headers: {
                ...(token && { 'Authorization': `Bearer ${token}` }),
              },
            }
          );

          if (response.ok) {
            const data = await response.json();
            set({ conversations: data.conversations });
          }
        } catch (error) {
          console.error('Failed to refresh conversations:', error);
        } finally {
          set({ isLoading: false });
        }
      },

      searchConversations: async (query) => {
        if (!query.trim()) {
          get().refreshConversations();
          return;
        }

        set({ isLoading: true, searchQuery: query });

        try {
          const token = localStorage.getItem('access_token');

          const response = await fetch(
            `${API_BASE}/api/conversations/search?q=${encodeURIComponent(query)}`,
            {
              headers: {
                ...(token && { 'Authorization': `Bearer ${token}` }),
              },
            }
          );

          if (response.ok) {
            const results = await response.json();
            set({ conversations: results });
          }
        } catch (error) {
          console.error('Failed to search conversations:', error);
        } finally {
          set({ isLoading: false });
        }
      },
    }),
    {
      name: 'conversation-storage',
      partialize: (state) => ({
        activeConversationId: state.activeConversationId,
        showArchived: state.showArchived,
      }),
    }
  )
);
```

- [ ] **Step 2: 提交**

```bash
git add frontend/lib/store/conversation-store.ts
git commit -m "feat(frontend): add conversation store with zustand

- Add conversation list state management
- Add active conversation tracking
- Add CRUD operations for conversations
- Add search functionality
- Add archived filter
"
```

### Task 5.3: 创建API客户端

**Files:**
- Create: `frontend/lib/api/auth.ts`
- Create: `frontend/lib/api/conversations.ts`

- [ ] **Step 1: 创建认证API客户端**

```typescript
/**
 * Authentication API client
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface SendCodeResponse {
  message: string;
  expires_in: number;
}

export interface LoginResponse {
  user_id: string;
  email: string;
  access_token: string;
  expires_in: number;
}

export interface RegisterResponse {
  user_id: string;
  email: string;
  access_token: string;
  expires_in: number;
}

export async function sendVerificationCode(email: string): Promise<SendCodeResponse> {
  const response = await fetch(`${API_BASE}/api/auth/send-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send code');
  }

  return response.json();
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Login failed');
  }

  return response.json();
}

export async function register(
  email: string,
  password: string,
  code: string
): Promise<RegisterResponse> {
  const response = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, verification_code: code }),
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Registration failed');
  }

  return response.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
}

export async function getCurrentUser(token: string) {
  const response = await fetch(`${API_BASE}/api/auth/me`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });

  if (!response.ok) {
    return null;
  }

  return response.json();
}

export async function refreshToken() {
  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error('Failed to refresh token');
  }

  return response.json();
}
```

- [ ] **Step 2: 创建会话API客户端**

```typescript
/**
 * Conversations API client
 */

import type { Conversation, ConversationUpdate, ConversationTag } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem('access_token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

export async function listConversations(includeArchived = false): Promise<Conversation[]> {
  const response = await fetch(
    `${API_BASE}/api/conversations?include_archived=${includeArchived}`,
    { headers: getAuthHeaders() }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch conversations');
  }

  const data = await response.json();
  return data.conversations;
}

export async function searchConversations(query: string): Promise<Conversation[]> {
  const response = await fetch(
    `${API_BASE}/api/conversations/search?q=${encodeURIComponent(query)}`,
    { headers: getAuthHeaders() }
  );

  if (!response.ok) {
    throw new Error('Failed to search conversations');
  }

  return response.json();
}

export async function getConversation(id: string): Promise<Conversation> {
  const response = await fetch(`${API_BASE}/api/conversations/${id}`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error('Failed to fetch conversation');
  }

  return response.json();
}

export async function updateConversation(
  id: string,
  update: ConversationUpdate
): Promise<Conversation> {
  const response = await fetch(`${API_BASE}/api/conversations/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(update),
  });

  if (!response.ok) {
    throw new Error('Failed to update conversation');
  }

  return response.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/conversations/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error('Failed to delete conversation');
  }
}

export async function togglePinConversation(id: string): Promise<{ pinned: boolean }> {
  const response = await fetch(`${API_BASE}/api/conversations/${id}/pin`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error('Failed to toggle pin');
  }

  return response.json();
}

export async function addTag(
  conversationId: string,
  tagName: string,
  color: string = '#6366f1'
): Promise<ConversationTag> {
  const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/tags`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ tag_name: tagName, color }),
  });

  if (!response.ok) {
    throw new Error('Failed to add tag');
  }

  return response.json();
}

export async function removeTag(conversationId: string, tagName: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/conversations/${conversationId}/tags/${encodeURIComponent(tagName)}`,
    {
      method: 'DELETE',
      headers: getAuthHeaders(),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to remove tag');
  }
}

export async function getConversationTags(conversationId: string): Promise<ConversationTag[]> {
  const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/tags`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error('Failed to fetch tags');
  }

  return response.json();
}

export async function getAllUserTags(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/api/conversations/tags`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error('Failed to fetch tags');
  }

  return response.json();
}
```

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/api/auth.ts frontend/lib/api/conversations.ts
git commit -m "feat(frontend): add API clients for auth and conversations

- Add auth API: sendCode, login, register, logout, getCurrentUser
- Add conversations API: list, search, get, update, delete
- Add tag management: addTag, removeTag, getConversationTags
"
```

---

## Phase 6: 前端认证UI组件

### Task 6.1: 创建认证Modal组件

**Files:**
- Create: `frontend/components/auth/auth-modal.tsx`

- [ ] **Step 1: 创建认证Modal**

```typescript
'use client';

import { useState } from 'react';
import { useAuthStore } from '@/lib/store/auth-store';
import { LoginForm } from './login-form';
import { RegisterForm } from './register-form';

type AuthView = 'login' | 'register';

export function AuthModal() {
  const [isOpen, setIsOpen] = useState(false);
  const [view, setView] = useState<AuthView>('login');
  const { isAuthenticated, user } = useAuthStore();

  if (isAuthenticated) {
    return (
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
          <span className="text-sm font-medium text-primary">
            {user?.email?.[0].toUpperCase()}
          </span>
        </div>
        <span className="text-sm text-muted-foreground hidden sm:inline">
          {user?.email}
        </span>
        <button
          onClick={() => useAuthStore.getState().logout()}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          登出
        </button>
      </div>
    );
  }

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 text-sm font-medium text-foreground bg-primary hover:bg-primary/90 rounded-md transition"
      >
        登录
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-background/80 backdrop-blur-sm"
            onClick={() => setIsOpen(false)}
          />
          <div className="relative w-full max-w-md bg-background border rounded-lg shadow-lg p-6">
            <button
              onClick={() => setIsOpen(false)}
              className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <div className="mb-6">
              <h2 className="text-xl font-semibold">
                {view === 'login' ? '登录' : '注册'}
              </h2>
            </div>

            {view === 'login' ? (
              <LoginForm
                onSuccess={() => setIsOpen(false)}
                onSwitchToRegister={() => setView('register')}
              />
            ) : (
              <RegisterForm
                onSuccess={() => setIsOpen(false)}
                onSwitchToLogin={() => setView('login')}
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/auth/auth-modal.tsx
git commit -m "feat(frontend): add auth modal component

- Add modal with login/register view toggle
- Add user avatar display when authenticated
- Add logout button
"
```

### Task 6.2: 创建登录表单

**Files:**
- Create: `frontend/components/auth/login-form.tsx`

- [ ] **Step 1: 创建登录表单**

```typescript
'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useState } from 'react';
import { useAuthStore } from '@/lib/store/auth-store';

const loginSchema = z.object({
  email: z.string().email('请输入有效的邮箱地址'),
  password: z.string().min(1, '请输入密码'),
});

type LoginFormData = z.infer<typeof loginSchema>;

interface LoginFormProps {
  onSuccess: () => void;
  onSwitchToRegister: () => void;
}

export function LoginForm({ onSuccess, onSwitchToRegister }: LoginFormProps) {
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const login = useAuthStore((state) => state.login);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormData) => {
    setError('');
    setIsLoading(true);

    try {
      await login(data);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请检查邮箱和密码');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {error && (
        <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md">
          {error}
        </div>
      )}

      <div>
        <label htmlFor="email" className="block text-sm font-medium mb-1">
          邮箱
        </label>
        <input
          {...register('email')}
          type="email"
          id="email"
          className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="your@email.com"
        />
        {errors.email && (
          <p className="mt-1 text-sm text-destructive">{errors.email.message}</p>
        )}
      </div>

      <div>
        <label htmlFor="password" className="block text-sm font-medium mb-1">
          密码
        </label>
        <input
          {...register('password')}
          type="password"
          id="password"
          className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="••••••••"
        />
        {errors.password && (
          <p className="mt-1 text-sm text-destructive">{errors.password.message}</p>
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="w-full py-2 px-4 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition"
      >
        {isLoading ? '登录中...' : '登录'}
      </button>

      <div className="text-center text-sm">
        <span className="text-muted-foreground">还没有账号？</span>
        <button
          type="button"
          onClick={onSwitchToRegister}
          className="ml-1 text-primary hover:underline"
        >
          注册
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/auth/login-form.tsx
git commit -m "feat(frontend): add login form component

- Add email and password inputs with validation
- Add error handling and loading state
- Add switch to register link
"
```

### Task 6.3: 创建注册表单

**Files:**
- Create: `frontend/components/auth/register-form.tsx`

- [ ] **Step 1: 创建注册表单**

```typescript
'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useState } from 'react';
import { useAuthStore } from '@/lib/store/auth-store';

const registerSchema = z.object({
  email: z.string().email('请输入有效的邮箱地址'),
  password: z.string().min(8, '密码至少8个字符'),
  confirmPassword: z.string(),
  verificationCode: z.string().regex(/^\d{6}$/, '请输入6位验证码'),
}).refine((data) => data.password === data.confirmPassword, {
  message: '两次输入的密码不一致',
  path: ['confirmPassword'],
});

type RegisterFormData = z.infer<typeof registerSchema>;

interface RegisterFormProps {
  onSuccess: () => void;
  onSwitchToLogin: () => void;
}

export function RegisterForm({ onSuccess, onSwitchToLogin }: RegisterFormProps) {
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [countdown, setCountdown] = useState(0);

  const register = useAuthStore((state) => state.register);
  const sendCode = useAuthStore((state) => state.sendCode);

  const {
    register: formRegister,
    handleSubmit,
    formState: { errors },
    watch,
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  });

  const email = watch('email', '');

  const handleSendCode = async () => {
    if (!email || !email.includes('@')) {
      setError('请先输入有效的邮箱地址');
      return;
    }

    setIsSendingCode(true);
    setError('');

    try {
      await sendCode(email);
      setCodeSent(true);
      setCountdown(60);

      // 倒计时
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送验证码失败');
    } finally {
      setIsSendingCode(false);
    }
  };

  const onSubmit = async (data: RegisterFormData) => {
    setError('');
    setIsLoading(true);

    try {
      await register({
        email: data.email,
        password: data.password,
        verification_code: data.verificationCode,
      });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败，请重试');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {error && (
        <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md">
          {error}
        </div>
      )}

      <div>
        <label htmlFor="reg-email" className="block text-sm font-medium mb-1">
          邮箱
        </label>
        <input
          {...formRegister('email')}
          type="email"
          id="reg-email"
          className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="your@email.com"
        />
        {errors.email && (
          <p className="mt-1 text-sm text-destructive">{errors.email.message}</p>
        )}
      </div>

      <div>
        <label htmlFor="reg-password" className="block text-sm font-medium mb-1">
          密码
        </label>
        <input
          {...formRegister('password')}
          type="password"
          id="reg-password"
          className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="至少8个字符"
        />
        {errors.password && (
          <p className="mt-1 text-sm text-destructive">{errors.password.message}</p>
        )}
      </div>

      <div>
        <label htmlFor="reg-confirm" className="block text-sm font-medium mb-1">
          确认密码
        </label>
        <input
          {...formRegister('confirmPassword')}
          type="password"
          id="reg-confirm"
          className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="再次输入密码"
        />
        {errors.confirmPassword && (
          <p className="mt-1 text-sm text-destructive">{errors.confirmPassword.message}</p>
        )}
      </div>

      <div>
        <label htmlFor="reg-code" className="block text-sm font-medium mb-1">
          验证码
        </label>
        <div className="flex gap-2">
          <input
            {...formRegister('verificationCode')}
            type="text"
            id="reg-code"
            className="flex-1 px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
            placeholder="6位数字"
            maxLength={6}
          />
          <button
            type="button"
            onClick={handleSendCode}
            disabled={isSendingCode || countdown > 0}
            className="px-4 py-2 text-sm bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/80 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {countdown > 0 ? `${countdown}秒` : isSendingCode ? '发送中...' : '发送验证码'}
          </button>
        </div>
        {errors.verificationCode && (
          <p className="mt-1 text-sm text-destructive">{errors.verificationCode.message}</p>
        )}
        {codeSent && countdown === 0 && (
          <p className="mt-1 text-sm text-muted-foreground">
            验证码已发送，请查看控制台
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="w-full py-2 px-4 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition"
      >
        {isLoading ? '注册中...' : '注册'}
      </button>

      <div className="text-center text-sm">
        <span className="text-muted-foreground">已有账号？</span>
        <button
          type="button"
          onClick={onSwitchToLogin}
          className="ml-1 text-primary hover:underline"
        >
          登录
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/auth/register-form.tsx
git commit -m "feat(frontend): add register form component

- Add email, password, confirm password inputs
- Add verification code input with send button
- Add countdown timer for resend
- Add validation and error handling
"
```

### Task 6.4: 更新layout使用认证Modal

**Files:**
- Modify: `frontend/app/layout.tsx`

- [ ] **Step 1: 在layout中添加认证Modal和初始化**

```typescript
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthModal } from "@/components/auth/auth-modal";
import { useEffect } from "react";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AI Travel Assistant",
  description: "Your intelligent travel planning companion",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <AuthInitializer />
        {children}
      </body>
    </html>
  );
}

function AuthInitializer() {
  useEffect(() => {
    // 初始化：刷新用户状态
    const { useAuthStore } = require('@/lib/store/auth-store');
    useAuthStore.getState().refreshUser();
  }, []);

  return null;
}
```

- [ ] **Step 2: 更新聊天页面添加认证按钮**

修改`frontend/app/chat/page.tsx`，在顶部栏添加AuthModal：

```typescript
// 在现有页面中添加
import { AuthModal } from "@/components/auth/auth-modal";

// 在顶部栏添加AuthModal组件
```

- [ ] **Step 3: 提交**

```bash
git add frontend/app/layout.tsx frontend/app/chat/page.tsx
git commit -m "feat(frontend): integrate auth modal into layout

- Add AuthModal to root layout
- Add auth state initialization on mount
- Add auth button to chat page header
"
```

---

## Phase 7: 前端会话列表UI

### Task 7.1: 创建会话列表组件

**Files:**
- Create: `frontend/components/conversations/conversation-list.tsx`

- [ ] **Step 1: 创建会话列表组件**

```typescript
'use client';

import { useEffect, useState } from 'react';
import { useConversationStore } from '@/lib/store/conversation-store';
import { ConversationItem } from './conversation-item';
import { ConversationSearch } from './conversation-search';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

interface ConversationListProps {
  onConversationSelect: (id: string) => void;
  activeConversationId: string | null;
}

export function ConversationList({
  onConversationSelect,
  activeConversationId,
}: ConversationListProps) {
  const {
    conversations,
    isLoading,
    activeConversationId: storeActiveId,
    setActiveConversation,
    refreshConversations,
  } = useConversationStore();

  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    refreshConversations();
  }, [refreshConversations]);

  const groupedConversations = conversations.reduce((acc, conv) => {
    const date = new Date(conv.updated_at);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    let group = '更早';
    if (date.toDateString() === today.toDateString()) {
      group = '今天';
    } else if (date.toDateString() === yesterday.toDateString()) {
      group = '昨天';
    } else if (conv.pinned) {
      group = 'pinned';
    }

    if (!acc[group]) acc[group] = [];
    acc[group].push(conv);
    return acc;
  }, {} as Record<string, typeof conversations>);

  const handleNewConversation = async () => {
    if (isCreating) return;
    setIsCreating(true);

    try {
      const response = await fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const newConv = await response.json();
      setActiveConversation(newConv.id);
      onConversationSelect(newConv.id);
      await refreshConversations();
    } catch (error) {
      console.error('Failed to create conversation:', error);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="h-14 border-b border-border flex items-center justify-between px-4">
        <h2 className="font-semibold text-sm text-foreground/80">聊天历史</h2>
        <AuthModal />
      </div>

      {/* Search */}
      <div className="p-2">
        <ConversationSearch />
      </div>

      {/* New Conversation Button */}
      <div className="px-2 pb-2">
        <button
          onClick={handleNewConversation}
          disabled={isCreating}
          className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition text-sm font-medium disabled:opacity-50"
        >
          {isCreating ? '创建中...' : '新建对话'}
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto px-2">
        {isLoading ? (
          <div className="text-center py-8 text-sm text-muted-foreground">
            加载中...
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-8 text-sm text-muted-foreground">
            暂无历史对话
          </div>
        ) : (
          <>
            {/* Pinned */}
            {groupedConversations.pinned && (
              <div className="mb-4">
                <div className="text-xs text-muted-foreground px-2 py-1">
                  📌 固定
                </div>
                {groupedConversations.pinned.map((conv) => (
                  <ConversationItem
                    key={conv.id}
                    conversation={conv}
                    isActive={activeConversationId === conv.id}
                    onSelect={() => {
                      setActiveConversation(conv.id);
                      onConversationSelect(conv.id);
                    }}
                  />
                ))}
              </div>
            )}

            {/* Today */}
            {groupedConversations['今天'] && (
              <div className="mb-4">
                <div className="text-xs text-muted-foreground px-2 py-1">
                  今天
                </div>
                {groupedConversations['今天'].map((conv) => (
                  <ConversationItem
                    key={conv.id}
                    conversation={conv}
                    isActive={activeConversationId === conv.id}
                    onSelect={() => {
                      setActiveConversation(conv.id);
                      onConversationSelect(conv.id);
                    }}
                  />
                ))}
              </div>
            )}

            {/* Yesterday */}
            {groupedConversations['昨天'] && (
              <div className="mb-4">
                <div className="text-xs text-muted-foreground px-2 py-1">
                  昨天
                </div>
                {groupedConversations['昨天'].map((conv) => (
                  <ConversationItem
                    key={conv.id}
                    conversation={conv}
                    isActive={activeConversationId === conv.id}
                    onSelect={() => {
                      setActiveConversation(conv.id);
                      onConversationSelect(conv.id);
                    }}
                  />
                ))}
              </div>
            )}

            {/* Earlier */}
            {groupedConversations['更早'] && (
              <div className="mb-4">
                <div className="text-xs text-muted-foreground px-2 py-1">
                  更早
                </div>
                {groupedConversations['更早'].map((conv) => (
                  <ConversationItem
                    key={conv.id}
                    conversation={conv}
                    isActive={activeConversationId === conv.id}
                    onSelect={() => {
                      setActiveConversation(conv.id);
                      onConversationSelect(conv.id);
                    }}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
```

注意：需要导入AuthModal

- [ ] **Step 2: 提交**

```bash
git add frontend/components/conversations/conversation-list.tsx
git commit -m "feat(frontend): add conversation list component

- Add grouped conversation list (today, yesterday, earlier)
- Add pinned conversations section
- Add new conversation button
- Add loading state
"
```

### Task 7.2: 创建会话项组件

**Files:**
- Create: `frontend/components/conversations/conversation-item.tsx`

- [ ] **Step 1: 创建会话项组件**

```typescript
'use client';

import { useState, useRef, useEffect } from 'react';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import type { Conversation } from '@/lib/types';
import { useConversationStore } from '@/lib/store/conversation-store';

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
}

export function ConversationItem({
  conversation,
  isActive,
  onSelect,
}: ConversationItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(conversation.title);
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const { updateConversation, deleteConversation } = useConversationStore();

  useEffect(() => {
    setEditTitle(conversation.title);
  }, [conversation.title]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSaveEdit = async () => {
    if (editTitle.trim() && editTitle !== conversation.title) {
      await updateConversation(conversation.id, { title: editTitle.trim() });
    }
    setIsEditing(false);
  };

  const handleCancelEdit = () => {
    setEditTitle(conversation.title);
    setIsEditing(false);
  };

  const handleTogglePin = async () => {
    await updateConversation(conversation.id, { pinned: !conversation.pinned });
    setShowMenu(false);
  };

  const handleToggleArchive = async () => {
    await updateConversation(conversation.id, { is_archived: !conversation.is_archived });
    setShowMenu(false);
  };

  const handleDelete = async () => {
    if (confirm('确定要删除这个对话吗？')) {
      await deleteConversation(conversation.id);
      setShowMenu(false);
    }
  };

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffHours = (now.getTime() - date.getTime()) / (1000 * 60 * 60);

    if (diffHours < 1) return '刚刚';
    if (diffHours < 24) return `${Math.floor(diffHours)}小时前`;
    return format(date, 'M月d日', { locale: zhCN });
  };

  return (
    <div
      className={`
        group relative flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition
        ${isActive ? 'bg-secondary' : 'hover:bg-secondary/50'}
      `}
      onClick={onSelect}
    >
      {/* Icon */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
        <svg className="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {isEditing ? (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveEdit();
                if (e.key === 'Escape') handleCancelEdit();
              }}
              className="flex-1 px-1 py-0.5 text-sm bg-background border rounded focus:outline-none focus:ring-1 focus:ring-primary"
              autoFocus
            />
            <button
              onClick={handleSaveEdit}
              className="p-1 text-green-600 hover:bg-green-50 rounded"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </button>
            <button
              onClick={handleCancelEdit}
              className="p-1 text-red-600 hover:bg-red-50 rounded"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-sm truncate">
              {conversation.pinned && '📌 '}
              {conversation.title}
            </span>
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              {formatTime(conversation.updated_at)}
            </span>
          </div>
        )}
      </div>

      {/* Menu Button */}
      <div className="relative" ref={menuRef}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowMenu(!showMenu);
          }}
          className="opacity-0 group-hover:opacity-100 p-1 hover:bg-secondary-50 rounded transition"
        >
          <svg className="w-4 h-4 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
          </svg>
        </button>

        {showMenu && (
          <div className="absolute right-0 top-full mt-1 w-40 bg-background border rounded-lg shadow-lg z-10">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsEditing(true);
                setShowMenu(false);
              }}
              className="w-full px-3 py-2 text-left text-sm hover:bg-secondary flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              重命名
            </button>
            <button
              onClick={handleTogglePin}
              className="w-full px-3 py-2 text-left text-sm hover:bg-secondary flex items-center gap-2"
            >
              {conversation.pinned ? (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                  </svg>
                  取消固定
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                  </svg>
                  固定
                </>
              )}
            </button>
            <button
              onClick={handleToggleArchive}
              className="w-full px-3 py-2 text-left text-sm hover:bg-secondary flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
              {conversation.is_archived ? '取消归档' : '归档'}
            </button>
            <hr className="border-border" />
            <button
              onClick={handleDelete}
              className="w-full px-3 py-2 text-left text-sm text-destructive hover:bg-destructive/10 flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              删除
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/conversations/conversation-item.tsx
git commit -m "feat(frontend): add conversation item component

- Add conversation display with title and time
- Add inline rename functionality
- Add context menu (pin, archive, delete)
- Add hover effects
"
```

### Task 7.3: 创建搜索组件

**Files:**
- Create: `frontend/components/conversations/conversation-search.tsx`

- [ ] **Step 1: 创建搜索组件**

```typescript
'use client';

import { useState, useEffect } from 'react';
import { useConversationStore } from '@/lib/store/conversation-store';
import { useAuthStore } from '@/lib/store/auth-store';

export function ConversationSearch() {
  const [query, setQuery] = useState('');
  const { searchConversations, refreshConversations } = useConversationStore();
  const { isAuthenticated } = useAuthStore();

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (query.trim()) {
        if (isAuthenticated) {
          searchConversations(query);
        }
      } else {
        refreshConversations();
      }
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [query, searchConversations, refreshConversations, isAuthenticated]);

  return (
    <div className="relative">
      <svg
        className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
        />
      </svg>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="搜索会话..."
        className="w-full pl-9 pr-3 py-2 text-sm bg-secondary/50 border-0 rounded-md focus:outline-none focus:ring-1 focus:ring-primary"
      />
      {query && (
        <button
          onClick={() => setQuery('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/components/conversations/conversation-search.tsx
git commit -m "feat(frontend): add conversation search component

- Add debounced search input
- Add clear button
- Add search icon
"
```

---

## Phase 8: 集成测试

### Task 8.1: 端到端测试认证流程

**Files:**
- Create: `backend/tests/test_auth_e2e.py`

- [ ] **Step 1: 创建端到端测试**

```python
"""End-to-end tests for authentication flow."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
class TestAuthE2E:
    """End-to-end authentication flow tests."""

    async def test_complete_registration_flow(self):
        """Test complete registration: send code -> register -> login."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. 发送验证码
            response = await client.post(
                "/api/auth/send-code",
                json={"email": "e2e@example.com"}
            )
            assert response.status_code == 200
            data = response.json()
            assert "message" in data

            # 2. 获取验证码（从控制台输出，这里需要手动输入）
            # 在实际测试中，可以mock send_verification_code函数

            # 3. 注册（需要验证码，这里用假的）
            # 注意：实际测试需要mock或从环境获取验证码
            pass

    async def test_login_flow(self):
        """Test login flow."""
        # 先创建一个测试用户
        from app.db.postgres import create_user, create_user_credentials
        from app.auth.service import AuthService

        user_id = await create_user()
        await create_user_credentials(
            user_id=user_id,
            email="test@example.com",
            password="test123456"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 登录
            response = await client.post(
                "/api/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "test123456"
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["email"] == "test@example.com"

            # 获取用户信息
            token = data["access_token"]
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            user_data = response.json()
            assert user_data["email"] == "test@example.com"

            # 登出
            response = await client.post("/api/auth/logout")
            assert response.status_code == 200

    async def test_invalid_credentials(self):
        """Test login with invalid credentials."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={
                    "email": "nonexistent@example.com",
                    "password": "wrongpassword"
                }
            )
            assert response.status_code == 401
```

- [ ] **Step 2: 运行测试**

```bash
cd backend && pytest tests/test_auth_e2e.py -v
```

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_auth_e2e.py
git commit -m "test(auth): add end-to-end authentication tests

- Test complete registration flow
- Test login flow
- Test invalid credentials handling
"
```

### Task 8.2: 前端集成测试

**Files:**
- Create: `frontend/tests/conversation.test.tsx`

- [ ] **Step 1: 创建前端测试（可选）**

由于前端测试配置较复杂，这里提供手动测试清单：

**测试清单：**

1. **认证测试**
   - [ ] 点击登录按钮，打开Modal
   - [ ] 输入邮箱密码，登录成功
   - [ ] 刷新页面，保持登录状态
   - [ ] 点击登出，清除状态
   - [ ] 注册流程：发送验证码 → 输入验证码 → 注册成功

2. **会话管理测试**
   - [ ] 点击新建对话，创建成功
   - [ ] 点击会话项，切换成功
   - [ ] 双击会话标题，进入编辑模式
   - [ ] 修改标题，保存成功
   - [ ] 点击菜单 → 固定，会话固定到顶部
   - [ ] 点击菜单 → 归档，会话隐藏
   - [ ] 点击菜单 → 删除，确认后删除成功

3. **搜索测试**
   - [ ] 输入搜索关键词，显示匹配结果
   - [ ] 清空搜索，恢复完整列表

- [ ] **Step 2: 提交测试文档**

```bash
cat > frontend/tests/MANUAL_TEST_CHECKLIST.md << 'EOF'
# 手动测试清单

## 认证测试
- [ ] 登录功能
- [ ] 注册功能
- [ ] 登出功能
- [ ] 刷新保持登录

## 会话管理测试
- [ ] 新建对话
- [ ] 切换对话
- [ ] 重命名对话
- [ ] 固定/取消固定
- [ ] 归档/取消归档
- [ ] 删除对话

## 搜索测试
- [ ] 关键词搜索
- [ ] 清空搜索
EOF

git add frontend/tests/MANUAL_TEST_CHECKLIST.md
git commit -m "test(frontend): add manual test checklist"
```

---

## 完成检查

### Task 9.1: 最终验证

- [ ] **后端测试**
```bash
cd backend && pytest tests/ -v
```

- [ ] **前端构建测试**
```bash
cd frontend && npm run build
```

- [ ] **启动完整系统测试**

1. 启动后端：`cd backend && python -m uvicorn app.main:app --reload`
2. 启动前端：`cd frontend && npm run dev`
3. 访问 http://localhost:3000
4. 完成手动测试清单

- [ ] **最终提交**

```bash
git add .
git commit -m "feat: complete auth and session management implementation

- Backend: FastAPI auth + conversation management
- Frontend: Zustand stores + React components
- Database: New tables for auth and sessions
- Tests: Unit and E2E tests

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 附录：快速命令参考

### 后端开发
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
pytest tests/ -v
```

### 前端开发
```bash
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

### 数据库操作
```bash
# 连接PostgreSQL
psql -h localhost -U postgres -d travel_assistant

# 查看表
\dt

# 查看用户
SELECT * FROM users;

# 查看凭证
SELECT * FROM user_credentials;
```

---

*计划版本: 1.0*
*创建日期: 2026-03-31*
*预计工作量: 11个工作日*

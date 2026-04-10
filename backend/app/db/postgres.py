"""PostgreSQL database connection and session management.

References:
- D-14: Session history stored in PostgreSQL
- D-15: Session ID in UUID format
- D-16: Message storage with role, content, timestamp, token usage
"""

import os
import re
from datetime import datetime
from typing import AsyncGenerator, Optional
from uuid import UUID, uuid4

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:123456@localhost:5432/travel_assistant")


def parse_database_url(url: str) -> dict:
    """Parse DATABASE_URL into components."""
    # Format: postgresql://user:password@host:port/database
    match = re.match(
        r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
        url
    )
    if match:
        return {
            "user": match.group(1),
            "password": match.group(2),
            "host": match.group(3),
            "port": int(match.group(4)),
            "database": match.group(5)
        }
    # Try without port
    match = re.match(
        r"postgresql://([^:]+):([^@]+)@([^/]+)/(.+)",
        url
    )
    if match:
        return {
            "user": match.group(1),
            "password": match.group(2),
            "host": match.group(3),
            "port": 5432,
            "database": match.group(4)
        }
    raise ValueError(f"Invalid DATABASE_URL format: {url}")


class Database:
    """Database connection manager."""

    _pool: Optional[asyncpg.Pool] = None
    _initialized = False

    @classmethod
    async def _create_database_if_not_exists(cls) -> None:
        """Create the database if it doesn't exist."""
        db_config = parse_database_url(DATABASE_URL)
        db_name = db_config["database"]

        # Connect to postgres default database to create our database
        default_db_url = DATABASE_URL.replace(f"/{db_name}", "/postgres")

        try:
            conn = await asyncpg.connect(default_db_url)
            try:
                # Check if database exists
                exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT datname FROM pg_database WHERE datname = $1)",
                    db_name
                )
                if not exists:
                    await conn.execute(f'CREATE DATABASE "{db_name}"')
                    print(f"[OK] Database '{db_name}' created")
                else:
                    print(f"[OK] Database '{db_name}' already exists")
            finally:
                await conn.close()
        except Exception as e:
            # Try to connect directly to target database - it might already exist
            try:
                test_conn = await asyncpg.connect(DATABASE_URL)
                await test_conn.close()
                print(f"[OK] Database '{db_name}' accessible")
            except Exception:
                print(f"[ERROR] Cannot connect to PostgreSQL: {e}")
                print(f"        Please ensure PostgreSQL is running and credentials are correct.")
                print(f"        DATABASE_URL: {DATABASE_URL}")
                raise

    @classmethod
    async def _create_tables_if_not_exists(cls) -> None:
        """Create tables if they don't exist."""
        conn = await cls.get_connection()
        try:
            # Create conversations table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id UUID PRIMARY KEY,
                    title VARCHAR(255) NOT NULL DEFAULT '新对话',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Create messages table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id UUID PRIMARY KEY,
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    tokens_used INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Create indexes for better query performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
                ON messages(conversation_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
                ON conversations(updated_at DESC)
            """)

            # Create itineraries table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS itineraries (
                    id UUID PRIMARY KEY,
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    destination VARCHAR(255) NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    preferences TEXT,
                    travelers INTEGER DEFAULT 1,
                    budget VARCHAR(20),
                    days JSONB DEFAULT '[]'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_itineraries_conversation_id
                ON itineraries(conversation_id)
            """)

            # Create users table (per D-01)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    username VARCHAR(100) UNIQUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Create user_preferences table (per D-04, D-06)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # GIN index for JSONB queries (per 03-RESEARCH.md Pitfall 4)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_preferences_gin
                ON user_preferences USING GIN (preferences)
            """)

            # Partial index for budget queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_preferences_budget
                ON user_preferences ((preferences->>'budget'))
                WHERE preferences ? 'budget'
            """)

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

            # Ensure at least email or phone is provided (use DO block for IF NOT EXISTS)
            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'check_contact_method'
                        AND conrelid = 'user_credentials'::regclass
                    ) THEN
                        ALTER TABLE user_credentials ADD CONSTRAINT check_contact_method
                        CHECK (email IS NOT NULL OR phone IS NOT NULL);
                    END IF;
                END $$;
            """)

            # Create refresh_tokens table (avoid confusion with chat sessions)
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
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_active ON refresh_tokens(user_id, is_revoked, expires_at);
            """)

            # Extend conversations table with auth-related fields
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

            # Create conversation_states table for Phase 2 episodic memory
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_states (
                    conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    state_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_states_user_id
                ON conversation_states(user_id)
            """)

            # Create episodic_memories table for short-term memory
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id UUID PRIMARY KEY,
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    memory_type VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    structured_data JSONB DEFAULT '{}',
                    confidence FLOAT DEFAULT 0.5,
                    importance FLOAT DEFAULT 0.5,
                    source_message_id UUID,
                    is_promoted BOOLEAN DEFAULT FALSE,
                    promoted_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_conversation ON episodic_memories(conversation_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_type ON episodic_memories(memory_type);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_promoted ON episodic_memories(is_promoted, importance DESC);
            """)

            # Create user_profiles table for long-term memory
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    travel_preferences JSONB DEFAULT '{}',
                    patterns JSONB DEFAULT '[]',
                    stats JSONB DEFAULT '{}',
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Create session_states table (per Phase 3: 会话生命周期)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS session_states (
                    session_id UUID PRIMARY KEY,
                    user_id UUID NOT NULL,
                    conversation_id UUID NOT NULL,
                    core_state JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    last_activity TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_states_user
                ON session_states(user_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_states_conv
                ON session_states(conversation_id)
            """)

            # Fix foreign key constraints for existing tables
            # This ensures CASCADE delete works properly even for tables created before FK constraints
            await cls._ensure_foreign_key_constraints()

            print("[OK] Database tables initialized")
        finally:
            await cls.release_connection(conn)

    @classmethod
    async def _ensure_foreign_key_constraints(cls) -> None:
        """Ensure foreign key constraints with CASCADE delete are properly set.

        This is a safety measure to fix any existing tables that may have been
        created without proper CASCADE delete constraints.
        """
        # Check and fix messages table foreign key
        await cls._fix_foreign_key(
            table_name="messages",
            column_name="conversation_id",
            referenced_table="conversations",
            referenced_column="id",
            on_delete="CASCADE"
        )

        # Check and fix itineraries table foreign key
        await cls._fix_foreign_key(
            table_name="itineraries",
            column_name="conversation_id",
            referenced_table="conversations",
            referenced_column="id",
            on_delete="CASCADE"
        )

        # Check and fix episodic_memories table foreign key
        await cls._fix_foreign_key(
            table_name="episodic_memories",
            column_name="conversation_id",
            referenced_table="conversations",
            referenced_column="id",
            on_delete="CASCADE"
        )

        # Check and fix conversation_tags table foreign key
        await cls._fix_foreign_key(
            table_name="conversation_tags",
            column_name="conversation_id",
            referenced_table="conversations",
            referenced_column="id",
            on_delete="CASCADE"
        )

        # Check and fix session_states table foreign keys
        await cls._fix_foreign_key(
            table_name="session_states",
            column_name="user_id",
            referenced_table="users",
            referenced_column="id",
            on_delete="CASCADE"
        )

        await cls._fix_foreign_key(
            table_name="session_states",
            column_name="conversation_id",
            referenced_table="conversations",
            referenced_column="id",
            on_delete="CASCADE"
        )

    @classmethod
    async def _fix_foreign_key(
        cls,
        table_name: str,
        column_name: str,
        referenced_table: str,
        referenced_column: str,
        on_delete: str
    ) -> None:
        """Fix or add a foreign key constraint with CASCADE delete.

        Args:
            table_name: The table that has the foreign key
            column_name: The column that references another table
            referenced_table: The table being referenced
            referenced_column: The column being referenced
            on_delete: Action on delete (CASCADE, SET NULL, etc.)
        """
        conn = await cls.get_connection()
        try:
            # Check if constraint already exists with correct CASCADE
            check_query = """
                SELECT EXISTS(
                    SELECT 1 FROM pg_constraint
                    WHERE conrelid = $1::regclass
                    AND confdeltype = 'c'  -- 'c' = CASCADE
                    AND conname LIKE $2
                )
            """
            constraint_name = f"fk_{table_name}_{column_name}"
            has_cascade = await conn.fetchval(
                check_query,
                table_name,
                f"%{constraint_name}%"
            )

            if not has_cascade:
                # Drop existing constraint if it exists (without CASCADE)
                drop_constraint_query = """
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = $1::regclass
                    AND conname LIKE $2
                """
                existing_constraint = await conn.fetchval(
                    drop_constraint_query,
                    table_name,
                    f"%{column_name}%"
                )

                if existing_constraint:
                    await conn.execute(
                        f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {existing_constraint}'
                    )

                # Add new constraint with CASCADE
                await conn.execute(f"""
                    ALTER TABLE {table_name}
                    ADD CONSTRAINT {constraint_name}
                    FOREIGN KEY ({column_name})
                    REFERENCES {referenced_table}({referenced_column})
                    ON DELETE {on_delete}
                """)
                print(f"[OK] Fixed foreign key constraint: {table_name}.{column_name} -> {referenced_table}.{referenced_column} ON DELETE {on_delete}")
        finally:
            await cls.release_connection(conn)

    @classmethod
    async def connect(cls) -> None:
        """Create connection pool and initialize database if needed."""
        if cls._pool is None:
            # Try to create database first
            if not cls._initialized:
                await cls._create_database_if_not_exists()

            cls._pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

            # Create tables if not exists
            if not cls._initialized:
                await cls._create_tables_if_not_exists()
                cls._initialized = True

    @classmethod
    async def disconnect(cls) -> None:
        """Close connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @classmethod
    async def get_connection(cls) -> asyncpg.Connection:
        """Get a connection from the pool."""
        if cls._pool is None:
            await cls.connect()
        return await cls._pool.acquire()  # type: ignore

    @classmethod
    async def release_connection(cls, conn: asyncpg.Connection) -> None:
        """Release a connection back to the pool."""
        if cls._pool:
            await cls._pool.release(conn)

    @classmethod
    def connection(cls):
        """Async context manager for database connections.

        Usage:
            async with Database.connection() as conn:
                await conn.execute("...")
        """
        class _ConnectionContextManager:
            def __init__(self):
                self._conn = None

            async def __aenter__(self) -> asyncpg.Connection:
                self._conn = await cls.get_connection()
                return self._conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if self._conn:
                    await cls.release_connection(self._conn)

        return _ConnectionContextManager()


# Conversation operations
async def create_conversation_ext(
    conn: asyncpg.Connection,
    conv_id: UUID,
    title: str = "新对话",
    user_id: str = None
) -> None:
    """Create a conversation with a specific ID (for external use).

    Args:
        conn: Database connection
        conv_id: Conversation ID to use
        title: Conversation title
        user_id: Optional user ID to associate with conversation
    """
    if user_id:
        await conn.execute(
            """INSERT INTO conversations (id, title, user_id, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $4)
               ON CONFLICT (id) DO UPDATE SET updated_at = $4""",
            conv_id, title, user_id, datetime.utcnow()
        )
    else:
        await conn.execute(
            """INSERT INTO conversations (id, title, created_at, updated_at)
               VALUES ($1, $2, $3, $3)
               ON CONFLICT (id) DO UPDATE SET updated_at = $3""",
            conv_id, title, datetime.utcnow()
        )


async def get_conversation_ext(conn: asyncpg.Connection, conv_id: UUID) -> Optional[dict]:
    """Get a conversation by ID (for external use).

    Args:
        conn: Database connection
        conv_id: Conversation ID

    Returns:
        Conversation dict or None if not found
    """
    row = await conn.fetchrow("SELECT * FROM conversations WHERE id = $1", conv_id)
    return dict(row) if row else None


async def create_conversation(title: str = "新对话", user_id: str = None) -> UUID:
    """Create a new conversation.

    Args:
        title: Conversation title
        user_id: Optional user ID to associate with conversation

    Returns:
        Created conversation UUID
    """
    conn = await Database.get_connection()
    try:
        conv_id = uuid4()
        if user_id:
            await conn.execute(
                """INSERT INTO conversations (id, title, user_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $4)""",
                conv_id, title, user_id, datetime.utcnow()
            )
        else:
            await conn.execute(
                """INSERT INTO conversations (id, title, created_at, updated_at)
                   VALUES ($1, $2, $3, $3)""",
                conv_id, title, datetime.utcnow()
            )
        return conv_id
    finally:
        await Database.release_connection(conn)


async def get_conversation(conv_id: UUID) -> Optional[dict]:
    """Get a conversation by ID."""
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow("SELECT * FROM conversations WHERE id = $1", conv_id)
        return dict(row) if row else None
    finally:
        await Database.release_connection(conn)


async def list_conversations(limit: int = 50) -> list[dict]:
    """List recent conversations."""
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch(
            """SELECT c.*, COUNT(m.id) as message_count
               FROM conversations c
               LEFT JOIN messages m ON c.id = m.conversation_id
               GROUP BY c.id
               ORDER BY c.updated_at DESC
               LIMIT $1""",
            limit
        )
        return [dict(row) for row in rows]
    finally:
        await Database.release_connection(conn)


# Message operations
async def create_message(
    conversation_id: UUID,
    role: str,
    content: str,
    tokens_used: Optional[int] = None
) -> UUID:
    """Create a new message."""
    conn = await Database.get_connection()
    try:
        msg_id = uuid4()
        await conn.execute(
            """INSERT INTO messages (id, conversation_id, role, content, tokens_used, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            msg_id, conversation_id, role, content, tokens_used, datetime.utcnow()
        )
        # Update conversation updated_at
        await conn.execute(
            "UPDATE conversations SET updated_at = $1 WHERE id = $2",
            datetime.utcnow(), conversation_id
        )
        return msg_id
    finally:
        await Database.release_connection(conn)


async def get_messages(conversation_id: UUID, limit: int = 100) -> list[dict]:
    """Get messages for a conversation."""
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch(
            """SELECT * FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at ASC
               LIMIT $2""",
            conversation_id, limit
        )
        return [dict(row) for row in rows]
    finally:
        await Database.release_connection(conn)


async def get_context_window(conversation_id: UUID, max_messages: int = 20, max_tokens: int = 4000) -> list[dict]:
    """Get conversation context within limits (per D-17)."""
    messages = await get_messages(conversation_id, limit=max_messages)

    # Build context list in LLM format
    context = []
    total_tokens = 0

    for msg in reversed(messages):
        # Rough token estimation (1 token ≈ 4 characters for Chinese)
        msg_tokens = len(msg["content"]) // 4

        if total_tokens + msg_tokens > max_tokens:
            break

        context.insert(0, {
            "role": msg["role"],
            "content": msg["content"]
        })
        total_tokens += msg_tokens

    return context


# Itinerary functions
async def create_itinerary(
    conversation_id: UUID,
    destination: str,
    start_date: str,
    end_date: str,
    preferences: Optional[str] = None,
    travelers: int = 1,
    budget: Optional[str] = None,
    days: Optional[list] = None
) -> UUID:
    """Create a new itinerary.

    Args:
        conversation_id: Associated conversation ID
        destination: Destination city/region
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        preferences: User preferences
        travelers: Number of travelers
        budget: Budget level
        days: List of daily plans

    Returns:
        Itinerary ID
    """
    import json
    from datetime import datetime
    itinerary_id = uuid4()

    # Convert string dates to date objects
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if isinstance(start_date, str) else start_date
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if isinstance(end_date, str) else end_date

    conn = await Database.get_connection()
    try:
        await conn.execute("""
            INSERT INTO itineraries (
                id, conversation_id, destination, start_date, end_date,
                preferences, travelers, budget, days
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, itinerary_id, conversation_id, destination, start_dt, end_dt,
            preferences, travelers, budget, json.dumps(days or []))
        return itinerary_id
    finally:
        await Database.release_connection(conn)


async def get_itinerary(itinerary_id: UUID) -> Optional[dict]:
    """Get an itinerary by ID.

    Args:
        itinerary_id: Itinerary UUID

    Returns:
        Itinerary dict or None if not found
    """
    import json
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow("""
            SELECT id, conversation_id, destination, start_date, end_date,
                   preferences, travelers, budget, days,
                   created_at, updated_at
            FROM itineraries
            WHERE id = $1
        """, itinerary_id)

        if row:
            return {
                "id": str(row["id"]),
                "conversation_id": str(row["conversation_id"]),
                "destination": row["destination"],
                "start_date": row["start_date"].isoformat() if row["start_date"] else None,
                "end_date": row["end_date"].isoformat() if row["end_date"] else None,
                "preferences": row["preferences"],
                "travelers": row["travelers"],
                "budget": row["budget"],
                "days": json.loads(row["days"]) if row["days"] else [],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat()
            }
        return None
    finally:
        await Database.release_connection(conn)


async def update_itinerary(
    itinerary_id: UUID,
    days: list
) -> bool:
    """Update itinerary days.

    Args:
        itinerary_id: Itinerary UUID
        days: Updated list of daily plans

    Returns:
        True if updated, False if not found
    """
    import json
    conn = await Database.get_connection()
    try:
        result = await conn.execute("""
            UPDATE itineraries
            SET days = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """, itinerary_id, json.dumps(days))

        return result == "UPDATE 1"
    finally:
        await Database.release_connection(conn)


async def get_conversation_itineraries(
    conversation_id: UUID,
    limit: int = 10
) -> list[dict]:
    """Get all itineraries for a conversation.

    Args:
        conversation_id: Conversation UUID
        limit: Maximum number of itineraries to return

    Returns:
        List of itinerary dicts
    """
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch("""
            SELECT id, destination, start_date, end_date,
                   preferences, travelers, budget,
                   created_at, updated_at
            FROM itineraries
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, conversation_id, limit)

        return [
            {
                "id": str(row["id"]),
                "destination": row["destination"],
                "start_date": row["start_date"].isoformat() if row["start_date"] else None,
                "end_date": row["end_date"].isoformat() if row["end_date"] else None,
                "preferences": row["preferences"],
                "travelers": row["travelers"],
                "budget": row["budget"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat()
            }
            for row in rows
        ]
    finally:
        await Database.release_connection(conn)


# User and preference operations (per D-01, D-04, D-06)
async def create_user(username: Optional[str] = None) -> str:
    """Create a new user with auto-generated UUID.

    Per D-01: UUID as user identifier.
    Per D-02: No password required.

    Args:
        username: Optional username for the user

    Returns:
        User ID (UUID string)
    """
    import json
    user_id = str(uuid4())

    conn = await Database.get_connection()
    try:
        # Create user record with username if provided
        if username:
            await conn.execute(
                """INSERT INTO users (id, username, created_at, updated_at)
                   VALUES ($1, $2, $3, $3)""",
                user_id, username, datetime.utcnow()
            )
        else:
            await conn.execute(
                """INSERT INTO users (id, created_at, updated_at)
                   VALUES ($1, $2, $2)""",
                user_id, datetime.utcnow()
            )

        # Create default preferences (per D-05)
        default_prefs = {
            "budget": None,
            "interests": [],
            "style": None,
            "travelers": 1
        }
        await conn.execute(
            """INSERT INTO user_preferences (user_id, preferences, updated_at)
               VALUES ($1, $2, $3)""",
            user_id, json.dumps(default_prefs), datetime.utcnow()
        )

        print(f"[OK] Created user: {user_id}")
        return user_id
    finally:
        await Database.release_connection(conn)


async def get_user(user_id: str) -> Optional[dict]:
    """Get a user by ID.

    Args:
        user_id: User UUID

    Returns:
        User dict or None if not found
    """
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow(
            "SELECT id, username, created_at, updated_at FROM users WHERE id = $1",
            user_id
        )
        if row:
            return {
                "id": str(row["id"]),
                "username": row["username"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return None
    finally:
        await Database.release_connection(conn)


async def update_preferences(user_id: str, preferences: dict) -> bool:
    """Update user preferences (partial update supported).

    Per D-06: JSONB field for flexible preference storage.
    Per D-07: Supports merging with existing preferences.

    Args:
        user_id: User UUID
        preferences: Preferences to update (merged with existing)

    Returns:
        True if updated, False if user not found
    """
    import json
    conn = await Database.get_connection()
    try:
        # PostgreSQL JSONB merge operator (||) for partial updates
        # Use json.dumps and cast to JSONB type
        result = await conn.execute("""
            UPDATE user_preferences
            SET preferences = preferences || $2::jsonb,
                updated_at = NOW()
            WHERE user_id = $1
        """, user_id, json.dumps(preferences))

        success = result == "UPDATE 1"
        if success:
            print(f"[OK] Updated preferences for user: {user_id}")
        return success
    finally:
        await Database.release_connection(conn)


async def get_preferences(user_id: str) -> Optional[dict]:
    """Get user preferences.

    Args:
        user_id: User UUID

    Returns:
        Preferences dict or None if not found
    """
    import json
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow(
            "SELECT preferences, updated_at FROM user_preferences WHERE user_id = $1",
            user_id
        )
        if row:
            prefs = row["preferences"]
            # asyncpg returns JSONB as string, need to parse
            if isinstance(prefs, str):
                prefs = json.loads(prefs)
            prefs["updated_at"] = row["updated_at"].isoformat()
            return prefs
        return None
    finally:
        await Database.release_connection(conn)


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
            "SELECT id, user_id, email, phone, password_hash, email_verified, phone_verified, created_at, updated_at FROM user_credentials WHERE email = $1",
            email
        )
        if row:
            return {
                "id": str(row["id"]),
                "user_id": str(row["user_id"]),
                "email": row["email"],
                "phone": row["phone"],
                "password_hash": row["password_hash"],
                "email_verified": row["email_verified"],
                "phone_verified": row["phone_verified"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
        return None
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
        """, token_id, user_id, token_hash, jti, user_agent, ip_address, expires_at)
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


# ============================================================
# Phase 2: Message Storage Extensions
# ============================================================

async def get_recent_messages(
    user_id: str,
    limit: int = 20
) -> list[dict]:
    """Get recent messages for a user across all conversations.

    Args:
        user_id: User UUID
        limit: Max messages to return

    Returns:
        List of message dicts, newest first
    """
    conn = await Database.get_connection()
    try:
        rows = await conn.fetch("""
            SELECT m.id, m.conversation_id, c.user_id, m.role, m.content,
                   COALESCE(m.tokens_used, 0) as tokens, m.created_at
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.user_id = $1
            ORDER BY m.created_at DESC
            LIMIT $2
        """, user_id, limit)

        return [
            {
                "id": str(row["id"]),
                "conversation_id": str(row["conversation_id"]),
                "user_id": str(row["user_id"]),
                "role": row["role"],
                "content": row["content"],
                "tokens": row["tokens"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
    finally:
        await Database.release_connection(conn)


async def create_message_ext(
    conn,
    conversation_id: UUID,
    user_id: str,
    role: str,
    content: str,
    tokens: int = 0,
) -> dict:
    """Create a message record (for use within existing transactions).

    This version takes a connection parameter for use in repository
    implementations that manage their own connections.

    Args:
        conn: Database connection
        conversation_id: Conversation UUID
        user_id: User ID
        role: Message role (user/assistant/system)
        content: Message content
        tokens: Estimated token count

    Returns:
        Created message record as dict
    """
    message_id = uuid4()
    now = datetime.utcnow()

    await conn.execute(
        """
        INSERT INTO messages (id, conversation_id, role, content, tokens_used, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        message_id, conversation_id, role, content, tokens, now
    )

    return {
        "id": str(message_id),
        "conversation_id": str(conversation_id),
        "user_id": user_id,
        "role": role,
        "content": content,
        "tokens": tokens,
        "created_at": now.isoformat(),
    }


async def get_messages_ext(
    conn,
    conversation_id: UUID,
    limit: int = 50,
) -> list[dict]:
    """Get messages for a conversation (for use within existing transactions).

    Args:
        conn: Database connection
        conversation_id: Conversation UUID
        limit: Max messages to return

    Returns:
        List of message dicts
    """
    rows = await conn.fetch(
        """
        SELECT id, conversation_id, role, content,
               COALESCE(tokens_used, 0) as tokens, created_at
        FROM messages
        WHERE conversation_id = $1
        ORDER BY created_at ASC
        LIMIT $2
        """,
        conversation_id, limit
    )

    return [
        {
            "id": str(row["id"]),
            "conversation_id": str(row["conversation_id"]),
            "role": row["role"],
            "content": row["content"],
            "tokens": row["tokens"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


# ============================================================
# Phase 2: Conversation State (Episodic Memory)
# ============================================================

async def upsert_conversation_state(
    conn,
    conversation_id: UUID,
    user_id: UUID,
    state_data: dict,
) -> bool:
    """Create or update conversation state.

    This version takes a connection parameter for use in repository
    implementations that manage their own connections.

    Args:
        conn: Database connection
        conversation_id: Conversation UUID
        user_id: User UUID
        state_data: State data to merge

    Returns:
        True if successful
    """
    import json
    await conn.execute(
        """
        INSERT INTO conversation_states (conversation_id, user_id, state_data, updated_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (conversation_id)
        DO UPDATE SET
            state_data = conversation_states.state_data || $3::jsonb,
            updated_at = NOW()
        """,
        conversation_id, user_id, json.dumps(state_data)
    )

    return True


async def get_conversation_state(
    conn,
    conversation_id: UUID,
) -> dict | None:
    """Get conversation state.

    This version takes a connection parameter for use in repository
    implementations that manage their own connections.

    Args:
        conn: Database connection
        conversation_id: Conversation UUID

    Returns:
        State data dict or None
    """
    row = await conn.fetchrow(
        """
        SELECT conversation_id, user_id, state_data, updated_at
        FROM conversation_states
        WHERE conversation_id = $1
        """,
        conversation_id
    )

    if not row:
        return None

    import json
    state_data = row["state_data"]
    if isinstance(state_data, str):
        state_data = json.loads(state_data)

    return {
        "conversation_id": str(row["conversation_id"]),
        "user_id": str(row["user_id"]),
        "state_data": state_data,
        "updated_at": row["updated_at"].isoformat(),
    }

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

            print("[OK] Database tables initialized")
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


# Conversation operations
async def create_conversation(title: str = "新对话") -> UUID:
    """Create a new conversation."""
    conn = await Database.get_connection()
    try:
        conv_id = uuid4()
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


# User and preference operations (per D-01, D-04, D-06)
async def create_user() -> str:
    """Create a new user with auto-generated UUID.

    Per D-01: UUID as user identifier.
    Per D-02: No password required.

    Returns:
        User ID (UUID string)
    """
    import json
    user_id = str(uuid4())

    conn = await Database.get_connection()
    try:
        # Create user record
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
            "SELECT * FROM users WHERE id = $1",
            user_id
        )
        return dict(row) if row else None
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
        result = await conn.execute("""
            UPDATE user_preferences
            SET preferences = preferences || $2,
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
    conn = await Database.get_connection()
    try:
        row = await conn.fetchrow(
            "SELECT preferences, updated_at FROM user_preferences WHERE user_id = $1",
            user_id
        )
        if row:
            prefs = dict(row["preferences"])
            prefs["updated_at"] = row["updated_at"].isoformat()
            return prefs
        return None
    finally:
        await Database.release_connection(conn)
    finally:
        await Database.release_connection(conn)

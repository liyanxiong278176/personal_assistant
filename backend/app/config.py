"""Application configuration using pydantic settings."""
import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    app_name: str = Field(default="Travel Assistant", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment name")

    # Database
    database_url: str = Field(
        default="postgresql://user:pass@localhost:5432/travel_assistant",
        description="PostgreSQL connection URL"
    )

    # ChromaDB
    chromadb_path: str = Field(
        default="./data/chroma_db",
        description="ChromaDB persistent storage path"
    )

    # Persistence
    persistence_max_retries: int = Field(default=3, description="Max retry attempts for persistence")
    persistence_queue_size: int = Field(default=1000, description="Retry queue max size")
    persistence_fallback_path: str = Field(
        default="failed_messages.jsonl",
        description="Fallback file for failed messages"
    )

    # LLM
    llm_api_key: Optional[str] = Field(default=None, description="LLM API key")
    llm_model: str = Field(default="deepseek-chat", description="LLM model name")
    llm_base_url: str = Field(default="https://api.deepseek.com/v1", description="LLM base URL")

    # Context
    context_window_size: int = Field(default=16000, description="LLM context window size")
    context_soft_trim_ratio: float = Field(default=0.3, description="Soft trim ratio")
    context_hard_clear_ratio: float = Field(default=0.5, description="Hard clear ratio")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()

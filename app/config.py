import os
import re
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str = Field(
        default="9013281225:AAH3xMNCDSXMttbG2NKlaYJjrz1vfR8JbRs",
        description="Telegram Bot API Token",
    )
    DATABASE_URL: str = Field(
        default="postgresql://neondb_owner:npg_r4RjlB9MsAyU@ep-falling-cake-bfmmp1a0.c-5.us-west-2.aws.neon.tech/neondb?sslmode=require",
        description="PostgreSQL async connection string",
    )
    WEBHOOK_SECRET: str = Field(
        default="ultra_giveaway_secret_token_secure_9013281225",
        description="Secret token for verifying Telegram webhook",
    )
    WEBHOOK_BASE_URL: str = Field(
        default="",
        description="Public HTTPS URL for Render / ngrok",
    )
    ADMIN_CHAT_ID: int = Field(default=6999627465, description="Primary Admin Telegram ID")
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    PORT: int = Field(default=8000, description="Port to listen on")

    DATABASE_POOL_SIZE: int = Field(default=5, description="Maximum DB pool connections")
    DATABASE_MAX_OVERFLOW: int = Field(default=0, description="Max overflow connections")
    DATABASE_POOL_TIMEOUT: int = Field(default=30, description="Pool connection timeout in seconds")

    WEBHOOK_PATH: str = Field(default="/webhook", description="Path for Telegram webhook")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("WEBHOOK_SECRET", mode="before")
    @classmethod
    def sanitize_webhook_secret(cls, v: Optional[str]) -> str:
        if not v:
            return "ultra_giveaway_secret_token_secure_9013281225"
        # Telegram API strictly allows only characters: A-Z, a-z, 0-9, _ and -
        cleaned = re.sub(r'[^A-Za-z0-9_-]', '_', str(v).strip().strip('"').strip("'"))
        if not cleaned or len(cleaned) < 8:
            return "ultra_giveaway_secret_token_secure_9013281225"
        return cleaned[:256]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        if not v:
            return v
        url = v.strip().strip('"').strip("'")
        # Convert postgres:// or postgresql:// to postgresql+asyncpg://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        # asyncpg prefers ssl=require or ssl in query params rather than sslmode
        # but SQLAlchemy query params pass through to asyncpg. Replace sslmode= with ssl=
        url = re.sub(r'([?&])sslmode=', r'\1ssl=', url)
        # asyncpg does not use channel_binding as a connection argument; strip to avoid warnings/errors
        url = re.sub(r'([?&])channel_binding=[^&]*', '', url)
        url = url.replace('?&', '?').rstrip('?&')
        return url

    @field_validator("WEBHOOK_BASE_URL", mode="before")
    @classmethod
    def clean_webhook_base_url(cls, v: Optional[str]) -> str:
        url = (v or "").strip().strip('"').strip("'")
        if not url:
            # Check Render standard environment variable
            url = os.environ.get("RENDER_EXTERNAL_URL", "https://ultra-giveaway-bot.onrender.com")
        return url.rstrip("/")

    @property
    def full_webhook_url(self) -> str:
        return f"{self.WEBHOOK_BASE_URL}{self.WEBHOOK_PATH}"


settings = Settings()

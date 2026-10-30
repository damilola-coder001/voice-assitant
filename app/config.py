import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application Settings
    APP_NAME: str = "NORE"
    APP_ENV: str = "development"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000"

    # ElevenLabs Server Secrets (NEVER expose to client)
    ELEVENLABS_API_KEY: str = Field(default="", description="Server-side secret key for ElevenLabs API")
    ELEVENLABS_BASE_URL: str = "https://api.elevenlabs.io/v1"
    ELEVENLABS_DEFAULT_VOICE_ID: str = "CwhRBWXzGAHq8TQ4Fs17"  # Roger (or Rachel 21m00Tcm4TlvDq8ikWAM)
    ELEVENLABS_DEFAULT_MODEL_ID: str = "eleven_turbo_v2_5"

    # Optional External LLM Integration (OpenAI, Groq, Ollama, Gemini, etc.)
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="Optional OpenAI or OpenAI-compatible API key")
    LLM_BASE_URL: str = Field(default="https://api.openai.com/v1", description="LLM Base URL")
    LLM_MODEL: str = Field(default="gpt-4o-mini", description="LLM model identifier")
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Optional Google Gemini API key")

    # Authentication & JWT
    JWT_SECRET_KEY: str = Field(
        default="test_jwt_secret_key_12345678901234567890123456789012",
        description="Secret key for signing JWT tokens",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Initial Owner Credentials (Secured First-Run)
    OWNER_INITIAL_EMAIL: Optional[str] = "owner@nore.ai"
    OWNER_INITIAL_PASSWORD: Optional[str] = "NoreOwner#2026!Master"

    # Access Control & RBAC Configuration
    ENABLE_RBAC: bool = Field(
        default=False,
        description="Enable role-based access control restrictions. When False (dormant), all authenticated users have access without role hierarchy gating.",
    )
    ENABLE_AUTH: bool = Field(
        default=False,
        description="Enable authentication barrier. When False (dormant), guest access is enabled automatically for instant testing without login.",
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./voice_assistant.db"

    # Optional Redis
    REDIS_URL: Optional[str] = None

    # Quotas & Rate Limits
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 120
    DEFAULT_DAILY_CHARACTER_QUOTA: int = 50000

    # Technology Intelligence & Web Search
    BRAVE_SEARCH_API_KEY: Optional[str] = Field(default=None, description="Optional Brave Search API key")
    TAVILY_API_KEY: Optional[str] = Field(default=None, description="Optional Tavily Search API key")
    TECH_SEARCH_PROVIDER: str = Field(default="auto", description="Search provider: auto, duckduckgo, brave, tavily, tech_feeds")
    TECH_SEARCH_MAX_RESULTS: int = 6
    TECH_CACHE_TTL_SECONDS: int = 600

    @property
    def is_serverless(self) -> bool:
        return bool(
            os.environ.get("VERCEL")
            or os.environ.get("VERCEL_ENV")
            or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
            or not os.access(".", os.W_OK)
        )

    @property
    def effective_database_url(self) -> str:
        # On Vercel / Lambda serverless, root filesystem (/var/task) is read-only.
        # Fall back to /tmp if SQLite is used without an external database URL.
        if self.is_serverless and (
            self.DATABASE_URL == "sqlite+aiosqlite:///./voice_assistant.db"
            or not self.DATABASE_URL
        ):
            return "sqlite+aiosqlite:////tmp/voice_assistant.db"
        # Support standard PostgreSQL URL format by converting to postgresql+asyncpg
        if self.DATABASE_URL.startswith("postgres://"):
            return self.DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
        if self.DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in self.DATABASE_URL:
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.DATABASE_URL

    @property
    def allowed_origins_list(self) -> List[str]:
        origins = [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]
        if self.is_serverless:
            origins.append("https://*.vercel.app")
        return origins

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    def masked_elevenlabs_key(self) -> str:
        """Safe masked display of ElevenLabs key for admin diagnosis."""
        if not self.ELEVENLABS_API_KEY:
            return "NOT_CONFIGURED"
        if len(self.ELEVENLABS_API_KEY) <= 8:
            return "***"
        return f"{self.ELEVENLABS_API_KEY[:4]}...{self.ELEVENLABS_API_KEY[-4:]}"

    def masked_search_key(self, key_val: Optional[str]) -> str:
        """Safe masked display of Search API keys."""
        if not key_val:
            return "NOT_CONFIGURED"
        if len(key_val) <= 8:
            return "***"
        return f"{key_val[:4]}...{key_val[-4:]}"

settings = Settings()


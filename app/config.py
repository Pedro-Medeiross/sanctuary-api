from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/discord_bot"

    # API Auth
    API_USER: str = "bot_user"
    API_PASS: str = "bot_pass_secure"

    # Discord OAuth2
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""
    DISCORD_REDIRECT_URI: str = "https://nolvusapp.com.br/auth/callback"
    DISCORD_BOT_TOKEN: str = ""

    # Google OAuth2
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MongoDB
    MONGODB_URL: str = "mongodb://admin:password@localhost:27017"
    MONGODB_DB: str = "sanctuary_logs"

    # App
    APP_NAME: str = "Sanctuary API"
    DEBUG: bool = False
    FRONTEND_URL: str = "https://nolvusapp.com.br"
    API_URL: str = "https://api.nolvusapp.com.br"
    BOT_URL: str = "https://bot.nolvusapp.com.br"

    @property
    def allowed_origins(self) -> List[str]:
        return [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "https://nolvusapp.com.br",
            "https://www.nolvusapp.com.br",
            "https://api.nolvusapp.com.br",
            "https://bot.nolvusapp.com.br",
        ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
# app/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/discord_bot"
    
    # API Auth (Basic Auth for Bot)
    API_USER: str = "bot_user"
    API_PASS: str = "bot_pass_secure"
    
    # Discord OAuth2
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""
    DISCORD_REDIRECT_URI: str = "http://localhost:3001/auth/callback"
    DISCORD_BOT_TOKEN: str = ""  # ← ADICIONAR
    
    # Google OAuth2 (futuro)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None  # ← ADICIONAR
    
    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # App
    APP_NAME: str = "Sanctuary API"
    DEBUG: bool = True
    FRONTEND_URL: str = "http://localhost:3001"
    API_URL: str = "http://localhost:8000"  # ← ADICIONAR
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # ← ADICIONAR (ignora campos extras do .env)

settings = Settings()
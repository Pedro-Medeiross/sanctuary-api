# app/config.py (atualizado)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/discord_bot"
    
    # API Auth (Basic Auth for Bot)
    API_USER: str = "bot_user"
    API_PASS: str = "bot_pass_secure"
    
    # Discord OAuth2
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""
    DISCORD_REDIRECT_URI: str = "http://localhost:3000/auth/callback"
    
    # JWT
    JWT_SECRET_KEY: str = "your-super-secret-jwt-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # App
    APP_NAME: str = "Discord Bot API"
    DEBUG: bool = True
    FRONTEND_URL: str = "http://localhost:3000"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
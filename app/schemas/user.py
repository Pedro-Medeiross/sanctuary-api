# app/schemas/user.py (atualizado)
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserResponse(BaseModel):
    id: int
    username: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool = False
    last_login: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class DiscordAuthRequest(BaseModel):
    code: str
    redirect_uri: str
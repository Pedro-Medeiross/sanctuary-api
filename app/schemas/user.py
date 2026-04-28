from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime
import uuid

class UserRegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    confirm_password: str
    
    @field_validator('username')
    @classmethod
    def username_min_length(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError('Username deve ter no mínimo 3 caracteres')
        return v.lower()
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Senhas não conferem')
        return v

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    roles: List[str] = []
    discord_id: Optional[int] = None
    google_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
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

class GoogleAuthRequest(BaseModel):
    code: str
    redirect_uri: str

class LinkDiscordRequest(BaseModel):
    code: str
    redirect_uri: str

class LinkGoogleRequest(BaseModel):
    code: str
    redirect_uri: str
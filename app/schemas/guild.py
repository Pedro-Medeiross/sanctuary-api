# app/schemas/guild.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class GuildResponse(BaseModel):
    id: int
    prefix: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class PrefixUpdate(BaseModel):
    prefix: str = Field(..., min_length=1, max_length=10)

class PrefixResponse(BaseModel):
    prefix: str
    guild_id: int
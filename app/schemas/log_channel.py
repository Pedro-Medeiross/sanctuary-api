# app/schemas/log_channel.py
from pydantic import BaseModel, Field
from typing import Optional, Dict

VALID_LOG_TYPES = [
    "voice", "message_delete", "message_edit", "message_pin",
    "member_join", "member_leave", "member_ban", "member_unban",
    "member_timeout", "member_nickname", "member_roles",
    "channel_create", "channel_delete", "channel_edit",
    "role_create", "role_delete", "role_update",
    "guild_update", "invite_create", "invite_delete"
]

class LogChannelResponse(BaseModel):
    log_type: str
    channel_id: Optional[int] = None
    enabled: bool = True

class SingleLogChannelResponse(BaseModel):
    channel_id: Optional[int] = None

class LogChannelsList(BaseModel):
    guild_id: int
    channels: Dict[str, Optional[int]]

class LogChannelUpdate(BaseModel):
    channels: Dict[str, Optional[int]] = Field(
        ...,
        description="Dict with log_type as key and channel_id as value"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "channels": {
                    "voice": 123456789,
                    "message_delete": 123456790,
                    "member_join": None
                }
            }
        }
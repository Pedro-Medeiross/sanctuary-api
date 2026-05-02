# app/schemas/log_channel.py
from pydantic import BaseModel, Field
from typing import Optional, Dict

VALID_LOG_TYPES = [
    # Message Events
    "message_delete",
    "message_edit",
    "image_delete",
    "bulk_message_delete",
    "log_invites",
    "moderator_commands",
    
    # Member Events
    "member_join",
    "member_leave",
    "member_role_add",
    "member_role_remove",
    "member_timeout",
    "member_nickname",
    "member_ban",
    "member_unban",
    "member_avatar_update",
    
    # Role Events
    "role_create",
    "role_delete",
    "role_update",
    
    # Channel Events
    "channel_create",
    "channel_update",
    "channel_delete",
    
    # Emoji Events
    "emoji_create",
    "emoji_name_change",
    "emoji_delete",
    
    # Voice Events
    "voice_join",
    "voice_leave",
    "voice_move",
    
    # Server Events
    "guild_update",
    "server_avatar_update",
    "server_banner_update",
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
                    "message_delete": 123456789,
                    "member_join": 123456790,
                }
            }
        }
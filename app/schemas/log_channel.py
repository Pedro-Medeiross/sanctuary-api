from pydantic import BaseModel, Field
from typing import Optional, Dict


# Mantém como referência/documentação, mas não valida mais
LOG_TYPES_REFERENCE = [
    "message_delete", "message_edit", "image_delete",
    "bulk_message_delete", "log_invites", "mod_commands",
    "member_join", "member_leave", "member_role_add", "member_role_remove",
    "member_timeout", "nickname_change", "member_ban", "member_unban", "avatar_update",
    "role_create", "role_delete", "role_update",
    "channel_create", "channel_update", "channel_delete",
    "emoji_create", "emoji_name_change", "emoji_delete",
    "voice_join", "voice_leave", "voice_move",
    "guild_update", "server_avatar_update", "server_banner_update",
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
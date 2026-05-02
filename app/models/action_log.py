# app/models/action_log.py
from datetime import datetime, timezone
from typing import Optional, Dict, Any

class ActionLog:
    """Modelo para logs de ação (MongoDB)"""
    
    def __init__(
        self,
        guild_id: int,
        log_type: str,
        user_id: Optional[int] = None,
        target_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None
    ):
        self.guild_id = guild_id
        self.log_type = log_type
        self.user_id = user_id
        self.target_id = target_id
        self.channel_id = channel_id
        self.data = data or {}
        self.created_at = created_at or datetime.now(timezone.utc)  # ← UTC
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "log_type": self.log_type,
            "user_id": self.user_id,
            "target_id": self.target_id,
            "channel_id": self.channel_id,
            "data": self.data,
            "created_at": self.created_at
        }
    
    @staticmethod
    def from_dict(doc: Dict[str, Any]) -> "ActionLog":
        created_at = doc.get("created_at")
        # Garantir timezone se vier sem
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        
        return ActionLog(
            guild_id=doc.get("guild_id"),
            log_type=doc.get("log_type"),
            user_id=doc.get("user_id"),
            target_id=doc.get("target_id"),
            channel_id=doc.get("channel_id"),
            data=doc.get("data", {}),
            created_at=created_at
        )
    
    def to_response(self) -> Dict[str, Any]:
        return {
            "id": str(self.id) if hasattr(self, 'id') else None,
            "guild_id": str(self.guild_id),
            "log_type": self.log_type,
            "user_id": str(self.user_id) if self.user_id else None,
            "target_id": str(self.target_id) if self.target_id else None,
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "data": self.data,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
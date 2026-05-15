from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ActionLog:
    """Modelo para logs de ação (MongoDB)"""
    guild_id: int
    log_type: str
    user_id: Optional[int] = None
    target_id: Optional[int] = None
    channel_id: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    _id: Optional[str] = None
    
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
    
    @classmethod
    def from_dict(cls, doc: Dict[str, Any]) -> "ActionLog":
        created_at = doc.get("created_at")
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        
        log = cls(
            guild_id=doc.get("guild_id"),
            log_type=doc.get("log_type"),
            user_id=doc.get("user_id"),
            target_id=doc.get("target_id"),
            channel_id=doc.get("channel_id"),
            data=doc.get("data", {}),
            created_at=created_at
        )
        log._id = str(doc.get("_id", ""))
        return log
    
    def to_response(self) -> Dict[str, Any]:
        return {
            "id": self._id or None,
            "guild_id": str(self.guild_id),
            "log_type": self.log_type,
            "user_id": str(self.user_id) if self.user_id else None,
            "target_id": str(self.target_id) if self.target_id else None,
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "data": self.data,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
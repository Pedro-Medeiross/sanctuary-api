# app/models/guild_stats.py
from sqlalchemy import BigInteger, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.guild import Guild

class GuildStats(Base):
    __tablename__ = "guild_stats"
    
    guild_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("guilds.id", ondelete="CASCADE"),
        primary_key=True
    )
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    online_count: Mapped[int] = mapped_column(Integer, default=0)
    channel_count: Mapped[int] = mapped_column(Integer, default=0)
    role_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    guild: Mapped["Guild"] = relationship("Guild")
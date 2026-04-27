# app/models/guild.py
from sqlalchemy import BigInteger, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.database import Base
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.log_channel import LogChannel

class Guild(Base):
    __tablename__ = "guilds"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prefix: Mapped[str] = mapped_column(String(10), default="!")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    log_channels: Mapped[List["LogChannel"]] = relationship(
        "LogChannel", 
        back_populates="guild", 
        cascade="all, delete-orphan"
    )
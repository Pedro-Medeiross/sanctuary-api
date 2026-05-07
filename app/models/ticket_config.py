from sqlalchemy import BigInteger, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.database import Base
from typing import Optional

class TicketConfig(Base):
    __tablename__ = "ticket_configs"
    
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    max_open_tickets: Mapped[int] = mapped_column(Integer, default=5)
    auto_close_hours: Mapped[int] = mapped_column(Integer, default=72)
    allow_user_close: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_attachments: Mapped[bool] = mapped_column(Boolean, default=True)
    transcript_channel: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
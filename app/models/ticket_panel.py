from sqlalchemy import BigInteger, Integer, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.database import Base
from typing import Optional, Dict, Any
import uuid

class TicketPanel(Base):
    __tablename__ = "ticket_panels"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    button_label: Mapped[str] = mapped_column(String(80), default="Abrir Ticket")
    button_color: Mapped[str] = mapped_column(String(20), default="green")
    category_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    support_roles: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    form_fields: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
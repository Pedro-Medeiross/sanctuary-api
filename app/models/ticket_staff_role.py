from sqlalchemy import BigInteger, Integer, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.database import Base
from typing import Optional
import uuid

class TicketStaffRole(Base):
    __tablename__ = "ticket_staff_roles"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1)
    can_claim: Mapped[bool] = mapped_column(Boolean, default=False)
    can_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    can_add_users: Mapped[bool] = mapped_column(Boolean, default=False)
    can_remove_users: Mapped[bool] = mapped_column(Boolean, default=False)
    can_ban_users: Mapped[bool] = mapped_column(Boolean, default=False)
    can_view_all: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_panels: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_config: Mapped[bool] = mapped_column(Boolean, default=False)
    is_trainee: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
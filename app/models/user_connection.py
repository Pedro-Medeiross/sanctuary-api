import uuid
from sqlalchemy import String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.database import Base
from typing import TYPE_CHECKING
import enum

if TYPE_CHECKING:
    from app.models.user import User

class ConnectionProvider(str, enum.Enum):
    DISCORD = "discord"
    GOOGLE = "google"

class UserConnection(Base):
    __tablename__ = "user_connections"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    provider: Mapped[ConnectionProvider] = mapped_column(
        SQLEnum(ConnectionProvider), 
        nullable=False
    )
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token: Mapped[str] = mapped_column(String, nullable=True)
    refresh_token: Mapped[str] = mapped_column(String, nullable=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Metadados do provider
    provider_username: Mapped[str] = mapped_column(String(100), nullable=True)
    provider_email: Mapped[str] = mapped_column(String(255), nullable=True)
    provider_avatar: Mapped[str] = mapped_column(String(500), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(default=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    
    user: Mapped["User"] = relationship("User", back_populates="connections")
# app/models/log_channel.py
from sqlalchemy import BigInteger, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.guild import Guild

class LogChannel(Base):
    __tablename__ = "log_channels"
    __table_args__ = (
        UniqueConstraint('guild_id', 'log_type', name='uq_guild_log_type'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("guilds.id", ondelete="CASCADE"),
        nullable=False
    )
    log_type: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    guild: Mapped["Guild"] = relationship("Guild", back_populates="log_channels")
# app/routes/tickets/bot.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from app.database import get_db
from app.models.tickets.ticket import Ticket, TicketStatus, TicketPriority
from app.models.tickets.ticket_config import TicketConfig
from app.models.tickets.ticket_staff_role import TicketStaffRole
from app.models.tickets.ticket_panel import TicketPanel
from app.models.tickets.ticket_member import TicketMember
from app.models.tickets.ticket_transfer import TicketTransfer
from app.models.tickets.ticket_ban import TicketBan
from app.models.tickets.ticket_category import TicketCategory
from app.schemas.ticket import (
    StaffRoleResponse, TicketPanelResponse,
    TicketBanResponse, TicketCategoryResponse, TicketConfigResponse,
)
from app.utils.security import verify_bot_auth
from app.services.websocket_manager import ws_manager
from app.config import settings
from app.services.bot_notifier import (
    notify_ticket_created, notify_ticket_closed, notify_ticket_claimed
)

router = APIRouter(prefix="/guilds", tags=["Tickets Bot"])


def _get_or_404(result, name: str = "Recurso"):
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, f"{name} não encontrado")
    return obj


# ============ CONFIG ============

@router.get("/{guild_id}/tickets/bot/config", response_model=TicketConfigResponse)
async def get_ticket_config_bot(
    guild_id: int,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketConfig).where(TicketConfig.guild_id == guild_id))
    config = result.scalar_one_or_none()
    if not config:
        config = TicketConfig(guild_id=guild_id)
        db.add(config)
        await db.commit()
    return TicketConfigResponse.model_validate(config)


# ============ STAFF ROLES ============

@router.get("/{guild_id}/tickets/bot/staff-roles", response_model=List[StaffRoleResponse])
async def get_staff_roles_bot(
    guild_id: int,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketStaffRole).where(TicketStaffRole.guild_id == guild_id))
    return [StaffRoleResponse.model_validate(r) for r in result.scalars().all()]


# ============ CATEGORIAS ============

@router.get("/{guild_id}/tickets/bot/categories", response_model=List[TicketCategoryResponse])
async def get_categories_bot(
    guild_id: int,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketCategory)
        .where(TicketCategory.guild_id == guild_id, TicketCategory.is_active == True)
        .order_by(TicketCategory.position)
    )
    return [TicketCategoryResponse.model_validate(c) for c in result.scalars().all()]


# ============ PAINÉIS ============

@router.get("/{guild_id}/tickets/panels/{panel_id}", response_model=TicketPanelResponse)
async def get_panel_bot(
    guild_id: int,
    panel_id: uuid.UUID,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketPanel).where(TicketPanel.id == panel_id, TicketPanel.guild_id == guild_id))
    return TicketPanelResponse.model_validate(_get_or_404(result, "Painel"))


@router.put("/{guild_id}/tickets/panels/{panel_id}/message")
async def update_panel_message(
    guild_id: int,
    panel_id: uuid.UUID,
    message_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketPanel).where(TicketPanel.id == panel_id, TicketPanel.guild_id == guild_id))
    panel = _get_or_404(result, "Painel")
    panel.message_id = message_data.get("message_id")
    await db.commit()
    return {"message": "Message ID atualizado", "panel_id": str(panel.id)}


# ============ TICKETS ============

@router.post("/{guild_id}/tickets/open")
async def open_ticket(
    guild_id: int,
    ticket_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    user_id = int(ticket_data.get("user_id"))
    channel_id = int(ticket_data.get("channel_id"))
    panel_id = ticket_data.get("panel_id")
    priority = ticket_data.get("priority", "medium")
    if priority not in ["low", "medium", "high", "urgent"]:
        priority = "medium"

    result = await db.execute(select(TicketConfig).where(TicketConfig.guild_id == guild_id))
    config = result.scalar_one_or_none()
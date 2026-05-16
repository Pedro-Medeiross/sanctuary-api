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

@router.get("/{guild_id}/tickets/bot/panels")
async def get_panels_bot(
    guild_id: int,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Lista painéis ativos com categorias"""
    result = await db.execute(
        select(TicketPanel).where(
            TicketPanel.guild_id == guild_id,
            TicketPanel.is_active == True
        )
    )
    panels = result.scalars().all()
    
    return [
        {
            "id": str(p.id),
            "title": p.title,
            "description": p.description,
            "button_label": p.button_label,
            "button_color": p.button_color,
            "channel_id": str(p.channel_id) if p.channel_id else None,
            "category_id": str(p.category_id) if p.category_id else None,
            "message_id": str(p.message_id) if p.message_id else None,
            "is_active": p.is_active,
        }
        for p in panels
    ]

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
    """[Bot] Abre um novo ticket com número sequencial"""
    user_id = int(ticket_data.get("user_id"))
    channel_id = int(ticket_data.get("channel_id"))
    panel_id = ticket_data.get("panel_id")
    priority = ticket_data.get("priority", "medium")
    if priority not in ["low", "medium", "high", "urgent"]:
        priority = "medium"

    # Incrementar contador
    result = await db.execute(select(TicketConfig).where(TicketConfig.guild_id == guild_id))
    config = result.scalar_one_or_none()
    if not config:
        config = TicketConfig(guild_id=guild_id)
        db.add(config)
        await db.flush()

    config.ticket_counter += 1
    ticket_number = config.ticket_counter

    ticket = Ticket(
        guild_id=guild_id,
        ticket_number=ticket_number,
        panel_id=uuid.UUID(panel_id) if panel_id else None,
        channel_id=channel_id,
        user_id=user_id,
        priority=TicketPriority(priority),
    )
    db.add(ticket)
    await db.commit()

    # Notificar WebSocket
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_created",
        "ticket": {
            "id": str(ticket.id), "guild_id": str(guild_id),
            "ticket_number": ticket_number, "channel_id": str(channel_id),
            "user_id": str(user_id), "status": "open",
            "priority": priority, "created_at": ticket.created_at.isoformat()
        }
    })

    # Notificar bot (webhook)
    await notify_ticket_created(guild_id, {
        "id": ticket.id, "channel_id": ticket.channel_id, "user_id": ticket.user_id,
    })

    return {"id": str(ticket.id), "ticket_number": ticket_number, "created_at": ticket.created_at.isoformat()}


@router.put("/{guild_id}/tickets/{ticket_id}/claim")
async def claim_ticket(
    guild_id: int,
    ticket_id: uuid.UUID,
    claim_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Reinvindica um ticket"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    staff_id = int(claim_data.get("staff_id"))
    ticket.claimed_by = staff_id
    ticket.status = TicketStatus.CLAIMED
    ticket.last_activity_at = datetime.now(timezone.utc)
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_claimed", "ticket_id": str(ticket_id), "claimed_by": str(staff_id)
    })
    await notify_ticket_claimed(guild_id, str(ticket_id), str(staff_id))
    return {"message": "Ticket reinvindicado"}


@router.post("/{guild_id}/tickets/{ticket_id}/bot/close")
async def close_ticket_bot(
    guild_id: int,
    ticket_id: uuid.UUID,
    close_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Fecha um ticket"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    ticket.status = TicketStatus.CLOSED
    ticket.closed_by = int(close_data.get("closed_by"))
    ticket.close_reason = close_data.get("reason")
    ticket.closed_at = datetime.now(timezone.utc)
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_closed", "ticket_id": str(ticket_id),
        "closed_by": str(close_data.get("closed_by")), "reason": close_data.get("reason")
    })
    await notify_ticket_closed(guild_id, str(ticket_id), str(close_data.get("closed_by", 0)), close_data.get("reason"))
    return {"message": "Ticket fechado com sucesso"}


@router.put("/{guild_id}/tickets/{ticket_id}/bot/priority")
async def update_ticket_priority_bot(
    guild_id: int,
    ticket_id: uuid.UUID,
    priority_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Atualiza a prioridade do ticket"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    priority = priority_data.get("priority")
    if priority not in ["low", "medium", "high", "urgent"]:
        raise HTTPException(400, "Prioridade inválida")

    ticket.priority = TicketPriority(priority)
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_priority", "ticket_id": str(ticket_id), "priority": priority
    })
    return {"message": "Prioridade atualizada", "priority": priority}


@router.post("/{guild_id}/tickets/{ticket_id}/bot/transfer")
async def transfer_ticket_bot(
    guild_id: int,
    ticket_id: uuid.UUID,
    transfer_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Transfere um ticket"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    to_staff_id = transfer_data.get("to_staff_id")
    if not to_staff_id:
        raise HTTPException(400, "to_staff_id é obrigatório")

    old_staff = ticket.claimed_by
    new_staff = int(to_staff_id)
    ticket.claimed_by = new_staff
    ticket.status = TicketStatus.CLAIMED

    db.add(TicketTransfer(ticket_id=ticket_id, from_staff=old_staff or 0, to_staff=new_staff, reason=transfer_data.get("reason")))
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_transfer", "ticket_id": str(ticket_id),
        "from_staff": str(old_staff) if old_staff else None, "to_staff": str(new_staff)
    })
    return {"message": "Ticket transferido com sucesso"}


# ============ LISTAR / VER TICKETS ============

@router.get("/{guild_id}/tickets/bot/list")
async def get_tickets_bot(
    guild_id: int,
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Lista tickets com filtros"""
    query = select(Ticket).where(Ticket.guild_id == guild_id)
    if status:
        query = query.where(Ticket.status == status)
    if user_id:
        query = query.where(Ticket.user_id == user_id)

    query = query.order_by(Ticket.created_at.desc()).limit(limit)
    tickets = (await db.execute(query)).scalars().all()

    return {
        "tickets": [
            {
                "id": str(t.id), "ticket_number": t.ticket_number,
                "channel_id": str(t.channel_id), "user_id": str(t.user_id),
                "claimed_by": str(t.claimed_by) if t.claimed_by else None,
                "status": t.status.value, "priority": t.priority.value,
                "created_at": t.created_at.isoformat(),
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            }
            for t in tickets
        ],
        "total": len(tickets)
    }


@router.get("/{guild_id}/tickets/bot/{ticket_id}")
async def get_ticket_bot(
    guild_id: int,
    ticket_id: uuid.UUID,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Retorna detalhes de um ticket específico"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    members = [m[0] for m in (await db.execute(select(TicketMember.user_id).where(TicketMember.ticket_id == ticket.id))).all()]

    return {
        "id": str(ticket.id), "ticket_number": ticket.ticket_number,
        "guild_id": str(ticket.guild_id), "channel_id": str(ticket.channel_id),
        "user_id": str(ticket.user_id),
        "claimed_by": str(ticket.claimed_by) if ticket.claimed_by else None,
        "status": ticket.status.value, "priority": ticket.priority.value,
        "members": members,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
    }


# ============ BANS ============

@router.get("/{guild_id}/tickets/bot/bans", response_model=List[TicketBanResponse])
async def get_bans_bot(
    guild_id: int,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Lista bans ativos"""
    result = await db.execute(
        select(TicketBan).where(TicketBan.guild_id == guild_id, TicketBan.is_active == True)
    )
    return [TicketBanResponse.model_validate(b) for b in result.scalars().all()]


# ============ TRANSCRIPT ============

@router.post("/{guild_id}/tickets/{ticket_id}/transcript")
async def save_transcript(
    guild_id: int,
    ticket_id: uuid.UUID,
    transcript_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Salva a transcrição do ticket como JSON"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    from app.database_mongo import get_mongo, is_mongo_available
    if is_mongo_available():
        await get_mongo().ticket_transcripts.insert_one({
            **transcript_data,
            "ticket_id": str(ticket_id),
            "guild_id": guild_id,
            "saved_at": datetime.now(timezone.utc),
        })
        print(f"📝 Transcrição salva no MongoDB: {ticket_id}")

    transcript_url = f"{settings.FRONTEND_URL}/transcript/{ticket_id}"
    ticket.transcript_url = transcript_url
    await db.commit()

    return {"url": transcript_url, "message": "Transcrição salva com sucesso"}
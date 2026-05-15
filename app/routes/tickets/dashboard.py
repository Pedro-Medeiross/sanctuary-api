# app/routes/tickets/dashboard.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid

from app.database import get_db
from app.models.core.user import User
from app.models.tickets.ticket import Ticket, TicketStatus, TicketPriority
from app.models.tickets.ticket_config import TicketConfig
from app.models.tickets.ticket_staff_role import TicketStaffRole
from app.models.tickets.ticket_panel import TicketPanel
from app.models.tickets.ticket_member import TicketMember
from app.models.tickets.ticket_transfer import TicketTransfer
from app.models.tickets.ticket_ban import TicketBan
from app.models.tickets.ticket_feedback import TicketFeedback
from app.models.tickets.ticket_category import TicketCategory
from app.schemas.ticket import (
    TicketPanelCreate, TicketPanelUpdate, TicketPanelResponse,
    StaffRoleCreate, StaffRoleUpdate, StaffRoleResponse,
    TicketPriorityUpdate, TicketTransferRequest,
    TicketMemberRequest, TicketCloseRequest,
    TicketBanCreate, TicketBanResponse,
    TicketFeedbackCreate, FeedbackStatsResponse,
    TicketConfigUpdate, TicketConfigResponse,
    TicketCategoryCreate, TicketCategoryUpdate, TicketCategoryResponse,
)
from app.utils.security import get_current_user
from app.services.websocket_manager import ws_manager
from app.config import settings
from app.services.bot_notifier import (
    notify_panel_created, notify_panel_updated, notify_panel_deleted,
    notify_ticket_closed
)

router = APIRouter(prefix="/guilds", tags=["Tickets Dashboard"])

DEFAULT_PERMISSIONS = {
    1: {"can_claim": False, "can_transfer": False, "can_add_users": False, "can_remove_users": False, "can_ban_users": False, "can_view_all": False, "can_manage_panels": False, "can_manage_config": False},
    2: {"can_claim": True, "can_transfer": True, "can_add_users": True, "can_remove_users": True, "can_ban_users": False, "can_view_all": False, "can_manage_panels": False, "can_manage_config": False},
    3: {"can_claim": True, "can_transfer": True, "can_add_users": True, "can_remove_users": True, "can_ban_users": True, "can_view_all": True, "can_manage_panels": False, "can_manage_config": False},
    4: {"can_claim": True, "can_transfer": True, "can_add_users": True, "can_remove_users": True, "can_ban_users": True, "can_view_all": True, "can_manage_panels": True, "can_manage_config": True},
}


# ============ HELPERS ============

def _get_or_404(result, name: str = "Recurso"):
    """Retorna o resultado ou levanta 404"""
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, f"{name} não encontrado")
    return obj


async def _get_or_create_config(guild_id: int, db: AsyncSession) -> TicketConfig:
    """Busca ou cria configuração de ticket"""
    result = await db.execute(select(TicketConfig).where(TicketConfig.guild_id == guild_id))
    config = result.scalar_one_or_none()
    if not config:
        config = TicketConfig(guild_id=guild_id)
        db.add(config)
        await db.flush()
        await db.commit()
    return config


# ============ CONFIGURAÇÕES ============

@router.get("/{guild_id}/tickets/config", response_model=TicketConfigResponse)
async def get_ticket_config(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    config = await _get_or_create_config(guild_id, db)
    return TicketConfigResponse.model_validate(config)


@router.put("/{guild_id}/tickets/config", response_model=TicketConfigResponse)
async def update_ticket_config(
    guild_id: int,
    config_data: TicketConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    config = await _get_or_create_config(guild_id, db)

    for field, value in config_data.model_dump(exclude_unset=True).items():
        setattr(config, field, value)

    await db.commit()
    return TicketConfigResponse.model_validate(config)


# ============ STAFF ROLES ============

@router.get("/{guild_id}/tickets/staff-roles", response_model=List[StaffRoleResponse])
async def get_staff_roles(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketStaffRole).where(TicketStaffRole.guild_id == guild_id))
    return [StaffRoleResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/{guild_id}/tickets/staff-roles", response_model=StaffRoleResponse)
async def create_staff_role(
    guild_id: int,
    role_data: StaffRoleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketStaffRole).where(
            TicketStaffRole.guild_id == guild_id,
            TicketStaffRole.role_id == role_data.role_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, "Este cargo já está configurado")

    perms = DEFAULT_PERMISSIONS.get(role_data.level, DEFAULT_PERMISSIONS[1])
    staff_role = TicketStaffRole(
        guild_id=guild_id,
        role_id=role_data.role_id,
        role_name=role_data.role_name,
        level=role_data.level,
        is_trainee=(role_data.role_name.lower() == "ajudante"),
        **perms
    )
    db.add(staff_role)
    await db.commit()
    return StaffRoleResponse.model_validate(staff_role)


@router.put("/{guild_id}/tickets/staff-roles/{role_id}", response_model=StaffRoleResponse)
async def update_staff_role(
    guild_id: int,
    role_id: uuid.UUID,
    role_data: StaffRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketStaffRole).where(TicketStaffRole.id == role_id, TicketStaffRole.guild_id == guild_id)
    )
    staff_role = _get_or_404(result, "Cargo")

    for field, value in role_data.model_dump(exclude_unset=True).items():
        setattr(staff_role, field, value)

    await db.commit()
    return StaffRoleResponse.model_validate(staff_role)


@router.delete("/{guild_id}/tickets/staff-roles/{role_id}")
async def delete_staff_role(
    guild_id: int,
    role_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketStaffRole).where(TicketStaffRole.id == role_id, TicketStaffRole.guild_id == guild_id)
    )
    staff_role = _get_or_404(result, "Cargo")
    await db.delete(staff_role)
    await db.commit()
    return {"message": "Cargo removido com sucesso"}


# ============ CATEGORIAS ============

@router.get("/{guild_id}/tickets/categories", response_model=List[TicketCategoryResponse])
async def get_categories(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketCategory).where(TicketCategory.guild_id == guild_id).order_by(TicketCategory.position)
    )
    return [TicketCategoryResponse.model_validate(c) for c in result.scalars().all()]


@router.post("/{guild_id}/tickets/categories", response_model=TicketCategoryResponse)
async def create_category(
    guild_id: int,
    category_data: TicketCategoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    category = TicketCategory(guild_id=guild_id, **category_data.model_dump())
    db.add(category)
    await db.commit()
    return TicketCategoryResponse.model_validate(category)


@router.put("/{guild_id}/tickets/categories/{category_id}", response_model=TicketCategoryResponse)
async def update_category(
    guild_id: int,
    category_id: uuid.UUID,
    category_data: TicketCategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketCategory).where(TicketCategory.id == category_id, TicketCategory.guild_id == guild_id)
    )
    category = _get_or_404(result, "Categoria")

    for field, value in category_data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)

    await db.commit()
    return TicketCategoryResponse.model_validate(category)


@router.delete("/{guild_id}/tickets/categories/{category_id}")
async def delete_category(
    guild_id: int,
    category_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketCategory).where(TicketCategory.id == category_id, TicketCategory.guild_id == guild_id)
    )
    category = _get_or_404(result, "Categoria")
    await db.delete(category)
    await db.commit()
    return {"message": "Categoria deletada com sucesso"}


# ============ PAINÉIS ============

@router.get("/{guild_id}/tickets/panels", response_model=List[TicketPanelResponse])
async def get_panels(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketPanel).where(TicketPanel.guild_id == guild_id))
    return [TicketPanelResponse.model_validate(p) for p in result.scalars().all()]


@router.post("/{guild_id}/tickets/panels", response_model=TicketPanelResponse)
async def create_panel(
    guild_id: int,
    panel_data: TicketPanelCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    panel = TicketPanel(guild_id=guild_id, **panel_data.model_dump())
    db.add(panel)
    await db.commit()

    await notify_panel_created(guild_id, {
        "id": panel.id, "title": panel.title, "description": panel.description,
        "button_label": panel.button_label, "button_color": panel.button_color,
        "category_id": panel.category_id, "channel_id": panel.channel_id,
    })
    return TicketPanelResponse.model_validate(panel)


@router.put("/{guild_id}/tickets/panels/{panel_id}", response_model=TicketPanelResponse)
async def update_panel(
    guild_id: int,
    panel_id: uuid.UUID,
    panel_data: TicketPanelUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketPanel).where(TicketPanel.id == panel_id, TicketPanel.guild_id == guild_id)
    )
    panel = _get_or_404(result, "Painel")

    for field, value in panel_data.model_dump(exclude_unset=True).items():
        setattr(panel, field, value)

    await db.commit()

    await notify_panel_updated(guild_id, {
        "id": panel.id, "title": panel.title, "description": panel.description,
        "button_label": panel.button_label, "button_color": panel.button_color,
        "category_id": panel.category_id, "channel_id": panel.channel_id,
        "is_active": panel.is_active,
    })
    return TicketPanelResponse.model_validate(panel)


@router.delete("/{guild_id}/tickets/panels/{panel_id}")
async def delete_panel(
    guild_id: int,
    panel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketPanel).where(TicketPanel.id == panel_id, TicketPanel.guild_id == guild_id)
    )
    panel = _get_or_404(result, "Painel")
    await db.delete(panel)
    await db.commit()
    await notify_panel_deleted(guild_id, str(panel.id))
    return {"message": "Painel deletado permanentemente"}


@router.put("/{guild_id}/tickets/panels/{panel_id}/toggle")
async def toggle_panel(
    guild_id: int,
    panel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketPanel).where(TicketPanel.id == panel_id, TicketPanel.guild_id == guild_id)
    )
    panel = _get_or_404(result, "Painel")
    panel.is_active = not panel.is_active
    await db.commit()

    await notify_panel_updated(guild_id, {
        "id": panel.id, "title": panel.title, "description": panel.description,
        "button_label": panel.button_label, "button_color": panel.button_color,
        "category_id": panel.category_id, "channel_id": panel.channel_id,
        "is_active": panel.is_active,
    })
    return {"message": f"Painel {'ativado' if panel.is_active else 'desativado'} com sucesso", "is_active": panel.is_active}


@router.post("/{guild_id}/tickets/panels/{panel_id}/resend")
async def resend_panel(
    guild_id: int,
    panel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketPanel).where(TicketPanel.id == panel_id, TicketPanel.guild_id == guild_id)
    )
    panel = _get_or_404(result, "Painel")

    await notify_panel_created(guild_id, {
        "id": panel.id, "title": panel.title, "description": panel.description,
        "button_label": panel.button_label, "button_color": panel.button_color,
        "channel_id": panel.channel_id, "category_id": panel.category_id,
    })
    return {"message": "Painel reenviado com sucesso", "panel_id": str(panel.id)}


# ============ TICKETS ============

@router.get("/{guild_id}/tickets")
async def get_tickets(
    guild_id: int,
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    claimed_by: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Ticket).where(Ticket.guild_id == guild_id)
    if status: query = query.where(Ticket.status == status)
    if priority: query = query.where(Ticket.priority == priority)
    if claimed_by: query = query.where(Ticket.claimed_by == claimed_by)
    if user_id: query = query.where(Ticket.user_id == user_id)

    total = (await db.execute(select(func.count()).select_from(Ticket).where(Ticket.guild_id == guild_id))).scalar()

    query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(limit)
    tickets = (await db.execute(query)).scalars().all()

    tickets_response = []
    for ticket in tickets:
        members = [m[0] for m in (await db.execute(select(TicketMember.user_id).where(TicketMember.ticket_id == ticket.id))).all()]
        tickets_response.append({
            "id": str(ticket.id), "guild_id": str(ticket.guild_id),
            "panel_id": str(ticket.panel_id) if ticket.panel_id else None,
            "channel_id": str(ticket.channel_id), "user_id": str(ticket.user_id),
            "claimed_by": str(ticket.claimed_by) if ticket.claimed_by else None,
            "status": ticket.status.value if ticket.status else None,
            "priority": ticket.priority.value if ticket.priority else None,
            "closed_by": str(ticket.closed_by) if ticket.closed_by else None,
            "close_reason": ticket.close_reason, "members": members,
            "last_activity_at": ticket.last_activity_at.isoformat() if ticket.last_activity_at else None,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        })

    return {"tickets": tickets_response, "total": total, "limit": limit, "offset": offset, "has_more": (offset + limit) < total}


@router.get("/{guild_id}/tickets/{ticket_id}")
async def get_ticket(
    guild_id: int,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    members = [
        {"user_id": str(m.user_id), "added_by": str(m.added_by), "added_at": m.created_at.isoformat()}
        for m in (await db.execute(select(TicketMember).where(TicketMember.ticket_id == ticket.id))).scalars().all()
    ]

    return {
        "id": str(ticket.id), "guild_id": str(ticket.guild_id),
        "channel_id": str(ticket.channel_id), "user_id": str(ticket.user_id),
        "claimed_by": str(ticket.claimed_by) if ticket.claimed_by else None,
        "status": ticket.status.value, "priority": ticket.priority.value,
        "members": members,
        "last_activity_at": ticket.last_activity_at.isoformat(),
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
    }


@router.put("/{guild_id}/tickets/{ticket_id}/priority")
async def update_ticket_priority(
    guild_id: int,
    ticket_id: uuid.UUID,
    priority_data: TicketPriorityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")
    ticket.priority = TicketPriority(priority_data.priority)
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {"type": "ticket_priority", "ticket_id": str(ticket_id), "priority": priority_data.priority})
    return {"message": "Prioridade atualizada", "priority": priority_data.priority}


@router.post("/{guild_id}/tickets/{ticket_id}/transfer")
async def transfer_ticket(
    guild_id: int,
    ticket_id: uuid.UUID,
    transfer_data: TicketTransferRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    old_staff = ticket.claimed_by
    ticket.claimed_by = transfer_data.to_staff_id
    ticket.status = TicketStatus.CLAIMED

    db.add(TicketTransfer(ticket_id=ticket_id, from_staff=old_staff or 0, to_staff=transfer_data.to_staff_id, reason=transfer_data.reason))
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {"type": "ticket_transfer", "ticket_id": str(ticket_id), "from_staff": str(old_staff) if old_staff else None, "to_staff": str(transfer_data.to_staff_id)})
    return {"message": "Ticket transferido com sucesso"}


@router.post("/{guild_id}/tickets/{ticket_id}/members")
async def add_ticket_member(
    guild_id: int,
    ticket_id: uuid.UUID,
    member_data: TicketMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(select(TicketMember).where(TicketMember.ticket_id == ticket_id, TicketMember.user_id == member_data.user_id))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Usuário já é membro deste ticket")

    db.add(TicketMember(ticket_id=ticket_id, user_id=member_data.user_id, added_by=current_user.id))
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {"type": "member_added", "ticket_id": str(ticket_id), "user_id": str(member_data.user_id)})
    return {"message": "Membro adicionado com sucesso"}


@router.delete("/{guild_id}/tickets/{ticket_id}/members/{user_id}")
async def remove_ticket_member(
    guild_id: int,
    ticket_id: uuid.UUID,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketMember).where(TicketMember.ticket_id == ticket_id, TicketMember.user_id == user_id))
    member = _get_or_404(result, "Membro")
    await db.delete(member)
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {"type": "member_removed", "ticket_id": str(ticket_id), "user_id": str(user_id)})
    return {"message": "Membro removido com sucesso"}


@router.post("/{guild_id}/tickets/{ticket_id}/close")
async def close_ticket(
    guild_id: int,
    ticket_id: uuid.UUID,
    close_data: TicketCloseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    ticket = _get_or_404(result, "Ticket")

    ticket.status = TicketStatus.CLOSED
    ticket.closed_by = current_user.id
    ticket.close_reason = close_data.reason
    ticket.closed_at = datetime.now(timezone.utc)
    await db.commit()

    await ws_manager.broadcast_to_guild(guild_id, {"type": "ticket_closed", "ticket_id": str(ticket_id), "closed_by": str(current_user.id), "reason": close_data.reason})
    await notify_ticket_closed(guild_id, str(ticket_id), str(current_user.id), close_data.reason)
    return {"message": "Ticket fechado com sucesso"}


# ============ BLOQUEIOS ============

@router.get("/{guild_id}/tickets/bans", response_model=List[TicketBanResponse])
async def get_bans(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketBan).where(TicketBan.guild_id == guild_id, TicketBan.is_active == True))
    return [TicketBanResponse.model_validate(b) for b in result.scalars().all()]


@router.post("/{guild_id}/tickets/bans", response_model=TicketBanResponse)
async def create_ban(
    guild_id: int,
    ban_data: TicketBanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ban = TicketBan(
        guild_id=guild_id, user_id=ban_data.user_id, reason=ban_data.reason,
        banned_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=ban_data.expires_in_days) if ban_data.expires_in_days else None,
    )
    db.add(ban)
    await db.commit()
    return TicketBanResponse.model_validate(ban)


@router.delete("/{guild_id}/tickets/bans/{ban_id}")
async def remove_ban(
    guild_id: int,
    ban_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketBan).where(TicketBan.id == ban_id, TicketBan.guild_id == guild_id))
    ban = _get_or_404(result, "Ban")
    ban.is_active = False
    await db.commit()
    return {"message": "Ban removido com sucesso"}


# ============ FEEDBACK ============

@router.post("/{guild_id}/tickets/{ticket_id}/feedback")
async def create_feedback(
    guild_id: int,
    ticket_id: uuid.UUID,
    feedback_data: TicketFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    db.add(TicketFeedback(ticket_id=ticket_id, user_id=current_user.id, staff_id=feedback_data.staff_id, rating=feedback_data.rating, comment=feedback_data.comment))
    await db.commit()
    return {"message": "Avaliação enviada com sucesso", "id": str(feedback_data.staff_id)}


@router.get("/{guild_id}/tickets/feedback/stats")
async def get_feedback_stats(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ticket_ids = [t[0] for t in (await db.execute(select(Ticket.id).where(Ticket.guild_id == guild_id))).all()]
    if not ticket_ids:
        return {"average_rating": 0, "total_feedbacks": 0, "by_staff": {}}

    result = await db.execute(select(TicketFeedback).where(TicketFeedback.ticket_id.in_(ticket_ids)))
    feedbacks = result.scalars().all()
    if not feedbacks:
        return {"average_rating": 0, "total_feedbacks": 0, "by_staff": {}}

    total_rating = sum(f.rating for f in feedbacks)
    by_staff = {}
    for f in feedbacks:
        sid = str(f.staff_id)
        if sid not in by_staff: by_staff[sid] = {"total_rating": 0, "count": 0}
        by_staff[sid]["total_rating"] += f.rating
        by_staff[sid]["count"] += 1
    for sid in by_staff:
        by_staff[sid]["average"] = round(by_staff[sid]["total_rating"] / by_staff[sid]["count"], 1)

    return {"average_rating": round(total_rating / len(feedbacks), 1), "total_feedbacks": len(feedbacks), "by_staff": by_staff}


# ============ TRANSCRIPT ============

@router.get("/{guild_id}/tickets/{ticket_id}/transcript")
async def get_transcript(
    guild_id: int,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id))
    _get_or_404(result, "Ticket")

    from app.database_mongo import get_mongo, is_mongo_available
    if not is_mongo_available():
        raise HTTPException(404, "Transcrição não encontrada")

    transcript = await get_mongo().ticket_transcripts.find_one({"ticket_id": str(ticket_id)})
    if not transcript:
        raise HTTPException(404, "Transcrição não encontrada")
    if "_id" in transcript:
        del transcript["_id"]

    return transcript
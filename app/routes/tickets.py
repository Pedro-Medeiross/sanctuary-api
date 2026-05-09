# app/routes/tickets.py
from fastapi import APIRouter, Depends, HTTPException, Request, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid

from app.database import get_db
from app.models.user import User
from app.models.ticket import Ticket, TicketStatus, TicketPriority
from app.models.ticket_config import TicketConfig
from app.models.ticket_staff_role import TicketStaffRole
from app.models.ticket_panel import TicketPanel
from app.models.ticket_member import TicketMember
from app.models.ticket_transfer import TicketTransfer
from app.models.ticket_ban import TicketBan
from app.models.ticket_feedback import TicketFeedback
from app.schemas.ticket import (
    TicketPanelCreate, TicketPanelUpdate, TicketPanelResponse,
    StaffRoleCreate, StaffRoleUpdate, StaffRoleResponse,
    TicketResponse, TicketPriorityUpdate, TicketTransferRequest,
    TicketMemberRequest, TicketCloseRequest,
    TicketBanCreate, TicketBanResponse,
    TicketFeedbackCreate, TicketFeedbackResponse, FeedbackStatsResponse,
    TicketConfigUpdate, TicketConfigResponse,
)
from app.utils.security import verify_bot_auth, get_current_user
from app.services.websocket_manager import ws_manager
from app.config import settings

from app.services.bot_notifier import (
    notify_panel_created, notify_panel_updated, notify_panel_deleted,
    notify_ticket_created, notify_ticket_closed, notify_ticket_claimed
)

router = APIRouter(prefix="/guilds", tags=["Tickets"])
ws_router = APIRouter(tags=["WebSocket Tickets"])

# Permissões padrão por nível
DEFAULT_PERMISSIONS = {
    1: {"can_claim": False, "can_transfer": False, "can_add_users": False, "can_remove_users": False, "can_ban_users": False, "can_view_all": False, "can_manage_panels": False, "can_manage_config": False},
    2: {"can_claim": True, "can_transfer": True, "can_add_users": True, "can_remove_users": True, "can_ban_users": False, "can_view_all": False, "can_manage_panels": False, "can_manage_config": False},
    3: {"can_claim": True, "can_transfer": True, "can_add_users": True, "can_remove_users": True, "can_ban_users": True, "can_view_all": True, "can_manage_panels": False, "can_manage_config": False},
    4: {"can_claim": True, "can_transfer": True, "can_add_users": True, "can_remove_users": True, "can_ban_users": True, "can_view_all": True, "can_manage_panels": True, "can_manage_config": True},
}

# ============ CONFIGURAÇÕES ============

@router.get("/{guild_id}/tickets/config", response_model=TicketConfigResponse)
async def get_ticket_config(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketConfig).where(TicketConfig.guild_id == guild_id))
    config = result.scalar_one_or_none()
    
    if not config:
        config = TicketConfig(guild_id=guild_id)
        db.add(config)
        await db.flush()
        await db.commit()
    
    return TicketConfigResponse.model_validate(config)

@router.put("/{guild_id}/tickets/config", response_model=TicketConfigResponse)
async def update_ticket_config(
    guild_id: int,
    config_data: TicketConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TicketConfig).where(TicketConfig.guild_id == guild_id))
    config = result.scalar_one_or_none()
    
    if not config:
        config = TicketConfig(guild_id=guild_id)
        db.add(config)
    
    if config_data.max_open_tickets is not None:
        config.max_open_tickets = config_data.max_open_tickets
    if config_data.auto_close_hours is not None:
        config.auto_close_hours = config_data.auto_close_hours
    if config_data.allow_user_close is not None:
        config.allow_user_close = config_data.allow_user_close
    if config_data.allow_attachments is not None:
        config.allow_attachments = config_data.allow_attachments
    if config_data.transcript_channel is not None:
        config.transcript_channel = config_data.transcript_channel
    
    await db.flush()
    await db.commit()
    
    return TicketConfigResponse.model_validate(config)

# ============ STAFF ROLES ============

@router.get("/{guild_id}/tickets/staff-roles", response_model=List[StaffRoleResponse])
async def get_staff_roles(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketStaffRole).where(TicketStaffRole.guild_id == guild_id)
    )
    return [StaffRoleResponse.model_validate(r) for r in result.scalars().all()]

@router.post("/{guild_id}/tickets/staff-roles", response_model=StaffRoleResponse)
async def create_staff_role(
    guild_id: int,
    role_data: StaffRoleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verificar se já existe
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
    await db.flush()
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
        select(TicketStaffRole).where(
            TicketStaffRole.id == role_id,
            TicketStaffRole.guild_id == guild_id
        )
    )
    staff_role = result.scalar_one_or_none()
    if not staff_role:
        raise HTTPException(404, "Cargo não encontrado")
    
    update_fields = role_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(staff_role, field, value)
    
    await db.flush()
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
        select(TicketStaffRole).where(
            TicketStaffRole.id == role_id,
            TicketStaffRole.guild_id == guild_id
        )
    )
    staff_role = result.scalar_one_or_none()
    if not staff_role:
        raise HTTPException(404, "Cargo não encontrado")
    
    await db.delete(staff_role)
    await db.commit()
    
    return {"message": "Cargo removido com sucesso"}

# ============ PAINÉIS ============

@router.get("/{guild_id}/tickets/panels", response_model=List[TicketPanelResponse])
async def get_panels(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketPanel).where(TicketPanel.guild_id == guild_id)
    )
    return [TicketPanelResponse.model_validate(p) for p in result.scalars().all()]

@router.post("/{guild_id}/tickets/panels", response_model=TicketPanelResponse)
async def create_panel(
    guild_id: int,
    panel_data: TicketPanelCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    panel = TicketPanel(
        guild_id=guild_id,
        title=panel_data.title,
        description=panel_data.description,
        button_label=panel_data.button_label,
        button_color=panel_data.button_color,
        category_id=panel_data.category_id,
    )
    db.add(panel)
    await db.flush()
    await db.commit()
    
    await notify_panel_created(guild_id, {
        "id": panel.id,
        "title": panel.title,
        "description": panel.description,
        "button_label": panel.button_label,
        "button_color": panel.button_color,
        "category_id": panel.category_id,
        "channel_id": panel.channel_id,
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
        select(TicketPanel).where(
            TicketPanel.id == panel_id,
            TicketPanel.guild_id == guild_id
        )
    )
    panel = result.scalar_one_or_none()
    if not panel:
        raise HTTPException(404, "Painel não encontrado")
    
    update_fields = panel_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(panel, field, value)
    
    await db.flush()
    await db.commit()
    
    await notify_panel_updated(guild_id, {
        "id": panel.id,
        "title": panel.title,
        "description": panel.description,
        "button_label": panel.button_label,
        "button_color": panel.button_color,
        "category_id": panel.category_id,
        "channel_id": panel.channel_id,
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
    """Remove permanentemente o painel"""
    result = await db.execute(
        select(TicketPanel).where(
            TicketPanel.id == panel_id,
            TicketPanel.guild_id == guild_id
        )
    )
    panel = result.scalar_one_or_none()
    if not panel:
        raise HTTPException(404, "Painel não encontrado")
    
    # Hard delete - remove do banco
    await db.delete(panel)
    await db.commit()
    
    # Notificar bot
    await notify_panel_deleted(guild_id, str(panel.id))
    
    return {"message": "Painel deletado permanentemente"}

@router.put("/{guild_id}/tickets/panels/{panel_id}/toggle")
async def toggle_panel(
    guild_id: int,
    panel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Ativa/Desativa um painel sem deletar"""
    result = await db.execute(
        select(TicketPanel).where(
            TicketPanel.id == panel_id,
            TicketPanel.guild_id == guild_id
        )
    )
    panel = result.scalar_one_or_none()
    if not panel:
        raise HTTPException(404, "Painel não encontrado")
    
    panel.is_active = not panel.is_active
    await db.commit()
    
    status = "ativado" if panel.is_active else "desativado"
    
    # Notificar bot com dados completos
    await notify_panel_updated(guild_id, {
        "id": panel.id,
        "title": panel.title,
        "description": panel.description,
        "button_label": panel.button_label,
        "button_color": panel.button_color,
        "category_id": panel.category_id,
        "channel_id": panel.channel_id,
        "is_active": panel.is_active,
    })
    
    return {"message": f"Painel {status} com sucesso", "is_active": panel.is_active}

@router.post("/{guild_id}/tickets/panels/{panel_id}/resend")
async def resend_panel(
    guild_id: int,
    panel_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Reenvia o embed do painel para o Discord"""
    result = await db.execute(
        select(TicketPanel).where(
            TicketPanel.id == panel_id,
            TicketPanel.guild_id == guild_id
        )
    )
    panel = result.scalar_one_or_none()
    if not panel:
        raise HTTPException(404, "Painel não encontrado")
    
    # Notificar bot para recriar o embed
    await notify_panel_created(guild_id, {
        "id": panel.id,
        "title": panel.title,
        "description": panel.description,
        "button_label": panel.button_label,
        "button_color": panel.button_color,
        "channel_id": panel.channel_id,
        "category_id": panel.category_id,
    })
    
    return {"message": "Painel reenviado com sucesso", "panel_id": str(panel.id)}

# ============ TICKETS (DASHBOARD) ============

@router.get("/{guild_id}/tickets", response_model=dict)
async def get_tickets(
    guild_id: int,
    request: Request,
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
    
    if status:
        query = query.where(Ticket.status == status)
    if priority:
        query = query.where(Ticket.priority == priority)
    if claimed_by:
        query = query.where(Ticket.claimed_by == claimed_by)
    if user_id:
        query = query.where(Ticket.user_id == user_id)
    
    # Contar total
    count_query = select(func.count()).select_from(Ticket).where(Ticket.guild_id == guild_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Buscar tickets
    query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    tickets = result.scalars().all()
    
    # Buscar membros para cada ticket
    tickets_response = []
    for ticket in tickets:
        members_result = await db.execute(
            select(TicketMember.user_id).where(TicketMember.ticket_id == ticket.id)
        )
        members = [m[0] for m in members_result.all()]
        
        tickets_response.append({
            "id": str(ticket.id),
            "guild_id": str(ticket.guild_id),
            "panel_id": str(ticket.panel_id) if ticket.panel_id else None,
            "channel_id": str(ticket.channel_id),
            "user_id": str(ticket.user_id),
            "claimed_by": str(ticket.claimed_by) if ticket.claimed_by else None,
            "status": ticket.status.value if ticket.status else None,
            "priority": ticket.priority.value if ticket.priority else None,
            "closed_by": str(ticket.closed_by) if ticket.closed_by else None,
            "close_reason": ticket.close_reason,
            "members": members,
            "last_activity_at": ticket.last_activity_at.isoformat() if ticket.last_activity_at else None,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        })
    
    return {
        "tickets": tickets_response,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total
    }

@router.get("/{guild_id}/tickets/{ticket_id}", response_model=dict)
async def get_ticket(
    guild_id: int,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, "Ticket não encontrado")
    
    members_result = await db.execute(
        select(TicketMember).where(TicketMember.ticket_id == ticket.id)
    )
    members = [{"user_id": str(m.user_id), "added_by": str(m.added_by), "added_at": m.created_at.isoformat()} for m in members_result.scalars().all()]
    
    return {
        "id": str(ticket.id),
        "guild_id": str(ticket.guild_id),
        "channel_id": str(ticket.channel_id),
        "user_id": str(ticket.user_id),
        "claimed_by": str(ticket.claimed_by) if ticket.claimed_by else None,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
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
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, "Ticket não encontrado")
    
    ticket.priority = TicketPriority(priority_data.priority)
    await db.commit()
    
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_priority",
        "ticket_id": str(ticket_id),
        "priority": priority_data.priority
    })
    
    return {"message": "Prioridade atualizada", "priority": priority_data.priority}

@router.post("/{guild_id}/tickets/{ticket_id}/transfer")
async def transfer_ticket(
    guild_id: int,
    ticket_id: uuid.UUID,
    transfer_data: TicketTransferRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, "Ticket não encontrado")
    
    old_staff = ticket.claimed_by
    ticket.claimed_by = transfer_data.to_staff_id
    ticket.status = TicketStatus.CLAIMED
    
    transfer = TicketTransfer(
        ticket_id=ticket_id,
        from_staff=old_staff or 0,
        to_staff=transfer_data.to_staff_id,
        reason=transfer_data.reason
    )
    db.add(transfer)
    await db.commit()
    
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_transfer",
        "ticket_id": str(ticket_id),
        "from_staff": str(old_staff) if old_staff else None,
        "to_staff": str(transfer_data.to_staff_id)
    })
    
    return {"message": "Ticket transferido com sucesso"}

@router.post("/{guild_id}/tickets/{ticket_id}/members")
async def add_ticket_member(
    guild_id: int,
    ticket_id: uuid.UUID,
    member_data: TicketMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(
        select(TicketMember).where(
            TicketMember.ticket_id == ticket_id,
            TicketMember.user_id == member_data.user_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Usuário já é membro deste ticket")
    
    member = TicketMember(
        ticket_id=ticket_id,
        user_id=member_data.user_id,
        added_by=current_user.id
    )
    db.add(member)
    await db.commit()
    
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "member_added",
        "ticket_id": str(ticket_id),
        "user_id": str(member_data.user_id)
    })
    
    return {"message": "Membro adicionado com sucesso"}

@router.delete("/{guild_id}/tickets/{ticket_id}/members/{user_id}")
async def remove_ticket_member(
    guild_id: int,
    ticket_id: uuid.UUID,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketMember).where(
            TicketMember.ticket_id == ticket_id,
            TicketMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "Membro não encontrado")
    
    await db.delete(member)
    await db.commit()
    
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "member_removed",
        "ticket_id": str(ticket_id),
        "user_id": str(user_id)
    })
    
    return {"message": "Membro removido com sucesso"}

@router.post("/{guild_id}/tickets/{ticket_id}/close")
async def close_ticket(
    guild_id: int,
    ticket_id: uuid.UUID,
    close_data: TicketCloseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, "Ticket não encontrado")
    
    ticket.status = TicketStatus.CLOSED
    ticket.closed_by = current_user.id
    ticket.close_reason = close_data.reason
    ticket.closed_at = datetime.now(timezone.utc)
    await db.commit()
    
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_closed",
        "ticket_id": str(ticket_id),
        "closed_by": str(current_user.id),
        "reason": close_data.reason
    })
    
    await notify_ticket_closed(guild_id, str(ticket_id), str(current_user.id), close_data.reason)
    
    return {"message": "Ticket fechado com sucesso"}

# ============ BOT: ABRIR TICKET ============

@router.post("/{guild_id}/tickets/open")
async def open_ticket(
    guild_id: int,
    ticket_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Abre um novo ticket"""
    user_id = int(ticket_data.get("user_id"))
    channel_id = int(ticket_data.get("channel_id"))
    panel_id = ticket_data.get("panel_id")
    
    ticket = Ticket(
        guild_id=guild_id,
        panel_id=uuid.UUID(panel_id) if panel_id else None,
        channel_id=channel_id,
        user_id=user_id,
    )
    db.add(ticket)
    await db.flush()
    await db.commit()
    
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_created",
        "ticket": {
            "id": str(ticket.id),
            "guild_id": str(guild_id),
            "channel_id": str(channel_id),
            "user_id": str(user_id),
            "status": "open",
            "priority": "medium",
            "created_at": ticket.created_at.isoformat()
        }
    })
    
    await notify_ticket_created(guild_id, {
        "id": ticket.id,
        "channel_id": ticket.channel_id,
        "user_id": ticket.user_id,
    })
    
    return {"id": str(ticket.id), "created_at": ticket.created_at.isoformat()}

# ============ BOT: REINVINDICAR TICKET ============

@router.put("/{guild_id}/tickets/{ticket_id}/claim")
async def claim_ticket(
    guild_id: int,
    ticket_id: uuid.UUID,
    claim_data: dict,
    bot_user: str = Depends(verify_bot_auth),
    db: AsyncSession = Depends(get_db)
):
    """[Bot] Reinvindica um ticket"""
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.guild_id == guild_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, "Ticket não encontrado")
    
    staff_id = int(claim_data.get("staff_id"))
    ticket.claimed_by = staff_id
    ticket.status = TicketStatus.CLAIMED
    ticket.last_activity_at = datetime.now(timezone.utc)
    await db.commit()
    
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "ticket_claimed",
        "ticket_id": str(ticket_id),
        "claimed_by": str(staff_id)
    })
    
    await notify_ticket_claimed(guild_id, str(ticket_id), str(staff_id))
    
    return {"message": "Ticket reinvindicado"}

# ============ BLOQUEIOS ============

@router.get("/{guild_id}/tickets/bans", response_model=List[TicketBanResponse])
async def get_bans(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketBan).where(
            TicketBan.guild_id == guild_id,
            TicketBan.is_active == True
        )
    )
    return [TicketBanResponse.model_validate(b) for b in result.scalars().all()]

@router.post("/{guild_id}/tickets/bans", response_model=TicketBanResponse)
async def create_ban(
    guild_id: int,
    ban_data: TicketBanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ban = TicketBan(
        guild_id=guild_id,
        user_id=ban_data.user_id,
        reason=ban_data.reason,
        banned_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=ban_data.expires_in_days) if ban_data.expires_in_days else None,
    )
    db.add(ban)
    await db.flush()
    await db.commit()
    
    return TicketBanResponse.model_validate(ban)

@router.delete("/{guild_id}/tickets/bans/{ban_id}")
async def remove_ban(
    guild_id: int,
    ban_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TicketBan).where(TicketBan.id == ban_id, TicketBan.guild_id == guild_id)
    )
    ban = result.scalar_one_or_none()
    if not ban:
        raise HTTPException(404, "Ban não encontrado")
    
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
    feedback = TicketFeedback(
        ticket_id=ticket_id,
        user_id=current_user.id,
        staff_id=feedback_data.staff_id,
        rating=feedback_data.rating,
        comment=feedback_data.comment
    )
    db.add(feedback)
    await db.flush()
    await db.commit()
    
    return {"message": "Avaliação enviada com sucesso", "id": str(feedback.id)}

@router.get("/{guild_id}/tickets/feedback/stats")
async def get_feedback_stats(
    guild_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Buscar tickets da guild
    tickets_result = await db.execute(
        select(Ticket.id).where(Ticket.guild_id == guild_id)
    )
    ticket_ids = [t[0] for t in tickets_result.all()]
    
    if not ticket_ids:
        return {"average_rating": 0, "total_feedbacks": 0, "by_staff": {}}
    
    # Buscar feedbacks
    result = await db.execute(
        select(TicketFeedback).where(TicketFeedback.ticket_id.in_(ticket_ids))
    )
    feedbacks = result.scalars().all()
    
    if not feedbacks:
        return {"average_rating": 0, "total_feedbacks": 0, "by_staff": {}}
    
    total_rating = sum(f.rating for f in feedbacks)
    by_staff = {}
    
    for f in feedbacks:
        staff_id = str(f.staff_id)
        if staff_id not in by_staff:
            by_staff[staff_id] = {"total_rating": 0, "count": 0}
        by_staff[staff_id]["total_rating"] += f.rating
        by_staff[staff_id]["count"] += 1
    
    # Calcular médias
    for staff_id in by_staff:
        by_staff[staff_id]["average"] = round(by_staff[staff_id]["total_rating"] / by_staff[staff_id]["count"], 1)
    
    return {
        "average_rating": round(total_rating / len(feedbacks), 1),
        "total_feedbacks": len(feedbacks),
        "by_staff": by_staff
    }

# ============ WEBSOCKET ============

@ws_router.websocket("/ws/guilds/{guild_id}/tickets")
async def websocket_tickets(
    websocket: WebSocket,
    guild_id: int,
    token: str = Query(None)
):
    if not token:
        await websocket.close(code=4001, reason="Token não fornecido")
        return
    
    from app.utils.security import verify_token
    try:
        payload = verify_token(token, "access")
        if not payload.get("sub"):
            await websocket.close(code=4001, reason="Token inválido")
            return
    except Exception:
        await websocket.close(code=4001, reason="Token inválido")
        return
    
    await ws_manager.connect(websocket, guild_id)
    
    try:
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        ws_manager.disconnect(websocket, guild_id)
# app/routes/guilds.py (COMPLETO E CORRIGIDO)
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict
import aiohttp

from app.database import get_db
from app.models.guild import Guild
from app.models.log_channel import LogChannel
from app.schemas.guild import GuildResponse, PrefixUpdate, PrefixResponse
from app.schemas.log_channel import (
    LogChannelResponse, 
    SingleLogChannelResponse, 
    LogChannelsList,
    LogChannelUpdate,
    VALID_LOG_TYPES
)
from app.utils.security import verify_bot_auth, get_current_user
from app.models.user import User
from app.config import settings

router = APIRouter(prefix="/guilds", tags=["Guilds"])

DISCORD_API_URL = "https://discord.com/api/v10"

async def get_or_create_guild(guild_id: int, db: AsyncSession) -> Guild:
    """Obtém ou cria uma guild automaticamente"""
    result = await db.execute(
        select(Guild).where(Guild.id == guild_id)
    )
    guild = result.scalar_one_or_none()
    
    if not guild:
        guild = Guild(id=guild_id)
        db.add(guild)
        await db.flush()
        print(f"✅ Nova guild criada: {guild_id}")
    
    return guild

async def verify_guild_permission(
    guild_id: int, 
    discord_token: str
) -> bool:
    """Verifica se o usuário tem permissão na guild via Discord API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{DISCORD_API_URL}/users/@me/guilds",
                headers={"Authorization": f"Bearer {discord_token}"}
            ) as response:
                if response.status != 200:
                    return False
                
                guilds = await response.json()
                
                for guild in guilds:
                    if int(guild["id"]) == guild_id:
                        permissions = int(guild.get("permissions", 0))
                        # ADMINISTRATOR (0x8) ou MANAGE_GUILD (0x20)
                        return bool(permissions & 0x8 or permissions & 0x20)
                
                return False
    except Exception as e:
        print(f"❌ Erro ao verificar permissão: {e}")
        return False

# ============ ROTAS DO BOT (Basic Auth) ============

@router.get("/{guild_id}/prefix", response_model=PrefixResponse)
async def get_guild_prefix_bot(
    guild_id: int,
    db: AsyncSession = Depends(get_db),
    bot_user: str = Depends(verify_bot_auth)
):
    """[Bot] Retorna o prefixo da guild"""
    guild = await get_or_create_guild(guild_id, db)
    return PrefixResponse(prefix=guild.prefix, guild_id=guild_id)

@router.get("/{guild_id}/log-channel/{log_type}", response_model=SingleLogChannelResponse)
async def get_log_channel_bot(
    guild_id: int,
    log_type: str,
    db: AsyncSession = Depends(get_db),
    bot_user: str = Depends(verify_bot_auth)
):
    """[Bot] Retorna o channel_id para um tipo de log específico"""
    if log_type not in VALID_LOG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de log inválido. Tipos válidos: {', '.join(VALID_LOG_TYPES)}"
        )
    
    guild = await get_or_create_guild(guild_id, db)
    
    result = await db.execute(
        select(LogChannel).where(
            LogChannel.guild_id == guild_id,
            LogChannel.log_type == log_type
        )
    )
    log_channel = result.scalar_one_or_none()
    
    if not log_channel:
        return SingleLogChannelResponse(channel_id=None)
    
    return SingleLogChannelResponse(
        channel_id=log_channel.channel_id if log_channel.enabled else None
    )

@router.get("/{guild_id}/log-channels", response_model=LogChannelsList)
async def get_all_log_channels_bot(
    guild_id: int,
    db: AsyncSession = Depends(get_db),
    bot_user: str = Depends(verify_bot_auth)
):
    """[Bot] Retorna todos os canais de log da guild"""
    guild = await get_or_create_guild(guild_id, db)
    
    result = await db.execute(
        select(LogChannel).where(LogChannel.guild_id == guild_id)
    )
    log_channels = result.scalars().all()
    
    channels_dict = {}
    for lc in log_channels:
        channels_dict[lc.log_type] = lc.channel_id if lc.enabled else None
    
    return LogChannelsList(guild_id=guild_id, channels=channels_dict)

# ============ ROTAS DO DASHBOARD (JWT + Discord Token) ============

@router.put("/{guild_id}/prefix", response_model=PrefixResponse)
async def update_guild_prefix_dashboard(
    guild_id: int,
    prefix_data: PrefixUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[Dashboard] Atualiza o prefixo da guild"""
    # Verificar permissão no Discord
    discord_token = request.headers.get("X-Discord-Token")
    if not discord_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token do Discord não fornecido"
        )
    
    has_permission = await verify_guild_permission(guild_id, discord_token)
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para modificar esta guild"
        )
    
    guild = await get_or_create_guild(guild_id, db)
    guild.prefix = prefix_data.prefix
    
    print(f"📝 Prefixo atualizado: guild={guild_id}, prefix={prefix_data.prefix} por {current_user.username}")
    return PrefixResponse(prefix=guild.prefix, guild_id=guild_id)

@router.put("/{guild_id}/log-channels")
async def update_log_channels_dashboard(
    guild_id: int,
    log_data: LogChannelUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[Dashboard] Atualiza os canais de log da guild"""
    # Verificar permissão no Discord
    discord_token = request.headers.get("X-Discord-Token")
    if not discord_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token do Discord não fornecido"
        )
    
    has_permission = await verify_guild_permission(guild_id, discord_token)
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para modificar esta guild"
        )
    
    guild = await get_or_create_guild(guild_id, db)
    updated_channels = []
    
    for log_type, channel_id in log_data.channels.items():
        if log_type not in VALID_LOG_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo de log inválido '{log_type}'. Tipos válidos: {', '.join(VALID_LOG_TYPES)}"
            )
        
        # Buscar ou criar configuração de log
        result = await db.execute(
            select(LogChannel).where(
                LogChannel.guild_id == guild_id,
                LogChannel.log_type == log_type
            )
        )
        log_channel = result.scalar_one_or_none()
        
        if log_channel:
            log_channel.channel_id = channel_id
            log_channel.enabled = channel_id is not None
        else:
            log_channel = LogChannel(
                guild_id=guild_id,
                log_type=log_type,
                channel_id=channel_id,
                enabled=channel_id is not None
            )
            db.add(log_channel)
        
        updated_channels.append(log_channel)
    
    print(f"📝 Canais de log atualizados: guild={guild_id}, canais={len(updated_channels)} por {current_user.username}")
    
    return {
        "message": "Canais de log atualizados com sucesso",
        "guild_id": guild_id,
        "updated_channels": len(updated_channels),
        "updated_by": current_user.username
    }

@router.get("/{guild_id}/config", response_model=Dict)
async def get_guild_full_config(
    guild_id: int,
    request: Request,  # ← ADICIONADO
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[Dashboard] Retorna configuração completa da guild para o dashboard"""
    # ← ADICIONADO - Verificar permissão no Discord
    discord_token = request.headers.get("X-Discord-Token")
    if not discord_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token do Discord não fornecido"
        )
    
    has_permission = await verify_guild_permission(guild_id, discord_token)
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar esta guild"
        )
    
    guild = await get_or_create_guild(guild_id, db)
    
    result = await db.execute(
        select(LogChannel).where(LogChannel.guild_id == guild_id)
    )
    log_channels = result.scalars().all()
    
    channels_config = {}
    for lc in log_channels:
        channels_config[lc.log_type] = {
            "channel_id": lc.channel_id,
            "enabled": lc.enabled
        }
    
    return {
        "guild_id": guild.id,
        "prefix": guild.prefix,
        "log_channels": channels_config,
        "created_at": guild.created_at.isoformat() if guild.created_at else None,
        "updated_at": guild.updated_at.isoformat() if guild.updated_at else None
    }
    
@router.post("/sync")
async def sync_guilds(
    guild_ids: list[int],  # Lista de IDs das guilds que o bot está
    db: AsyncSession = Depends(get_db),
    bot_user: str = Depends(verify_bot_auth)
):
    """Sincroniza guilds - cria as que não existem ainda"""
    created = []
    existing = []
    
    for guild_id in guild_ids:
        result = await db.execute(select(Guild).where(Guild.id == guild_id))
        guild = result.scalar_one_or_none()
        
        if not guild:
            guild = Guild(id=guild_id)
            db.add(guild)
            created.append(guild_id)
        else:
            existing.append(guild_id)
    
    await db.flush()
    await db.commit()
    
    print(f"✅ Sync: {len(created)} criadas, {len(existing)} já existiam")
    
    return {
        "created": created,
        "existing": existing,
        "total": len(guild_ids)
    }
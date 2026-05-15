from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict
import aiohttp

from app.database import get_db
from app.models.discord.guild import Guild
from app.models.discord.guild_stats import GuildStats
from app.models.discord.log_channel import LogChannel
from app.models.core.user import User
from app.schemas.guild import PrefixUpdate, PrefixResponse
from app.schemas.log_channel import (
    SingleLogChannelResponse,
    LogChannelsList,
    LogChannelUpdate,
)
from app.utils.security import verify_bot_auth, get_current_user
from app.utils.cache import cache_get, cache_set, cache_delete_pattern
from app.config import settings

router = APIRouter(prefix="/guilds", tags=["Guilds"])

DISCORD_API_URL = "https://discord.com/api/v10"


# ============ HELPERS ============

def _require_discord_token(request: Request) -> str:
    """Extrai e valida X-Discord-Token do header"""
    token = request.headers.get("X-Discord-Token")
    if not token:
        raise HTTPException(400, "Token do Discord não fornecido")
    return token


async def get_or_create_guild(guild_id: int, db: AsyncSession) -> Guild:
    """Obtém ou cria uma guild automaticamente"""
    result = await db.execute(select(Guild).where(Guild.id == guild_id))
    guild = result.scalar_one_or_none()

    if not guild:
        guild = Guild(id=guild_id)
        db.add(guild)
        await db.flush()
        print(f"✅ Nova guild criada: {guild_id}")

    return guild


async def verify_guild_permission(
    guild_id: int, discord_token: str, user_id: str = None
) -> bool:
    """Verifica permissão com cache (Redis + Local)"""
    if user_id:
        cache_key = f"discord:guilds:perms:{user_id}"
        cached_guilds = await cache_get(cache_key)
        if cached_guilds:
            guild_perm = cached_guilds.get(str(guild_id))
            if guild_perm is not None:
                return guild_perm

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{DISCORD_API_URL}/users/@me/guilds",
                headers={"Authorization": f"Bearer {discord_token}"}
            ) as response:
                if response.status != 200:
                    return False

                guilds = await response.json()

                if user_id:
                    guild_perms = {
                        str(g["id"]): bool(int(g.get("permissions", 0)) & 0x8 or int(g.get("permissions", 0)) & 0x20)
                        for g in guilds
                    }
                    await cache_set(f"discord:guilds:perms:{user_id}", guild_perms, ttl_seconds=300)

                for guild in guilds:
                    if int(guild["id"]) == guild_id:
                        permissions = int(guild.get("permissions", 0))
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
    await get_or_create_guild(guild_id, db)

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
    await get_or_create_guild(guild_id, db)

    result = await db.execute(select(LogChannel).where(LogChannel.guild_id == guild_id))
    log_channels = result.scalars().all()

    channels_dict = {
        lc.log_type: lc.channel_id if lc.enabled else None
        for lc in log_channels
    }

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
    discord_token = _require_discord_token(request)

    if not await verify_guild_permission(guild_id, discord_token, str(current_user.id)):
        raise HTTPException(403, "Você não tem permissão para modificar esta guild")

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
    discord_token = _require_discord_token(request)

    if not await verify_guild_permission(guild_id, discord_token, str(current_user.id)):
        raise HTTPException(403, "Você não tem permissão para modificar esta guild")

    await get_or_create_guild(guild_id, db)
    updated_channels = []

    for log_type, channel_id in log_data.channels.items():
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
                guild_id=guild_id, log_type=log_type,
                channel_id=channel_id, enabled=channel_id is not None
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[Dashboard] Retorna configuração completa da guild"""
    _require_discord_token(request)

    guild = await get_or_create_guild(guild_id, db)

    result = await db.execute(select(GuildStats).where(GuildStats.guild_id == guild_id))
    stats = result.scalar_one_or_none()

    result = await db.execute(select(LogChannel).where(LogChannel.guild_id == guild_id))
    log_channels = result.scalars().all()

    return {
        "guild_id": guild.id,
        "prefix": guild.prefix,
        "log_channels": {
            lc.log_type: {"channel_id": lc.channel_id, "enabled": lc.enabled}
            for lc in log_channels
        },
        "stats": {
            "member_count": stats.member_count if stats else 0,
            "online_count": stats.online_count if stats else 0,
            "channel_count": stats.channel_count if stats else 0,
            "role_count": stats.role_count if stats else 0,
            "updated_at": stats.updated_at.isoformat() if stats else None,
        },
        "created_at": guild.created_at.isoformat() if guild.created_at else None,
        "updated_at": guild.updated_at.isoformat() if guild.updated_at else None
    }


@router.post("/sync")
async def sync_guilds(
    guild_ids: list[int],
    db: AsyncSession = Depends(get_db),
    bot_user: str = Depends(verify_bot_auth)
):
    """[Bot] Sincroniza guilds"""
    created, existing = [], []

    for guild_id in guild_ids:
        result = await db.execute(select(Guild).where(Guild.id == guild_id))
        if not result.scalar_one_or_none():
            db.add(Guild(id=guild_id))
            created.append(guild_id)
        else:
            existing.append(guild_id)

    await db.commit()
    print(f"✅ Sync: {len(created)} criadas, {len(existing)} já existiam")
    return {"created": created, "existing": existing, "total": len(guild_ids)}


@router.put("/{guild_id}/stats")
async def update_guild_stats(
    guild_id: int,
    stats_data: dict,
    db: AsyncSession = Depends(get_db),
    bot_user: str = Depends(verify_bot_auth)
):
    """[Bot] Atualiza estatísticas da guild"""
    await get_or_create_guild(guild_id, db)

    result = await db.execute(select(GuildStats).where(GuildStats.guild_id == guild_id))
    stats = result.scalar_one_or_none()

    if not stats:
        stats = GuildStats(guild_id=guild_id)
        db.add(stats)

    stats.member_count = stats_data.get("member_count", 0)
    stats.online_count = stats_data.get("online_count", 0)
    stats.channel_count = stats_data.get("channel_count", 0)
    stats.role_count = stats_data.get("role_count", 0)

    await db.commit()
    await cache_delete_pattern(f"discord:guilds:list:*")

    return {"message": "Stats atualizados", "guild_id": guild_id}
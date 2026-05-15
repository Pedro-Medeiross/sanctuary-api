# app/routes/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from app.database import get_db
from app.models.core.user import User
from app.utils.security import get_current_user, get_valid_discord_token
from app.utils.cache import cache_get, cache_set, cache_delete
from app.config import settings

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

DISCORD_API_URL = "https://discord.com/api/v10"


# ============ HELPERS ============

async def _fetch_guild_channels(guild_id: int, discord_token: str) -> list:
    """Busca canais da guild com fallback bot token → user token"""
    async with aiohttp.ClientSession() as session:
        bot_token = settings.DISCORD_BOT_TOKEN

        if bot_token:
            async with session.get(
                f"{DISCORD_API_URL}/guilds/{guild_id}/channels",
                headers={"Authorization": f"Bot {bot_token}"}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()

        async with session.get(
            f"{DISCORD_API_URL}/guilds/{guild_id}/channels",
            headers={"Authorization": f"Bearer {discord_token}"}
        ) as resp:
            if resp.status != 200:
                raise HTTPException(400, "Falha ao obter canais")
            return await resp.json()


def _format_channels(guild_channels: list) -> dict:
    """Formata canais por tipo (categoria, texto, voz)"""
    channels = [
        {
            "id": ch["id"],
            "name": ch["name"],
            "type": ch["type"],
            "position": ch["position"],
            "parent_id": ch.get("parent_id")
        }
        for ch in guild_channels
        if ch["type"] in [0, 2, 4]  # 0=text, 2=voice, 4=category
    ]
    channels.sort(key=lambda x: x["position"])

    return {
        "categories": [c for c in channels if c["type"] == 4],
        "text_channels": [c for c in channels if c["type"] == 0],
        "voice_channels": [c for c in channels if c["type"] == 2],
        "total": len(channels),
        "all": channels
    }


async def _get_discord_token(request: Request, user: User, db) -> str:
    """Obtém token do Discord (header ou auto-renew)"""
    token = request.headers.get("X-Discord-Token")
    if not token:
        token = await get_valid_discord_token(user.id, db)
    if not token:
        raise HTTPException(400, "Token do Discord não fornecido")
    return token


# ============ ROTAS ============

@router.get("/guilds")
async def get_user_guilds_info(
    current_user: User = Depends(get_current_user)
):
    """Informações sobre como listar guilds."""
    return {
        "message": "Para listar guilds, use /dashboard/guilds/list enviando o token do Discord",
        "user_id": current_user.id,
        "username": current_user.username,
        "required_header": "X-Discord-Token"
    }


@router.get("/guilds/list")
async def list_manageable_guilds(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lista guilds do usuário com cache (2 min) e auto-renew"""
    discord_token = await _get_discord_token(request, current_user, db)

    # Cache
    cache_key = f"discord:guilds:list:{str(current_user.id)}"
    cached = await cache_get(cache_key)
    if cached:
        print(f"📦 Cache hit: guilds list para {current_user.username}")
        return cached

    # Buscar guilds
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DISCORD_API_URL}/users/@me/guilds",
            headers={"Authorization": f"Bearer {discord_token}"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                print(f"❌ Discord API error {resp.status}: {error_text}")
                raise HTTPException(400, "Falha ao obter guilds do Discord")
            guilds = await resp.json()

    manageable_guilds = [
        {
            "id": g["id"],
            "name": g["name"],
            "icon": g["icon"],
            "owner": g.get("owner", False),
            "permissions": g.get("permissions", "0"),
            "channels": [],  # Carregados sob demanda
            "approximate_member_count": g.get("approximate_member_count", 0)
        }
        for g in guilds
        if int(g.get("permissions", 0)) & 0x8 or int(g.get("permissions", 0)) & 0x20
    ]

    result = {"guilds": manageable_guilds, "total": len(manageable_guilds)}
    await cache_set(cache_key, result, ttl_seconds=120)

    print(f"✅ Guilds carregadas para {current_user.username}: {len(manageable_guilds)}")
    return result


@router.get("/guilds/{guild_id}/channels")
async def get_guild_channels(
    guild_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Retorna canais de uma guild específica (com cache)"""
    discord_token = await _get_discord_token(request, current_user, None)

    # Cache
    cache_key = f"discord:channels:detail:{guild_id}:{str(current_user.id)}"
    cached = await cache_get(cache_key)
    if cached:
        print(f"📦 Cache hit: canais guild {guild_id}")
        return cached

    # Buscar e formatar
    guild_channels = await _fetch_guild_channels(guild_id, discord_token)
    result = _format_channels(guild_channels)
    
    # Remover 'all' da resposta
    del result["all"]
    result["guild_id"] = guild_id

    await cache_set(cache_key, result, ttl_seconds=300)
    print(f"✅ Canais carregados para guild {guild_id}: {result['total']}")
    return result


@router.post("/guilds/{guild_id}/sync-channels")
async def sync_guild_channels(
    guild_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Força atualização do cache de canais de uma guild"""
    discord_token = await _get_discord_token(request, current_user, None)

    # Limpar caches
    await cache_delete(f"discord:channels:{guild_id}:{str(current_user.id)}")
    await cache_delete(f"discord:channels:detail:{guild_id}:{str(current_user.id)}")
    await cache_delete(f"discord:guilds:list:{str(current_user.id)}")

    # Buscar e formatar
    guild_channels = await _fetch_guild_channels(guild_id, discord_token)
    formatted = _format_channels(guild_channels)

    # Atualizar caches
    await cache_set(
        f"discord:channels:{guild_id}:{str(current_user.id)}",
        {"channels": formatted["all"]},
        ttl_seconds=300
    )
    await cache_set(
        f"discord:channels:detail:{guild_id}:{str(current_user.id)}",
        {
            "guild_id": guild_id,
            "categories": formatted["categories"],
            "text_channels": formatted["text_channels"],
            "voice_channels": formatted["voice_channels"],
            "total": formatted["total"]
        },
        ttl_seconds=300
    )

    print(f"🔄 Cache de canais atualizado: guild {guild_id} ({formatted['total']} canais)")

    return {
        "message": "Canais sincronizados com sucesso",
        "guild_id": guild_id,
        "categories": formatted["categories"],
        "text_channels": formatted["text_channels"],
        "voice_channels": formatted["voice_channels"],
        "total": formatted["total"]
    }
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from app.database import get_db
from app.models.core.user import User
from app.utils.security import get_current_user
from app.utils.cache import cache_get, cache_set, cache_delete
from app.config import settings

router = APIRouter(prefix="/guilds", tags=["Roles"])

DISCORD_API_URL = "https://discord.com/api/v10"

# ============ NÍVEIS DE SUPORTE ============

SUPPORT_LEVELS = {
    1: {"name": "Ajudante", "description": "Em treinamento, supervisionado por Supervisores+"},
    2: {"name": "Moderador", "description": "Staff padrão, atende tickets normalmente"},
    3: {"name": "Supervisor", "description": "Gerencia equipe, vê todos tickets, aplica bans"},
    4: {"name": "Coordenador", "description": "Gerencia painéis, configurações e cargos"},
}


# ============ HELPERS ============

def _format_roles(roles: list) -> list:
    """Formata roles da Discord API para resposta"""
    formatted = []
    for role in roles:
        if role["name"] == "@everyone":
            continue
        color = role.get("color", 0)
        formatted.append({
            "id": role["id"],
            "name": role["name"],
            "color": color,
            "hex_color": f"#{color:06x}" if color > 0 else "#99AAB5",
            "position": role.get("position", 0),
            "permissions": role.get("permissions", "0"),
            "managed": role.get("managed", False),
            "hoist": role.get("hoist", False),
            "mentionable": role.get("mentionable", False),
        })
    formatted.sort(key=lambda x: x["position"], reverse=True)
    return formatted


async def _fetch_discord_roles(guild_id: int) -> list:
    """Busca roles da Discord API usando o bot token"""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DISCORD_API_URL}/guilds/{guild_id}/roles",
            headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
        ) as resp:
            if resp.status != 200:
                raise HTTPException(400, "Falha ao obter cargos")
            return await resp.json()


def _require_discord_token(request: Request) -> str:
    """Extrai e valida X-Discord-Token do header"""
    token = request.headers.get("X-Discord-Token")
    if not token:
        raise HTTPException(400, "Token do Discord não fornecido")
    return token


# ============ ROTAS ============

@router.get("/support-levels")
async def get_support_levels():
    """Retorna os níveis de suporte disponíveis"""
    return {
        "levels": [
            {"level": level, "name": data["name"], "description": data["description"]}
            for level, data in SUPPORT_LEVELS.items()
        ]
    }


@router.get("/{guild_id}/roles")
async def get_guild_roles(
    guild_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Retorna os cargos de uma guild (com cache)"""
    _require_discord_token(request)

    # Cache
    cache_key = f"discord:roles:{guild_id}"
    cached = await cache_get(cache_key)
    if cached:
        print(f"📦 Cache hit: roles guild {guild_id}")
        return cached

    # Buscar e formatar
    roles = await _fetch_discord_roles(guild_id)
    formatted_roles = _format_roles(roles)

    result = {
        "guild_id": guild_id,
        "roles": formatted_roles,
        "total": len(formatted_roles)
    }

    await cache_set(cache_key, result, ttl_seconds=600)
    print(f"✅ Cargos carregados: guild {guild_id} ({len(formatted_roles)} cargos)")
    return result


@router.post("/{guild_id}/roles/sync")
async def sync_guild_roles(
    guild_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Força atualização do cache de cargos"""
    _require_discord_token(request)

    # Limpar cache
    cache_key = f"discord:roles:{guild_id}"
    await cache_delete(cache_key)

    # Buscar e formatar
    roles = await _fetch_discord_roles(guild_id)
    formatted_roles = _format_roles(roles)

    result = {
        "guild_id": guild_id,
        "roles": formatted_roles,
        "total": len(formatted_roles)
    }

    await cache_set(cache_key, result, ttl_seconds=600)
    print(f"🔄 Cargos sincronizados: guild {guild_id}")
    return result
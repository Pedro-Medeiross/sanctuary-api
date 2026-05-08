# app/routes/roles.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from app.database import get_db
from app.models.user import User
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

@router.get("/support-levels")
async def get_support_levels():
    """Retorna os níveis de suporte disponíveis"""
    return {
        "levels": [
            {"level": level, "name": data["name"], "description": data["description"]}
            for level, data in SUPPORT_LEVELS.items()
        ]
    }

# ============ ROLES DA GUILD ============

@router.get("/{guild_id}/roles")
async def get_guild_roles(
    guild_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Retorna os cargos de uma guild (com cache)"""
    discord_token = request.headers.get("X-Discord-Token")
    if not discord_token:
        raise HTTPException(400, "Token do Discord não fornecido")
    
    # ========== VERIFICAR CACHE ==========
    cache_key = f"discord:roles:{guild_id}"
    cached = await cache_get(cache_key)
    if cached:
        print(f"📦 Cache hit: roles guild {guild_id}")
        return cached
    
    # ========== BUSCAR DA API ==========
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DISCORD_API_URL}/guilds/{guild_id}/roles",
            headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
        ) as roles_response:
            if roles_response.status != 200:
                raise HTTPException(400, "Falha ao obter cargos")
            
            roles = await roles_response.json()
    
    # Formatar resposta
    formatted_roles = []
    for role in roles:
        # Pular @everyone
        if role["name"] == "@everyone":
            continue
            
        formatted_roles.append({
            "id": role["id"],
            "name": role["name"],
            "color": role.get("color", 0),
            "hex_color": f"#{role.get('color', 0):06x}" if role.get("color", 0) > 0 else "#99AAB5",
            "position": role.get("position", 0),
            "permissions": role.get("permissions", "0"),
            "managed": role.get("managed", False),
            "hoist": role.get("hoist", False),
            "mentionable": role.get("mentionable", False),
        })
    
    # Ordenar por posição (cargos mais altos primeiro)
    formatted_roles.sort(key=lambda x: x["position"], reverse=True)
    
    result = {
        "guild_id": guild_id,
        "roles": formatted_roles,
        "total": len(formatted_roles)
    }
    
    # ========== SALVAR NO CACHE (10 min) ==========
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
    discord_token = request.headers.get("X-Discord-Token")
    if not discord_token:
        raise HTTPException(400, "Token do Discord não fornecido")
    
    # Limpar cache
    cache_key = f"discord:roles:{guild_id}"
    await cache_delete(cache_key)
    
    # Buscar atualizado
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DISCORD_API_URL}/guilds/{guild_id}/roles",
            headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
        ) as roles_response:
            if roles_response.status != 200:
                raise HTTPException(400, "Falha ao obter cargos")
            
            roles = await roles_response.json()
    
    formatted_roles = []
    for role in roles:
        if role["name"] == "@everyone":
            continue
            
        formatted_roles.append({
            "id": role["id"],
            "name": role["name"],
            "color": role.get("color", 0),
            "hex_color": f"#{role.get('color', 0):06x}" if role.get("color", 0) > 0 else "#99AAB5",
            "position": role.get("position", 0),
            "permissions": role.get("permissions", "0"),
            "managed": role.get("managed", False),
            "hoist": role.get("hoist", False),
            "mentionable": role.get("mentionable", False),
        })
    
    formatted_roles.sort(key=lambda x: x["position"], reverse=True)
    
    result = {
        "guild_id": guild_id,
        "roles": formatted_roles,
        "total": len(formatted_roles)
    }
    
    await cache_set(cache_key, result, ttl_seconds=600)
    
    print(f"🔄 Cargos sincronizados: guild {guild_id}")
    return result
# app/routes/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
import aiohttp

from app.database import get_db
from app.models.user import User
from app.utils.security import get_current_user
from app.utils.cache import cache_get, cache_set, cache_delete_pattern, cache_delete
from app.config import settings

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

DISCORD_API_URL = "https://discord.com/api/v10"

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
    current_user: User = Depends(get_current_user)
):
    """Lista guilds do usuário com cache (2 min)"""
    discord_token = request.headers.get("X-Discord-Token")
    
    if not discord_token:
        raise HTTPException(400, "Token do Discord não fornecido")
    
    # ========== VERIFICAR CACHE ==========
    cache_key = f"discord:guilds:list:{str(current_user.id)}"
    cached = await cache_get(cache_key)
    if cached:
        print(f"📦 Cache hit: guilds list para {current_user.username}")
        return cached
    
    # ========== BUSCAR DA API ==========
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DISCORD_API_URL}/users/@me/guilds",
            headers={"Authorization": f"Bearer {discord_token}"}
        ) as guilds_response:
            if guilds_response.status != 200:
                raise HTTPException(400, "Falha ao obter guilds do Discord")
            guilds = await guilds_response.json()
        
        manageable_guilds = []
        
        for guild in guilds:
            permissions = int(guild.get("permissions", 0))
            
            if permissions & 0x8 or permissions & 0x20:
                
                # ========== CACHE DE CANAIS POR GUILD ==========
                channels_cache_key = f"discord:channels:{guild['id']}:{str(current_user.id)}"
                cached_data = await cache_get(channels_cache_key)  # ← Renomear

                if cached_data and isinstance(cached_data, dict):
                    channels = cached_data.get("channels", [])
                else:
                    channels = None

                if channels is None:
                    async with session.get(
                        f"{DISCORD_API_URL}/guilds/{guild['id']}/channels",
                        headers={"Authorization": f"Bearer {discord_token}"}
                    ) as channels_response:
                        if channels_response.status == 200:
                            guild_channels = await channels_response.json()
                            channels = [
                                {
                                    "id": ch["id"],
                                    "name": ch["name"],
                                    "type": ch["type"],
                                    "position": ch["position"],
                                    "parent_id": ch.get("parent_id")
                                }
                                for ch in guild_channels
                                if ch["type"] in [0, 2, 4]
                            ]
                            channels.sort(key=lambda x: x["position"])
                        else:
                            channels = []
                    
                    # Salvar canais em cache (5 min)
                    await cache_set(channels_cache_key, {"channels": channels}, ttl_seconds=300)
                
                manageable_guilds.append({
                    "id": guild["id"],
                    "name": guild["name"],
                    "icon": guild["icon"],
                    "owner": guild.get("owner", False),
                    "permissions": guild.get("permissions", "0"),
                    "channels": channels,
                    "approximate_member_count": guild.get("approximate_member_count", 0)
                })
        
        result = {"guilds": manageable_guilds, "total": len(manageable_guilds)}
        
        # ========== SALVAR NO CACHE (2 min) ==========
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
    discord_token = request.headers.get("X-Discord-Token")
    
    if not discord_token:
        raise HTTPException(400, "Token do Discord não fornecido")
    
    # ========== VERIFICAR CACHE ==========
    cache_key = f"discord:channels:detail:{guild_id}:{str(current_user.id)}"
    cached = await cache_get(cache_key)
    if cached:
        print(f"📦 Cache hit: canais guild {guild_id}")
        return cached
    
    async with aiohttp.ClientSession() as session:
        # Tentar com token do BOT primeiro (mais confiável)
        bot_token = settings.DISCORD_BOT_TOKEN
        
        if bot_token:
            async with session.get(
                f"{DISCORD_API_URL}/guilds/{guild_id}/channels",
                headers={"Authorization": f"Bot {bot_token}"}
            ) as channels_response:
                if channels_response.status == 200:
                    channels = await channels_response.json()
                else:
                    # Fallback: tentar com token do usuário
                    async with session.get(
                        f"{DISCORD_API_URL}/guilds/{guild_id}/channels",
                        headers={"Authorization": f"Bearer {discord_token}"}
                    ) as user_channels_response:
                        if user_channels_response.status != 200:
                            raise HTTPException(400, "Falha ao obter canais")
                        channels = await user_channels_response.json()
        else:
            # Sem bot token, usar token do usuário
            async with session.get(
                f"{DISCORD_API_URL}/guilds/{guild_id}/channels",
                headers={"Authorization": f"Bearer {discord_token}"}
            ) as channels_response:
                if channels_response.status != 200:
                    raise HTTPException(400, "Falha ao obter canais")
                channels = await channels_response.json()
        
        categories = []
        text_channels = []
        voice_channels = []
        
        for ch in channels:
            channel_info = {
                "id": ch["id"],
                "name": ch["name"],
                "type": ch["type"],
                "position": ch["position"],
                "parent_id": ch.get("parent_id")
            }
            
            if ch["type"] == 4:
                categories.append(channel_info)
            elif ch["type"] == 0:
                text_channels.append(channel_info)
            elif ch["type"] == 2:
                voice_channels.append(channel_info)
        
        result = {
            "guild_id": guild_id,
            "categories": sorted(categories, key=lambda x: x["position"]),
            "text_channels": sorted(text_channels, key=lambda x: x["position"]),
            "voice_channels": sorted(voice_channels, key=lambda x: x["position"]),
            "total": len(channels)
        }
        
        await cache_set(cache_key, result, ttl_seconds=300)
        
        print(f"✅ Canais carregados para guild {guild_id}: {len(channels)}")
        return result
        
@router.post("/guilds/{guild_id}/sync-channels")
async def sync_guild_channels(
    guild_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Força atualização do cache de canais de uma guild"""
    discord_token = request.headers.get("X-Discord-Token")
    if not discord_token:
        raise HTTPException(400, "Token do Discord não fornecido")
    
    # Limpar cache de canais dessa guild
    await cache_delete(f"discord:channels:{guild_id}:{str(current_user.id)}")
    await cache_delete(f"discord:channels:detail:{guild_id}:{str(current_user.id)}")
    await cache_delete(f"discord:guilds:list:{str(current_user.id)}")
    
    # Buscar canais atualizados da Discord API
    async with aiohttp.ClientSession() as session:
        # Tentar com token do BOT primeiro (mais confiável, não expira)
        bot_token = settings.DISCORD_BOT_TOKEN
        headers = {"Authorization": f"Bot {bot_token}"} if bot_token else {"Authorization": f"Bearer {discord_token}"}
        
        async with session.get(
            f"{DISCORD_API_URL}/guilds/{guild_id}/channels",
            headers=headers
        ) as channels_response:
            if channels_response.status != 200:
                # Fallback: tentar com token do usuário
                async with session.get(
                    f"{DISCORD_API_URL}/guilds/{guild_id}/channels",
                    headers={"Authorization": f"Bearer {discord_token}"}
                ) as fallback_response:
                    if fallback_response.status != 200:
                        raise HTTPException(400, "Falha ao obter canais")
                    guild_channels = await fallback_response.json()
            else:
                guild_channels = await channels_response.json()
        
        channels = [
            {
                "id": ch["id"],
                "name": ch["name"],
                "type": ch["type"],
                "position": ch["position"],
                "parent_id": ch.get("parent_id")
            }
            for ch in guild_channels
            if ch["type"] in [0, 2, 4]
        ]
        channels.sort(key=lambda x: x["position"])
    
    # Atualizar cache
    await cache_set(
        f"discord:channels:{guild_id}:{str(current_user.id)}",
        {"channels": channels},
        ttl_seconds=300
    )
    await cache_set(
        f"discord:channels:detail:{guild_id}:{str(current_user.id)}",
        {
            "guild_id": guild_id,
            "categories": [c for c in channels if c["type"] == 4],
            "text_channels": [c for c in channels if c["type"] == 0],
            "voice_channels": [c for c in channels if c["type"] == 2],
            "total": len(channels)
        },
        ttl_seconds=300
    )
    
    # Organizar por tipo
    categories = [c for c in channels if c["type"] == 4]
    text = [c for c in channels if c["type"] == 0]
    voice = [c for c in channels if c["type"] == 2]
    
    print(f"🔄 Cache de canais atualizado: guild {guild_id} ({len(channels)} canais)")
    
    return {
        "message": "Canais sincronizados com sucesso",
        "guild_id": guild_id,
        "categories": categories,
        "text_channels": text,
        "voice_channels": voice,
        "total": len(channels)
    }
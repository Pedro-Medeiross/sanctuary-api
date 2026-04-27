# app/routes/dashboard.py (atualizado com aiohttp)
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
import aiohttp

from app.database import get_db
from app.models.user import User
from app.utils.security import get_current_user
from app.config import settings

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

DISCORD_API_URL = "https://discord.com/api/v10"

@router.get("/guilds")
async def get_user_guilds_info(
    current_user: User = Depends(get_current_user)
):
    """
    Informações sobre como listar guilds.
    """
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
    """
    Lista guilds do usuário usando o token do Discord enviado pelo frontend.
    Header: X-Discord-Token: <discord_oauth_token>
    """
    discord_token = request.headers.get("X-Discord-Token")
    
    if not discord_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token do Discord não fornecido. Envie no header X-Discord-Token"
        )
    
    async with aiohttp.ClientSession() as session:
        # Buscar guilds do usuário
        async with session.get(
            f"{DISCORD_API_URL}/users/@me/guilds",
            headers={"Authorization": f"Bearer {discord_token}"}
        ) as guilds_response:
            if guilds_response.status != 200:
                error_text = await guilds_response.text()
                print(f"❌ Erro ao buscar guilds: {error_text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Falha ao obter guilds do Discord"
                )
            
            guilds = await guilds_response.json()
        
        # Filtrar guilds onde o usuário tem permissão e buscar canais
        manageable_guilds = []
        
        for guild in guilds:
            permissions = int(guild.get("permissions", 0))
            
            # Verificar se tem permissão de administrador ou gerenciar servidor
            if permissions & 0x8 or permissions & 0x20:  # ADMINISTRATOR ou MANAGE_GUILD
                # Buscar canais da guild
                async with session.get(
                    f"{DISCORD_API_URL}/guilds/{guild['id']}/channels",
                    headers={"Authorization": f"Bearer {discord_token}"}
                ) as channels_response:
                    channels = []
                    if channels_response.status == 200:
                        guild_channels = await channels_response.json()
                        # Filtrar apenas canais de texto, voz e categorias
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
                        # Ordenar por posição
                        channels.sort(key=lambda x: x["position"])
                
                manageable_guilds.append({
                    "id": guild["id"],
                    "name": guild["name"],
                    "icon": guild["icon"],
                    "owner": guild.get("owner", False),
                    "permissions": guild.get("permissions", "0"),
                    "channels": channels,
                    "approximate_member_count": guild.get("approximate_member_count", 0)
                })
        
        print(f"✅ Guilds carregadas para {current_user.username}: {len(manageable_guilds)}")
        
        return {
            "guilds": manageable_guilds,
            "total": len(manageable_guilds)
        }

@router.get("/guilds/{guild_id}/channels")
async def get_guild_channels(
    guild_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Retorna canais de uma guild específica.
    Header: X-Discord-Token: <discord_oauth_token>
    """
    discord_token = request.headers.get("X-Discord-Token")
    
    if not discord_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token do Discord não fornecido"
        )
    
    async with aiohttp.ClientSession() as session:
        # Verificar se usuário tem permissão na guild
        async with session.get(
            f"{DISCORD_API_URL}/users/@me/guilds",
            headers={"Authorization": f"Bearer {discord_token}"}
        ) as guilds_response:
            if guilds_response.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sem permissão para acessar esta guild"
                )
            
            guilds = await guilds_response.json()
            
            has_permission = False
            for guild in guilds:
                if int(guild["id"]) == guild_id:
                    permissions = int(guild.get("permissions", 0))
                    if permissions & 0x8 or permissions & 0x20:
                        has_permission = True
                    break
            
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para gerenciar esta guild"
                )
        
        # Buscar canais
        async with session.get(
            f"{DISCORD_API_URL}/guilds/{guild_id}/channels",
            headers={"Authorization": f"Bearer {discord_token}"}
        ) as channels_response:
            if channels_response.status != 200:
                error_text = await channels_response.text()
                print(f"❌ Erro ao buscar canais: {error_text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Falha ao obter canais"
                )
            
            channels = await channels_response.json()
            
            # Organizar canais por categoria
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
                
                if ch["type"] == 4:  # Category
                    categories.append(channel_info)
                elif ch["type"] == 0:  # Text
                    text_channels.append(channel_info)
                elif ch["type"] == 2:  # Voice
                    voice_channels.append(channel_info)
            
            print(f"✅ Canais carregados para guild {guild_id}: {len(channels)}")
            
            return {
                "guild_id": guild_id,
                "categories": sorted(categories, key=lambda x: x["position"]),
                "text_channels": sorted(text_channels, key=lambda x: x["position"]),
                "voice_channels": sorted(voice_channels, key=lambda x: x["position"]),
                "total": len(channels)
            }
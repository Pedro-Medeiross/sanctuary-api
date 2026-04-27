# app/routes/auth.py (atualizado com aiohttp)
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
import aiohttp

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.session import Session
from app.schemas.user import UserResponse, TokenResponse, DiscordAuthRequest
from app.utils.security import (
    get_current_user, 
    get_current_user_optional,
    create_access_token, 
    create_refresh_token
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])

DISCORD_API_URL = "https://discord.com/api/v10"
DISCORD_OAUTH_SCOPES = "identify email guilds guilds.members.read"

@router.post("/discord", response_model=TokenResponse)
async def discord_auth(
    auth_data: DiscordAuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Autentica com Discord OAuth2.
    O dashboard React envia o código de autorização e recebe os tokens.
    """
    async with aiohttp.ClientSession() as session:
        # Trocar code por access token do Discord
        token_data = {
            "client_id": settings.DISCORD_CLIENT_ID,
            "client_secret": settings.DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": auth_data.code,
            "redirect_uri": auth_data.redirect_uri,
        }
        
        async with session.post(
            f"{DISCORD_API_URL}/oauth2/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        ) as token_response:
            if token_response.status != 200:
                error_text = await token_response.text()
                print(f"❌ Erro Discord OAuth: {error_text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Falha na autenticação com Discord"
                )
            
            token_json = await token_response.json()
            discord_access_token = token_json["access_token"]
        
        # Obter dados do usuário
        async with session.get(
            f"{DISCORD_API_URL}/users/@me",
            headers={"Authorization": f"Bearer {discord_access_token}"}
        ) as user_response:
            if user_response.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Falha ao obter dados do usuário"
                )
            
            user_data = await user_response.json()
        
        # Obter guilds do usuário (para verificar permissões)
        async with session.get(
            f"{DISCORD_API_URL}/users/@me/guilds",
            headers={"Authorization": f"Bearer {discord_access_token}"}
        ) as guilds_response:
            user_guilds = []
            if guilds_response.status == 200:
                user_guilds = await guilds_response.json()
    
    # Criar ou atualizar usuário
    result = await db.execute(
        select(User).where(User.id == int(user_data["id"]))
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Atualizar dados
        user.username = user_data.get("username")
        user.avatar = user_data.get("avatar")
        user.email = user_data.get("email")
        user.last_login = datetime.now(timezone.utc)
    else:
        # Criar novo usuário
        user = User(
            id=int(user_data["id"]),
            username=user_data.get("username"),
            avatar=user_data.get("avatar"),
            email=user_data.get("email"),
            last_login=datetime.now(timezone.utc)
        )
        db.add(user)
    
    await db.flush()
    
    # Criar tokens JWT (30 dias)
    access_token = create_access_token({
        "sub": str(user.id),
    })
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    # Salvar sessão
    session = Session(
        user_id=user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    )
    db.add(session)
    await db.flush()
    
    # Configurar cookies HTTP-only
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=False,  # True em produção com HTTPS
        samesite="lax",
        path="/"
    )
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=False,  # True em produção com HTTPS
        samesite="lax",
        path="/"
    )
    
    print(f"✅ Login bem-sucedido: {user.username} (ID: {user.id})")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user)
    )

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Retorna dados do usuário logado"""
    return UserResponse.model_validate(current_user)

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Renova o access token usando refresh token (do cookie)"""
    refresh_token_value = request.cookies.get("refresh_token")
    
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token não encontrado"
        )
    
    from app.utils.security import verify_token
    
    payload = verify_token(refresh_token_value, "refresh")
    user_id = payload.get("sub")
    
    # Verificar se sessão existe e está ativa
    result = await db.execute(
        select(Session).where(
            Session.user_id == int(user_id),
            Session.refresh_token == refresh_token_value,
            Session.is_active == True
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou revogado"
        )
    
    # Desativar sessão antiga
    session.is_active = False
    
    # Obter usuário
    result = await db.execute(
        select(User).where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado"
        )
    
    # Criar novos tokens
    new_access_token = create_access_token({"sub": user_id})
    new_refresh_token = create_refresh_token({"sub": user_id})
    
    # Criar nova sessão
    new_session = Session(
        user_id=user.id,
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    )
    db.add(new_session)
    
    # Atualizar cookies
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/"
    )
    
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/"
    )
    
    print(f"🔄 Token renovado para usuário: {user.username}")
    
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        user=UserResponse.model_validate(user)
    )

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Logout - invalida a sessão atual"""
    access_token = request.cookies.get("access_token")
    
    if access_token:
        # Buscar e desativar sessão
        result = await db.execute(
            select(Session).where(
                Session.access_token == access_token,
                Session.is_active == True
            )
        )
        session = result.scalar_one_or_none()
        
        if session:
            session.is_active = False
            print(f"👋 Logout: usuário {session.user_id}")
    
    # Limpar cookies
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    
    return {"message": "Logout realizado com sucesso"}

@router.get("/login-url")
async def get_discord_login_url():
    """Retorna a URL de login do Discord para o frontend"""
    discord_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={settings.DISCORD_CLIENT_ID}"
        f"&redirect_uri={settings.DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={DISCORD_OAUTH_SCOPES.replace(' ', '%20')}"
    )
    
    return {
        "url": discord_url
    }
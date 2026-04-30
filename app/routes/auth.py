# app/routes/auth.py - ADICIONAR NO TOPO
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, UploadFile  # ← ADICIONAR UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp
import uuid
import os
from pathlib import Path

from app.utils.uploads import (
    ensure_directories, validate_image, delete_old_file, 
    save_image, get_file_path, AVATARS_DIR, BANNERS_DIR
)

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.session import Session
from app.models.user_connection import UserConnection, ConnectionProvider
from app.models.role import Role
from app.schemas.user import (
    UserRegisterRequest, 
    UserLoginRequest, 
    UserResponse, 
    TokenResponse, 
    DiscordAuthRequest, 
    GoogleAuthRequest,
    LinkDiscordRequest, 
    LinkGoogleRequest,
    UserProfileUpdate,
    UserPasswordUpdate,
)
from app.utils.security import (
    get_current_user, 
    create_access_token, 
    create_refresh_token,
    hash_password,
    verify_password,
    verify_app_auth
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])

DISCORD_API_URL = "https://discord.com/api/v10"

# ============ REGISTRO LOCAL ============

# app/routes/auth.py - REGISTER CORRIGIDO
@router.post("/register", response_model=TokenResponse)
async def register(
    user_data: UserRegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    app_user: str = Depends(verify_app_auth)
):
    """Registro com email/senha"""
    from app.models.role import user_roles  # ← IMPORTAR TABELA DE ASSOCIAÇÃO
    
    # Verificar se email já existe
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email já cadastrado")
    
    # Verificar se username já existe
    result = await db.execute(
        select(User).where(User.username == user_data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, "Username já existe")
    
    # Criar usuário
    user = User(
        id=uuid.uuid4(),
        username=user_data.username,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        is_verified=False
    )
    db.add(user)
    await db.flush()
    
    # Atribuir role padrão "Player"
    result = await db.execute(
        select(Role).where(Role.name == "Player", Role.is_default == True)
    )
    default_role = result.scalar_one_or_none()
    
    if default_role:
        # Inserir diretamente na tabela de associação (sem disparar lazy load)
        from sqlalchemy import insert
        await db.execute(
            insert(user_roles).values(
                user_id=user.id,
                role_id=default_role.id
            )
        )
    
    # Criar tokens JWT
    access_token = create_access_token({"sub": str(user.id)})
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
    await db.commit()
    
    # Cookies
    response.set_cookie(
        "access_token", access_token, 
        max_age=settings.ACCESS_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=False, samesite="lax", path="/"
    )
    response.set_cookie(
        "refresh_token", refresh_token, 
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=False, samesite="lax", path="/"
    )
    
    print(f"✅ Novo registro: {user.username} ({user.email})")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            roles=["Player"] if default_role else [],
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    )

# ============ LOGIN LOCAL ============

@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    app_user: str = Depends(verify_app_auth)
):
    """Login com email/senha"""
    
    # Buscar usuário COM ROLES (eager load)
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.email == login_data.email)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(401, "Email ou senha inválidos")
    
    if not user.is_active:
        raise HTTPException(403, "Conta desativada")
    
    # Criar tokens
    access_token = create_access_token({"sub": str(user.id)})
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
    await db.commit()
    
    # Cookies
    response.set_cookie(
        "access_token", access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=False, samesite="lax", path="/"
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=False, samesite="lax", path="/"
    )
    
    print(f"🔑 Login: {user.username}")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            avatar_url=user.avatar_url,
            roles=[role.name for role in user.roles],
            discord_id=user.discord_id,
            google_id=user.google_id,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    )

# ============ OAUTH DISCORD ============

@router.get("/discord/login-url")
async def get_discord_login_url(
    app_user: str = Depends(verify_app_auth)
):
    """URL de login com Discord"""
    url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={settings.DISCORD_CLIENT_ID}"
        f"&redirect_uri={settings.DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20email%20guilds"
    )
    return {"url": url}

@router.post("/discord", response_model=TokenResponse)
async def discord_auth(
    auth_data: DiscordAuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    app_user: str = Depends(verify_app_auth)
):
    """Login/Criar conta com Discord"""
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{DISCORD_API_URL}/oauth2/token",
            data={
                "client_id": settings.DISCORD_CLIENT_ID,
                "client_secret": settings.DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": auth_data.code,
                "redirect_uri": auth_data.redirect_uri,
            }
        ) as token_resp:
            if token_resp.status != 200:
                raise HTTPException(400, "Falha na autenticação Discord")
            token_data = await token_resp.json()
        
        async with session.get(
            f"{DISCORD_API_URL}/users/@me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        ) as user_resp:
            discord_user = await user_resp.json()
    
    discord_id = int(discord_user["id"])
    role_names = []
    
    # Verificar se já existe usuário com esse Discord
    result = await db.execute(
        select(User).where(User.discord_id == discord_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        discord_email = discord_user.get("email")
        if discord_email:
            result = await db.execute(
                select(User).where(User.email == discord_email)
            )
            user = result.scalar_one_or_none()
            if user:
                user.discord_id = discord_id
                user.avatar_url = user.avatar_url or f"https://cdn.discordapp.com/avatars/{discord_id}/{discord_user['avatar']}.png"
        
        if not user:
            user = User(
                id=uuid.uuid4(),
                username=discord_user["username"],
                email=discord_email or f"{discord_id}@discord.user",
                password_hash=hash_password(str(uuid.uuid4())),
                avatar_url=f"https://cdn.discordapp.com/avatars/{discord_id}/{discord_user['avatar']}.png" if discord_user.get("avatar") else None,
                discord_id=discord_id,
                is_verified=True
            )
            db.add(user)
            await db.flush()
            
            # Atribuir role Player
            result = await db.execute(
                select(Role).where(Role.name == "Player", Role.is_default == True)
            )
            default_role = result.scalar_one_or_none()
            if default_role:
                from sqlalchemy import insert
                await db.execute(
                    insert(user_roles).values(
                        user_id=user.id,
                        role_id=default_role.id
                    )
                )
    
    # Se usuário já existia, carregar roles
    if not role_names and user:
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user.id)
        )
        user = result.scalar_one()
        role_names = [role.name for role in user.roles]
    
    # Criar conexão
    connection = UserConnection(
        user_id=user.id,
        provider=ConnectionProvider.DISCORD,
        provider_user_id=str(discord_id),
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        provider_username=discord_user["username"],
        provider_email=discord_user.get("email"),
        provider_avatar=discord_user.get("avatar")
    )
    db.add(connection)
    
    # Criar tokens JWT
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    # Salvar sessão
    db_session = Session(
        user_id=user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    )
    db.add(db_session)
    await db.flush()
    await db.commit()
    
    # Cookies
    response.set_cookie(
        "access_token", access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=False, samesite="lax", path="/"
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=False, samesite="lax", path="/"
    )
    
    print(f"✅ Login Discord: {user.username}")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            avatar_url=user.avatar_url,
            roles=role_names,
            discord_id=user.discord_id,
            google_id=user.google_id,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    )

# ============ VINCULAR DISCORD ============

@router.post("/link-discord")
async def link_discord(
    link_data: LinkDiscordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Vincula Discord a uma conta existente"""
    
    if current_user.discord_id:
        raise HTTPException(400, "Discord já vinculado")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{DISCORD_API_URL}/oauth2/token",
            data={
                "client_id": settings.DISCORD_CLIENT_ID,
                "client_secret": settings.DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": link_data.code,
                "redirect_uri": link_data.redirect_uri,
            }
        ) as token_resp:
            if token_resp.status != 200:
                raise HTTPException(400, "Falha na autenticação Discord")
            token_data = await token_resp.json()
        
        async with session.get(
            f"{DISCORD_API_URL}/users/@me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        ) as user_resp:
            discord_user = await user_resp.json()
    
    discord_id = int(discord_user["id"])
    
    result = await db.execute(
        select(User).where(User.discord_id == discord_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, "Este Discord já está vinculado a outra conta")
    
    current_user.discord_id = discord_id
    current_user.avatar_url = current_user.avatar_url or f"https://cdn.discordapp.com/avatars/{discord_id}/{discord_user['avatar']}.png"
    
    connection = UserConnection(
        user_id=current_user.id,
        provider=ConnectionProvider.DISCORD,
        provider_user_id=str(discord_id),
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        provider_username=discord_user["username"],
        provider_email=discord_user.get("email"),
        provider_avatar=discord_user.get("avatar")
    )
    db.add(connection)
    await db.flush()
    await db.commit()
    
    print(f"🔗 Discord vinculado: {current_user.username} -> {discord_user['username']}")
    
    return {"message": "Discord vinculado com sucesso", "discord_id": discord_id}

# ============ ME ============

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retorna dados do usuário logado"""
    
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == current_user.id)
    )
    user = result.scalar_one()
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        avatar_url=user.avatar_url,
        banner_url=user.banner_url,  # ← NOVO
        bio=user.bio,  # ← NOVO
        roles=[role.name for role in user.roles],
        discord_id=user.discord_id,
        google_id=user.google_id,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        updated_at=user.updated_at
    )

# ============ REFRESH ============

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Renova o access token usando refresh token (do cookie)"""
    refresh_token_value = request.cookies.get("refresh_token")
    
    if not refresh_token_value:
        raise HTTPException(401, "Refresh token não encontrado")
    
    from app.utils.security import verify_token
    
    payload = verify_token(refresh_token_value, "refresh")
    user_id = payload.get("sub")
    
    result = await db.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.refresh_token == refresh_token_value,
            Session.is_active == True
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(401, "Refresh token inválido ou revogado")
    
    session.is_active = False
    
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(401, "Usuário não encontrado")
    
    new_access_token = create_access_token({"sub": str(user.id)})
    new_refresh_token = create_refresh_token({"sub": str(user.id)})
    
    new_session = Session(
        user_id=user.id,
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    )
    db.add(new_session)
    await db.flush()
    await db.commit()
    
    response.set_cookie(
        "access_token", new_access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=False, samesite="lax", path="/"
    )
    response.set_cookie(
        "refresh_token", new_refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=False, samesite="lax", path="/"
    )
    
    print(f"🔄 Token renovado para: {user.username}")
    
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            avatar_url=user.avatar_url,
            roles=[role.name for role in user.roles],
            discord_id=user.discord_id,
            google_id=user.google_id,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    )

# ============ LOGOUT ============

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Logout - invalida a sessão atual"""
    access_token = request.cookies.get("access_token")
    
    if access_token:
        result = await db.execute(
            select(Session).where(
                Session.access_token == access_token,
                Session.is_active == True
            )
        )
        session = result.scalar_one_or_none()
        
        if session:
            session.is_active = False
            await db.flush()
            await db.commit()
            print(f"👋 Logout: usuário {session.user_id}")
    
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    
    return {"message": "Logout realizado com sucesso"}

# ============ PERFIL ============

@router.put("/me/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Atualizar username, email, bio"""
    
    if profile_data.username and profile_data.username != current_user.username:
        # Verificar se username já existe
        result = await db.execute(
            select(User).where(User.username == profile_data.username)
        )
        if result.scalar_one_or_none():
            raise HTTPException(400, "Username já existe")
        current_user.username = profile_data.username
    
    if profile_data.email and profile_data.email != current_user.email:
        # Verificar se email já existe
        result = await db.execute(
            select(User).where(User.email == profile_data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(400, "Email já cadastrado")
        current_user.email = profile_data.email
    
    if profile_data.bio is not None:
        current_user.bio = profile_data.bio
    
    await db.flush()
    await db.commit()
    
    # Recarregar com roles
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == current_user.id)
    )
    user = result.scalar_one()
    
    print(f"📝 Perfil atualizado: {user.username}")
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        avatar_url=user.avatar_url,
        banner_url=user.banner_url,
        bio=user.bio,
        roles=[role.name for role in user.roles],
        discord_id=user.discord_id,
        google_id=user.google_id,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        updated_at=user.updated_at
    )

# ============ SENHA ============

@router.put("/me/password")
async def update_password(
    password_data: UserPasswordUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Trocar senha"""
    
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(400, "Senha atual incorreta")
    
    current_user.password_hash = hash_password(password_data.new_password)
    
    await db.flush()
    await db.commit()
    
    print(f"🔒 Senha alterada: {current_user.username}")
    
    return {"message": "Senha alterada com sucesso"}

# ============ AVATAR ============

@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload de avatar"""
    
    validate_image(file)
    await ensure_directories()
    
    # Salvar imagem (remove antiga automaticamente)
    relative_path = await save_image(file, AVATARS_DIR, str(current_user.id))
    
    # Atualizar URL no banco
    current_user.avatar_url = f"/uploads/avatars/{str(current_user.id)}.webp"
    
    await db.flush()
    await db.commit()
    
    print(f"🖼️ Avatar atualizado: {current_user.username}")
    
    return {
        "message": "Avatar atualizado com sucesso",
        "avatar_url": current_user.avatar_url
    }

@router.delete("/me/avatar")
async def delete_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remover avatar"""
    
    await ensure_directories()
    await delete_old_file(AVATARS_DIR, str(current_user.id))
    
    current_user.avatar_url = None
    
    await db.flush()
    await db.commit()
    
    print(f"🗑️ Avatar removido: {current_user.username}")
    
    return {
        "message": "Avatar removido com sucesso",
        "avatar_url": None
    }

# ============ BANNER ============

@router.post("/me/banner")
async def upload_banner(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload de banner"""
    
    validate_image(file)
    await ensure_directories()
    
    relative_path = await save_image(file, BANNERS_DIR, str(current_user.id))
    
    current_user.banner_url = f"/uploads/banners/{str(current_user.id)}.webp"
    
    await db.flush()
    await db.commit()
    
    print(f"🖼️ Banner atualizado: {current_user.username}")
    
    return {
        "message": "Banner atualizado com sucesso",
        "banner_url": current_user.banner_url
    }

@router.delete("/me/banner")
async def delete_banner(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remover banner"""
    
    await ensure_directories()
    await delete_old_file(BANNERS_DIR, str(current_user.id))
    
    current_user.banner_url = None
    
    await db.flush()
    await db.commit()
    
    print(f"🗑️ Banner removido: {current_user.username}")
    
    return {
        "message": "Banner removido com sucesso",
        "banner_url": None
    }

# ============ UNLINK DISCORD ============

@router.delete("/unlink-discord")
async def unlink_discord(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Desvincula Discord da conta"""
    
    if not current_user.discord_id:
        raise HTTPException(400, "Nenhuma conta Discord vinculada")
    
    # Marcar conexão como inativa
    result = await db.execute(
        select(UserConnection).where(
            UserConnection.user_id == current_user.id,
            UserConnection.provider == ConnectionProvider.DISCORD,
            UserConnection.is_active == True
        )
    )
    connection = result.scalar_one_or_none()
    
    if connection:
        connection.is_active = False
    
    # Limpar discord_id
    current_user.discord_id = None
    
    await db.flush()
    await db.commit()
    
    print(f"🔗 Discord desvinculado: {current_user.username}")
    
    return {"message": "Discord desvinculado com sucesso"}
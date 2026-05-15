from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import List
import secrets
import bcrypt
import aiohttp

from app.config import settings
from app.database import get_db
from app.models.core.user import User
from app.models.core.session import Session

DISCORD_TOKEN_URL = "https://discord.com/api/v10/oauth2/token"

# ============ BASIC AUTH ============

basic_security = HTTPBasic()
app_security = HTTPBasic()


async def verify_bot_auth(credentials: HTTPBasicCredentials = Depends(basic_security)):
    """Verifica Basic Auth para o bot Discord"""
    is_correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"), settings.API_USER.encode("utf-8")
    )
    is_correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"), settings.API_PASS.encode("utf-8")
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas para o bot",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


async def verify_app_auth(credentials: HTTPBasicCredentials = Depends(app_security)):
    """Verifica Basic Auth para o frontend/app (sem WWW-Authenticate)"""
    is_correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"), settings.API_USER.encode("utf-8")
    )
    is_correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"), settings.API_PASS.encode("utf-8")
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso não autorizado",
        )
    return credentials.username


# ============ BCRYPT ============

def hash_password(password: str) -> str:
    """Hash senha com bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verifica senha contra hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


# ============ JWT ============

def create_access_token(data: dict) -> str:
    """Cria um token JWT de acesso"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Cria um token JWT de refresh"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> dict:
    """Verifica e decodifica um token JWT"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != token_type:
            raise HTTPException(401, f"Token inválido: esperado tipo {token_type}")
        return payload
    except JWTError:
        raise HTTPException(401, "Token inválido ou expirado")


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """Obtém o usuário atual do token JWT (cookie ou header Bearer)"""
    token = request.cookies.get("access_token")

    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")

    if not token:
        raise HTTPException(401, "Token não encontrado")

    payload = verify_token(token, "access")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(401, "Token não contém identificação do usuário")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(401, "Usuário não encontrado ou inativo")

    return user


# ============ DISCORD OAUTH ============

async def refresh_discord_token(connection) -> bool:
    """Renova o token do Discord usando refresh_token"""
    if not connection.refresh_token:
        print("⚠️ Sem refresh_token disponível")
        return False

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_TOKEN_URL, data={
                "client_id": settings.DISCORD_CLIENT_ID,
                "client_secret": settings.DISCORD_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": connection.refresh_token,
            }) as resp:
                if resp.status != 200:
                    print(f"❌ Discord refresh falhou ({resp.status}): {await resp.text()}")
                    return False
                data = await resp.json()

        connection.access_token = data["access_token"]
        connection.refresh_token = data.get("refresh_token", connection.refresh_token)
        connection.token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=data.get("expires_in", 604800)
        )
        print(f"🔄 Discord token renovado até {connection.token_expires_at}")
        return True
    except Exception as e:
        print(f"❌ Erro ao renovar token: {e}")
        return False


async def get_valid_discord_token(user_id, db: AsyncSession) -> str | None:
    """Retorna um token Discord válido, renovando se necessário"""
    from app.models.core.user_connection import UserConnection, ConnectionProvider

    result = await db.execute(
        select(UserConnection).where(
            UserConnection.user_id == user_id,
            UserConnection.provider == ConnectionProvider.DISCORD,
            UserConnection.is_active == True
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        return None

    if connection.token_expires_at and connection.token_expires_at < datetime.now(timezone.utc):
        print("⏰ Token Discord expirado, renovando...")
        if await refresh_discord_token(connection):
            await db.commit()
        else:
            print("❌ Não foi possível renovar token Discord")
            return None

    return connection.access_token
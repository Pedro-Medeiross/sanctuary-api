from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import secrets
import bcrypt

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.session import Session
from app.models.role import Role

# Basic Auth for Bot
basic_security = HTTPBasic()

async def verify_bot_auth(credentials: HTTPBasicCredentials = Depends(basic_security)):
    """Verifica Basic Auth para o bot Discord"""
    is_correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.API_USER.encode("utf-8")
    )
    is_correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.API_PASS.encode("utf-8")
    )
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas para o bot",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# JWT Bearer for Dashboard
jwt_bearer = HTTPBearer(auto_error=False)

# ============ BCRYPT HELPERS ============

def hash_password(password: str) -> str:
    """Hash senha com bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Verifica senha contra hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

# ============ JWT HELPERS ============

def create_access_token(data: dict) -> str:
    """Cria um token JWT de acesso"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Cria um token JWT de refresh"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt

def verify_token(token: str, token_type: str = "access") -> dict:
    """Verifica e decodifica um token JWT"""
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        if payload.get("type") != token_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token inválido: esperado tipo {token_type}"
            )
        
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado"
        )

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """Obtém o usuário atual do token JWT (cookie ou header)"""
    token = None
    
    # Tentar obter token do cookie primeiro
    token = request.cookies.get("access_token")
    
    # Se não encontrou no cookie, tentar header Bearer
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não encontrado"
        )
    
    payload = verify_token(token, "access")
    user_id = payload.get("sub")
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não contém identificação do usuário"
        )
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo"
        )
    
    return user

# ============ ROLE CHECKERS ============

async def get_user_roles(user: User, db: AsyncSession) -> List[str]:
    """Retorna lista de nomes de roles do usuário"""
    return [role.name for role in user.roles]

async def require_role(role_name: str):
    """Factory para criar dependency de role específica"""
    async def role_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        # Recarregar user com roles
        result = await db.execute(
            select(User).where(User.id == current_user.id)
        )
        user = result.scalar_one()
        
        user_role_names = [role.name.lower() for role in user.roles]
        
        if role_name.lower() not in user_role_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_name}' necessária"
            )
        
        return user
    
    return role_checker

# Dependencies pré-configuradas
require_admin = require_role("admin")
require_mod = require_role("mod")
require_owner = require_role("owner")
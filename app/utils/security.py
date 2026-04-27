# app/utils/security.py (atualizado)
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import secrets

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.session import Session

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

def create_access_token(data: dict) -> str:
    """Cria um token JWT de acesso com 30 dias de duração"""
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
    """Cria um token JWT de refresh com 30 dias de duração"""
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
        select(User).where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado"
        )
    
    return user

async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User | None:
    """Obtém o usuário atual de forma opcional (sem lançar erro)"""
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None
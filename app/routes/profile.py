from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pathlib import Path

from app.database import get_db
from app.models.core.user import User
from app.schemas.user import UserResponse, UserProfileUpdate, UserPasswordUpdate
from app.utils.security import get_current_user, hash_password, verify_password
from app.utils.uploads import (
    ensure_directories, validate_image, delete_old_file,
    save_image, is_animated_gif,
    AVATARS_DIR, BANNERS_DIR
)

router = APIRouter(prefix="/me", tags=["Perfil"])


# ============ HELPERS ============

async def _upload_image(
    file: UploadFile,
    directory: Path,
    url_prefix: str,
    user: User,
    db: AsyncSession
) -> str:
    """Upload genérico de imagem (avatar ou banner). Retorna a URL."""
    validate_image(file)
    await ensure_directories()

    # Verificar se é GIF animado
    content = await file.read()
    await file.seek(0)

    await save_image(file, directory, str(user.id))

    ext = "gif" if file.filename.endswith('.gif') and is_animated_gif(content) else "webp"
    return f"/uploads/{url_prefix}/{str(user.id)}.{ext}"


async def _delete_image(
    directory: Path,
    user: User,
    db: AsyncSession
) -> None:
    """Remove imagem (avatar ou banner)"""
    await ensure_directories()
    await delete_old_file(directory, str(user.id))


async def _get_user_with_roles(user_id: str, db: AsyncSession) -> User:
    """Busca usuário com roles carregadas"""
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    return result.scalar_one()


def _build_profile_response(user: User) -> UserResponse:
    """Monta UserResponse para perfil"""
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
        updated_at=user.updated_at,
    )


# ============ PERFIL ============

@router.put("/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Atualizar username, email, bio"""
    if profile_data.username and profile_data.username != current_user.username:
        result = await db.execute(select(User).where(User.username == profile_data.username))
        if result.scalar_one_or_none():
            raise HTTPException(400, "Username já existe")
        current_user.username = profile_data.username

    if profile_data.email and profile_data.email != current_user.email:
        result = await db.execute(select(User).where(User.email == profile_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(400, "Email já cadastrado")
        current_user.email = profile_data.email

    if profile_data.bio is not None:
        current_user.bio = profile_data.bio

    await db.commit()

    user = await _get_user_with_roles(current_user.id, db)
    print(f"📝 Perfil atualizado: {user.username}")
    return _build_profile_response(user)


# ============ SENHA ============

@router.put("/password")
async def update_password(
    password_data: UserPasswordUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Trocar senha"""
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(400, "Senha atual incorreta")

    current_user.password_hash = hash_password(password_data.new_password)
    await db.commit()

    print(f"🔒 Senha alterada: {current_user.username}")
    return {"message": "Senha alterada com sucesso"}


# ============ AVATAR ============

@router.post("/avatar")
async def upload_avatar(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload de avatar"""
    url = await _upload_image(file, AVATARS_DIR, "avatars", current_user, db)
    current_user.avatar_url = url
    await db.commit()

    print(f"🖼️ Avatar atualizado: {current_user.username}")
    return {"message": "Avatar atualizado com sucesso", "avatar_url": url}


@router.delete("/avatar")
async def delete_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remover avatar"""
    await _delete_image(AVATARS_DIR, current_user, db)
    current_user.avatar_url = None
    await db.commit()

    print(f"🗑️ Avatar removido: {current_user.username}")
    return {"message": "Avatar removido com sucesso"}


# ============ BANNER ============

@router.post("/banner")
async def upload_banner(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload de banner"""
    url = await _upload_image(file, BANNERS_DIR, "banners", current_user, db)
    current_user.banner_url = url
    await db.commit()

    print(f"🖼️ Banner atualizado: {current_user.username}")
    return {"message": "Banner atualizado com sucesso", "banner_url": url}


@router.delete("/banner")
async def delete_banner(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remover banner"""
    await _delete_image(BANNERS_DIR, current_user, db)
    current_user.banner_url = None
    await db.commit()

    print(f"🗑️ Banner removido: {current_user.username}")
    return {"message": "Banner removido com sucesso"}
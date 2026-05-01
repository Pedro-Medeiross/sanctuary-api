# app/routes/profile.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserProfileUpdate, UserPasswordUpdate
from app.utils.security import get_current_user, hash_password, verify_password
from app.utils.uploads import (
    ensure_directories, validate_image, delete_old_file,
    save_image, is_animated_gif,
    AVATARS_DIR, BANNERS_DIR
)

router = APIRouter(prefix="/me", tags=["Perfil"])

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
    
    await db.flush()
    await db.commit()
    
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
    )
    user = result.scalar_one()
    
    print(f"📝 Perfil atualizado: {user.username}")
    
    return UserResponse(
        id=user.id, username=user.username, email=user.email,
        avatar_url=user.avatar_url, banner_url=user.banner_url, bio=user.bio,
        roles=[role.name for role in user.roles],
        discord_id=user.discord_id, google_id=user.google_id,
        is_active=user.is_active, is_verified=user.is_verified,
        created_at=user.created_at, updated_at=user.updated_at
    )

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
    await db.flush()
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
    validate_image(file)
    await ensure_directories()
    
    # Ler conteúdo para verificar se é GIF animado
    content = await file.read()
    await file.seek(0)  # Voltar ao início para save_image ler
    
    await save_image(file, AVATARS_DIR, str(current_user.id))
    
    # Definir URL correta
    if file.filename.endswith('.gif') and is_animated_gif(content):
        current_user.avatar_url = f"/uploads/avatars/{str(current_user.id)}.gif"
    else:
        current_user.avatar_url = f"/uploads/avatars/{str(current_user.id)}.webp"
    
    await db.flush()
    await db.commit()
    
    print(f"🖼️ Avatar atualizado: {current_user.username}")
    return {"message": "Avatar atualizado com sucesso", "avatar_url": current_user.avatar_url}

@router.delete("/avatar")
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
    return {"message": "Avatar removido com sucesso"}

# ============ BANNER ============

@router.post("/banner")
async def upload_banner(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload de banner"""
    validate_image(file)
    await ensure_directories()
    
    # Ler conteúdo para verificar se é GIF animado
    content = await file.read()
    await file.seek(0)  # Voltar ao início para save_image ler
    
    await save_image(file, BANNERS_DIR, str(current_user.id))
    
    # Definir URL correta
    if file.filename.endswith('.gif') and is_animated_gif(content):
        current_user.banner_url = f"/uploads/banners/{str(current_user.id)}.gif"
    else:
        current_user.banner_url = f"/uploads/banners/{str(current_user.id)}.webp"
    
    await db.flush()
    await db.commit()
    
    print(f"🖼️ Banner atualizado: {current_user.username}")
    return {"message": "Banner atualizado com sucesso", "banner_url": current_user.banner_url}

@router.delete("/banner")
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
    return {"message": "Banner removido com sucesso"}
# app/utils/uploads.py
import os
import aiofiles
from fastapi import UploadFile, HTTPException, status
from PIL import Image
import io
from pathlib import Path

# Configurações
UPLOAD_DIR = Path("uploads")
AVATARS_DIR = UPLOAD_DIR / "avatars"
BANNERS_DIR = UPLOAD_DIR / "banners"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

async def ensure_directories():
    """Cria diretórios de upload se não existirem"""
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    BANNERS_DIR.mkdir(parents=True, exist_ok=True)

def validate_image(file: UploadFile) -> bool:
    """Valida tipo e tamanho da imagem"""
    if not file.filename:
        return False
    
    ext = file.filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato não permitido. Use: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    return True

async def delete_old_file(directory: Path, user_id: str) -> bool:
    """Remove arquivo antigo do usuário (qualquer extensão)"""
    for ext in ALLOWED_EXTENSIONS:
        old_file = directory / f"{user_id}.{ext}"
        if old_file.exists():
            old_file.unlink()
            return True
    return False

async def save_image(file: UploadFile, directory: Path, user_id: str) -> str:
    """
    Salva imagem e retorna o caminho relativo.
    Remove arquivo antigo automaticamente.
    """
    await delete_old_file(directory, user_id)
    
    ext = file.filename.split(".")[-1].lower()
    filename = f"{user_id}.{ext}"
    filepath = directory / filename
    
    # Ler conteúdo
    content = await file.read()
    
    # Verificar tamanho
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE // (1024*1024)}MB")
    
    # Converter para WebP para otimização (opcional)
    try:
        img = Image.open(io.BytesIO(content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        
        # Redimensionar se muito grande
        max_size = (512, 512) if directory == AVATARS_DIR else (1920, 600)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Salvar como WebP
        webp_filename = f"{user_id}.webp"
        webp_filepath = directory / webp_filename
        
        if img.mode == "RGBA":
            img.save(webp_filepath, "WEBP", quality=85, lossless=False)
        else:
            img.save(webp_filepath, "WEBP", quality=85)
        
        # Remover arquivo original se extensão diferente
        if ext != "webp" and filepath != webp_filepath:
            if filepath.exists():
                filepath.unlink()
        
        return str(webp_filepath.relative_to(UPLOAD_DIR.parent))
    
    except Exception as e:
        # Se falhar conversão, salvar original
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)
        return str(filepath.relative_to(UPLOAD_DIR.parent))

def get_file_path(relative_path: str) -> Path:
    """Retorna caminho absoluto do arquivo"""
    return Path(__file__).parent.parent.parent / relative_path
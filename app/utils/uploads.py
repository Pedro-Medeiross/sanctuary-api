import io
from pathlib import Path
import aiofiles
from fastapi import UploadFile, HTTPException
from PIL import Image, ImageSequence

UPLOAD_DIR = Path("uploads")
AVATARS_DIR = UPLOAD_DIR / "avatars"
BANNERS_DIR = UPLOAD_DIR / "banners"
TRANSCRIPTS_DIR = UPLOAD_DIR / "transcripts"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


async def ensure_directories():
    """Cria diretórios de upload se não existirem"""
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    BANNERS_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def validate_image(file: UploadFile) -> bool:
    """Valida tipo de arquivo de imagem"""
    if not file.filename:
        return False
    ext = file.filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Formato não permitido. Use: {', '.join(ALLOWED_EXTENSIONS)}")
    return True


async def delete_old_file(directory: Path, user_id: str) -> bool:
    """Remove arquivo antigo do usuário (qualquer extensão)"""
    for ext in ALLOWED_EXTENSIONS:
        old_file = directory / f"{user_id}.{ext}"
        if old_file.exists():
            old_file.unlink()
            return True
    return False


def is_animated_gif(content: bytes) -> bool:
    """Verifica se é um GIF animado"""
    try:
        img = Image.open(io.BytesIO(content))
        if img.format == "GIF":
            frames = 0
            for _ in ImageSequence.Iterator(img):
                frames += 1
                if frames > 1:
                    return True
        return False
    except Exception:
        return False


async def save_image(file: UploadFile, directory: Path, user_id: str) -> str:
    """Salva imagem, mantendo GIF animado. Retorna o caminho do arquivo."""
    await delete_old_file(directory, user_id)

    content = await file.read()
    ext = file.filename.split(".")[-1].lower()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE // (1024*1024)}MB")

    # GIF animado: salvar original
    if ext == "gif" and is_animated_gif(content):
        filename = f"{user_id}.gif"
        filepath = directory / filename
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)
        return str(filepath)

    # Converter para WebP
    try:
        img = Image.open(io.BytesIO(content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        max_size = (512, 512) if directory == AVATARS_DIR else (1920, 600)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        filename = f"{user_id}.webp"
        filepath = directory / filename

        if img.mode == "RGBA":
            img.save(filepath, "WEBP", quality=85, lossless=False)
        else:
            img.save(filepath, "WEBP", quality=85)

        return str(filepath)
    except Exception:
        # Fallback: salvar original
        filename = f"{user_id}.{ext}"
        filepath = directory / filename
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)
        return str(filepath)


def get_file_path(relative_path: str) -> Path:
    """Retorna caminho absoluto a partir do caminho relativo"""
    return Path(__file__).parent.parent.parent / relative_path
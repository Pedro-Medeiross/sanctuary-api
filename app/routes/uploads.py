from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from app.utils.uploads import AVATARS_DIR, BANNERS_DIR, TRANSCRIPTS_DIR

router = APIRouter(prefix="/uploads", tags=["Uploads"])

MEDIA_TYPES = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
    'gif': 'image/gif',
    'txt': 'text/plain',
    'html': 'text/html',
    'json': 'application/json',
    'md': 'text/markdown',
}


def _serve_file(filepath: Path, directory: Path, default_media_type: str = "application/octet-stream") -> FileResponse:
    """Serve arquivo estático com segurança path traversal"""
    if not filepath.resolve().is_relative_to(directory.resolve()):
        raise HTTPException(403, "Acesso negado")

    if not filepath.exists():
        raise HTTPException(404, "Arquivo não encontrado")

    ext = filepath.suffix.lstrip('.').lower()
    return FileResponse(filepath, media_type=MEDIA_TYPES.get(ext, default_media_type))


@router.get("/avatars/{filename}")
async def serve_avatar(filename: str):
    """Serve imagens de avatar"""
    return _serve_file(AVATARS_DIR / filename, AVATARS_DIR, "image/webp")


@router.get("/banners/{filename}")
async def serve_banner(filename: str):
    """Serve imagens de banner"""
    return _serve_file(BANNERS_DIR / filename, BANNERS_DIR, "image/webp")


@router.get("/transcripts/{filename}")
async def serve_transcript(filename: str):
    """Serve arquivos de transcrição"""
    return _serve_file(TRANSCRIPTS_DIR / filename, TRANSCRIPTS_DIR, "text/plain")
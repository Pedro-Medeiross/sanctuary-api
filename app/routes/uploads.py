# app/routes/uploads.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os
from app.utils.uploads import AVATARS_DIR, BANNERS_DIR, UPLOAD_DIR

TRANSCRIPTS_DIR = Path("uploads/transcripts")

router = APIRouter(prefix="/uploads", tags=["Uploads"])

@router.get("/avatars/{filename}")
async def serve_avatar(filename: str):
    """Serve imagens de avatar"""
    filepath = AVATARS_DIR / filename
    
    # Segurança: evitar path traversal
    if not filepath.resolve().is_relative_to(AVATARS_DIR.resolve()):
        raise HTTPException(403, "Acesso negado")
    
    if not filepath.exists():
        raise HTTPException(404, "Avatar não encontrado")
    
    return FileResponse(
        filepath,
        media_type="image/webp" if filename.endswith(".webp") else "image/jpeg"
    )

@router.get("/banners/{filename}")
async def serve_banner(filename: str):
    """Serve imagens de banner"""
    filepath = BANNERS_DIR / filename
    
    if not filepath.resolve().is_relative_to(BANNERS_DIR.resolve()):
        raise HTTPException(403, "Acesso negado")
    
    if not filepath.exists():
        raise HTTPException(404, "Banner não encontrado")
    
    return FileResponse(
        filepath,
        media_type="image/webp" if filename.endswith(".webp") else "image/jpeg"
    )
    
    
@router.get("/transcripts/{filename}")
async def serve_transcript(filename: str):
    """Serve arquivos de transcrição"""
    filepath = TRANSCRIPTS_DIR / filename
    
    if not filepath.resolve().is_relative_to(TRANSCRIPTS_DIR.resolve()):
        raise HTTPException(403, "Acesso negado")
    
    if not filepath.exists():
        raise HTTPException(404, "Transcrição não encontrada")
    
    return FileResponse(filepath, media_type="text/plain")
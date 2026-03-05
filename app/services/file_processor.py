import base64
import io
import logging
from typing import Tuple
from fastapi import UploadFile, HTTPException
from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024

# Extensão -> MIME type (quando o cliente não envia Content-Type no multipart)
EXTENSAO_PARA_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def _mime_do_arquivo(file: UploadFile) -> str:
    """Usa content_type do upload ou infere pela extensão do nome do arquivo."""
    if file.content_type and file.content_type in settings.ALLOWED_MIME_TYPES:
        return file.content_type
    if file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext in EXTENSAO_PARA_MIME:
            return EXTENSAO_PARA_MIME[ext]
    return file.content_type or "application/octet-stream"


async def read_and_validate_file(file: UploadFile) -> Tuple[bytes, str]:
    """Lê o arquivo, valida tipo e tamanho. Retorna (bytes, mime_type)."""
    filename = file.filename or "(sem nome)"
    logger.info("[file_processor] Etapa: lendo arquivo filename=%s", filename)
    mime_type = _mime_do_arquivo(file)
    logger.info("[file_processor] mime_type inferido/recebido=%s", mime_type)
    if mime_type not in settings.ALLOWED_MIME_TYPES:
        logger.warning("[file_processor] Tipo rejeitado: %s", mime_type)
        raise HTTPException(
            status_code=415,
            detail=f"Tipo de arquivo nao suportado: {mime_type}. "
                   f"Aceitos: {settings.ALLOWED_MIME_TYPES}"
        )

    content = await file.read()
    logger.info("[file_processor] Arquivo lido: size=%d bytes (max=%d)", len(content), MAX_BYTES)
    if len(content) > MAX_BYTES:
        logger.warning("[file_processor] Arquivo excede tamanho max")
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Maximo: {settings.MAX_FILE_SIZE_MB}MB"
        )
    logger.info("[file_processor] Etapa: validacao OK, retornando (bytes, mime_type)")
    return content, mime_type


def to_base64(content: bytes) -> str:
    return base64.b64encode(content).decode("utf-8")


def build_gemini_image_part(content: bytes, mime_type: str) -> dict:
    """Monta a parte de imagem/pdf para a API Gemini."""
    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": to_base64(content),
        }
    }

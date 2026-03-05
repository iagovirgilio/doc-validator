import logging
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.documents import RGValidationResult, ErrorResponse
from app.services.file_processor import read_and_validate_file
from app.services.openai_client import call_openai, extract_json_from_response
from app.services.prompts import RG_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/rg", response_model=RGValidationResult, responses={400: {"model": ErrorResponse}})
async def validate_rg(file: UploadFile = File(..., description="Imagem (JPG/PNG/WEBP) ou PDF do RG")):
    """Valida documento RG brasileiro. Aceita imagem ou PDF."""
    try:
        content, mime_type = await read_and_validate_file(file)
        raw = await call_openai(content, mime_type, RG_EXTRACTION_PROMPT)
        result = extract_json_from_response(raw)
        return RGValidationResult(**result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except httpx.ReadTimeout:
        logger.warning("OpenAI timeout processing RG")
        raise HTTPException(
            status_code=504,
            detail="Tempo esgotado ao processar o documento. Tente uma imagem menor ou tente novamente.",
        )
    except RuntimeError as e:
        logger.error("OpenAI error: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error processing RG")
        raise HTTPException(status_code=500, detail=str(e))
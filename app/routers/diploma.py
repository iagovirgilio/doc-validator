import logging
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.documents import DiplomaValidationResult, ErrorResponse
from app.services.file_processor import read_and_validate_file
from app.services.openai_client import call_openai, extract_json_from_response
from app.services.prompts import DIPLOMA_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/diploma", response_model=DiplomaValidationResult, responses={400: {"model": ErrorResponse}})
async def validate_diploma(file: UploadFile = File(..., description="Imagem ou PDF do diploma de nivel superior")):
    """Valida diploma de nivel superior brasileiro. Aceita imagem ou PDF."""
    try:
        content, mime_type = await read_and_validate_file(file)
        raw = await call_openai(content, mime_type, DIPLOMA_EXTRACTION_PROMPT)
        result = extract_json_from_response(raw)
        return DiplomaValidationResult(**result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except httpx.ReadTimeout:
        logger.warning("OpenAI timeout processing diploma")
        raise HTTPException(
            status_code=504,
            detail="Tempo esgotado ao processar o documento. Tente uma imagem menor ou tente novamente.",
        )
    except RuntimeError as e:
        logger.error("OpenAI error: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error processing diploma")
        raise HTTPException(status_code=500, detail=str(e))

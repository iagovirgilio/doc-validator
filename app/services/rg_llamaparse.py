import logging
import tempfile
from pathlib import Path

from llama_cloud import AsyncLlamaCloud

from app.core.config import settings
from app.models.documents import RGValidationResult
from app.services.openai_client import _call_openai_text_only, extract_json_from_response
from app.services.prompts import RG_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

_llama_client = AsyncLlamaCloud(api_key=settings.LLAMA_CLOUD_API_KEY or None)


async def _parse_pdf_with_llamaparse(content: bytes) -> str:
    """
    Envia o PDF para o LlamaParse (Llama Cloud) e retorna o texto completo (markdown_full ou text_full).
    Implementação simples, baseada no snippet oficial.
    """
    if not settings.LLAMA_CLOUD_API_KEY:
        raise RuntimeError("LLAMA_CLOUD_API_KEY não configurada para usar LlamaParse.")

    logger.info("[rg_llamaparse] Etapa: criando arquivo temporario para envio ao LlamaParse")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(content)
        tmp_path = Path(f.name)

    try:
        logger.info("[rg_llamaparse] Etapa: enviando arquivo para LlamaParse path=%s", tmp_path)
        file_obj = await _llama_client.files.create(file=str(tmp_path), purpose="parse")

        result = await _llama_client.parsing.parse(
            file_id=file_obj.id,
            tier=settings.LLAMAPARSE_TIER or "agentic",
            version="latest",
            processing_options={},
            expand=["markdown_full", "text_full"],
        )

        texto = getattr(result, "markdown_full", None) or getattr(result, "text_full", None)
        if not texto:
            raise RuntimeError("LlamaParse não retornou markdown_full nem text_full.")

        texto_str = str(texto).strip()
        logger.info("[rg_llamaparse] Texto retornado pelo LlamaParse len=%d", len(texto_str))
        return texto_str
    finally:
        tmp_path.unlink(missing_ok=True)
        logger.info("[rg_llamaparse] Etapa: arquivo temporario removido")


async def extract_rg_from_pdf_bytes(content: bytes) -> RGValidationResult:
    """
    Pipeline simples para RG em PDF:
    1) PDF -> LlamaParse (texto completo)
    2) Texto -> OpenAI (JSON mode) -> RGValidationResult
    """
    logger.info("[rg_llamaparse] Pipeline iniciado (LlamaParse + OpenAI texto) tamanho=%d", len(content))
    texto = await _parse_pdf_with_llamaparse(content)
    logger.info("[rg_llamaparse] Texto extraido len=%d, chamando OpenAI para RGValidationResult", len(texto))

    raw = await _call_openai_text_only(RG_EXTRACTION_PROMPT, texto)
    parsed = extract_json_from_response(raw)
    result = RGValidationResult(**parsed)

    logger.info(
        "[rg_llamaparse] Pipeline concluido com sucesso status=%s confidence=%.2f",
        result.status.value,
        result.confidence_score,
    )
    return result


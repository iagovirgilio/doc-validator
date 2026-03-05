import asyncio
import json
import logging
import re
import base64
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _pdf_page_to_png_b64(pdf_bytes: bytes, page_index: int = 0, dpi: int = 300) -> str:
    """Converte uma página do PDF em PNG base64 via pymupdf (DPI maior para melhor leitura)."""
    try:
        import fitz  # pymupdf
    except ImportError:
        raise RuntimeError(
            "pymupdf nao instalado. Adicione 'pymupdf' ao requirements.txt "
            "para suporte a PDF com OpenAI."
        )
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_index]
    pix = page.get_pixmap(dpi=dpi)
    out = base64.b64encode(pix.tobytes("png")).decode("utf-8")
    doc.close()
    return out


def _build_image_url(content: bytes, mime_type: str, pdf_dpi: int = 300) -> str:
    """Monta o data URL para a API da OpenAI.
    PDFs sao convertidos para PNG (OpenAI nao aceita PDF nativo). pdf_dpi controla a resolução.
    """
    if mime_type == "application/pdf":
        b64 = _pdf_page_to_png_b64(content, dpi=pdf_dpi)
        return f"data:image/png;base64,{b64}"
    b64 = base64.b64encode(content).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


async def _call_openai_text_only(prompt: str, texto_documento: str) -> str:
    """Chama a API OpenAI apenas com texto (sem imagem). Usado quando o PDF tem texto extraível."""
    user_content = (
        "O texto abaixo foi extraído de um documento (imagem ou PDF). "
        "Extraia os dados conforme as regras indicadas.\n\n"
        "--- TEXTO DO DOCUMENTO ---\n"
        f"{texto_documento}\n"
        "--- FIM DO TEXTO ---\n\n"
        f"{prompt}"
    )
    payload = {
        "model": settings.OPENAI_MODEL,
        "response_format": {"type": "json_object"},
        "max_tokens": 2048,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": user_content}],
    }
    headers = {
        "Authorization": "Bearer " + settings.OPENAI_API_KEY,
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(OPENAI_URL, headers=headers, json=payload)
    if response.status_code != 200:
        raise RuntimeError(
            "OpenAI API error " + str(response.status_code) + ": " + response.text[:500]
        )
    data = response.json()
    return data["choices"][0]["message"]["content"]


async def call_openai(content: bytes, mime_type: str, prompt: str) -> str:
    """
    Chama a API OpenAI para extrair dados do documento.
    PDF: sempre usa visão (imagem da página em DPI 300).
    Imagem: envia direto para a API de visão.
    """
    logger.info("[openai_client] Etapa: call_openai iniciado mime_type=%s content_size=%d", mime_type, len(content))
    if mime_type == "application/pdf":
        logger.info("[openai_client] PDF detectado: convertendo primeira pagina para PNG (DPI 300) e usando visao")
    else:
        logger.info("[openai_client] Imagem: enviando direto para API de visao")

    headers = {
        "Authorization": "Bearer " + settings.OPENAI_API_KEY,
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=15.0)
    max_retries = 3
    retry_statuses = (500, 502, 503)

    def _make_payload(image_url: str):
        return {
            "model": settings.OPENAI_MODEL,
            "response_format": {"type": "json_object"},
            "max_tokens": 2048,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "high"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

    pdf_dpi = 300
    last_error = None

    for attempt in range(max_retries):
        image_url = _build_image_url(content, mime_type, pdf_dpi=pdf_dpi)
        if attempt == 0:
            logger.info("[openai_client] image_url montado (base64 length ~%d), chamando OpenAI...", len(image_url))
        payload = _make_payload(image_url)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENAI_URL, headers=headers, json=payload)

        logger.info(
            "[openai_client] OpenAI response status=%d (tentativa %d/%d, DPI=%d)",
            response.status_code, attempt + 1, max_retries, pdf_dpi,
        )
        if response.status_code == 200:
            data = response.json()
            logger.info("[openai_client] Etapa: call_openai concluido com sucesso")
            return data["choices"][0]["message"]["content"]

        last_error = RuntimeError(
            "OpenAI API error " + str(response.status_code) + ": " + response.text[:500]
        )
        last_status = response.status_code
        if last_status not in retry_statuses or attempt == max_retries - 1:
            break
        logger.warning(
            "[openai_client] Erro %s (tentativa %d/%d), aguardando 3s para retry...",
            response.status_code, attempt + 1, max_retries,
        )
        await asyncio.sleep(3)

    # PDF: após 500/502/503 em todas as tentativas, tentar uma vez com imagem menor (menos payload)
    if last_error and mime_type == "application/pdf" and pdf_dpi == 300 and last_status in retry_statuses:
        logger.warning("[openai_client] Tentando uma vez com DPI 150 para reduzir tamanho do request")
        pdf_dpi = 150
        image_url = _build_image_url(content, mime_type, pdf_dpi=pdf_dpi)
        payload = _make_payload(image_url)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENAI_URL, headers=headers, json=payload)
        logger.info("[openai_client] OpenAI response status=%d (retry DPI 150)", response.status_code)
        if response.status_code == 200:
            data = response.json()
            logger.info("[openai_client] Etapa: call_openai concluido com sucesso (DPI 150)")
            return data["choices"][0]["message"]["content"]

    logger.error("[openai_client] OpenAI erro: %s", (last_error.args[0] if last_error else "")[:300])
    raise last_error


def extract_json_from_response(text: str) -> dict:
    """Extrai JSON da resposta — com json_object mode ja vem limpo,
    mas aplica limpeza defensiva caso venha com markdown fences."""
    cleaned = re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("JSON parse error: " + str(exc) + " | Response: " + text[:300])

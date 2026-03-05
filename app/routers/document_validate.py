"""
Endpoint unificado POST /documents/validate: recebe vários documentos e o nome do arquivo
indica para qual serviço enviar (RG, DIPLOMA, COMPROVANTE_RESIDENCIA).
"""
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.models.documents import (
    ComprovanteValidationResult,
    DiplomaValidationResult,
    DocumentValidateResponse,
    IssueItem,
    ResumoValidate,
    ResultadoDocumento,
    RGValidationResult,
)
from app.services.file_processor import read_and_validate_file
from app.services.openai_client import call_openai, extract_json_from_response
from app.services.rg_llamaparse import extract_rg_from_pdf_bytes
from app.services.prompts import (
    COMPROVANTE_EXTRACTION_PROMPT,
    DIPLOMA_EXTRACTION_PROMPT,
    RG_EXTRACTION_PROMPT,
)

logger = logging.getLogger(__name__)
router = APIRouter()

TipoDocumento = Literal["RG", "DIPLOMA", "COMPROVANTE_RESIDENCIA"]

# Nome do arquivo (sem extensão, lower) -> tipo para envio (match exato)
MAPEAMENTO_NOME_ARQUIVO: dict[str, TipoDocumento] = {
    "rg": "RG",
    "diploma": "DIPLOMA",
    "comprovante": "COMPROVANTE_RESIDENCIA",
    "comprovante_residencia": "COMPROVANTE_RESIDENCIA",
}

STATUS_PARA_RESPOSTA = {
    "valid": "VALIDADO",
    "partial": "PARCIALMENTE_VALIDADO",
    "invalid": "INVALIDO",
    "unreadable": "ILEGIVEL",
}


def _tipo_pelo_nome_arquivo(filename: str) -> TipoDocumento | None:
    """
    Define o tipo de documento pelo nome do arquivo.
    Ex.: rg.pdf, RG.jpeg, diploma.jpg, comprovante_residencia.png, rg_frente.pdf
    """
    if not filename or not filename.strip():
        return None
    # Remove extensão e normaliza para minúsculo
    nome_sem_ext = re.sub(r"\.[^.]+$", "", filename).strip().lower()
    if not nome_sem_ext:
        return None
    # Match exato (ex: rg, diploma, comprovante_residencia)
    if nome_sem_ext in MAPEAMENTO_NOME_ARQUIVO:
        return MAPEAMENTO_NOME_ARQUIVO[nome_sem_ext]
    # Prefixos: rg_*, diploma_*, comprovante_* (ex: rg_frente.pdf, diploma_verso.jpg)
    if nome_sem_ext.startswith("comprovante"):
        return "COMPROVANTE_RESIDENCIA"
    if nome_sem_ext.startswith("diploma"):
        return "DIPLOMA"
    if nome_sem_ext.startswith("rg") or nome_sem_ext.endswith("_rg") or "_rg_" in nome_sem_ext:
        return "RG"
    return None


def _build_issues(errors: list[str], warnings: list[str]) -> list[IssueItem]:
    """Converte validation_errors e warnings em lista de IssueItem."""
    issues: list[IssueItem] = []
    for msg in errors:
        issues.append(
            IssueItem(
                tipo="VALIDACAO",
                descricao=msg,
                severidade="ALTA",
                notificar_recrutador=True,
            )
        )
    for msg in warnings:
        issues.append(
            IssueItem(
                tipo="OUTRO",
                descricao=msg,
                severidade="MEDIA",
                notificar_recrutador=False,
            )
        )
    return issues


def _dados_estruturados_rg(data: dict) -> dict:
    """Normaliza dados do RG para dados_estruturados do formato unificado."""
    return {
        k: v
        for k, v in (data or {}).items()
        if v is not None
    }


def _dados_estruturados_diploma(data: dict) -> dict:
    """Normaliza dados do diploma para dados_estruturados."""
    return {
        k: v
        for k, v in (data or {}).items()
        if v is not None
    }


def _dados_estruturados_comprovante(data: dict) -> dict:
    """Normaliza dados do comprovante para dados_estruturados."""
    return {
        k: v
        for k, v in (data or {}).items()
        if v is not None
    }


async def _validar_um(
    file: UploadFile,
    tipo: TipoDocumento,
    documento_id: str,
    timestamp: str,
) -> ResultadoDocumento:
    """Valida um único documento e retorna ResultadoDocumento (OpenAI ou Agno conforme config)."""
    logger.info("[doc_validate] _validar_um: inicio tipo=%s documento_id=%s", tipo, documento_id[:8])
    content, mime_type = await read_and_validate_file(file)
    logger.info("[doc_validate] _validar_um: arquivo lido mime_type=%s size=%d", mime_type, len(content))
    if tipo == "RG":
        prompt = RG_EXTRACTION_PROMPT
        model_result = RGValidationResult
        to_structured = _dados_estruturados_rg
    elif tipo == "DIPLOMA":
        prompt = DIPLOMA_EXTRACTION_PROMPT
        model_result = DiplomaValidationResult
        to_structured = _dados_estruturados_diploma
    else:
        prompt = COMPROVANTE_EXTRACTION_PROMPT
        model_result = ComprovanteValidationResult
        to_structured = _dados_estruturados_comprovante

    # Caso especial: RG em PDF -> usar LlamaParse + OpenAI texto
    if tipo == "RG" and mime_type == "application/pdf":
        logger.info("[doc_validate] _validar_um: RG + PDF -> usando LlamaParse + OpenAI texto")
        try:
            result = await extract_rg_from_pdf_bytes(content)
            processador = "llamaparse"
            logger.info("[doc_validate] _validar_um: LlamaParse RG concluido com sucesso")
            data_dict = result.data.model_dump() if result.data else {}
            status_str = STATUS_PARA_RESPOSTA.get(result.status.value, "PARCIALMENTE_VALIDADO")
            issues = _build_issues(
                getattr(result, "validation_errors", []) or [],
                getattr(result, "warnings", []) or [],
            )
            requer_notificacao = bool(getattr(result, "validation_errors", None))
            nivel = "CRITICO" if requer_notificacao and status_str == "INVALIDO" else None
            msg_recrutador = None
            if requer_notificacao and issues:
                msg_recrutador = "; ".join(i.descricao for i in issues[:3])

            return ResultadoDocumento(
                documento_id=documento_id,
                tipo_documento=tipo,
                status=status_str,
                conteudo_extraido=getattr(result, "raw_text_detected") or "",
                dados_estruturados=to_structured(data_dict),
                issues=issues,
                confianca=result.confidence_score,
                timestamp=timestamp,
                modelo_utilizado=settings.OPENAI_MODEL,
                processador=processador,
                requer_notificacao_recrutador=requer_notificacao,
                nivel_alerta=nivel,
                mensagem_recrutador=msg_recrutador,
            )
        except Exception as e:
            logger.exception("[doc_validate] _validar_um: LlamaParse RG falhou, caindo no fluxo padrao: %s", e)

    processador = "openai"
    if mime_type != "application/pdf":
        logger.info("[doc_validate] _validar_um: imagem (nao PDF) -> usando OpenAI visao")
    else:
        logger.info("[doc_validate] _validar_um: PDF (sem LlamaParse) -> usando OpenAI visao")
    raw = await call_openai(content, mime_type, prompt)
    parsed = extract_json_from_response(raw)
    result = model_result(**parsed)
    logger.info("[doc_validate] _validar_um: OpenAI concluido tipo=%s", tipo)

    data_dict = result.data.model_dump() if result.data else {}
    status_str = STATUS_PARA_RESPOSTA.get(result.status.value, "PARCIALMENTE_VALIDADO")
    issues = _build_issues(
        getattr(result, "validation_errors", []) or [],
        getattr(result, "warnings", []) or [],
    )
    requer_notificacao = bool(getattr(result, "validation_errors", None))
    nivel = "CRITICO" if requer_notificacao and status_str == "INVALIDO" else None
    msg_recrutador = None
    if requer_notificacao and issues:
        msg_recrutador = "; ".join(i.descricao for i in issues[:3])

    return ResultadoDocumento(
        documento_id=documento_id,
        tipo_documento=tipo,
        status=status_str,
        conteudo_extraido=getattr(result, "raw_text_detected") or "",
        dados_estruturados=to_structured(data_dict),
        issues=issues,
        confianca=result.confidence_score,
        timestamp=timestamp,
        modelo_utilizado=settings.OPENAI_MODEL,
        processador=processador,
        requer_notificacao_recrutador=requer_notificacao,
        nivel_alerta=nivel,
        mensagem_recrutador=msg_recrutador,
    )
    logger.info("[doc_validate] _validar_um: ResultadoDocumento montado processador=%s status=%s", processador, status_str)


def _nome_do_resultado(r: ResultadoDocumento) -> str | None:
    """Extrai o nome do titular do resultado conforme o tipo do documento."""
    d = r.dados_estruturados or {}
    nome = d.get("nome") or d.get("nome_diplomado") or d.get("nome_titular")
    return (nome or "").strip() or None


def _normalizar_nome(nome: str) -> str:
    """Minúsculas, sem acentos, para comparação."""
    s = (nome or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _aplicar_issues_inconsistencia_nomes(
    resultados: list[ResultadoDocumento],
) -> list[ResultadoDocumento]:
    """
    Quando há inconsistência de nomes entre documentos, adiciona uma issue
    no resultado do documento que está divergente (ex.: comprovante com nome diferente do RG).
    """
    logger.info("[doc_validate] _aplicar_issues_inconsistencia_nomes: inicio n=%d", len(resultados))
    nomes_por_tipo: dict[str, str] = {}
    for r in resultados:
        nome = _nome_do_resultado(r)
        if nome:
            nomes_por_tipo[r.tipo_documento] = nome
    if len(nomes_por_tipo) < 2 or len(set(_normalizar_nome(n) for n in nomes_por_tipo.values())) <= 1:
        logger.info("[doc_validate] _aplicar_issues_inconsistencia_nomes: nomes consistentes ou insuficientes, sem alteracao")
        return resultados
    logger.info("[doc_validate] _aplicar_issues_inconsistencia_nomes: inconsistencia detectada nomes_por_tipo=%s", nomes_por_tipo)
    # Nome de referência: prioridade RG > DIPLOMA > primeiro disponível
    referencia_nome = (
        nomes_por_tipo.get("RG")
        or nomes_por_tipo.get("DIPLOMA")
        or next(iter(nomes_por_tipo.values()))
    )
    referencia_norm = _normalizar_nome(referencia_nome)
    label_referencia = "RG" if "RG" in nomes_por_tipo and nomes_por_tipo.get("RG") == referencia_nome else "documento de identidade"

    saida: list[ResultadoDocumento] = []
    for r in resultados:
        nome = _nome_do_resultado(r)
        if not nome or _normalizar_nome(nome) == referencia_norm:
            saida.append(r)
            continue
        msg_issue = (
            f"Nome no {r.tipo_documento.replace('_', ' ')} ({nome}) não confere com o nome no {label_referencia} ({referencia_nome})."
        )
        issues_novas = list(r.issues) + [
            IssueItem(
                tipo="INCONSISTENCIA_NOME",
                descricao=msg_issue,
                severidade="CRITICA",
                notificar_recrutador=True,
            )
        ]
        saida.append(
            r.model_copy(
                update={
                    "issues": issues_novas,
                    "requer_notificacao_recrutador": True,
                    "nivel_alerta": "CRITICO",
                    "mensagem_recrutador": msg_issue,
                }
            )
        )
    docs_com_inconsistencia = sum(1 for r in resultados if _nome_do_resultado(r) and _normalizar_nome(_nome_do_resultado(r) or "") != referencia_norm)
    logger.info("[doc_validate] _aplicar_issues_inconsistencia_nomes: fim, %d documento(s) com issue de nome adicionada", docs_com_inconsistencia)
    return saida


def _resumo(
    total_arquivos: int,
    resultados: list[ResultadoDocumento],
    tipos_detectados: dict[str, str],
    erros: list[str],
) -> ResumoValidate:
    """Monta o resumo da validação e verifica consistência de nomes."""
    logger.info("[doc_validate] _resumo: montando total_arquivos=%d resultados=%d erros=%d", total_arquivos, len(resultados), len(erros))
    validados = sum(1 for r in resultados if r.status == "VALIDADO")
    com_erro = len(erros)
    tipos_processados = list({r.tipo_documento for r in resultados})
    nomes: dict[str, str] = {}
    for r in resultados:
        nome = _nome_do_resultado(r)
        if nome:
            nomes[r.tipo_documento] = nome.strip().lower()
    nomes_consistentes = len(set(_normalizar_nome(n) for n in nomes.values())) <= 1 if nomes else True
    mensagem_nomes = None
    if not nomes_consistentes and nomes:
        mensagem_nomes = (
            "Inconsistência detectada: documentos com nomes diferentes - "
            + str(nomes)
        )
    processadores_utilizados = list({r.processador for r in resultados})
    return ResumoValidate(
        total_documentos=total_arquivos,
        documentos_validados=validados,
        documentos_com_erro=com_erro,
        tipos_processados=tipos_processados,
        tipos_detectados=tipos_detectados,
        processadores_utilizados=processadores_utilizados,
        nomes_consistentes=nomes_consistentes,
        mensagem_nomes=mensagem_nomes,
        nomes_detectados=nomes,
        erros=erros,
        documento_ids=[r.documento_id for r in resultados],
    )


@router.post("/documents/validate", response_model=DocumentValidateResponse)
async def document_validate(
    documentos: list[UploadFile] = File(..., description="Lista de arquivos (RG, diploma, comprovante). O nome do arquivo define o tipo (ex: rg.pdf, diploma.jpg, comprovante_residencia.png)"),
):
    """
    Valida até 3 documentos de uma vez. O **nome do arquivo** define o serviço:
    - `rg` / `rg.pdf` -> RG
    - `diploma` / `diploma.jpg` -> DIPLOMA
    - `comprovante` ou `comprovante_residencia` -> COMPROVANTE_RESIDENCIA
    """
    logger.info("[doc_validate] ========== INICIO POST /documents/validate ==========")
    if not documentos:
        raise HTTPException(status_code=400, detail="Envie pelo menos um documento.")
    if len(documentos) > 3:
        raise HTTPException(status_code=400, detail="Máximo de 3 documentos por requisição.")
    logger.info("[doc_validate] Etapa: recebidos %d arquivo(s)", len(documentos))

    inicio = datetime.now(timezone.utc)
    tipos_detectados: dict[str, str] = {}
    resultados: list[ResultadoDocumento] = []
    erros: list[str] = []

    for idx, f in enumerate(documentos):
        filename = f.filename or "arquivo"
        logger.info("[doc_validate] Etapa: processando arquivo %d/%d filename=%s", idx + 1, len(documentos), filename)
        tipo = _tipo_pelo_nome_arquivo(filename)
        if not tipo:
            logger.warning("[doc_validate] Tipo nao reconhecido para filename=%s", filename)
            erros.append(
                f"Tipo não reconhecido para '{filename}'. "
                "Use o nome do arquivo para indicar o tipo: rg.ext, diploma.ext, comprovante.ext ou comprovante_residencia.ext"
            )
            continue
        tipos_detectados[filename] = tipo
        doc_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        logger.info("[doc_validate] Etapa: tipo=%s doc_id=%s -> chamando _validar_um", tipo, doc_id[:8])
        try:
            res = await _validar_um(f, tipo, doc_id, ts)
            resultados.append(res)
            logger.info("[doc_validate] Etapa: arquivo %s concluido processador=%s status=%s", filename, res.processador, res.status)
        except httpx.ReadTimeout:
            logger.warning("[doc_validate] Timeout ao processar %s", filename)
            erros.append(f"Timeout ao processar '{filename}'.")
        except (ValueError, RuntimeError) as e:
            logger.exception("[doc_validate] Erro ao validar %s: %s", filename, e)
            erros.append(f"Erro ao processar '{filename}': {e!s}.")
        except Exception:
            logger.exception("[doc_validate] Erro inesperado ao validar %s", filename)
            erros.append(f"Erro inesperado em '{filename}'.")

    logger.info("[doc_validate] Etapa: loop concluido resultados=%d erros=%d", len(resultados), len(erros))
    fim = datetime.now(timezone.utc)
    tempo_ms = (fim - inicio).total_seconds() * 1000
    logger.info("[doc_validate] Etapa: aplicando consistencia de nomes (_aplicar_issues_inconsistencia_nomes)")
    resultados = _aplicar_issues_inconsistencia_nomes(resultados)
    logger.info("[doc_validate] Etapa: montando resumo")
    resumo = _resumo(len(documentos), resultados, tipos_detectados, erros)
    logger.info("[doc_validate] Etapa: resposta pronta tempo_ms=%.2f processadores=%s", tempo_ms, resumo.processadores_utilizados)
    logger.info("[doc_validate] ========== FIM POST /documents/validate ==========")

    return DocumentValidateResponse(
        resultados=resultados,
        resumo=resumo,
        tempo_processamento_ms=tempo_ms,
        data_processamento=fim.isoformat(),
    )

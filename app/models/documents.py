from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class DocumentStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    PARTIAL = "partial"
    UNREADABLE = "unreadable"


class RGData(BaseModel):
    nome: Optional[str] = None
    rg: Optional[str] = None
    cpf: Optional[str] = None
    data_nascimento: Optional[str] = None
    naturalidade: Optional[str] = None
    filiacao_mae: Optional[str] = None
    filiacao_pai: Optional[str] = None
    orgao_emissor: Optional[str] = None
    data_expedicao: Optional[str] = None
    uf_emissor: Optional[str] = None


class RGValidationResult(BaseModel):
    status: DocumentStatus
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    data: RGData
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_text_detected: Optional[str] = None


class DiplomaData(BaseModel):
    nome_diplomado: Optional[str] = None
    cpf: Optional[str] = None
    curso: Optional[str] = None
    grau: Optional[str] = None
    instituicao: Optional[str] = None
    cnpj_instituicao: Optional[str] = None
    data_colacao_grau: Optional[str] = None
    data_expedicao: Optional[str] = None
    registro_mec: Optional[str] = None
    habilitacao: Optional[str] = None
    carga_horaria: Optional[str] = None
    is_nivel_superior: Optional[bool] = None


class DiplomaValidationResult(BaseModel):
    status: DocumentStatus
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    data: DiplomaData
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_text_detected: Optional[str] = None


class ComprovanteData(BaseModel):
    nome_titular: Optional[str] = None
    cpf_cnpj: Optional[str] = None
    logradouro: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    cep: Optional[str] = None
    data_emissao: Optional[str] = None
    empresa_emissora: Optional[str] = None
    tipo_comprovante: Optional[str] = None
    valor: Optional[str] = None
    vencimento: Optional[str] = None


class ComprovanteValidationResult(BaseModel):
    status: DocumentStatus
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    data: ComprovanteData
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_text_detected: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


# ─── Resposta unificada POST /document/validate ─────────────────────────────


class IssueItem(BaseModel):
    tipo: str = "OUTRO"
    descricao: str
    severidade: str = "ALTA"
    dados_extraidos: Optional[dict] = None
    notificar_recrutador: bool = False


class ResultadoDocumento(BaseModel):
    documento_id: str
    tipo_documento: str  # RG | DIPLOMA | COMPROVANTE_RESIDENCIA
    status: str  # VALIDADO | PARCIALMENTE_VALIDADO | INVALIDO | ILEGIVEL
    conteudo_extraido: Optional[str] = None
    dados_estruturados: dict = Field(default_factory=dict)
    issues: list[IssueItem] = Field(default_factory=list)
    confianca: float = 0.0
    timestamp: str = ""
    modelo_utilizado: str = ""
    processador: str = "openai"  # backend que processou este documento (ex.: "openai", "llamaparse")
    requer_notificacao_recrutador: bool = False
    nivel_alerta: Optional[str] = None
    mensagem_recrutador: Optional[str] = None


class ResumoValidate(BaseModel):
    total_documentos: int = 0
    documentos_validados: int = 0
    documentos_com_erro: int = 0
    tipos_processados: list[str] = Field(default_factory=list)
    tipos_detectados: dict[str, str] = Field(default_factory=dict)  # filename -> tipo
    processadores_utilizados: list[str] = Field(default_factory=list)  # ex.: ["openai", "llamaparse"]
    nomes_consistentes: bool = True
    mensagem_nomes: Optional[str] = None
    nomes_detectados: dict[str, str] = Field(default_factory=dict)  # tipo -> nome
    erros: list[str] = Field(default_factory=list)
    documento_ids: list[str] = Field(default_factory=list)


class DocumentValidateResponse(BaseModel):
    resultados: list[ResultadoDocumento] = Field(default_factory=list)
    resumo: ResumoValidate = Field(default_factory=ResumoValidate)
    tempo_processamento_ms: float = 0.0
    data_processamento: str = ""

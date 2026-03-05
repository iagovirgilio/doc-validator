import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import rg, diploma, comprovante, document_validate

# Garante que os logs do app apareçam com prefixo claro
app_logger = logging.getLogger("app")
app_logger.setLevel(logging.INFO)
if not app_logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    app_logger.addHandler(h)
    app_logger.propagate = False

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Document Validator API",
    description="Microserviço de validação de documentos brasileiros com IA (Gemini)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rg.router, prefix="/validate", tags=["RG"])
app.include_router(diploma.router, prefix="/validate", tags=["Diploma"])
app.include_router(comprovante.router, prefix="/validate", tags=["Comprovante de Residência"])
app.include_router(document_validate.router, tags=["Documentos"])


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "document-validator"}

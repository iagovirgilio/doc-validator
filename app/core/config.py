import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # ── OpenAI ──────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # ── Gemini ──────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # ── LlamaParse (extração estruturada via Llama Cloud) ───────
    LLAMA_CLOUD_API_KEY: str = os.getenv("LLAMA_CLOUD_API_KEY", "")
    LLAMAPARSE_TIER: str = os.getenv("LLAMAPARSE_TIER", "agentic")

    # ── File Processing ──────────────────────────────────────
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_MIME_TYPES: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

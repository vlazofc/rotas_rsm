"""Configuração do worker OCR (lê o mesmo .env da stack)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class OcrSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str
    celery_broker_url: str
    celery_result_backend: str

    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "admmendes"
    minio_root_password: str = "trocar_senha_minio"
    minio_use_ssl: bool = False
    minio_bucket_manifests: str = "manifestos"

    ocr_engine: str = "easyocr"
    ocr_lang: str = "pt"
    ocr_min_confidence: float = 0.82
    app_timezone: str = "America/Sao_Paulo"

    # Motor OCR/IA externo. Use OCR_ENGINE=ai para ativar.
    ai_ocr_provider: str = "ocrspace"  # ocrspace | custom | jmhelpdesk
    ai_ocr_api_url: str = "https://api.ocr.space/parse/image"
    ai_ocr_api_key: str = ""
    ai_ocr_language: str = "por"
    ai_ocr_timeout_seconds: int = 90
    ai_ocr_auth_type: str = "header"  # header | bearer | basic | none
    ai_ocr_api_key_header: str = "apikey"
    ai_ocr_basic_username: str = ""
    ai_ocr_basic_password: str = ""
    ai_ocr_extra_form_json: str = "{}"

    # Extrator ESTRUTURADO (tabela do manifesto -> JSON): "rules" ou "llm".
    extractor: str = "rules"
    ocr_llm_base_url: str = "http://ollama:11434/v1"
    ocr_llm_model: str = "llama3.1:8b"
    ocr_llm_api_key: str = "ollama"
    ocr_llm_timeout: float = 120.0

    # Motor de visão (IA multimodal local via Ollama). Use OCR_ENGINE=vision_llm.
    vision_llm_base_url: str = "http://ollama:11434"
    vision_llm_model: str = "qwen2.5vl:7b"
    vision_llm_timeout: float = 240.0
    vision_llm_num_ctx: int = 16384

    # Motor de visão via Google Gemini (API gratuita). Use OCR_ENGINE=gemini.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout: float = 120.0


settings = OcrSettings()

"""Configuração central — lê todas as variáveis do .env."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # App
    app_name: str = "Rotas Brasil RSM"
    app_env: str = "production"
    app_debug: bool = False
    app_timezone: str = "America/Sao_Paulo"
    api_v1_prefix: str = "/api"
    log_level: str = "INFO"

    # Domínio / CORS
    public_domain: str = "rotas.seudominio.com.br"
    allowed_origins: str = "http://localhost:5173"

    # Banco
    database_url: str

    # Redis / Celery
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_public_endpoint: str | None = None
    minio_root_user: str = "admmendes"
    minio_root_password: str = "trocar_senha_minio"
    minio_use_ssl: bool = False
    minio_public_secure: bool | None = None
    minio_bucket_manifests: str = "manifestos"
    minio_bucket_proofs: str = "comprovantes"
    minio_bucket_branding: str = "custom"

    # JWT
    jwt_secret: str = "trocar"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Microsoft Entra
    auth_mode: str = "local"  # local | entra
    microsoft_tenant_id: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = ""

    # OCR
    ocr_engine: str = "easyocr"
    ocr_lang: str = "pt"
    ocr_min_confidence: float = 0.82
    max_upload_mb: int = 25

    # Seed admin
    seed_admin_email: str = "admin@admmendes.com.br"
    seed_admin_password: str = "trocar_admin_senha"
    seed_admin_name: str = "Administrador Global"

    # Roteirização (router_run — maestro/GraphHopper)
    router_base_url: str = "http://localhost:3005"
    router_api_key: str | None = None

    # SharePoint (Microsoft Graph) — sincronização da planilha Torre de Controle.
    # Vazio = sincronização desativada (a tarefa agendada só loga um aviso).
    sharepoint_tenant_id: str = ""
    sharepoint_client_id: str = ""
    sharepoint_client_secret: str = ""
    sharepoint_file_url: str = ""
    sharepoint_sync_branch_id: int | None = None
    sharepoint_sync_origin_address: str = ""

    @property
    def sharepoint_configured(self) -> bool:
        return bool(self.sharepoint_tenant_id and self.sharepoint_client_id
                     and self.sharepoint_client_secret and self.sharepoint_file_url)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def minio_public_is_secure(self) -> bool:
        """Esquema (http/https) usado para assinar URLs públicas do MinIO.

        Em produção, o domínio público fica por trás do Cloudflare Tunnel + Caddy
        com TLS, mesmo que a conexão interna ao MinIO seja HTTP simples — por isso
        este flag é independente de minio_use_ssl. Ver MINIO_PUBLIC_SECURE no .env.
        """
        if self.minio_public_secure is not None:
            return self.minio_public_secure
        return self.minio_use_ssl

    @field_validator("ocr_engine")
    @classmethod
    def _engine(cls, v: str) -> str:
        return v.lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

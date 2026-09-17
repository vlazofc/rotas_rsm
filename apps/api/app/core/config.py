"""Configuração central — lê todas as variáveis do .env."""
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # App
    app_name: str = "Adimax"
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
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 10
    db_pool_recycle_seconds: int = 1800

    # Redis / Celery
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str
    api_rate_limit: str = "6000/minute"

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_public_endpoint: str | None = None
    minio_root_user: str = "admmendes"
    minio_root_password: str = "trocar_senha_minio"
    minio_use_ssl: bool = False
    minio_public_secure: bool | None = None
    minio_bucket_proofs: str = "comprovantes"
    minio_bucket_branding: str = "custom"

    # JWT
    jwt_secret: str = "trocar"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7
    # Chave exclusiva para cifrar credenciais de integrações. Se vazia, deriva do
    # JWT_SECRET para compatibilidade; em produção, configure uma chave distinta.
    integration_encryption_key: str = ""
    # Chave mantida também em mídia externa. Protege dados pessoais no banco e backups.
    data_encryption_key: str = ""

    auth_mode: str = "local"

    max_upload_mb: int = 25

    # Seed admin
    seed_admin_email: str = "admin@jmdistribuicao.com.br"
    seed_admin_password: str = "trocar_admin_senha"
    seed_admin_name: str = "Administrador Global"

    # Pesquisa diária de alterações tributárias (Groq Compound + web search).
    groq_api_key: str = ""
    help_groq_api_key: str = ""
    help_groq_model: str = "openai/gpt-oss-120b"
    groq_model: str = "groq/compound"
    # Motor isolado do Agente Executivo. EPORTS é mantido por compatibilidade
    # com o nome da variável já adotado no ambiente deste projeto.
    groq_api_eports_key: str = ""
    groq_reports_api_key: str = ""
    groq_reports_model: str = "openai/gpt-oss-120b"

    @property
    def executive_groq_api_key(self) -> str:
        return self.groq_api_eports_key or self.groq_reports_api_key

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

    @field_validator("auth_mode")
    @classmethod
    def _auth_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "local":
            raise ValueError("Somente AUTH_MODE=local está disponível; o fluxo Entra ID foi removido por estar incompleto.")
        return normalized

    @model_validator(mode="after")
    def _reject_insecure_production_settings(self):
        if self.app_env.strip().lower() not in {"production", "prod"}:
            return self
        insecure_markers = ("trocar", "change", "cole_aqui", "seudominio")
        secrets = {
            "JWT_SECRET": self.jwt_secret,
            "MINIO_ROOT_PASSWORD": self.minio_root_password,
            "SEED_ADMIN_PASSWORD": self.seed_admin_password,
        }
        invalid = [name for name, value in secrets.items()
                   if len(value.strip()) < 12 or any(marker in value.lower() for marker in insecure_markers)]
        if invalid:
            raise ValueError(f"Configuração insegura em produção: {', '.join(invalid)}")
        if len(self.jwt_secret.strip()) < 32:
            raise ValueError("JWT_SECRET deve ter pelo menos 32 caracteres em produção.")
        if len(self.data_encryption_key.strip()) < 32:
            raise ValueError("DATA_ENCRYPTION_KEY deve estar configurada em produção.")
        if any(origin.startswith("http://") or "localhost" in origin for origin in self.cors_origins):
            raise ValueError("ALLOWED_ORIGINS de produção deve conter somente origens HTTPS públicas.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

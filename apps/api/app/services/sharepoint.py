"""Cliente do Microsoft Graph — baixa a planilha "Torre de Controle" do SharePoint.

Autenticação client-credentials (app-only): requer um app registrado no
Entra ID com permissão de aplicação `Files.Read.All` (ou `Sites.Read.All`)
consentida pelo administrador do tenant do cliente. Configure em .env:
  SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET,
  SHAREPOINT_FILE_URL (o link de compartilhamento, ex.: .../:x:/g/...)

Sem essas variáveis, `settings.sharepoint_configured` é False e o chamador
(tarefa agendada ou botão "Sincronizar agora") deve pular a sincronização.
"""
from __future__ import annotations

import base64
import io

import httpx
import msal

from app.core.config import settings
from app.core.logging import logger

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _encode_share_url(share_url: str) -> str:
    """Codifica a URL de compartilhamento no formato exigido pelo endpoint /shares/{id}.

    https://learn.microsoft.com/graph/api/shares-get
    """
    encoded = base64.urlsafe_b64encode(share_url.encode("utf-8")).decode("utf-8").rstrip("=")
    return f"u!{encoded}"


def _get_access_token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=settings.sharepoint_client_id,
        client_credential=settings.sharepoint_client_secret,
        authority=f"https://login.microsoftonline.com/{settings.sharepoint_tenant_id}",
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(
            f"Falha ao autenticar no Microsoft Graph: {result.get('error')} — {result.get('error_description')}"
        )
    return result["access_token"]


def download_torre_controle_xlsx() -> io.BytesIO:
    """Baixa o arquivo Excel configurado em SHAREPOINT_FILE_URL e retorna seus bytes."""
    if not settings.sharepoint_configured:
        raise RuntimeError("Integração com SharePoint não configurada (SHAREPOINT_* vazio em .env).")

    token = _get_access_token()
    share_id = _encode_share_url(settings.sharepoint_file_url)
    headers = {"Authorization": f"Bearer {token}"}

    resp = httpx.get(f"{GRAPH_BASE}/shares/{share_id}/driveItem/content", headers=headers, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    logger.info("SharePoint: planilha baixada (%d bytes).", len(resp.content))
    return io.BytesIO(resp.content)

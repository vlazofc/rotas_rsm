"""Personalização visual: nome do app, cor, logo e imagem de fundo do login."""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Role, require_roles
from app.db.models import Attachment, BrandingSettings, Tenant, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user_optional
from app.services import storage
from app.services.audit import log_update, snapshot

router = APIRouter(prefix="/branding", tags=["branding"])

SUPPORTED_LOCALES = {"pt-BR"}
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/x-icon", "image/vnd.microsoft.icon"}
EXTENSION_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".ico": "image/x-icon",
}


class BrandingOut(BaseModel):
    app_name: str | None = None
    app_subtitle: str | None = None
    login_intro_text: str | None = None
    login_layout: str = "centered"
    primary_color: str | None = None
    sidebar_background_color: str | None = None
    sidebar_text_color: str | None = None
    sidebar_active_color: str | None = None
    enabled_locales: list[str] | None = None
    topbar_extends_sidebar: bool = True
    logo_url: str | None = None
    logo_rail_url: str | None = None
    background_url: str | None = None
    favicon_url: str | None = None


def _get_or_create(db: Session, tenant_id: int | None) -> BrandingSettings:
    row = db.scalar(select(BrandingSettings).where(BrandingSettings.tenant_id == tenant_id))
    if row is None:
        row = BrandingSettings(tenant_id=tenant_id)
        db.add(row)
        db.flush()
    return row


def _resolve_tenant_id(db: Session, tenant_slug: str | None, user: User | None) -> int | None:
    """Resolve o tenant para a requisição de branding.

    Prioridade: slug explícito na URL (tela de login, ?empresa=) > tenant do
    usuário autenticado > None (padrão da plataforma, sem personalização).
    """
    if tenant_slug:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug, Tenant.active.is_(True)))
        if tenant is not None:
            return tenant.id
    if user is not None:
        return user.tenant_id
    return None


def _branding_for_tenant(db: Session, tenant_id: int | None) -> BrandingSettings:
    """Branding do tenant, com fallback para o padrão da plataforma (tenant_id NULL)
    quando o tenant ainda não personalizou nada."""
    if tenant_id is not None:
        row = db.scalar(select(BrandingSettings).where(BrandingSettings.tenant_id == tenant_id))
        if row is not None and (row.app_name or row.logo_attachment_id or row.primary_color or row.login_intro_text or row.login_layout != "centered" or row.sidebar_background_color or row.sidebar_text_color or row.sidebar_active_color):
            return row
    return _get_or_create(db, None)


def _resolve_content_type(file: UploadFile) -> str:
    content_type = file.content_type or "application/octet-stream"
    if content_type in ALLOWED_TYPES:
        return content_type
    guessed = EXTENSION_TYPES.get(Path(file.filename or "").suffix.lower())
    if guessed:
        return guessed
    raise HTTPException(status_code=415, detail=f"Tipo de imagem não suportado: {content_type}")


async def _save_image(file: UploadFile, kind: str) -> Attachment:
    content_type = _resolve_content_type(file)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Arquivo de imagem vazio.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo acima de {settings.max_upload_mb} MB.")
    storage.ensure_buckets()
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or kind).name)[:120]
    key = f"{kind}/{uuid.uuid4().hex}-{filename}"
    storage.put_object(settings.minio_bucket_branding, key, data, content_type)
    return Attachment(bucket=settings.minio_bucket_branding, storage_key=key, content_type=content_type, size_bytes=len(data))


def _serialize(row: BrandingSettings) -> BrandingOut:
    logo = row.logo_attachment
    logo_rail = row.logo_rail_attachment
    background = row.background_attachment
    favicon = row.favicon_attachment
    return BrandingOut(
        app_name=row.app_name,
        app_subtitle=row.app_subtitle,
        login_intro_text=row.login_intro_text,
        login_layout=row.login_layout or "centered",
        primary_color=row.primary_color,
        sidebar_background_color=row.sidebar_background_color,
        sidebar_text_color=row.sidebar_text_color,
        sidebar_active_color=row.sidebar_active_color,
        enabled_locales=[code for code in row.enabled_locales.split(",") if code] if row.enabled_locales else None,
        topbar_extends_sidebar=row.topbar_extends_sidebar,
        logo_url=f"{settings.api_v1_prefix}/branding/assets/{logo.id}" if logo else None,
        logo_rail_url=f"{settings.api_v1_prefix}/branding/assets/{logo_rail.id}" if logo_rail else None,
        background_url=f"{settings.api_v1_prefix}/branding/assets/{background.id}" if background else None,
        favicon_url=f"{settings.api_v1_prefix}/branding/assets/{favicon.id}" if favicon else None,
    )


@router.get("/assets/{attachment_id}", include_in_schema=False)
def branding_asset(attachment_id: int, db: Session = Depends(get_db)):
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.bucket != settings.minio_bucket_branding:
        raise HTTPException(status_code=404, detail="Imagem não encontrada.")
    return Response(
        content=storage.get_object_bytes(attachment.bucket, attachment.storage_key),
        media_type=attachment.content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400, immutable", "X-Content-Type-Options": "nosniff"},
    )


@router.get("", response_model=BrandingOut)
def get_branding(
    tenant_slug: str | None = None,
    edit_tenant_id: int | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    # edit_tenant_id: usado pelo painel "Clientes" (admin_global) para editar
    # o branding de um cliente específico, sem o fallback para o padrão da
    # plataforma — precisa ver exatamente o que está salvo (mesmo que vazio).
    if edit_tenant_id is not None and user is not None and user.role == Role.ADMIN_GLOBAL.value:
        return _serialize(_get_or_create(db, edit_tenant_id))
    tenant_id = _resolve_tenant_id(db, tenant_slug, user)
    return _serialize(_branding_for_tenant(db, tenant_id))


@router.put("", response_model=BrandingOut)
async def update_branding(
    tenant_id: int | None = None,
    app_name: str | None = Form(None),
    app_subtitle: str | None = Form(None),
    login_intro_text: str | None = Form(None),
    login_layout: str | None = Form(None),
    primary_color: str | None = Form(None),
    sidebar_background_color: str | None = Form(None),
    sidebar_text_color: str | None = Form(None),
    sidebar_active_color: str | None = Form(None),
    enabled_locales: str | None = Form(None),
    topbar_extends_sidebar: bool | None = Form(None),
    remove_logo: bool = Form(False),
    remove_logo_rail: bool = Form(False),
    remove_background: bool = Form(False),
    remove_favicon: bool = Form(False),
    logo: UploadFile | None = File(None),
    logo_rail: UploadFile | None = File(None),
    background: UploadFile | None = File(None),
    favicon: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)),
):
    # admin_global pode editar o branding de qualquer cliente (?tenant_id=);
    # demais perfis ficam restritos ao próprio tenant.
    target_tenant_id = tenant_id if actor.role == Role.ADMIN_GLOBAL.value else actor.tenant_id
    if target_tenant_id is not None and db.get(Tenant, target_tenant_id) is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    row = _get_or_create(db, target_tenant_id)
    updates: dict[str, str | bool | None] = {}
    if app_name is not None:
        updates["app_name"] = app_name.strip() or None
    if app_subtitle is not None:
        updates["app_subtitle"] = app_subtitle.strip() or None
    if login_intro_text is not None:
        updates["login_intro_text"] = login_intro_text.strip()[:1000] or None
    if login_layout is not None:
        if login_layout not in {"centered", "institutional", "side_form"}:
            raise HTTPException(status_code=422, detail="Layout de login inválido.")
        updates["login_layout"] = login_layout
    if primary_color is not None:
        updates["primary_color"] = primary_color.strip() or None
    for color_field, color_value in (("sidebar_background_color", sidebar_background_color), ("sidebar_text_color", sidebar_text_color), ("sidebar_active_color", sidebar_active_color)):
        if color_value is not None:
            normalized = color_value.strip()
            if normalized and not re.fullmatch(r"#[0-9a-fA-F]{6}", normalized):
                raise HTTPException(status_code=422, detail="Cor da barra inválida.")
            updates[color_field] = normalized or None
    if enabled_locales is not None:
        codes = [code.strip() for code in enabled_locales.split(",") if code.strip()]
        invalid = [code for code in codes if code not in SUPPORTED_LOCALES]
        if invalid:
            raise HTTPException(status_code=422, detail=f"Idioma não suportado: {', '.join(invalid)}.")
        if not codes:
            raise HTTPException(status_code=422, detail="Selecione ao menos um idioma.")
        updates["enabled_locales"] = ",".join(codes)
    if topbar_extends_sidebar is not None:
        updates["topbar_extends_sidebar"] = topbar_extends_sidebar
    before = snapshot(row, list(updates))
    for field, value in updates.items():
        setattr(row, field, value)
    if remove_logo:
        row.logo_attachment_id = None
    if logo is not None and logo.filename:
        attachment = await _save_image(logo, "logo")
        db.add(attachment)
        db.flush()
        row.logo_attachment_id = attachment.id
    if remove_logo_rail:
        row.logo_rail_attachment_id = None
    if logo_rail is not None and logo_rail.filename:
        attachment = await _save_image(logo_rail, "logo_rail")
        db.add(attachment)
        db.flush()
        row.logo_rail_attachment_id = attachment.id
    if remove_background:
        row.background_attachment_id = None
    if background is not None and background.filename:
        attachment = await _save_image(background, "background")
        db.add(attachment)
        db.flush()
        row.background_attachment_id = attachment.id
    if remove_favicon:
        row.favicon_attachment_id = None
    if favicon is not None and favicon.filename:
        attachment = await _save_image(favicon, "favicon")
        db.add(attachment)
        db.flush()
        row.favicon_attachment_id = attachment.id
    log_update(db, user_id=actor.id, entity="branding", entity_id=row.id, before=before, obj=row, updates=updates)
    db.commit()
    db.refresh(row)
    return _serialize(row)

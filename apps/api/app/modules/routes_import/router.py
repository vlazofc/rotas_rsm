"""Importação de rotas via planilha — modelo padrão (.xlsx/.csv), qualquer cliente."""
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_roles
from app.db.models import User
from app.db.session import get_db
from app.services.audit import log
from app.services.generic_route_import import build_template_xlsx, import_generic_routes

router = APIRouter(prefix="/routes-import", tags=["routes-import"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO)

ALLOWED_EXTENSIONS = (".xlsx", ".csv")


class ImportResult(BaseModel):
    rows_read: int
    routes_created: int
    routes_updated: int
    stops_created: int
    stops_updated: int
    revenues_created: int
    errors: list[str]


@router.get("/template.xlsx", dependencies=[Depends(_MANAGER)])
def download_template():
    output = build_template_xlsx()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo-importacao-rotas.xlsx"'},
    )


@router.post("/upload", response_model=ImportResult)
async def upload_routes(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(_MANAGER)):
    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=415, detail="Envie um arquivo .xlsx ou .csv.")
    if user.branch_id is None:
        raise HTTPException(status_code=409, detail="Usuário sem filial associada.")
    data = await file.read()
    try:
        stats = import_generic_routes(io.BytesIO(data), filename, branch_id=user.branch_id)
    except Exception as exc:  # noqa: BLE001 — erro de leitura/parsing da planilha do usuário
        raise HTTPException(status_code=422, detail=f"Não foi possível ler a planilha: {exc}")
    log(db, user_id=user.id, action="import", entity="routes",
        detail=f"Importação via planilha: {stats['routes_created']} rotas criadas, {stats['routes_updated']} atualizadas.")
    db.commit()
    return ImportResult(**stats)

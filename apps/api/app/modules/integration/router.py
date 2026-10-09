"""API de integração externa (parceiros/ERP) — autenticação por token fixo.

Reaproveita as regras de negócio de app.modules.routes.router, autenticando
como o usuário de serviço vinculado ao token em vez de um login JWT.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.modules.integration.deps import get_api_token_user
from app.modules.routes.router import _require_route_editor, create_route as _create_route, get_route as _get_route, list_routes as _list_routes
from app.modules.routes.schemas import RouteIn, RouteOut

router = APIRouter(prefix="/integration/v1", tags=["integration"])


@router.get("/routes", response_model=list[RouteOut])
def integration_list_routes(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_token_user),
):
    return _list_routes(db=db, user=user, status_filter=status_filter)


@router.get("/routes/{route_id}", response_model=RouteOut)
def integration_get_route(
    route_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_token_user),
):
    return _get_route(route_id, db=db, user=user)


@router.post("/routes", response_model=RouteOut)
def integration_create_route(
    data: RouteIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_token_user),
):
    _require_route_editor(user=user, db=db)
    return _create_route(data, db=db, user=user)

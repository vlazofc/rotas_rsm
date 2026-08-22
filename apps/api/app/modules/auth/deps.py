"""Dependências de autenticação — extrai e valida o usuário do JWT."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.models import Branch, Tenant, User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=True)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def ensure_user_scope(user: User, db: Session) -> User:
    """Confirma o escopo no banco em cada requisição; claims do JWT não são autoridade."""
    if user.role == "admin_global":
        return user
    if user.tenant_id is None or user.branch_id is None:
        raise HTTPException(status_code=403, detail="Usuário sem empresa ou filial válida.")
    tenant = db.get(Tenant, user.tenant_id)
    branch = db.get(Branch, user.branch_id)
    if tenant is None or not tenant.active:
        raise HTTPException(status_code=403, detail="Empresa inativa ou inexistente.")
    if branch is None or not branch.active or branch.tenant_id != tenant.id:
        raise HTTPException(status_code=403, detail="Filial inativa ou incompatível com a empresa.")
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except ValueError:
        raise cred_exc
    if payload.get("type") != "access":
        raise cred_exc
    user_id = payload.get("sub")
    if user_id is None:
        raise cred_exc
    user = db.get(User, int(user_id))
    if user is None or not user.active:
        raise cred_exc
    return ensure_user_scope(user, db)


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """Versão tolerante de get_current_user — usada em endpoints públicos
    (ex.: branding) que devem personalizar a resposta quando há sessão,
    sem exigir login (a tela de login também precisa carregar o branding)."""
    if not token:
        return None
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    if payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    user = db.get(User, int(user_id))
    if user is None or not user.active:
        return None
    try:
        return ensure_user_scope(user, db)
    except HTTPException:
        return None

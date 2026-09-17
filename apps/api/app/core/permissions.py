"""RBAC — perfis e dependências de autorização (toda proteção no backend)."""
from enum import Enum

from fastapi import Depends, HTTPException, status
from sqlalchemy import false, select, true
from sqlalchemy.orm import Session

from app.modules.auth.deps import get_current_user
from app.db.models import Branch, RoleProfile, Tenant, User
from app.db.session import get_db


class Role(str, Enum):
    ADMIN_GLOBAL = "admin_global"
    ADMIN_SITE = "admin_site"
    GERENTE = "gerente"
    LIDER = "lider"
    PLANEJAMENTO = "planejamento"
    MONITORAMENTO = "monitoramento"
    GESTOR_BRASIL = "gestor_brasil"
    GESTOR_FINANCEIRO = "gestor_financeiro"
    OPERADOR_LOGISTICO = "operador_logistico"
    TORRE_CONTROLE = "torre_controle"
    MOTORISTA = "motorista"
    AUDITOR = "auditor"
    DIRETORIA = "diretoria"
    CLIENTE = "cliente"


ROLE_CONFIG = {
    Role.ADMIN_SITE: {"order": 20, "label": "Admin Site", "description": "Administra usuários e cadastros da operação", "permissions": ["module.dashboard", "module.routes", "module.monitoring", "module.occurrences", "module.gallery", "module.tracking", "module.drivers", "module.vehicles", "module.reports", "module.users"]},
    Role.GERENTE: {"order": 30, "label": "Gerente", "description": "Visão gerencial da operação e da filial", "permissions": ["module.dashboard", "module.routes", "module.monitoring", "module.occurrences", "module.gallery", "module.tracking", "module.drivers", "module.vehicles", "module.reports", "module.users"]},
    Role.LIDER: {"order": 40, "label": "Líder", "description": "Coordena a execução operacional da filial", "permissions": ["module.dashboard", "module.routes", "module.monitoring", "module.occurrences", "module.gallery", "module.tracking"]},
    Role.PLANEJAMENTO: {"order": 50, "label": "Planejamento", "description": "Planeja rotas, motoristas e veículos", "permissions": ["module.dashboard", "module.routes", "module.routing", "module.monitoring", "module.drivers", "module.vehicles"]},
    Role.MONITORAMENTO: {"order": 60, "label": "Monitoramento", "description": "Monitora viagens, ocorrências e evidências", "permissions": ["module.dashboard", "module.routes", "module.monitoring", "module.occurrences", "module.gallery", "module.tracking"]},
    Role.ADMIN_GLOBAL: {
        "order": 10,
        "label": "Administrador global",
        "description": "Configura filial, usuários, integrações — acesso total",
        "permissions": [
            "Acesso total ao sistema",
            "Gerenciar usuários e perfis",
            "Gerenciar filiais e integrações",
            "Consultar auditoria",
        ],
    },
    Role.AUDITOR: {
        "order": 20,
        "label": "Auditor",
        "description": "Consulta histórico e relatórios sem editar",
        "permissions": [
            "Consultar auditoria",
            "Consultar histórico operacional",
            "Visualizar relatórios",
        ],
    },
    Role.DIRETORIA: {
        "order": 25,
        "label": "Diretoria",
        "description": "Acompanha indicadores e relatórios executivos sem operar lançamentos",
        "permissions": ["Visualizar relatórios", "Consultar indicadores executivos", "Usar agente executivo"],
    },
    Role.MOTORISTA: {
        "order": 40,
        "label": "Motorista",
        "description": "Vê somente as próprias rotas e faz check-in",
        "permissions": [
            "Visualizar rota atribuída",
            "Registrar chegada ao CD",
            "Fazer check-in em entregas",
            "Confirmar entrega ou ocorrência",
        ],
    },
    Role.OPERADOR_LOGISTICO: {
        "order": 50,
        "label": "Operador logístico",
        "description": "Doca, rotas e liberação de carregamento",
        "permissions": [
            "Criar e atualizar rotas",
            "Registrar tempos de doca",
            "Liberar carregamento",
        ],
    },
}
ROLE_EQUIVALENTS = {
    Role.ADMIN_SITE.value: Role.GESTOR_BRASIL.value,
    Role.GERENTE.value: Role.GESTOR_BRASIL.value,
    Role.LIDER.value: Role.OPERADOR_LOGISTICO.value,
    Role.PLANEJAMENTO.value: Role.OPERADOR_LOGISTICO.value,
    Role.MONITORAMENTO.value: Role.TORRE_CONTROLE.value,
}
ROLE_DESCRIPTIONS = {role: cfg["description"] for role, cfg in ROLE_CONFIG.items()}

FINANCE_VIEW = "finance.view"
FINANCE_EXPENSE_CREATE = "finance.expense.create"
FINANCE_REVENUE_MANAGE = "finance.revenue.manage"
FINANCE_ACCOUNTS_MANAGE = "finance.accounts.manage"
FINANCE_EXPENSE_APPROVE = "finance.expense.approve"
SCOPE_GLOBAL = "scope.global"
SCOPE_TENANT = "scope.tenant"


class AccessScope(str, Enum):
    GLOBAL = "global"
    TENANT = "tenant"
    BRANCH = "branch"
    ASSIGNED = "assigned"

def has_all_environment_access(user: User, db: Session | None = None) -> bool:
    """Acesso entre empresas exige perfil global ou capacidade explícita."""
    return user.role == Role.ADMIN_GLOBAL.value or SCOPE_GLOBAL in user_permissions(user, db)


def operational_scope(user: User, db: Session | None = None) -> AccessScope:
    """Resolve a fronteira de dados independentemente dos módulos habilitados."""
    if has_all_environment_access(user, db):
        return AccessScope.GLOBAL
    permissions = user_permissions(user, db)
    effective_role = ROLE_EQUIVALENTS.get(user.role, user.role)
    if SCOPE_TENANT in permissions or effective_role in {
        Role.GESTOR_BRASIL.value,
        Role.GESTOR_FINANCEIRO.value,
        Role.TORRE_CONTROLE.value,
    } or user.role in {Role.AUDITOR.value, Role.DIRETORIA.value}:
        return AccessScope.TENANT
    if user.role == Role.CLIENTE.value:
        return AccessScope.TENANT
    if user.role == Role.MOTORISTA.value:
        return AccessScope.ASSIGNED
    return AccessScope.BRANCH


def branch_scope_filter(branch_column, user: User, db: Session):
    """Retorna a condição SQL correspondente ao escopo operacional."""
    scope = operational_scope(user, db)
    if scope == AccessScope.GLOBAL:
        return true()
    if scope == AccessScope.TENANT:
        if user.tenant_id is None:
            return false()
        branch_ids = select(Branch.id).where(Branch.tenant_id == user.tenant_id)
        return branch_column.in_(branch_ids)
    if scope == AccessScope.BRANCH and user.branch_id is not None:
        return branch_column == user.branch_id
    return false()


def scope_by_branch(stmt, branch_column, user: User, db: Session):
    """Aplica escopo global, empresa ou filial a uma consulta operacional."""
    return stmt.where(branch_scope_filter(branch_column, user, db))


def user_permissions(user: User, db: Session | None = None) -> set[str]:
    """Permissões adicionais concedidas individualmente pelo gestor/admin."""
    permissions = {item.strip() for item in (getattr(user, "permissions_json", None) or "").splitlines() if item.strip()}
    profile = db.get(RoleProfile, user.role) if db is not None else None
    if profile and profile.active:
        permissions.update(item.strip() for item in (profile.permissions_json or "").splitlines() if item.strip())
    return permissions


def has_permission(user: User, permission: str, *fallback_roles: Role) -> bool:
    if user.role == Role.ADMIN_GLOBAL.value:
        return True
    return permission in user_permissions(user) or user.role in {role.value for role in fallback_roles}


def require_permission(permission: str, *fallback_roles: Role):
    def _checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission, *fallback_roles):
            raise HTTPException(status_code=403, detail="Acesso não liberado pelo gestor para este módulo.")
        return user
    return _checker


def require_roles(*roles: Role):
    """Dependência que exige um dos perfis informados."""
    allowed = {r.value for r in roles}

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role == Role.ADMIN_GLOBAL.value:
            return user  # admin global passa em tudo
        if user.role not in allowed and ROLE_EQUIVALENTS.get(user.role) not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Perfil sem permissão para esta ação.",
            )
        return user

    return _checker


def require_same_branch(user: User, branch_id: int) -> None:
    """Impede acesso cruzado entre filiais e empresas."""
    if has_all_environment_access(user):
        return
    # O motorista pode trabalhar em várias filiais. O acesso efetivo continua
    # limitado à rota atribuída pelos guards específicos de rotas/tracking.
    if user.role == Role.MOTORISTA.value:
        return
    if user.branch_id is None or branch_id != user.branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à própria filial.",
        )


def require_same_tenant(user: User, tenant_id: int | None) -> None:
    """Bloqueia acesso entre empresas, independentemente do ID recebido pela API."""
    if has_all_environment_access(user):
        return
    if user.tenant_id is None or tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Acesso restrito à própria empresa.")


def require_branch_access(db: Session, user: User, branch_id: int) -> Branch:
    """Resolve a filial e valida o escopo global, de empresa ou de filial."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Filial não encontrada.")
    if not branch.active:
        raise HTTPException(status_code=409, detail="Unidade operacional inativa.")
    require_same_tenant(user, branch.tenant_id)
    scope = operational_scope(user, db)
    if scope == AccessScope.BRANCH and (user.branch_id is None or branch.id != user.branch_id):
        raise HTTPException(status_code=403, detail="Acesso restrito à própria filial.")
    if scope == AccessScope.ASSIGNED and user.role != Role.MOTORISTA.value:
        raise HTTPException(status_code=403, detail="Acesso restrito aos registros atribuídos ao usuário.")
    return branch


def require_feature(feature: str):
    """Dependência para impedir uso de módulos desativados no plano do tenant."""
    allowed = {"feature_sharepoint_sync", "feature_financeiro", "feature_rastreamento"}
    if feature not in allowed:
        raise ValueError(f"Feature desconhecida: {feature}")

    def _checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.role == Role.ADMIN_GLOBAL.value:
            return user
        tenant = db.get(Tenant, user.tenant_id) if user.tenant_id is not None else None
        if tenant is None or not bool(getattr(tenant, feature)):
            raise HTTPException(status_code=403, detail="Serviço não habilitado para esta empresa.")
        return user

    return _checker

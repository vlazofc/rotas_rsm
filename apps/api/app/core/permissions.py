"""RBAC — perfis e dependências de autorização (toda proteção no backend)."""
from enum import Enum

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.modules.auth.deps import get_current_user
from app.db.models import Branch, Tenant, User
from app.db.session import get_db


class Role(str, Enum):
    ADMIN_GLOBAL = "admin_global"
    GESTOR_BRASIL = "gestor_brasil"
    GESTOR_FINANCEIRO = "gestor_financeiro"
    OPERADOR_LOGISTICO = "operador_logistico"
    TORRE_CONTROLE = "torre_controle"
    MOTORISTA = "motorista"
    AUDITOR = "auditor"
    DIRETORIA = "diretoria"


ROLE_CONFIG = {
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
    Role.GESTOR_BRASIL: {
        "order": 30,
        "label": "Gestor Brasil",
        "description": "Vê rotas, relatórios e usuários da filial Brasil",
        "permissions": [
            "Gerenciar usuários da filial",
            "Gerenciar motoristas e veículos",
            "Gerar rotas",
            "Visualizar relatórios",
        ],
    },
    Role.GESTOR_FINANCEIRO: {
        "order": 35,
        "label": "Gestor Financeiro",
        "description": "Lança receitas e despesas, vê o balancete e o dashboard financeiro",
        "permissions": [
            "Lançar receitas por rota",
            "Lançar e revisar despesas",
            "Visualizar balancete (receita x despesa)",
            "Visualizar dashboard financeiro",
        ],
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
    Role.TORRE_CONTROLE: {
        "order": 60,
        "label": "Torre de controle",
        "description": "Monitora rotas em tempo real e ocorrências",
        "permissions": [
            "Monitorar rotas em andamento",
            "Acompanhar atrasos e ocorrências",
            "Consultar dashboard operacional",
        ],
    },
}
ROLE_DESCRIPTIONS = {role: cfg["description"] for role, cfg in ROLE_CONFIG.items()}

FINANCE_VIEW = "finance.view"
FINANCE_EXPENSE_CREATE = "finance.expense.create"
FINANCE_REVENUE_MANAGE = "finance.revenue.manage"
FINANCE_ACCOUNTS_MANAGE = "finance.accounts.manage"
FINANCE_EXPENSE_APPROVE = "finance.expense.approve"


def user_permissions(user: User) -> set[str]:
    """Permissões adicionais concedidas individualmente pelo gestor/admin."""
    return {item.strip() for item in (user.permissions_json or "").splitlines() if item.strip()}


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
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Perfil sem permissão para esta ação.",
            )
        return user

    return _checker


def require_same_branch(user: User, branch_id: int) -> None:
    """Impede acesso cruzado entre filiais e empresas."""
    if user.role == Role.ADMIN_GLOBAL.value:
        return
    if user.branch_id is None or branch_id != user.branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à própria filial.",
        )


def require_same_tenant(user: User, tenant_id: int | None) -> None:
    """Bloqueia acesso entre empresas, independentemente do ID recebido pela API."""
    if user.role == Role.ADMIN_GLOBAL.value:
        return
    if user.tenant_id is None or tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Acesso restrito à própria empresa.")


def require_branch_access(db: Session, user: User, branch_id: int) -> Branch:
    """Resolve a filial e valida empresa e filial do usuário."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Filial não encontrada.")
    if not branch.active:
        raise HTTPException(status_code=409, detail="Unidade operacional inativa.")
    require_same_tenant(user, branch.tenant_id)
    require_same_branch(user, branch.id)
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

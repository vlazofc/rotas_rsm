"""CLI para importar a planilha "Torre de Controle" (arquivo local) — testes manuais.

A lógica de importação vive em app.services.torre_controle_import (reusada
também pela sincronização automática do SharePoint). Este script é só um
wrapper fino para rodar contra um arquivo .xlsx na sua máquina.

Uso:
    python scripts/import_torre_controle.py "C:\\caminho\\TORRE DE CONTROLE ADESTE - JM_MRD.xlsx"

Requer DATABASE_URL no ambiente (mesma config da API).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from sqlalchemy import select  # noqa: E402

from app.db.models import Branch, Tenant  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.torre_controle_import import import_workbook  # noqa: E402

FILIAL_ORIGEM = "Av. Industrial, 3331, Campestre, Santo André, SP, 09080-511"
CLIENTE_SLUG = "adeste"  # esta planilha é do cliente Adeste — nunca do tenant da Admmendes


def _resolve_adeste_branch_id() -> int:
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == CLIENTE_SLUG))
        if tenant is None:
            raise RuntimeError(f"Tenant '{CLIENTE_SLUG}' não encontrado — crie o cliente no painel antes de importar.")
        branch = db.scalar(select(Branch).where(Branch.tenant_id == tenant.id).order_by(Branch.id))
        if branch is None:
            raise RuntimeError(f"Tenant '{CLIENTE_SLUG}' não tem filial — crie uma antes de importar.")
        return branch.id


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python import_torre_controle.py <caminho_planilha.xlsx>")
        sys.exit(1)
    branch_id = _resolve_adeste_branch_id()
    stats = import_workbook(Path(sys.argv[1]), branch_id=branch_id, origin_address=FILIAL_ORIGEM)
    print("Resumo da importação:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

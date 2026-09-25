from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Carrier, CarrierBranch


def resolve_import_carrier(db: Session, branch_id: int, *, carrier_id: int | None, name: str | None) -> tuple[Carrier | None, str | None]:
    """O ID é a identidade; o nome importado é uma conferência humana."""
    if carrier_id is None:
        return None, "ID da transportadora ausente."
    carrier = db.get(Carrier, carrier_id)
    if carrier is None or not carrier.active:
        return None, f"Transportadora ID {carrier_id} inexistente ou inativa."
    if not name or carrier.name.strip().casefold() != name.strip().casefold():
        return None, f"Nome da transportadora não corresponde ao ID {carrier_id}. Esperado: {carrier.name}."
    enabled = db.scalar(select(CarrierBranch).where(
        CarrierBranch.carrier_id == carrier.id,
        CarrierBranch.branch_id == branch_id,
        CarrierBranch.active.is_(True),
    ))
    if enabled is None:
        return None, f"Transportadora {carrier.name} não habilitada para a filial."
    return carrier, None


def apply_import_carrier(route, carrier: Carrier | None, issue: str | None) -> None:
    route.carrier_id = carrier.id if carrier else None
    route.carrier_assignment_status = "valid" if carrier else "pending_carrier"
    route.carrier_assignment_issue = issue
    # Reimportações não apagam escala/histórico existente. O status
    # pending_carrier é suficiente para ocultar a rota das transportadoras.

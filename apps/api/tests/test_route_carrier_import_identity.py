import openpyxl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Branch, Carrier, CarrierBranch, Tenant
from app.db.session import Base
from app.services.jm_load_import import build_jm_template_xlsx
from app.services.route_carrier import resolve_import_carrier


@pytest.fixture
def carrier_identity_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(name="Adimax", slug="adimax-import-identity")
        db.add(tenant); db.flush()
        salto = Branch(name="Salto", tenant_id=tenant.id)
        barueri = Branch(name="Barueri", tenant_id=tenant.id)
        db.add_all([salto, barueri]); db.flush()
        alfa = Carrier(name="Transportadora Alfa", document="11111111000111", person_type="pessoa_juridica", tenant_id=tenant.id)
        db.add(alfa); db.flush()
        db.add(CarrierBranch(carrier_id=alfa.id, branch_id=salto.id))
        db.commit()
        yield db, salto, barueri, alfa
    engine.dispose()


def test_import_resolves_carrier_by_id_and_checks_name(carrier_identity_db):
    db, salto, _, alfa = carrier_identity_db
    carrier, issue = resolve_import_carrier(db, salto.id, carrier_id=alfa.id, name="Transportadora Alfa")
    assert carrier.id == alfa.id
    assert issue is None

    carrier, issue = resolve_import_carrier(db, salto.id, carrier_id=alfa.id, name="Transportadora Beta")
    assert carrier is None
    assert "não corresponde" in issue


def test_import_rejects_unknown_id_and_carrier_outside_branch(carrier_identity_db):
    db, salto, barueri, alfa = carrier_identity_db
    carrier, issue = resolve_import_carrier(db, salto.id, carrier_id=999999, name="Transportadora Alfa")
    assert carrier is None
    assert "inexistente ou inativa" in issue

    carrier, issue = resolve_import_carrier(db, barueri.id, carrier_id=alfa.id, name="Transportadora Alfa")
    assert carrier is None
    assert "não habilitada" in issue


def test_template_lists_carrier_ids_and_names():
    workbook = openpyxl.load_workbook(build_jm_template_xlsx([(7, "Transportadora Alfa"), (9, "Transportadora Beta")]))
    try:
        detail_headers = [cell.value for cell in workbook["Detalhes da carga"][1]]
        assert "ID Transportadora" in detail_headers
        assert "Transportadora" in detail_headers
        assert list(workbook["Transportadoras"].values) == [
            ("ID TRANSPORTADORA", "TRANSPORTADORA"),
            (7, "Transportadora Alfa"),
            (9, "Transportadora Beta"),
        ]
    finally:
        workbook.close()

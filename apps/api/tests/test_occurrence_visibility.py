from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Branch, Driver, Route, RouteOccurrence, Tenant, User
from app.db.session import Base
from app.modules.erp_admin.router import OccurrenceUpdateIn, occurrences, update_occurrence


def test_manager_sees_occurrences_from_all_tenant_branches_only():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="Empresa A", slug="empresa-a")
            foreign_tenant = Tenant(name="Empresa B", slug="empresa-b")
            db.add_all([tenant, foreign_tenant]); db.flush()
            branch_a = Branch(name="A", tenant_id=tenant.id)
            branch_b = Branch(name="B", tenant_id=tenant.id)
            foreign_branch = Branch(name="Outra", tenant_id=foreign_tenant.id)
            db.add_all([branch_a, branch_b, foreign_branch]); db.flush()
            manager = User(name="Gabriela", email="gabriela@example.com", role="gerente", tenant_id=tenant.id, branch_id=branch_a.id)
            driver = Driver(name="Motorista", tenant_id=tenant.id, branch_id=branch_b.id)
            db.add_all([manager, driver]); db.flush()
            own_route = Route(tenant_id=tenant.id, branch_id=branch_b.id, codigo_ut="UT-OWN", route_date=date.today(), driver_id=driver.id)
            foreign_route = Route(tenant_id=foreign_tenant.id, branch_id=foreign_branch.id, codigo_ut="UT-FOREIGN", route_date=date.today())
            db.add_all([own_route, foreign_route]); db.flush()
            db.add_all([
                RouteOccurrence(tenant_id=tenant.id, branch_id=branch_b.id, route_id=own_route.id, driver_id=driver.id, reported_by=manager.id, description="Ocorrência da empresa"),
                RouteOccurrence(tenant_id=foreign_tenant.id, branch_id=foreign_branch.id, route_id=foreign_route.id, reported_by=manager.id, description="Ocorrência externa"),
            ])
            db.commit()

            result = occurrences(db=db, user=manager)
            assert [item["codigo_ut"] for item in result] == ["UT-OWN"]
    finally:
        engine.dispose()


def test_manager_can_assume_and_treat_occurrence_in_tenant_scope():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="Empresa A", slug="empresa-a")
            db.add(tenant); db.flush()
            manager_branch = Branch(name="Gestão", tenant_id=tenant.id)
            route_branch = Branch(name="Operação", tenant_id=tenant.id)
            db.add_all([manager_branch, route_branch]); db.flush()
            manager = User(name="Gabriela", email="gabriela@example.com", role="gerente", tenant_id=tenant.id, branch_id=manager_branch.id)
            driver = Driver(name="Motorista", tenant_id=tenant.id, branch_id=route_branch.id)
            db.add_all([manager, driver]); db.flush()
            route = Route(tenant_id=tenant.id, branch_id=route_branch.id, codigo_ut="UT-001", route_date=date.today(), driver_id=driver.id)
            db.add(route); db.flush()
            occurrence = RouteOccurrence(
                tenant_id=tenant.id,
                branch_id=route_branch.id,
                route_id=route.id,
                driver_id=driver.id,
                reported_by=manager.id,
                description="Entrega bloqueada",
                status="aberta",
            )
            db.add(occurrence); db.commit()

            result = update_occurrence(
                occurrence.id,
                OccurrenceUpdateIn(status="em_tratamento", treatment_note="Gestor assumiu a ocorrência."),
                db=db,
                user=manager,
            )

            assert result.status == "em_tratamento"
            assert result.assigned_to_id == manager.id
            assert result.treatment_started_at is not None
    finally:
        engine.dispose()

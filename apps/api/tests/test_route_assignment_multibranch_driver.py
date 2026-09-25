from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Branch, Driver, DriverBranch, Route, Tenant, User, Vehicle, VehicleBranch
from app.db.session import Base
from app.modules.branches.router import BranchIn, create_branch
from app.modules.drivers.router import _sync_branches
from app.modules.routes.router import assign_route
from app.modules.routes.schemas import RouteAssignmentIn


def test_assignment_accepts_any_driver_from_route_tenant():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm")
            db.add(tenant); db.flush()
            primary = Branch(name="Piedade", tenant_id=tenant.id)
            secondary = Branch(name="Barueri", tenant_id=tenant.id)
            db.add_all([primary, secondary]); db.flush()
            manager = User(
                name="Gestor", email="gestor@example.com", role="gestor_brasil",
                tenant_id=tenant.id, branch_id=primary.id,
            )
            driver = Driver(name="Motorista multifilial", tenant_id=tenant.id, branch_id=primary.id)
            vehicle = Vehicle(plate="ABC1D23", tenant_id=tenant.id, branch_id=primary.id)
            db.add_all([manager, driver, vehicle]); db.flush()
            route = Route(
                tenant_id=tenant.id, branch_id=secondary.id, codigo_ut="ROTA-MULTIFILIAL",
                route_date=date.today(), status="planejada",
            )
            db.add(route); db.commit()
            db.add_all([
                DriverBranch(driver_id=driver.id, branch_id=secondary.id),
                VehicleBranch(vehicle_id=vehicle.id, branch_id=secondary.id),
            ])
            db.commit()

            result = assign_route(
                route.id,
                RouteAssignmentIn(driver_id=driver.id, vehicle_id=vehicle.id),
                db=db,
                user=manager,
            )

            assert result.driver_id == driver.id
            assert result.vehicle_id == vehicle.id
    finally:
        engine.dispose()


def test_driver_membership_is_explicit_and_new_branches_are_not_inherited():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm-membership")
            db.add(tenant); db.flush()
            first = Branch(name="Piedade", tenant_id=tenant.id)
            second = Branch(name="Barueri", tenant_id=tenant.id)
            db.add_all([first, second]); db.flush()
            manager = User(
                name="Gestor", email="gestor-membership@example.com", role="gestor_brasil",
                tenant_id=tenant.id, branch_id=first.id,
            )
            driver = Driver(name="Motorista", tenant_id=tenant.id, branch_id=first.id)
            db.add_all([manager, driver]); db.flush()

            _sync_branches(db, driver, [first.id], manager)
            db.flush()
            assert set(db.scalars(select(DriverBranch.branch_id).where(DriverBranch.driver_id == driver.id))) == {first.id}

            third = create_branch(BranchIn(name="Jundiaí"), db=db, actor=manager)
            assert db.scalar(select(DriverBranch).where(
                DriverBranch.driver_id == driver.id,
                DriverBranch.branch_id == third.id,
            )) is None
    finally:
        engine.dispose()

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Branch, Carrier, Driver, DriverBranch, Route, Tenant, User, Vehicle, VehicleBranch
from app.db.session import Base
from app.modules.branches.router import BranchIn, create_branch
from app.modules.drivers.router import _sync_branches
from app.modules.vehicles.router import _sync_vehicle_branches
from app.modules.routes.router import assign_route, route_assignment_options, update_route
from app.modules.routes.schemas import RouteAssignmentIn, RouteUpdate


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


def test_vehicle_is_available_on_any_branch_of_its_company_and_carrier():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm-any-branch")
            other_tenant = Tenant(name="Outra", slug="other-company")
            db.add_all([tenant, other_tenant]); db.flush()
            branch = Branch(name="Salto", tenant_id=tenant.id)
            other_branch = Branch(name="Piedade", tenant_id=tenant.id)
            carrier = Carrier(name="Executora", document="22222222000122", person_type="pessoa_juridica", tenant_id=tenant.id)
            other_carrier = Carrier(name="Outra", document="33333333000133", person_type="pessoa_juridica", tenant_id=tenant.id)
            db.add_all([branch, other_branch, carrier, other_carrier]); db.flush()
            admin = User(name="Admin", email="any-branch@example.com", role="admin_global")
            eligible = Vehicle(plate="ANY1A23", tenant_id=tenant.id, branch_id=other_branch.id, carrier_id=carrier.id)
            wrong_carrier = Vehicle(plate="OTH1A23", tenant_id=tenant.id, branch_id=branch.id, carrier_id=other_carrier.id)
            wrong_tenant = Vehicle(plate="TEN1A23", tenant_id=other_tenant.id, branch_id=branch.id, carrier_id=carrier.id)
            blocked = Vehicle(plate="BLK1A23", tenant_id=tenant.id, branch_id=branch.id, carrier_id=carrier.id, blocked=True)
            db.add_all([admin, eligible, wrong_carrier, wrong_tenant, blocked]); db.flush()
            route = Route(tenant_id=tenant.id, branch_id=branch.id, carrier_id=carrier.id,
                          codigo_ut="VEHICLE-ANY-BRANCH", route_date=date.today())
            db.add(route); db.commit()

            options = route_assignment_options(route.id, db=db, user=admin)
            assert options["vehicle_ids"] == [eligible.id]
            assigned = assign_route(route.id, RouteAssignmentIn(vehicle_id=eligible.id), db=db, user=admin)
            assert assigned.vehicle_id == eligible.id
            for vehicle in (wrong_carrier, wrong_tenant, blocked):
                with pytest.raises(HTTPException) as error:
                    assign_route(route.id, RouteAssignmentIn(vehicle_id=vehicle.id), db=db, user=admin)
                assert error.value.status_code == 422
    finally:
        engine.dispose()


def test_resources_are_available_in_current_and_future_tenant_branches():
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
            vehicle = Vehicle(plate="XYZ1A23", tenant_id=tenant.id, branch_id=first.id)
            db.add_all([manager, driver, vehicle]); db.flush()

            _sync_branches(db, driver, [first.id], manager)
            _sync_vehicle_branches(db, vehicle)
            db.flush()
            assert set(db.scalars(select(DriverBranch.branch_id).where(DriverBranch.driver_id == driver.id))) == {first.id, second.id}
            assert set(db.scalars(select(VehicleBranch.branch_id).where(VehicleBranch.vehicle_id == vehicle.id))) == {first.id, second.id}

            third = create_branch(BranchIn(name="Jundiaí"), db=db, actor=manager)
            assert db.scalar(select(DriverBranch).where(
                DriverBranch.driver_id == driver.id,
                DriverBranch.branch_id == third.id,
            )) is not None
            assert db.scalar(select(VehicleBranch).where(
                VehicleBranch.vehicle_id == vehicle.id,
                VehicleBranch.branch_id == third.id,
            )) is not None
    finally:
        engine.dispose()


def test_global_admin_sees_only_resources_available_to_route_and_can_edit_existing_assignment():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm-global-options")
            db.add(tenant); db.flush()
            branch = Branch(name="Salto", tenant_id=tenant.id)
            other_branch = Branch(name="Piedade", tenant_id=tenant.id)
            carrier = Carrier(name="Executora", document="11111111000111", person_type="pessoa_juridica", tenant_id=tenant.id)
            db.add_all([branch, other_branch, carrier]); db.flush()
            admin = User(name="Admin", email="global-options@example.com", role="admin_global")
            db.add(admin); db.flush()
            eligible = Driver(name="Liberado", tenant_id=tenant.id, branch_id=branch.id, carrier_id=carrier.id)
            unavailable = Driver(name="Outra filial", tenant_id=tenant.id, branch_id=other_branch.id)
            wrong_carrier = Driver(name="Outra transportadora", tenant_id=tenant.id, branch_id=branch.id)
            vehicle = Vehicle(plate="ABC1D23", tenant_id=tenant.id, branch_id=branch.id, carrier_id=carrier.id)
            db.add_all([eligible, unavailable, wrong_carrier, vehicle]); db.flush()
            db.add_all([DriverBranch(driver_id=eligible.id, branch_id=branch.id),
                        DriverBranch(driver_id=wrong_carrier.id, branch_id=branch.id),
                        VehicleBranch(vehicle_id=vehicle.id, branch_id=branch.id)])
            route = Route(tenant_id=tenant.id, branch_id=branch.id, carrier_id=carrier.id, codigo_ut="GLOBAL",
                          route_date=date.today(), driver_id=unavailable.id)
            db.add(route); db.commit()

            options = route_assignment_options(route.id, db=db, user=admin)
            assert options == {"driver_ids": [eligible.id], "vehicle_ids": [vehicle.id]}
            updated = update_route(route.id, RouteUpdate(origin_name="Novo nome"), db=db, user=admin)
            assert updated.driver_id == unavailable.id
            assigned = assign_route(route.id, RouteAssignmentIn(driver_id=eligible.id, vehicle_id=vehicle.id), db=db, user=admin)
            assert (assigned.driver_id, assigned.vehicle_id) == (eligible.id, vehicle.id)
    finally:
        engine.dispose()


def test_editing_one_assignment_does_not_revalidate_legacy_other_assignment():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm-legacy-assignment")
            db.add(tenant); db.flush()
            branch = Branch(name="Salto", tenant_id=tenant.id)
            other_branch = Branch(name="Piedade", tenant_id=tenant.id)
            db.add_all([branch, other_branch]); db.flush()
            admin = User(name="Admin", email="legacy-assignment@example.com", role="admin_global")
            old_driver = Driver(name="Motorista antigo", tenant_id=tenant.id, branch_id=other_branch.id)
            new_driver = Driver(name="Motorista liberado", tenant_id=tenant.id, branch_id=branch.id)
            old_vehicle = Vehicle(plate="OLD1A23", tenant_id=tenant.id, branch_id=other_branch.id)
            new_vehicle = Vehicle(plate="NEW1A23", tenant_id=tenant.id, branch_id=branch.id)
            db.add_all([admin, old_driver, new_driver, old_vehicle, new_vehicle]); db.flush()
            db.add_all([
                DriverBranch(driver_id=new_driver.id, branch_id=branch.id),
                VehicleBranch(vehicle_id=new_vehicle.id, branch_id=branch.id),
            ])
            route = Route(
                tenant_id=tenant.id, branch_id=branch.id, codigo_ut="LEGACY-ASSIGNMENT",
                route_date=date.today(), driver_id=old_driver.id, vehicle_id=old_vehicle.id,
            )
            db.add(route); db.commit()

            updated = update_route(route.id, RouteUpdate(driver_id=new_driver.id), db=db, user=admin)
            assert (updated.driver_id, updated.vehicle_id) == (new_driver.id, old_vehicle.id)

            updated = update_route(route.id, RouteUpdate(vehicle_id=new_vehicle.id), db=db, user=admin)
            assert (updated.driver_id, updated.vehicle_id) == (new_driver.id, new_vehicle.id)
    finally:
        engine.dispose()

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Branch, Carrier, CarrierBranch, CarrierUser, CarrierVehicleLink, Tenant, User, Vehicle, VehicleBranch, VehicleOwner, VehicleType
from app.db.session import Base, get_db
from app.modules.auth.deps import get_current_user
from app.modules.routes.router import _validate_route_resources
from app.modules.vehicles import router as vehicles_module


@pytest.mark.parametrize("stale_branch_id", [None, "999"])
@pytest.mark.parametrize("pending_antt", [False, True])
@pytest.mark.parametrize("with_owner", [False, True])
def test_carrier_master_registers_vehicle_in_all_enabled_branches_without_choosing_one(monkeypatch, stale_branch_id, pending_antt, with_owner):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="Adimax", slug="vehicle-all-branches")
            db.add(tenant); db.flush()
            branches = [Branch(name="Barueri", tenant_id=tenant.id), Branch(name="Salto", tenant_id=tenant.id)]
            carrier = Carrier(name="JM", tenant_id=tenant.id, antt_number=None if pending_antt else "12345678")
            owner = VehicleOwner(name="JM", document="16784574000138", tenant_id=tenant.id, carrier_id=None)
            kind = VehicleType(code="TRUCK", label="Truck")
            db.add_all([*branches, carrier, owner, kind]); db.flush()
            owner.carrier_id = carrier.id
            actor = User(name="Master JM", email="master-jm@example.com", role="gestor_brasil", tenant_id=tenant.id, branch_id=None)
            db.add(actor); db.flush()
            db.add(CarrierUser(user_id=actor.id, carrier_id=carrier.id))
            db.add_all(CarrierBranch(carrier_id=carrier.id, branch_id=branch.id) for branch in branches)
            db.commit()

            monkeypatch.setattr(vehicles_module.storage, "ensure_buckets", lambda: None)
            monkeypatch.setattr(vehicles_module.storage, "put_object", lambda *args: None)
            monkeypatch.setattr(vehicles_module.storage, "get_presigned_url", lambda *args: "https://example.invalid/crlv")
            app = FastAPI()
            app.include_router(vehicles_module.router)
            app.dependency_overrides[get_current_user] = lambda: actor
            app.dependency_overrides[get_db] = lambda: db
            data = {
                "plate": "UPM1D85", "renavam": "01508487470", "chassis": "93ZE62LNZT8719411",
                "vehicle_type_id": str(kind.id), "axles": "3",
                "ownership_type": "agregado",
            }
            if with_owner:
                data["owner_id"] = str(owner.id)
            if not pending_antt:
                data["antt_number"] = "12345678"
            if stale_branch_id is not None:
                data["branch_id"] = stale_branch_id
            with TestClient(app) as client:
                response = client.post("/vehicles/with-crlv", data=data, files={"crlv": ("UPM1D85.pdf", b"CRLV", "application/pdf")})

            assert response.status_code == 200, response.text
            vehicle = db.scalar(select(Vehicle).where(Vehicle.plate == "UPM1D85"))
            assert vehicle is not None
            assert vehicle.branch_id == min(branch.id for branch in branches)
            assert vehicle.carrier_id == carrier.id
            assert vehicle.owner_id == (owner.id if with_owner else None)
            assert set(db.scalars(select(VehicleBranch.branch_id).where(VehicleBranch.vehicle_id == vehicle.id))) == {branch.id for branch in branches}
            assert all(link.active for link in db.scalars(select(VehicleBranch).where(VehicleBranch.vehicle_id == vehicle.id)))
            carrier_link = db.scalar(select(CarrierVehicleLink).where(CarrierVehicleLink.vehicle_id == vehicle.id))
            assert carrier_link.antt_authorized is not pending_antt
            _validate_route_resources(db, branches[0].id, None, vehicle.id, carrier.id)
            with TestClient(app) as client:
                response = client.put(f"/vehicles/{vehicle.id}", json={"owner_id": None if with_owner else owner.id})
            assert response.status_code == 200, response.text
            db.refresh(vehicle)
            assert vehicle.owner_id == (None if with_owner else owner.id)
    finally:
        engine.dispose()

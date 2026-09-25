"""Carga fictícia idempotente para testar transportadoras e filiais localmente."""
from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import (
    Branch, BranchApprovalPolicy, Carrier, CarrierBranch, CarrierMaster,
    CarrierUser, DockSession, Driver, DriverBranch, Route, Tenant, User,
    UserBranchAccess, Vehicle, VehicleBranch,
)
from app.db.session import SessionLocal


CARRIERS = (
    ("Transportadora Alfa", "11111111000111", "alfa", "ALF1A01"),
    ("Transportadora Beta", "22222222000122", "beta", "BET2B02"),
    ("Transportadora Gama", "33333333000133", "gama", "GAM3C03"),
    ("Transportadora Delta", "44444444000144", "delta", "DEL4D04"),
)


def one(db, model, **filters):
    return db.scalar(select(model).filter_by(**filters))


def main() -> None:
    with SessionLocal() as db:
        # O validador de e-mail rejeita o TLD reservado ".test" ao serializar
        # /auth/me. Campos de login/e-mail são criptografados, portanto buscas
        # com LIKE não são possíveis: localizamos as contas pelo login exato.
        admin = one(db, User, email="admin.local@adimax.test")
        if admin is not None:
            target = one(db, User, email="admin.local@example.com")
            admin.email = "admin.local@example.com" if target is None else f"admin.local.legacy{admin.id}@example.com"
        local_logins = [
            f"{kind}.{slug}" for _, _, slug, _ in CARRIERS for kind in ("master", "motorista")
        ]
        for login in local_logins:
            user = one(db, User, login=login)
            if user is not None and user.email.endswith("@adimax.test"):
                user.email = user.email.removesuffix("@adimax.test") + "@example.com"

        tenant = db.scalar(select(Tenant).where(Tenant.slug == "adimax"))
        if tenant is None:
            tenant = Tenant(name="Adimax", slug="adimax", country="BR")
            db.add(tenant); db.flush()

        branches = {}
        for name in ("Salto", "Barueri"):
            branch = one(db, Branch, tenant_id=tenant.id, name=name)
            if branch is None:
                branch = Branch(tenant_id=tenant.id, name=name, country="BR", locale="pt-BR", active=True)
                db.add(branch); db.flush()
            branches[name] = branch
            if one(db, BranchApprovalPolicy, branch_id=branch.id) is None:
                db.add(BranchApprovalPolicy(branch_id=branch.id, require_driver_approval=False, require_vehicle_approval=False))

        created = {"carriers": 0, "users": 0, "drivers": 0, "vehicles": 0, "routes": 0}
        for index, (name, document, slug, plate) in enumerate(CARRIERS, start=1):
            carrier = one(db, Carrier, document=document)
            if carrier is None:
                carrier = Carrier(tenant_id=tenant.id, name=name, document=document, person_type="pessoa_juridica", kind="arrendatario", active=True)
                db.add(carrier); db.flush(); created["carriers"] += 1
            for branch in branches.values():
                if one(db, CarrierBranch, carrier_id=carrier.id, branch_id=branch.id) is None:
                    db.add(CarrierBranch(carrier_id=carrier.id, branch_id=branch.id, active=True))

            master_email = f"master.{slug}@example.com"
            master = one(db, User, login=f"master.{slug}")
            if master is None:
                master = User(
                    tenant_id=tenant.id, branch_id=branches["Salto"].id,
                    email=master_email, login=f"master.{slug}", name=f"Master {name}",
                    role="gestor_brasil", hashed_password=hash_password(settings.seed_admin_password),
                    active=True, must_change_password=False,
                )
                db.add(master); db.flush(); created["users"] += 1
            elif master.email != master_email:
                master.email = master_email
            if one(db, CarrierUser, user_id=master.id) is None:
                db.add(CarrierUser(carrier_id=carrier.id, user_id=master.id, active=True))
            if one(db, CarrierMaster, user_id=master.id) is None:
                db.add(CarrierMaster(carrier_id=carrier.id, user_id=master.id, active=True, is_first_master=True))
            for branch in branches.values():
                if one(db, UserBranchAccess, user_id=master.id, branch_id=branch.id) is None:
                    db.add(UserBranchAccess(user_id=master.id, branch_id=branch.id))

            driver_email = f"motorista.{slug}@example.com"
            driver_user = one(db, User, login=f"motorista.{slug}")
            if driver_user is None:
                driver_user = User(
                    tenant_id=tenant.id, branch_id=branches["Salto"].id,
                    email=driver_email, login=f"motorista.{slug}", name=f"Motorista {slug.title()}",
                    role="motorista", hashed_password=hash_password(settings.seed_admin_password),
                    active=True, must_change_password=False,
                )
                db.add(driver_user); db.flush(); created["users"] += 1
            elif driver_user.email != driver_email:
                driver_user.email = driver_email
            driver = one(db, Driver, user_id=driver_user.id)
            if driver is None:
                driver = Driver(
                    tenant_id=tenant.id, branch_id=branches["Salto"].id,
                    carrier_id=carrier.id, user_id=driver_user.id,
                    name=driver_user.name, employment_type="agregado", active=True,
                )
                db.add(driver); db.flush(); created["drivers"] += 1
            for branch in branches.values():
                if one(db, DriverBranch, driver_id=driver.id, branch_id=branch.id) is None:
                    db.add(DriverBranch(driver_id=driver.id, branch_id=branch.id, active=True, approval_status="approved"))

            vehicle = one(db, Vehicle, plate=plate)
            if vehicle is None:
                vehicle = Vehicle(
                    tenant_id=tenant.id, branch_id=branches["Salto"].id,
                    carrier_id=carrier.id, plate=plate, description=f"Veículo de teste {name}",
                    ownership_type="agregado", active=True,
                )
                db.add(vehicle); db.flush(); created["vehicles"] += 1
            for branch in branches.values():
                if one(db, VehicleBranch, vehicle_id=vehicle.id, branch_id=branch.id) is None:
                    db.add(VehicleBranch(vehicle_id=vehicle.id, branch_id=branch.id, active=True, approval_status="approved"))

            branch = branches["Salto"] if index % 2 else branches["Barueri"]
            code = f"DEMO-{slug.upper()}-001"
            route = one(db, Route, branch_id=branch.id, codigo_ut=code)
            if route is None:
                route = Route(
                    tenant_id=tenant.id, branch_id=branch.id, carrier_id=carrier.id,
                    carrier_assignment_status="valid", codigo_ut=code,
                    route_date=date.today() + timedelta(days=index), status="planejada",
                    driver_id=driver.id, vehicle_id=vehicle.id, source="manual",
                    origin_name=f"CD {branch.name}",
                )
                route.dock_session = DockSession()
                db.add(route); created["routes"] += 1

        pending = one(db, Route, branch_id=branches["Salto"].id, codigo_ut="DEMO-PENDENTE-001")
        if pending is None:
            pending = Route(
                tenant_id=tenant.id, branch_id=branches["Salto"].id,
                carrier_id=None, carrier_assignment_status="pending_carrier",
                carrier_assignment_issue="Transportadora fictícia não encontrada na importação.",
                codigo_ut="DEMO-PENDENTE-001", route_date=date.today(),
                status="planejada", source="automatico", origin_name="CD Salto",
            )
            pending.dock_session = DockSession()
            db.add(pending); created["routes"] += 1

        db.commit()
        counts = {
            "carriers": db.scalar(select(func.count()).select_from(Carrier)),
            "demo_routes": db.scalar(select(func.count()).select_from(Route).where(Route.codigo_ut.like("DEMO-%"))),
        }
        print({"created": created, "totals": counts, "branches": ["Salto", "Barueri"]})


if __name__ == "__main__":
    main()

"""Carga idempotente de rotas demonstrativas para a empresa principal."""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.db.models import Customer, Driver, Route, RouteStop, User, Vehicle, VehiclePosition
from app.db.session import SessionLocal


TODAY = date.today()


def one(db, model, **where):
    return db.scalar(select(model).filter_by(**where))


def ensure(db, model, where, values):
    row = one(db, model, **where)
    if row:
        return row
    row = model(**where, **values)
    db.add(row)
    db.flush()
    return row


def main():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.role == "admin_global").order_by(User.id))
        if not admin or not admin.tenant_id or not admin.branch_id:
            raise RuntimeError("Administrador global com empresa e filial não encontrado.")

        driver = ensure(db, Driver, {
            "tenant_id": admin.tenant_id, "document": "987.654.321-00"
        }, {
            "branch_id": admin.branch_id, "name": "Carlos Eduardo Demo",
            "phone": "(11) 98888-2026", "email": "motorista.demo@rotas.local",
            "city": "Santo André", "state": "SP", "cnh_number": "DEMO987654",
            "cnh_category": "D", "cnh_expiry_date": TODAY + timedelta(days=210),
            "registration_updated_at": TODAY - timedelta(days=45), "active": True,
        })

        vehicles = []
        for plate, model in [
            ("RSM2A26", "Volvo VM 270"),
            ("RSM4B24", "Mercedes-Benz Atego 1719"),
            ("RSM8C22", "Volkswagen Delivery 11.180"),
        ]:
            vehicles.append(ensure(db, Vehicle, {
                "tenant_id": admin.tenant_id, "plate": plate
            }, {
                "branch_id": admin.branch_id, "description": "Veículo de demonstração",
                "renavam": f"DEMO-{plate}", "registry_state": "SP",
                "brand": model.split()[0], "model": model, "manufacture_year": 2023,
                "model_year": 2024, "color": "Branco", "fuel": "Diesel",
                "axles": 2 if "Delivery" in model else 3, "active": True,
            }))

        destinations = [
            ("Mercado Paulista", "São Paulo", -23.5505, -46.6333),
            ("Rede Campinas", "Campinas", -22.9056, -47.0608),
            ("Atacado Santista", "Santos", -23.9608, -46.3331),
            ("Centro Sorocaba", "Sorocaba", -23.5015, -47.4526),
            ("Distribuidora Jundiaí", "Jundiaí", -23.1857, -46.8978),
            ("Varejo Guarulhos", "Guarulhos", -23.4543, -46.5337),
            ("Comercial Barueri", "Barueri", -23.5114, -46.8729),
            ("Loja São Bernardo", "São Bernardo do Campo", -23.6914, -46.5646),
        ]
        for index, (name, city, _, _) in enumerate(destinations, start=1):
            ensure(db, Customer, {
                "tenant_id": admin.tenant_id, "document": f"90.000.00{index}/0001-{index:02d}"
            }, {
                "name": name, "customer_type": "PJ", "trade_name": name,
                "city": city, "state": "SP", "phone": f"(11) 4000-{3000 + index}",
                "email": f"financeiro{index}@cliente.demo", "payment_term_days": 30,
                "active": True,
            })

        statuses = [
            "planejada", "planejada", "em_carregamento", "liberada",
            "em_rota", "em_rota", "finalizada", "cancelada",
        ]
        for index, status in enumerate(statuses, start=1):
            code = f"RSM-DEMO-{index:03d}"
            route_day = TODAY + timedelta(days=index - 4)
            route = ensure(db, Route, {
                "tenant_id": admin.tenant_id, "codigo_ut": code
            }, {
                "branch_id": admin.branch_id, "route_date": route_day,
                "origin_name": "CD Santo André", "origin_address": "Santo André - SP",
                "driver_id": driver.id, "vehicle_id": vehicles[(index - 1) % len(vehicles)].id,
                "status": status, "planned_departure_at": datetime.combine(
                    route_day, time(7, 30), tzinfo=timezone.utc
                ), "actual_departure_at": datetime.now(timezone.utc) - timedelta(hours=2)
                if status in {"em_rota", "finalizada"} else None,
                "km_total_informed": 95 + index * 28, "toll_outbound": 18 + index * 2.5,
                "toll_return": 18 + index * 2.5, "created_by": admin.id,
                "source": "manual", "fieldeas_description": f"Carga demonstrativa {city}",
            })

            for sequence in range(1, 4):
                destination = destinations[(index + sequence - 2) % len(destinations)]
                customer_name, stop_city, latitude, longitude = destination
                stop_status = "pendente"
                delivered_at = None
                if status == "finalizada" or (status == "em_rota" and sequence == 1):
                    stop_status = "entregue"
                    delivered_at = datetime.now(timezone.utc) - timedelta(minutes=35 * sequence)
                elif status == "em_rota" and sequence == 2:
                    stop_status = "em_rota"
                elif status == "cancelada":
                    stop_status = "devolvido"
                ensure(db, RouteStop, {
                    "route_id": route.id, "sequence": sequence
                }, {
                    "customer_name": customer_name,
                    "customer_address": f"Endereço demonstrativo {sequence}, {stop_city} - SP",
                    "city": stop_city, "planned_date": route_day,
                    "planned_time": time(9 + sequence * 2, 0), "weight_kg": 850 + 120 * sequence,
                    "pallets": 3 + sequence, "order_number": f"PED-{index:03d}-{sequence:02d}",
                    "status": stop_status, "delivered_at": delivered_at,
                    "latitude": latitude + sequence * 0.002,
                    "longitude": longitude + sequence * 0.002,
                    "client_name": customer_name, "invoice_number": f"NF-{index:03d}{sequence:02d}",
                    "invoice_value": 4200 + index * 350 + sequence * 190,
                    "volumes": 12 + sequence * 3, "stop_type": "descarga",
                })

            if status == "em_rota" and not one(db, VehiclePosition, route_id=route.id):
                _, _, latitude, longitude = destinations[index - 1]
                db.add(VehiclePosition(
                    tenant_id=admin.tenant_id, branch_id=admin.branch_id,
                    route_id=route.id, vehicle_id=route.vehicle_id, driver_id=driver.id,
                    user_id=admin.id, latitude=latitude, longitude=longitude,
                    accuracy_m=10, speed_kmh=52, recorded_at=datetime.now(timezone.utc),
                ))

        db.commit()
        print({"status": "ok", "tenant_id": admin.tenant_id, "branch_id": admin.branch_id,
               "routes": len(statuses), "stops": len(statuses) * 3})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

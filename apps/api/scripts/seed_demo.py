"""Carga idempotente do ambiente de demonstração/homologação."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import (
    Branch, Customer, Driver, Expense, FinancialAccount, MaintenanceOrder,
    MaintenancePlan, Part, PurchaseItem, PurchaseTicket, Revenue, Route,
    RouteOccurrence, ServiceProvider, StockMovement, Supplier, Tenant, Tire,
    User, Vehicle, VehicleOwner, VehiclePosition, WorkflowTask, WorkflowTaskEvent,
)
from app.db.session import SessionLocal

SLUG = "demonstracao-homologacao"
PASSWORD = "Demo@2026!"
TODAY = date.today()


def one(db, cls, **where):
    return db.scalar(select(cls).filter_by(**where))


def add(db, cls, **values):
    row = cls(**values)
    db.add(row)
    db.flush()
    return row


def ensure(db, cls, where: dict, values: dict):
    return one(db, cls, **where) or add(db, cls, **where, **values)


def main():
    db = SessionLocal()
    try:
        tenant = ensure(db, Tenant, {"slug": SLUG}, {
            "name": "Rotas Brasil — Demonstração", "country": "BR", "active": True,
            "feature_financeiro": True,
        })
        branch = ensure(db, Branch, {"tenant_id": tenant.id, "name": "Filial Demo — São Paulo"}, {
            "country": "BR", "locale": "pt-BR", "active": True,
        })

        users = {}
        for key, name, role, department in [
            ("admin", "Administrador Demo", "gestor_brasil", "Diretoria"),
            ("financeiro", "Fernanda Financeiro", "gestor_financeiro", "Financeiro"),
            ("torre", "Tiago Torre", "torre_controle", "Operação"),
            ("motorista", "Marcos Motorista", "motorista", "Transportes"),
        ]:
            email = f"{key}@demo.rotasbrasil.com.br"
            user = one(db, User, email=email) or one(db, User, email=f"{key}@demo.rotas.local")
            if not user:
                user = add(db, User, tenant_id=tenant.id, branch_id=branch.id, email=email,
                           name=name, role=role, department=department,
                           hashed_password=hash_password(PASSWORD), active=True)
            else:
                user.tenant_id, user.branch_id, user.name, user.email = tenant.id, branch.id, name, email
                user.role, user.department, user.active = role, department, True
            users[key] = user

        owner = ensure(db, VehicleOwner, {"tenant_id": tenant.id, "document": "12.345.678/0001-90"}, {
            "name": "Transportes Demonstração Ltda", "phone": "(11) 4000-1000",
            "email": "frota@demo.local", "address": "Av. das Rotas, 1000 — São Paulo/SP",
        })
        vehicles = []
        for plate, model, year, axles in [("DEM2A26", "Volvo VM 270", 2023, 3), ("HML4B24", "Mercedes-Benz Atego", 2021, 2), ("TST8C22", "Volkswagen Delivery", 2020, 2)]:
            vehicles.append(ensure(db, Vehicle, {"tenant_id": tenant.id, "plate": plate}, {
                "branch_id": branch.id, "owner_id": owner.id, "description": "Veículo de demonstração",
                "renavam": f"DEMO{plate}", "chassis": f"9BRDEMO{plate}00001", "registry_state": "SP",
                "brand": model.split()[0], "model": model, "manufacture_year": year, "model_year": year,
                "color": "Branco", "fuel": "Diesel", "crlv_expiry_date": TODAY + timedelta(days=180),
                "axles": axles, "length_m": 8.4, "width_m": 2.6, "height_m": 3.2,
                "gross_weight_kg": 16000, "active": True,
            }))

        driver = ensure(db, Driver, {"tenant_id": tenant.id, "document": "123.456.789-00"}, {
            "branch_id": branch.id, "user_id": users["motorista"].id, "name": "Marcos Motorista",
            "phone": "(11) 99999-1000", "email": "motorista@demo.rotasbrasil.com.br", "city": "São Paulo",
            "state": "SP", "cnh_number": "DEMO123456", "cnh_category": "D",
            "cnh_expiry_date": TODAY + timedelta(days=45), "antt_number": "ANTT-DEMO-001",
            "registration_updated_at": TODAY - timedelta(days=300), "active": True,
        })

        customers = []
        for document, name, city in [("11.111.111/0001-11", "Mercado Central Demo", "Campinas"), ("22.222.222/0001-22", "Rede Varejo Homologação", "Santos")]:
            customers.append(ensure(db, Customer, {"tenant_id": tenant.id, "document": document}, {
                "name": name, "customer_type": "PJ", "trade_name": name, "phone": "(11) 4000-2000",
                "email": "financeiro@cliente.demo", "city": city, "state": "SP", "payment_term_days": 30,
                "credit_limit": 100000, "active": True,
            }))

        supplier = ensure(db, Supplier, {"tenant_id": tenant.id, "document": "33.333.333/0001-33"}, {
            "legal_name": "Autopeças Demo Ltda", "trade_name": "Autopeças Demo", "supplier_type": "both",
            "phone": "(11) 4000-3000", "email": "vendas@autopecas.demo", "city": "São Paulo", "state": "SP",
        })
        provider = ensure(db, ServiceProvider, {"tenant_id": tenant.id, "document": "44.444.444/0001-44"}, {
            "supplier_id": supplier.id, "branch_id": branch.id, "name": "Oficina Homologação",
            "category": "oficina_mecanica", "phone": "(11) 4000-4000", "address": "Rua da Oficina, 45",
            "authorized": True, "rating": 4.7, "active": True,
        })

        routes = []
        statuses = ["finalizada", "finalizada", "em_rota", "planejada"]
        for index in range(8):
            route_day = TODAY - timedelta(days=index * 9)
            code = f"DEMO-{route_day:%Y%m%d}-{index + 1:02d}"
            routes.append(ensure(db, Route, {"tenant_id": tenant.id, "codigo_ut": code}, {
                "branch_id": branch.id, "route_date": route_day, "origin_name": "CD São Paulo",
                "origin_address": "Av. das Rotas, 1000", "driver_id": driver.id,
                "vehicle_id": vehicles[index % len(vehicles)].id, "status": statuses[index % len(statuses)],
                "km_total_informed": 180 + index * 35, "toll_outbound": 28.5, "toll_return": 28.5,
                "created_by": users["torre"].id, "source": "manual",
            }))

        # Volume operacional para visualizar filtros, quadros e indicadores em todos os estados.
        route_statuses = ["planejada", "em_carregamento", "liberada", "em_rota", "finalizada", "cancelada"]
        demo_cities = ["Campinas", "Santos", "Sorocaba", "Guarulhos", "Barueri", "Jundiaí"]
        for index in range(24):
            status = route_statuses[index % len(route_statuses)]
            route = ensure(db, Route, {"tenant_id": tenant.id, "codigo_ut": f"DEMO-ROTA-{index+1:03d}"}, {
                "branch_id": branch.id, "route_date": TODAY + timedelta(days=(index % 9) - 4),
                "origin_name": "CD São Paulo", "origin_address": "Av. das Rotas, 1000",
                "driver_id": driver.id, "vehicle_id": vehicles[index % len(vehicles)].id,
                "status": status, "km_total_informed": 95 + index * 17,
                "toll_outbound": 18.5 + index, "toll_return": 18.5 + index,
                "created_by": users["torre"].id, "source": "manual",
                "fieldeas_description": f"Carga demonstrativa para {demo_cities[index % len(demo_cities)]}",
            })
            if status == "em_rota" and not one(db, VehiclePosition, route_id=route.id):
                coordinates = [(-23.5505,-46.6333),(-23.2136,-46.8133),(-22.9099,-47.0626),(-23.9608,-46.3331)]
                latitude, longitude = coordinates[(index // len(route_statuses)) % len(coordinates)]
                add(db, VehiclePosition, tenant_id=tenant.id, branch_id=branch.id, route_id=route.id,
                    vehicle_id=route.vehicle_id, driver_id=driver.id, user_id=users["motorista"].id,
                    latitude=latitude, longitude=longitude, accuracy_m=12, speed_kmh=48 + index,
                    recorded_at=datetime.now(timezone.utc) - timedelta(minutes=index))

        task_examples = [
            (1,"Conferir divergência de comprovante","Financeiro","open"),
            (2,"Validar previsão de entrega da compra","Compras","in_progress"),
            (3,"Reprogramar veículo para rota prioritária","Operação","returned"),
            (4,"Analisar orçamento de manutenção corretiva","Frota","open"),
            (5,"Atualizar documentação do veículo","Cadastros","in_progress"),
            (6,"Responder ocorrência de entrega","Torre de controle","returned"),
            (7,"Homologar fornecedor de pneus","Compras","closed"),
            (8,"Aprovar despesa extraordinária","Diretoria","open"),
            (9,"Conciliar conta a receber vencida","Financeiro","in_progress"),
            (10,"Confirmar baixa de item do estoque","Frota","closed"),
            (11,"Solicitar ajuste na nota fiscal","Financeiro","returned"),
            (12,"Revisar SLA de ordem de serviço","Frota","open"),
        ]
        for source_id,title,department,status in task_examples:
            task=one(db,WorkflowTask,tenant_id=tenant.id,source_type="demo_task",source_id=source_id)
            if not task:
                task=add(db,WorkflowTask,tenant_id=tenant.id,branch_id=branch.id,source_type="demo_task",source_id=source_id,
                    title=title,description="Tarefa criada para simulação do ambiente de homologação.",requester_id=users["torre"].id,
                    current_department=department,status=status,source_status=status,
                    current_assignee_id=users["financeiro"].id if status=="in_progress" else None,
                    resolution="Tratativa demonstrativa concluída e devolvida ao solicitante." if status in {"returned","closed"} else None,
                    returned_at=datetime.now(timezone.utc) if status=="returned" else None,
                    closed_at=datetime.now(timezone.utc) if status=="closed" else None,
                    closed_by_id=users["torre"].id if status=="closed" else None)
            if not one(db,WorkflowTaskEvent,task_id=task.id,action="demo_created"):
                add(db,WorkflowTaskEvent,task_id=task.id,actor_id=users["torre"].id,action="demo_created",
                    to_department=department,to_status=status,note="Carga demonstrativa com trilha de eventos.")

        if not one(db, RouteOccurrence, tenant_id=tenant.id, description="Atraso por congestionamento — dado demonstrativo"):
            add(db, RouteOccurrence, tenant_id=tenant.id, branch_id=branch.id, route_id=routes[2].id,
                driver_id=driver.id, reported_by=users["motorista"].id, category="atraso", severity="media",
                description="Atraso por congestionamento — dado demonstrativo", status="aberta")

        plan = ensure(db, MaintenancePlan, {"tenant_id": tenant.id, "vehicle_id": vehicles[0].id, "service_name": "Troca de óleo e filtros"}, {
            "branch_id": branch.id, "interval_km": 10000, "interval_days": 180,
            "last_done_at": TODAY - timedelta(days=150), "last_done_km": 82000, "active": True,
        })
        ensure(db, MaintenanceOrder, {"tenant_id": tenant.id, "vehicle_id": vehicles[1].id, "description": "Revisão do sistema de freios — demonstração"}, {
            "branch_id": branch.id, "provider_id": provider.id, "kind": "corretiva", "status": "em_andamento",
            "opened_at": TODAY - timedelta(days=2), "expected_completion_date": TODAY + timedelta(days=2),
            "odometer_km": 96300, "cost": 2450, "approval_status": "aprovado",
            "approved_by": users["admin"].id, "approved_at": datetime.now(timezone.utc),
            "created_by": users["torre"].id,
        })

        for i, position in enumerate(["dianteiro_esq", "dianteiro_dir", "traseiro_esq_ext", "traseiro_esq_int", "traseiro_dir_int", "traseiro_dir_ext"]):
            ensure(db, Tire, {"tenant_id": tenant.id, "fire_number": f"DEMO-PN-{i+1:03d}"}, {
                "branch_id": branch.id, "vehicle_id": vehicles[0].id, "brand": "Goodyear", "model": "KMax",
                "position": position, "status": "em_uso", "tread_depth_mm": 14 - i, "install_date": TODAY - timedelta(days=120),
                "install_km": 78000, "cost": 2350, "active": True,
            })

        for sku, name, qty, minimum, cost in [("DEMO-FLT-001", "Filtro de óleo", 18, 6, 48.9), ("DEMO-LUB-015", "Óleo 15W40 — litro", 42, 20, 31.5), ("DEMO-PST-002", "Pastilha de freio", 3, 5, 380)]:
            part = ensure(db, Part, {"tenant_id": tenant.id, "sku": sku}, {
                "branch_id": branch.id, "name": name, "unit": "un", "quantity": qty,
                "minimum_quantity": minimum, "average_cost": cost, "active": True,
            })
            if not one(db, StockMovement, part_id=part.id, reference="CARGA-DEMO"):
                add(db, StockMovement, part_id=part.id, kind="entrada", quantity=qty, unit_cost=cost,
                    reference="CARGA-DEMO", user_id=users["torre"].id)

        # Série histórica para dashboards, contas e filtros.
        for index, route in enumerate(routes[:6]):
            rev = one(db, Revenue, tenant_id=tenant.id, route_id=route.id)
            if not rev:
                rev = add(db, Revenue, tenant_id=tenant.id, branch_id=branch.id, route_id=route.id,
                          user_id=users["financeiro"].id, revenue_date=route.route_date,
                          amount=9800 + index * 1350, notes="Faturamento demonstrativo", source="manual")
            ensure(db, FinancialAccount, {"tenant_id": tenant.id, "revenue_id": rev.id}, {
                "branch_id": branch.id, "kind": "receivable", "description": f"Frete {route.codigo_ut}",
                "counterparty": customers[index % 2].name, "category": "frete", "document": f"NF-DEMO-{index+1:03d}",
                "issue_date": route.route_date, "due_date": route.route_date + timedelta(days=30),
                "amount": rev.amount, "status": "recebida" if index >= 3 else "pendente",
                "settled_at": route.route_date + timedelta(days=25) if index >= 3 else None,
                "created_by": users["financeiro"].id,
            })
            expense = one(db, Expense, tenant_id=tenant.id, route_id=route.id, reason="combustivel")
            if not expense:
                expense = add(db, Expense, tenant_id=tenant.id, branch_id=branch.id, driver_id=driver.id,
                              vehicle_id=route.vehicle_id, user_id=users["motorista"].id, route_id=route.id,
                              expense_date=route.route_date, reason="combustivel", amount=2100 + index * 180,
                              notes="Abastecimento demonstrativo", source="manual", approval_status="approved",
                              submitted_at=datetime.now(timezone.utc), reviewed_by_id=users["financeiro"].id,
                              reviewed_at=datetime.now(timezone.utc), due_date=route.route_date + timedelta(days=10))
            ensure(db, FinancialAccount, {"tenant_id": tenant.id, "expense_id": expense.id}, {
                "branch_id": branch.id, "kind": "payable", "description": f"Combustível {route.codigo_ut}",
                "counterparty": "Posto Rodovia Demo", "category": "combustivel", "document": f"CUPOM-{index+1:03d}",
                "issue_date": route.route_date, "due_date": route.route_date + timedelta(days=10),
                "amount": expense.amount, "status": "paga" if index >= 4 else "pendente",
                "settled_at": route.route_date + timedelta(days=8) if index >= 4 else None,
                "created_by": users["financeiro"].id,
            })

        purchase = ensure(db, PurchaseTicket, {"ticket": "COMPRA-DEMO-001"}, {
            "tenant_id": tenant.id, "branch_id": branch.id, "requester_id": users["torre"].id,
            "department": "frota", "description": "Reposição de filtros e pastilhas para homologação",
            "amount": 2678, "supplier_id": supplier.id, "category": "estoque", "cost_center": "Frota",
            "due_date": TODAY + timedelta(days=15), "status": "aprovada", "approved_by": users["admin"].id,
            "approved_at": datetime.now(timezone.utc), "delivery_due_date": TODAY + timedelta(days=5),
        })
        if not one(db, PurchaseItem, purchase_id=purchase.id, description="Kit de filtros"):
            add(db, PurchaseItem, purchase_id=purchase.id, description="Kit de filtros", quantity=10, unit="un", unit_price=89.8)
            add(db, PurchaseItem, purchase_id=purchase.id, description="Pastilhas de freio", quantity=4, unit="jg", unit_price=445)

        db.commit()
        print({"status": "ok", "tenant": tenant.name, "tenant_id": tenant.id,
               "url": "http://localhost:8089", "users": [u.email for u in users.values()]})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

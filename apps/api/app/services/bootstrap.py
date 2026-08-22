"""Inicialização: cria tabelas, filial Brasil, admin semente e motivos de falha."""
from sqlalchemy import select, text

from app.core.config import settings
from app.core.permissions import ROLE_CONFIG
from app.core.security import hash_password
from app.db.models import Branch, DeliveryFailureReason, RoleProfile, Tenant, User, VehicleType
from app.db.session import Base, SessionLocal, engine
from app.core.logging import logger

# Tabelas que ganharam a coluna tenant_id (multiempresa) após o create_all
# inicial. Para bancos de dev já existentes, a coluna precisa ser adicionada
# manualmente — ver docs/visao-evolucao.md (seção "Multiempresa SaaS").
_TENANT_ID_TABLES = (
    "branches", "users", "drivers", "vehicles", "routes", "manifests",
    "audit_logs", "notifications",
)


def _add_missing_columns() -> None:
    """ALTER TABLE leve para colunas novas em bancos de dev já criados."""
    with engine.begin() as conn:
        for table in _TENANT_ID_TABLES:
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                    "tenant_id INTEGER REFERENCES tenants(id)"
                )
            )
        for column in ("km_outbound_informed", "km_return_informed"):
            conn.execute(text(f"ALTER TABLE routes ADD COLUMN IF NOT EXISTS {column} FLOAT"))
        conn.execute(
            text("ALTER TABLE delivery_failure_reasons ADD COLUMN IF NOT EXISTS label_pt_br VARCHAR(160)")
        )
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id)"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS vehicle_id INTEGER REFERENCES vehicles(id)"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS odometer_km FLOAT"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS odometer_attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS vehicle_type_id INTEGER REFERENCES vehicle_types(id)"))
        # Campos Fieldeas
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual'"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS fieldeas_description VARCHAR(255)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS fieldeas_sync_at TIMESTAMPTZ"))
        # Campos Fieldeas
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS fieldeas_internal_code VARCHAR(60)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS stop_type VARCHAR(20)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS province VARCHAR(120)"))
        # Comprovantes de entrega e devolução.
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS proof_attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS return_type VARCHAR(20)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS returned_quantity FLOAT"))
        conn.execute(
            text(
                "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS "
                "warehouse_return_attachment_id INTEGER REFERENCES attachments(id)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS "
                "logo_rail_attachment_id INTEGER REFERENCES attachments(id)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS "
                "favicon_attachment_id INTEGER REFERENCES attachments(id)"
            )
        )
        conn.execute(
            text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS enabled_locales VARCHAR(60)")
        )
        conn.execute(
            text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS topbar_extends_sidebar BOOLEAN DEFAULT TRUE")
        )
        # Campos importados da Torre de Controle (planilha) — routes
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS vehicle_requested VARCHAR(40)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS vehicle_sent VARCHAR(40)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS helper_assigned BOOLEAN"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS tracked BOOLEAN"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS km_source VARCHAR(20) DEFAULT 'informado'"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS raw_import_json TEXT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS excluded BOOLEAN DEFAULT false"))
        # Campos importados da Torre de Controle (planilha) — route_stops
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS client_name VARCHAR(160)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS invoicing_date DATE"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(40)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS remessa_code VARCHAR(40)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS delivery_type VARCHAR(40)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS invoice_value NUMERIC(12,2)"))
        for column in ("qty_saco", "qty_bombona", "qty_balde", "qty_tambor", "qty_ibc", "volumes"):
            conn.execute(text(f"ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS {column} INTEGER"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS delivery_protocol VARCHAR(60)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS raw_import_json TEXT"))
        # Despesas importadas em lote (sem comprovante) — relaxa NOT NULL e adiciona source.
        conn.execute(text("ALTER TABLE expenses ALTER COLUMN attachment_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual'"))
        # Branding por cliente (multi-tenant) — tenant_id NULL = padrão da plataforma.
        conn.execute(text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_branding_settings_tenant_id_unique "
                "ON branding_settings (tenant_id) WHERE tenant_id IS NOT NULL"
            )
        )
        # Serviços ativáveis por cliente.
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_ocr BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_sharepoint_sync BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_financeiro BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_rastreamento BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_route_optimization BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_km_calculation BOOLEAN DEFAULT TRUE"))
        # Transportadoras (fornecedores) por cliente.
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS carrier_id INTEGER REFERENCES carriers(id)"))
        # Conta SaaS — plano, mensalidade e vencimento por cliente.
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_plan VARCHAR(60)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_amount NUMERIC(10,2)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_due_day INTEGER"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_last_payment_date DATE"))
        # Renomeia o perfil "gestor_portugal" (nome herdado do piloto Portugal) para "gestor_brasil".
        conn.execute(text("UPDATE users SET role = 'gestor_brasil' WHERE role = 'gestor_portugal'"))
        conn.execute(text("UPDATE role_profiles SET value = 'gestor_brasil' WHERE value = 'gestor_portugal'"))


# Motivos de falha de entrega mais comuns (criados no primeiro boot).
# Cada motivo tem o rótulo em pt-PT (label) e o equivalente em pt-BR (label_pt_br).
DEFAULT_FAILURE_REASONS = [
    ("endereco_errado", "Endereço errado", "Endereço errado", 10),
    ("local_fechado", "Local fechado", "Local fechado", 20),
    ("recusa_cliente", "Recusa do cliente", "Recusa do cliente", 30),
    ("cliente_ausente", "Cliente ausente", "Cliente ausente", 40),
    ("mercadoria_avariada", "Mercadoria avariada", "Mercadoria avariada", 50),
    ("fora_horario", "Fora do horário de recebimento", "Fora do horário de recebimento", 60),
    ("sem_acesso", "Sem acesso / espaço para descarga", "Sem acesso / espaço para descarga", 70),
    ("outros", "Outros", "Outros", 999),
]

# Tipologias de veículo mais comuns (criadas no primeiro boot).
# Cada tipo tem o rótulo em pt-PT (label) e o equivalente em pt-BR (label_pt_br).
DEFAULT_VEHICLE_TYPES = [
    ("van", "Furgão", "Van", 10),
    ("ligeiro", "Veículo ligeiro de mercadorias", "Veículo leve de carga", 20),
    ("vuc", "VUC", "VUC", 30),
    ("toco", "Camião toco", "Caminhão toco", 40),
    ("truck", "Camião truck", "Caminhão truck", 50),
    ("bau", "Camião baú", "Caminhão baú", 60),
    ("frigorifico", "Camião frigorífico", "Caminhão frigorífico", 70),
    ("pesado_rigido", "Camião rígido", "Caminhão rígido", 80),
    ("pesado_articulado", "Camião articulado (semi-reboque)", "Caminhão articulado (carreta)", 90),
    ("porta_contentor", "Porta-contentores", "Porta-contêiner", 100),
    ("moto", "Motociclo", "Motocicleta", 110),
    ("outro", "Outro", "Outro", 999),
]


_INIT_DB_LOCK_KEY = 727384910  # chave arbitrária para o advisory lock abaixo.


def init_db() -> None:
    # Com múltiplos workers (gunicorn -w N), cada processo roda init_db() ao subir.
    # Sem serializar, as ALTER TABLE concorrentes podem deadlockar no Postgres e
    # derrubar o boot dos workers. O advisory lock garante que só um processo
    # roda a migração por vez; os demais esperam e seguem (idempotente).
    with engine.connect() as lock_conn:
        lock_conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _INIT_DB_LOCK_KEY})
        try:
            _init_db_locked()
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _INIT_DB_LOCK_KEY})


def _init_db_locked() -> None:
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    with SessionLocal() as db:
        for role, config in ROLE_CONFIG.items():
            profile = db.get(RoleProfile, role.value)
            if profile is None:
                db.add(
                    RoleProfile(
                        value=role.value,
                        label=config["label"],
                        description=config["description"],
                        permissions_json="\n".join(config["permissions"]),
                        sort_order=config["order"],
                        active=True,
                        system=True,
                    )
                )
            else:
                if profile.label == role.value:
                    profile.label = config["label"]
                profile.system = True

        for code, label, label_pt_br, order in DEFAULT_FAILURE_REASONS:
            reason = db.scalar(select(DeliveryFailureReason).where(DeliveryFailureReason.code == code))
            if reason is None:
                db.add(DeliveryFailureReason(code=code, label=label, label_pt_br=label_pt_br, sort_order=order))
            elif reason.label_pt_br is None:
                reason.label_pt_br = label_pt_br

        for code, label, label_pt_br, order in DEFAULT_VEHICLE_TYPES:
            vtype = db.scalar(select(VehicleType).where(VehicleType.code == code))
            if vtype is None:
                db.add(VehicleType(code=code, label=label, label_pt_br=label_pt_br, sort_order=order))
            elif vtype.label_pt_br is None:
                vtype.label_pt_br = label_pt_br

        # Migra em vez de duplicar: bancos antigos podem ter o tenant/filial de
        # Portugal (scaffold inicial) ou o nome/slug antigo "JM Brasil"
        # (rebranding para Admmendes) — a operação real é 100% Brasil.
        tenant = (
            db.scalar(select(Tenant).where(Tenant.slug == "jm-portugal"))
            or db.scalar(select(Tenant).where(Tenant.slug == "jm-brasil"))
        )
        if tenant is not None:
            tenant.name, tenant.slug, tenant.country = "Admmendes Brasil", "admmendes-brasil", "BR"
            logger.info("Tenant migrado para Admmendes Brasil.")
        else:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == "admmendes-brasil"))
        if tenant is None:
            tenant = Tenant(name="Admmendes Brasil", slug="admmendes-brasil", country="BR")
            db.add(tenant)
            db.flush()
            logger.info("Tenant Admmendes Brasil criado.")

        branch = db.scalar(select(Branch).where(Branch.country == "PT"))
        if branch is not None:
            branch.name = "Admmendes Distribuição - Brasil (Santo André)"
            branch.country, branch.locale = "BR", "pt-BR"
            logger.info("Filial Portugal migrada para Brasil.")
        else:
            branch = db.scalar(select(Branch).where(Branch.country == "BR"))
        if branch is None:
            branch = Branch(
                name="Admmendes Distribuição - Brasil (Santo André)", country="BR", locale="pt-BR", tenant_id=tenant.id,
            )
            db.add(branch)
            db.flush()
            logger.info("Filial Brasil criada.")
        else:
            branch.active = True
            if branch.tenant_id is None:
                branch.tenant_id = tenant.id

        if settings.auth_mode == "local":
            admin = db.scalar(select(User).where(User.email == settings.seed_admin_email))
            if admin is None:
                db.add(
                    User(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        email=settings.seed_admin_email,
                        name=settings.seed_admin_name,
                        role="admin_global",
                        hashed_password=hash_password(settings.seed_admin_password),
                    )
                )
                logger.info("Admin semente criado: %s", settings.seed_admin_email)
            elif admin.branch_id is None or db.get(Branch, admin.branch_id) is None:
                admin.branch_id = branch.id
                admin.tenant_id = tenant.id

        db.flush()
        db.execute(
            text(
                "UPDATE branches SET tenant_id = :tid WHERE tenant_id IS NULL"
            ),
            {"tid": tenant.id},
        )
        for table in ("users", "drivers", "vehicles", "routes", "manifests", "expenses", "revenues"):
            db.execute(
                text(
                    f"UPDATE {table} t SET tenant_id = b.tenant_id "
                    f"FROM branches b WHERE t.branch_id = b.id AND t.tenant_id IS NULL"
                )
            )
        for table in ("audit_logs", "notifications"):
            db.execute(
                text(
                    f"UPDATE {table} t SET tenant_id = u.tenant_id "
                    f"FROM users u WHERE t.user_id = u.id AND t.tenant_id IS NULL"
                )
            )
        db.commit()

"""Inicialização: cria tabelas, filial Brasil, admin semente e motivos de falha."""
from datetime import date
from sqlalchemy import select, text

from app.core.config import settings
from app.core.permissions import ROLE_CONFIG
from app.core.security import hash_password
from app.db.models import Branch, ChecklistTemplateItem, DeliveryFailureReason, Expense, FinancialAccount, FinancialCategory, Revenue, RoleProfile, Route, Tenant, User, VehicleType
from app.services.accounting import post_expense, post_revenue
from app.db.session import Base, SessionLocal, engine
from app.core.logging import logger

# Tabelas que ganharam a coluna tenant_id (multiempresa) após o create_all
# inicial. Para bancos de dev já existentes, a coluna precisa ser adicionada
# manualmente para manter compatibilidade com bancos de desenvolvimento existentes.
_TENANT_ID_TABLES = (
    "branches", "users", "drivers", "vehicles", "routes",
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
        conn.execute(text("ALTER TABLE branches ADD COLUMN IF NOT EXISTS default_origin_address VARCHAR(255)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR(80)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS subgroup VARCHAR(80)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions_json TEXT"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS login VARCHAR(80)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_login ON users (login) WHERE login IS NOT NULL"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_version INTEGER NOT NULL DEFAULT 1"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS carrier_id INTEGER REFERENCES carriers(id)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS carrier_assignment_status VARCHAR(30) NOT NULL DEFAULT 'pending_carrier'"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS carrier_assignment_issue TEXT"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_routes_carrier_id ON routes (carrier_id)"))
        conn.execute(text("ALTER TABLE driver_branches ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE driver_branches ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'"))
        conn.execute(text("ALTER TABLE driver_branches ADD COLUMN IF NOT EXISTS approval_reason TEXT"))
        conn.execute(text("ALTER TABLE driver_branches ADD COLUMN IF NOT EXISTS reviewed_by_id INTEGER REFERENCES users(id)"))
        conn.execute(text("ALTER TABLE driver_branches ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ"))
        conn.execute(text("INSERT INTO driver_branches (driver_id, branch_id, active, approval_status) SELECT id, branch_id, TRUE, 'approved' FROM drivers ON CONFLICT (driver_id, branch_id) DO NOTHING"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS customer_type VARCHAR(2) DEFAULT 'PJ'"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS trade_name VARCHAR(160)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS state_registration VARCHAR(40)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS municipal_registration VARCHAR(40)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS identity_document VARCHAR(40)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS birth_date DATE"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS main_activity VARCHAR(160)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS contact_name VARCHAR(120)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS financial_contact VARCHAR(120)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS financial_phone VARCHAR(40)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS address_number VARCHAR(20)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS complement VARCHAR(100)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS district VARCHAR(100)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS city VARCHAR(120)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS state VARCHAR(2)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS credit_limit NUMERIC(12,2)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS payment_term_days INTEGER"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS bank_reference VARCHAR(180)"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS commercial_reference TEXT"))
        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS notes TEXT"))
        for column in ("km_outbound_informed", "km_return_informed"):
            conn.execute(text(f"ALTER TABLE routes ADD COLUMN IF NOT EXISTS {column} FLOAT"))
        conn.execute(
            text("ALTER TABLE delivery_failure_reasons ADD COLUMN IF NOT EXISTS label_pt_br VARCHAR(160)")
        )
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id)"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS vehicle_id INTEGER REFERENCES vehicles(id)"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS odometer_km FLOAT"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS odometer_attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("ALTER TABLE route_occurrences ADD COLUMN IF NOT EXISTS assigned_to_id INTEGER REFERENCES users(id)"))
        conn.execute(text("ALTER TABLE route_occurrences ADD COLUMN IF NOT EXISTS treatment_started_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE route_occurrences ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE route_occurrences ADD COLUMN IF NOT EXISTS finalized_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS vehicle_type_id INTEGER REFERENCES vehicle_types(id)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS carrier_id INTEGER REFERENCES carriers(id)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS freight_receiver_type VARCHAR(20) DEFAULT 'proprietario'"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_carrier_vehicle_single ON carrier_vehicle_links(vehicle_id)"))
        conn.execute(text("UPDATE vehicles v SET carrier_id = l.carrier_id, freight_receiver_type = 'terceiro' FROM carrier_vehicle_links l WHERE l.vehicle_id = v.id AND v.carrier_id IS NULL"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS person_type VARCHAR(20) DEFAULT 'pessoa_fisica'"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS phone VARCHAR(40)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS email VARCHAR(180)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS address VARCHAR(255)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS bank_name VARCHAR(120)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS bank_agency VARCHAR(30)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS bank_account VARCHAR(40)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS bank_account_type VARCHAR(30)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS pix_key_type VARCHAR(20)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS pix_key VARCHAR(180)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS antt_number VARCHAR(40)"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS antt_expiry_date DATE"))
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
        conn.execute(text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS login_intro_text TEXT"))
        conn.execute(text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS login_layout VARCHAR(30) DEFAULT 'centered'"))
        conn.execute(text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS sidebar_background_color VARCHAR(20)"))
        conn.execute(text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS sidebar_text_color VARCHAR(20)"))
        conn.execute(text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS sidebar_active_color VARCHAR(20)"))
        # Migração de identidade deste projeto: remove a identidade anterior.
        # e deixa os arquivos estáticos oficiais como fonte do logo e favicon.
        conn.execute(text("""
            UPDATE branding_settings
               SET app_name = 'Adimax',
                   app_subtitle = 'Gestão de rotas e entregas',
                   login_intro_text = 'Operação logística com rotas, entregas e ocorrências em um só lugar.',
                   login_layout = 'institutional',
                   primary_color = '#F9A61A',
                   sidebar_background_color = '#F2F2F2',
                   sidebar_text_color = '#242424',
                   sidebar_active_color = '#F9A61A',
                   enabled_locales = 'pt-BR',
                   topbar_extends_sidebar = TRUE,
                   logo_attachment_id = NULL,
                   logo_rail_attachment_id = NULL,
                   background_attachment_id = NULL,
                   favicon_attachment_id = NULL
             WHERE app_name IS NULL OR app_name ILIKE ('%Trans ' || 'Adimax%')
        """))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS navigation_layout VARCHAR(20) DEFAULT 'sidebar'"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS acting_branch_id INTEGER REFERENCES branches(id)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS acting_carrier_id INTEGER REFERENCES carriers(id)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS max_carrier_masters INTEGER NOT NULL DEFAULT 3"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS max_masters INTEGER"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS help_assistant_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
        # Campos importados da Torre de Controle (planilha) — routes
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS vehicle_requested VARCHAR(40)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS vehicle_sent VARCHAR(40)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS helper_assigned BOOLEAN"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS tracked BOOLEAN"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS km_source VARCHAR(20) DEFAULT 'informado'"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS raw_import_json TEXT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS excluded BOOLEAN DEFAULT false"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS routing_status VARCHAR(20) DEFAULT 'pending'"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS routing_distance_km FLOAT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS routing_duration_minutes INTEGER"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS routing_optimized_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS routing_error TEXT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS overnight_count INTEGER"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS cte_number VARCHAR(120)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS route_observations (id SERIAL PRIMARY KEY, route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE, sequence INTEGER NOT NULL, text TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_route_observations_route_id ON route_observations(route_id)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS routing_geometry_json TEXT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS suggested_geometry_json TEXT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS origin_id INTEGER REFERENCES route_origins(id)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS spreadsheet_route VARCHAR(80)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS delivery_date DATE"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS driver_type VARCHAR(40)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS vehicle_profile_sent VARCHAR(40)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS vehicle_profile_requested VARCHAR(40)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS typology_view VARCHAR(60)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS overnight BOOLEAN"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS daily_count FLOAT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS daily_value TEXT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS administrative_notes TEXT"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS helper_requested VARCHAR(40)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS helper_sent VARCHAR(80)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS load_quantity INTEGER"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS spreadsheet_sequence INTEGER"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS optimized_sequence INTEGER"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES customers(id)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS destination_id INTEGER REFERENCES delivery_destinations(id)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS cte_number VARCHAR(255)"))
        conn.execute(text("ALTER TABLE route_stops ALTER COLUMN cte_number TYPE VARCHAR(255)"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS customer_notes TEXT"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS customer_notes_2 TEXT"))
        conn.execute(text("ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS customer_notes_3 TEXT"))
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
        conn.execute(text("ALTER TABLE route_occurrences ADD COLUMN IF NOT EXISTS evidence_attachment_id INTEGER REFERENCES attachments(id)"))
        # Despesas importadas em lote (sem comprovante) — relaxa NOT NULL e adiciona source.
        conn.execute(text("ALTER TABLE expenses ALTER COLUMN attachment_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual'"))
        conn.execute(text("UPDATE expenses e SET source = 'driver' FROM users u WHERE e.user_id = u.id AND u.role = 'motorista' AND e.source = 'manual'"))
        conn.execute(text("UPDATE expenses SET source = 'administrative' WHERE source = 'manual'"))
        conn.execute(text("ALTER TABLE expenses ALTER COLUMN driver_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS maintenance_order_id INTEGER REFERENCES maintenance_orders(id)"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30) DEFAULT 'approved'"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS reviewed_by_id INTEGER REFERENCES users(id)"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS decision_note TEXT"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS due_date DATE"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS recurrence VARCHAR(20) DEFAULT 'none'"))
        conn.execute(text("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS recurrence_count INTEGER DEFAULT 1"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_expenses_approval_status ON expenses (approval_status)"))
        # Lançamentos anteriores à implantação já compunham o financeiro; novos aguardam aceite.
        conn.execute(text("UPDATE expenses SET approval_status = 'approved' WHERE approval_status IS NULL"))
        conn.execute(text("ALTER TABLE expenses ALTER COLUMN approval_status SET DEFAULT 'pending'"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS expense_id INTEGER REFERENCES expenses(id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_financial_accounts_expense_id_unique ON financial_accounts (expense_id) WHERE expense_id IS NOT NULL"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS revenue_id INTEGER REFERENCES revenues(id)"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS driver_id INTEGER REFERENCES drivers(id)"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS route_id INTEGER REFERENCES routes(id)"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS discount_reason VARCHAR(180)"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS payment_period_start DATE"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS payment_period_end DATE"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_financial_accounts_driver_id ON financial_accounts (driver_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_financial_accounts_route_id ON financial_accounts (route_id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_financial_accounts_driver_period_unique ON financial_accounts (driver_id, payment_period_start, payment_period_end) WHERE driver_id IS NOT NULL"))
        conn.execute(text("ALTER TABLE driver_statement_adjustments ADD COLUMN IF NOT EXISTS financial_account_id INTEGER REFERENCES financial_accounts(id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_driver_adjustment_financial_account_unique ON driver_statement_adjustments (financial_account_id) WHERE financial_account_id IS NOT NULL"))
        conn.execute(text("ALTER TABLE workflow_tasks ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 3"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_financial_accounts_revenue_id_unique ON financial_accounts (revenue_id) WHERE revenue_id IS NOT NULL"))
        conn.execute(text("ALTER TABLE revenues ADD COLUMN IF NOT EXISTS billed_customer_name VARCHAR(180)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_revenues_billed_customer_name ON revenues (billed_customer_name)"))
        conn.execute(text("INSERT INTO revenue_route_links (revenue_id, route_id) SELECT id, route_id FROM revenues WHERE route_id IS NOT NULL ON CONFLICT (revenue_id, route_id) DO NOTHING"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS recurrence_group VARCHAR(60)"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS recurrence_sequence INTEGER"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS recurrence_total INTEGER"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS service_invoice_number VARCHAR(80)"))
        conn.execute(text("ALTER TABLE financial_accounts ADD COLUMN IF NOT EXISTS service_invoice_attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_financial_accounts_service_invoice_number ON financial_accounts (service_invoice_number)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_financial_accounts_recurrence_group ON financial_accounts (recurrence_group)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_financial_accounts_recurrence_sequence_unique ON financial_accounts (recurrence_group, recurrence_sequence) WHERE recurrence_group IS NOT NULL"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_expenses_maintenance_order_id_unique ON expenses (maintenance_order_id) WHERE maintenance_order_id IS NOT NULL"))
        # Branding por cliente (multi-tenant) — tenant_id NULL = padrão da plataforma.
        conn.execute(text("ALTER TABLE branding_settings ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_branding_settings_tenant_id_unique "
                "ON branding_settings (tenant_id) WHERE tenant_id IS NOT NULL"
            )
        )
        # Serviços ativáveis por cliente.
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_sharepoint_sync BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_financeiro BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_rastreamento BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_route_optimization BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_km_calculation BOOLEAN DEFAULT TRUE"))
        # Transportadoras (fornecedores) por cliente.
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS carrier_id INTEGER REFERENCES carriers(id)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS employment_type VARCHAR(20) DEFAULT 'proprio'"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS daily_rate NUMERIC(10,2)"))
        conn.execute(text("ALTER TABLE driver_settings ADD COLUMN IF NOT EXISTS statement_release_day INTEGER DEFAULT 1"))
        conn.execute(text("UPDATE drivers SET employment_type = 'agregado' WHERE carrier_id IS NOT NULL AND (employment_type IS NULL OR employment_type = 'proprio')"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS email VARCHAR(180)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS address VARCHAR(255)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS city VARCHAR(120)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS state VARCHAR(2)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS birth_date DATE"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS cnh_number VARCHAR(40)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS cnh_category VARCHAR(10)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS cnh_expiry_date DATE"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS antt_number VARCHAR(40)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS antt_expiry_date DATE"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS registration_updated_at DATE"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS document_attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS cnh_attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES vehicle_owners(id)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS ownership_type VARCHAR(20) DEFAULT 'proprio'"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS antt_number VARCHAR(40)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS antt_expiry_date DATE"))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS person_type VARCHAR(20) DEFAULT 'pessoa_fisica'"))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS carrier_id INTEGER REFERENCES carriers(id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vehicle_owners_carrier_id ON vehicle_owners(carrier_id)"))
        conn.execute(text(
            "UPDATE vehicle_owners owner SET carrier_id = inferred.carrier_id "
            "FROM (SELECT owner_id, MIN(carrier_id) AS carrier_id FROM vehicles "
            "WHERE owner_id IS NOT NULL AND carrier_id IS NOT NULL GROUP BY owner_id "
            "HAVING COUNT(DISTINCT carrier_id) = 1) inferred "
            "WHERE owner.id = inferred.owner_id AND owner.carrier_id IS NULL AND owner.is_tenant_company IS NOT TRUE"
        ))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS bank_name VARCHAR(120)"))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS bank_agency VARCHAR(30)"))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS bank_account VARCHAR(40)"))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS bank_account_type VARCHAR(30)"))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS pix_key_type VARCHAR(20)"))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS pix_key VARCHAR(180)"))
        conn.execute(text("ALTER TABLE vehicle_owners ADD COLUMN IF NOT EXISTS is_tenant_company BOOLEAN DEFAULT FALSE"))
        for table in ("users", "drivers", "vehicles", "vehicle_owners"):
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS blocked BOOLEAN DEFAULT FALSE"))
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS status_reason TEXT"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS legal_name VARCHAR(180)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS document VARCHAR(40)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS state_registration VARCHAR(40)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS address VARCHAR(255)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS city VARCHAR(120)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS state VARCHAR(2)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS phone VARCHAR(40)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email VARCHAR(180)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS antt_number VARCHAR(40)"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS antt_expiry_date DATE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS partners TEXT"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS renavam VARCHAR(30)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS chassis VARCHAR(40)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS registry_state VARCHAR(2)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS brand VARCHAR(80)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS model VARCHAR(100)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS manufacture_year INTEGER"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS model_year INTEGER"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS color VARCHAR(40)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS fuel VARCHAR(40)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS crlv_expiry_date DATE"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS axles INTEGER"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS rear_dual_wheels BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tire_inspections ADD COLUMN IF NOT EXISTS checklist_id INTEGER REFERENCES vehicle_checklists(id) ON DELETE CASCADE"))
        conn.execute(text("ALTER TABLE operational_settings ADD COLUMN IF NOT EXISTS alert_due_days INTEGER DEFAULT 3"))
        conn.execute(text("ALTER TABLE operational_settings ADD COLUMN IF NOT EXISTS alert_document_days INTEGER DEFAULT 30"))
        conn.execute(text("ALTER TABLE operational_settings ADD COLUMN IF NOT EXISTS tire_warning_mm FLOAT DEFAULT 3"))
        conn.execute(text("ALTER TABLE operational_settings ADD COLUMN IF NOT EXISTS tire_critical_mm FLOAT DEFAULT 1.6"))
        conn.execute(text("ALTER TABLE operational_settings ADD COLUMN IF NOT EXISTS routing_enabled BOOLEAN DEFAULT TRUE"))
        conn.execute(text("UPDATE operational_settings SET alert_due_days=COALESCE(alert_due_days,3), alert_document_days=COALESCE(alert_document_days,30), tire_warning_mm=COALESCE(tire_warning_mm,3), tire_critical_mm=COALESCE(tire_critical_mm,1.6)"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS length_m FLOAT"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS width_m FLOAT"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS height_m FLOAT"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS gross_weight_kg FLOAT"))
        conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS crlv_attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("ALTER TABLE service_providers ADD COLUMN IF NOT EXISTS supplier_id INTEGER REFERENCES suppliers(id)"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS supplier_id INTEGER REFERENCES suppliers(id)"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS category VARCHAR(80) DEFAULT 'outros'"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS document VARCHAR(80)"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS due_date DATE"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS cost_center VARCHAR(80)"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS financial_account_id INTEGER REFERENCES financial_accounts(id)"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS purchased_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS delivery_due_date DATE"))
        conn.execute(text("ALTER TABLE purchase_tickets ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE maintenance_orders ADD COLUMN IF NOT EXISTS expected_completion_date DATE"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_purchase_financial_account_unique ON purchase_tickets (financial_account_id) WHERE financial_account_id IS NOT NULL"))
        conn.execute(text("ALTER TABLE carriers ADD COLUMN IF NOT EXISTS kind VARCHAR(20) DEFAULT 'arrendatario'"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS driver_payment_amount NUMERIC(12,2)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS driver_payment_notes TEXT"))
        # Fotos obrigatórias no fechamento da rota: baú vazio e carro carregado com as devoluções.
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS empty_truck_photo_attachment_id INTEGER REFERENCES attachments(id)"))
        conn.execute(text("ALTER TABLE routes ADD COLUMN IF NOT EXISTS loaded_return_photo_attachment_id INTEGER REFERENCES attachments(id)"))
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


# Itens de checklist de veículo mais comuns (criados no primeiro boot).
# (code, label, label_pt_br, category, required, sort_order)
DEFAULT_CHECKLIST_ITEMS = [
    ("freios", "Travões", "Freios", "freios", True, 10),
    ("pneus_estado", "Estado dos pneus", "Estado dos pneus", "pneus", True, 20),
    ("pneus_calibragem", "Calibragem dos pneus", "Calibragem dos pneus", "pneus", False, 30),
    ("estepe", "Roda sobresselente / estepe", "Estepe", "pneus", False, 40),
    ("luzes", "Luzes e sinalização", "Luzes e sinalização", "eletrica", True, 50),
    ("bateria", "Bateria", "Bateria", "eletrica", False, 60),
    ("nivel_oleo", "Nível de óleo", "Nível de óleo", "fluidos", True, 70),
    ("nivel_agua", "Nível de água/arrefecimento", "Nível de água/arrefecimento", "fluidos", False, 80),
    ("vazamentos", "Vazamentos visíveis", "Vazamentos visíveis", "fluidos", True, 90),
    ("documentacao", "Documentação do veículo em dia", "Documentação do veículo em dia", "documentacao", True, 100),
    ("cnh_motorista", "CNH do motorista válida", "CNH do motorista válida", "documentacao", True, 110),
    ("cinto_seguranca", "Cinto de segurança", "Cinto de segurança", "seguranca", True, 120),
    ("extintor", "Extintor de incêndio", "Extintor de incêndio", "seguranca", True, 130),
    ("triangulo_macaco", "Triângulo e macaco", "Triângulo e macaco", "seguranca", False, 140),
    ("epi", "EPI do motorista/ajudante", "EPI do motorista/ajudante", "seguranca", False, 150),
    ("limpeza_cabine", "Limpeza da cabine/baú", "Limpeza da cabine/baú", "outros", False, 160),
]

_INIT_DB_LOCK_KEY = 727384910  # chave arbitrária para o advisory lock abaixo.
_BOOTSTRAP_VERSION = "2026-09-25.branch-default-origin-v4"


def init_db() -> None:
    # Com múltiplos workers (gunicorn -w N), cada processo roda init_db() ao subir.
    # Sem serializar, as ALTER TABLE concorrentes podem deadlockar no Postgres e
    # derrubar o boot dos workers. O advisory lock garante que só um processo
    # roda a migração por vez; os demais esperam e seguem (idempotente).
    with engine.connect() as lock_conn:
        lock_conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _INIT_DB_LOCK_KEY})
        try:
            lock_conn.execute(text(
                "CREATE TABLE IF NOT EXISTS app_bootstrap_versions ("
                "version VARCHAR(120) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            ))
            already_applied = lock_conn.scalar(
                text("SELECT 1 FROM app_bootstrap_versions WHERE version = :version"),
                {"version": _BOOTSTRAP_VERSION},
            )
            if already_applied is None:
                _init_db_locked()
                lock_conn.execute(
                    text("INSERT INTO app_bootstrap_versions (version) VALUES (:version) ON CONFLICT DO NOTHING"),
                    {"version": _BOOTSTRAP_VERSION},
                )
                lock_conn.commit()
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

        # Perfis antigos eram aliases com autoridade implícita. Consolida as
        # contas existentes nos perfis canônicos e mantém os registros antigos
        # inativos apenas para rastreabilidade histórica.
        legacy_roles = {
            "admin_site": "gestor_brasil", "gerente": "gestor_brasil",
            "lider": "operador_logistico", "planejamento": "operador_logistico",
            "monitoramento": "torre_controle",
        }
        for legacy, canonical in legacy_roles.items():
            db.execute(text("UPDATE users SET role=:canonical WHERE role=:legacy"), {"legacy": legacy, "canonical": canonical})
            legacy_profile = db.get(RoleProfile, legacy)
            if legacy_profile is not None:
                legacy_profile.active = False
                legacy_profile.description = f"Perfil legado consolidado em {canonical}."

        # Garante que receitas históricas/importadas também apareçam em Contas a Receber.
        linked_revenue_ids = select(FinancialAccount.revenue_id).where(FinancialAccount.revenue_id.is_not(None))
        for revenue in db.scalars(select(Revenue).where(~Revenue.id.in_(linked_revenue_ids))).all():
            route = db.get(Route, revenue.route_id) if revenue.route_id else None
            db.add(FinancialAccount(
                branch_id=revenue.branch_id, kind="receivable",
                description=f"Receita da rota {route.codigo_ut if route else revenue.route_id or revenue.id}",
                counterparty="Cliente da rota" if route else "Receita financeira",
                category="frete" if route else "outros",
                document=f"ROTA-{route.codigo_ut}" if route else f"RECEITA-{revenue.id}",
                issue_date=revenue.revenue_date,
                due_date=max(revenue.revenue_date, date.today()),
                amount=revenue.amount, status="pendente", notes=revenue.notes,
                created_by=revenue.user_id, revenue_id=revenue.id,
            ))

        # Converte o histórico financeiro em partidas dobradas, de forma idempotente.
        for revenue in db.scalars(select(Revenue)).all():
            try: post_revenue(db, revenue, revenue.user_id)
            except Exception as exc: logger.warning("Receita %s não retrocontabilizada: %s", revenue.id, exc)
        for expense in db.scalars(select(Expense).where(Expense.approval_status == "approved")).all():
            try: post_expense(db, expense, expense.reviewed_by_id or expense.user_id)
            except Exception as exc: logger.warning("Despesa %s não retrocontabilizada: %s", expense.id, exc)

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

        for code, label, label_pt_br, category, required, order in DEFAULT_CHECKLIST_ITEMS:
            citem = db.scalar(select(ChecklistTemplateItem).where(ChecklistTemplateItem.code == code))
            if citem is None:
                db.add(ChecklistTemplateItem(
                    code=code, label=label, label_pt_br=label_pt_br,
                    category=category, required=required, sort_order=order,
                ))

        # Migra em vez de duplicar: bancos antigos podem ter o tenant/filial de
        # Portugal (scaffold inicial) ou o nome/slug antigo "JM Brasil"
        # (rebranding para Admmendes) — a operação real é 100% Brasil.
        tenant = (
            db.scalar(select(Tenant).where(Tenant.slug == "adimax"))
            or db.scalar(select(Tenant).where(Tenant.slug == "jm-portugal"))
            or db.scalar(select(Tenant).where(Tenant.slug == "jm-brasil"))
            or db.scalar(select(Tenant).where(Tenant.slug == "admmendes-brasil"))
        )
        if tenant is None:
            tenant = Tenant(name="Adimax", slug="adimax", country="BR")
            db.add(tenant)
            db.flush()
            logger.info("Tenant Adimax criado.")

        branch = db.scalar(select(Branch).where(Branch.country == "PT"))
        if branch is not None:
            branch.name = "Salto"
            branch.country, branch.locale = "BR", "pt-BR"
            logger.info("Filial Portugal migrada para Brasil.")
        else:
            branch = db.scalar(select(Branch).where(Branch.name == "Salto"))
        if branch is None:
            branch = Branch(
                name="Salto", country="BR", locale="pt-BR", tenant_id=tenant.id,
            )
            db.add(branch)
            db.flush()
            logger.info("Filial Brasil criada.")
        else:
            branch.active = True
            if branch.tenant_id is None:
                branch.tenant_id = tenant.id

        default_financial_categories = {
            "payable": (
                ("combustivel", "Combustível"), ("manutencao", "Manutenção"),
                ("limpeza", "Limpeza"),
                ("diaria_motorista", "Diária de motorista"), ("diaria_ajudante", "Diária de ajudante"),
                ("frete_transportadora", "Frete de transportadora"), ("diarias_pessoal", "Diárias e pessoal"),
                ("impostos_taxas", "Impostos e taxas"), ("seguros", "Seguros"),
                ("compras_estoque", "Compras e estoque"), ("servicos", "Serviços"),
                ("outros", "Outras despesas"),
            ),
            "receivable": (
                ("frete", "Fretes"), ("servicos", "Serviços"),
                ("reembolso", "Reembolsos"), ("desconto_motorista", "Desconto de motorista"), ("outras_receitas", "Outras receitas"),
                ("outros", "Outras receitas"),
            ),
        }
        for kind, categories in default_financial_categories.items():
            for code, name in categories:
                existing = db.scalar(select(FinancialCategory).where(
                    FinancialCategory.tenant_id == tenant.id,
                    FinancialCategory.kind == kind,
                    FinancialCategory.code == code,
                ))
                if existing is None:
                    db.add(FinancialCategory(tenant_id=tenant.id, kind=kind, code=code, name=name, active=True, system=True))

        db.flush()
        # Preserva categorias livres usadas antes deste cadastro estruturado.
        legacy_categories = db.execute(
            select(FinancialAccount.kind, FinancialAccount.category)
            .join(Branch, Branch.id == FinancialAccount.branch_id)
            .where(Branch.tenant_id == tenant.id)
            .distinct()
        ).all()
        for kind, code in legacy_categories:
            if not code or kind not in {"payable", "receivable"}: continue
            existing = db.scalar(select(FinancialCategory).where(
                FinancialCategory.tenant_id == tenant.id,
                FinancialCategory.kind == kind,
                FinancialCategory.code == code,
            ))
            if existing is None:
                db.add(FinancialCategory(
                    tenant_id=tenant.id, kind=kind, code=code,
                    name=code.replace("_", " ").strip().title(), active=True, system=False,
                ))

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
            elif admin.branch_id is not None and db.get(Branch, admin.branch_id) is None:
                admin.branch_id = branch.id
                admin.tenant_id = tenant.id

        db.flush()
        db.execute(
            text(
                "UPDATE branches SET tenant_id = :tid WHERE tenant_id IS NULL"
            ),
            {"tid": tenant.id},
        )
        for table in ("users", "drivers", "vehicles", "routes", "expenses", "revenues"):
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

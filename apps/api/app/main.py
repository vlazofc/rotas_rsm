"""Rotas Brasil RSM — API FastAPI (API-first, multilíngue, segura)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from redis import Redis

from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.modules.audit.router import router as audit_router
from app.modules.accounting.router import router as accounting_router
from app.modules.auth.router import router as auth_router
from app.modules.branches.router import router as branches_router
from app.modules.branding.router import router as branding_router
from app.modules.carriers.router import router as carriers_router
from app.modules.calculation_memory.router import router as calculation_memory_router
from app.modules.customers.router import router as customers_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.drivers.router import router as drivers_router
from app.modules.failure_reasons.router import router as failure_reasons_router
from app.modules.expenses.router import router as expenses_router
from app.modules.executive_ai.router import router as executive_ai_router
from app.modules.fleet_maintenance.router import router as fleet_maintenance_router
from app.modules.gallery.router import router as gallery_router
from app.modules.integrations.router import router as integrations_router
from app.modules.erp_admin.router import router as erp_admin_router
from app.modules.notifications.router import router as notifications_router
from app.modules.operational_settings.router import router as operational_settings_router
from app.modules.tracking.router import router as tracking_router
from app.modules.reports.router import router as reports_router
from app.modules.revenues.router import router as revenues_router
from app.modules.routes.router import router as routes_router
from app.modules.routes_import.router import router as routes_import_router
from app.modules.service_providers.router import router as service_providers_router
from app.modules.sync.router import router as sync_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router
from app.modules.vehicle_checklist.router import router as vehicle_checklist_router
from app.modules.vehicles.router import router as vehicles_router
from app.modules.vehicle_types.router import router as vehicle_types_router
from app.modules.workflow.router import router as workflow_router
from app.services.bootstrap import init_db
from app.db.session import engine

def _client_ip(request: Request) -> str:
    """IP original preservado pelo Cloudflare/Caddy; fallback para conexão direta."""
    return (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        or (request.client.host if request.client else "unknown")
    )


limiter = Limiter(
    key_func=_client_ip,
    default_limits=[settings.api_rate_limit],
    storage_uri=settings.redis_url,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Iniciando %s (%s)", settings.app_name, settings.app_env)
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/ready", include_in_schema=False)
def ready():
    """Readiness: só recebe tráfego quando banco e Redis respondem."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        try:
            redis.ping()
        finally:
            redis.close()
    except Exception as exc:
        logger.error("Readiness falhou: %s", exc)
        raise HTTPException(status_code=503, detail="Dependência indisponível") from exc
    return {"status": "ready"}


prefix = settings.api_v1_prefix
for r in (
    auth_router, users_router, branches_router, drivers_router, vehicles_router,
    routes_router, dashboard_router, audit_router,
    failure_reasons_router, expenses_router, reports_router, tenants_router,
    vehicle_types_router, branding_router, sync_router, carriers_router, customers_router, revenues_router, routes_import_router,
    fleet_maintenance_router, service_providers_router, vehicle_checklist_router, gallery_router,
    erp_admin_router, notifications_router, tracking_router, integrations_router,
    operational_settings_router,
    accounting_router, suppliers_router, workflow_router,
    calculation_memory_router, executive_ai_router,
):
    app.include_router(r, prefix=prefix)

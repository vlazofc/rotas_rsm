"""Rotas Brasil RSM — API FastAPI (API-first, multilíngue, segura)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.branches.router import router as branches_router
from app.modules.branding.router import router as branding_router
from app.modules.carriers.router import router as carriers_router
from app.modules.customers.router import router as customers_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.drivers.router import router as drivers_router
from app.modules.failure_reasons.router import router as failure_reasons_router
from app.modules.expenses.router import router as expenses_router
from app.modules.manifests.router import router as manifests_router
from app.modules.reports.router import router as reports_router
from app.modules.revenues.router import router as revenues_router
from app.modules.routes.router import router as routes_router
from app.modules.routes_import.router import router as routes_import_router
from app.modules.sync.router import router as sync_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router
from app.modules.vehicles.router import router as vehicles_router
from app.modules.vehicle_types.router import router as vehicle_types_router
from app.services.bootstrap import init_db

limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"])


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


prefix = settings.api_v1_prefix
for r in (
    auth_router, users_router, branches_router, drivers_router, vehicles_router,
    routes_router, manifests_router, dashboard_router, audit_router,
    failure_reasons_router, expenses_router, reports_router, tenants_router,
    vehicle_types_router, branding_router, sync_router, carriers_router, customers_router, revenues_router, routes_import_router,
):
    app.include_router(r, prefix=prefix)

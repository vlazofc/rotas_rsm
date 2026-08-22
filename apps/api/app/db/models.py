"""Modelos ORM — banco Rotas Brasil RSM (PostgreSQL + PostGIS)."""
from __future__ import annotations

from datetime import datetime, date, time

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric,
    String, Text, Time, UniqueConstraint, event, func, select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Tenant(Base, TimestampMixin):
    """Empresa cliente da plataforma SaaS (ex.: Adeste, outros clientes da Admmendes)."""
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    country: Mapped[str] = mapped_column(String(2), default="BR")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Serviços que podem ser ligados/desligados por cliente.
    feature_ocr: Mapped[bool] = mapped_column(Boolean, default=True)
    feature_sharepoint_sync: Mapped[bool] = mapped_column(Boolean, default=False)
    feature_financeiro: Mapped[bool] = mapped_column(Boolean, default=True)
    feature_rastreamento: Mapped[bool] = mapped_column(Boolean, default=True)
    feature_route_optimization: Mapped[bool] = mapped_column(Boolean, default=True)
    feature_km_calculation: Mapped[bool] = mapped_column(Boolean, default=True)
    # Conta SaaS — plano, mensalidade e controle interno de vencimento.
    billing_plan: Mapped[str | None] = mapped_column(String(60), nullable=True)
    billing_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    billing_due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)  # dia do mês (1-28)
    billing_last_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    branches: Mapped[list[Branch]] = relationship(back_populates="tenant")


class Branch(Base, TimestampMixin):
    __tablename__ = "branches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2), default="BR")
    locale: Mapped[str] = mapped_column(String(5), default="pt-BR")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped[Tenant | None] = relationship(back_populates="branches")
    users: Mapped[list[User]] = relationship(back_populates="branch")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Perfil RBAC (ver core.permissions.Role)
    role: Mapped[str] = mapped_column(String(40), default="motorista")
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entra_oid: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    branch: Mapped[Branch | None] = relationship(back_populates="users")


class RoleProfile(Base, TimestampMixin):
    """Configuração dos perfis usados na criação e manutenção de usuários."""
    __tablename__ = "role_profiles"
    value: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    system: Mapped[bool] = mapped_column(Boolean, default=False)


class Carrier(Base, TimestampMixin):
    """Transportadora — fornecedor de motoristas/veículos de um cliente."""
    __tablename__ = "carriers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    document: Mapped[str | None] = mapped_column(String(40), nullable=True)  # CNPJ
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base, TimestampMixin):
    """Cliente final atendido pelo tenant (não confundir com o cliente SaaS)."""
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "document", name="uq_customer_tenant_document"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), index=True)
    document: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Driver(Base, TimestampMixin):
    __tablename__ = "drivers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    document: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(160), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    expenses: Mapped[list["Expense"]] = relationship(back_populates="driver")


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    plate: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vehicle_type_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_types.id"), nullable=True)
    temperature_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Route(Base, TimestampMixin):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    codigo_ut: Mapped[str] = mapped_column(String(40), index=True)
    route_date: Mapped[date] = mapped_column(Date)
    origin_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    origin_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    # planejada | em_carregamento | liberada | em_rota | finalizada | cancelada
    status: Mapped[str] = mapped_column(String(30), default="planejada", index=True)
    planned_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    toll_outbound: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    toll_return: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    km_total_informed: Mapped[float | None] = mapped_column(Float, nullable=True)
    km_outbound_informed: Mapped[float | None] = mapped_column(Float, nullable=True)
    km_return_informed: Mapped[float | None] = mapped_column(Float, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Campos Fieldeas
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | automatico | fieldeas
    fieldeas_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fieldeas_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Campos importados da Torre de Controle (planilha)
    vehicle_requested: Mapped[str | None] = mapped_column(String(40), nullable=True)  # SOLICITADO
    vehicle_sent: Mapped[str | None] = mapped_column(String(40), nullable=True)  # ENVIADO
    helper_assigned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # AJUDANTE
    tracked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # RASTREADA
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # excluída da visão do tenant
    km_source: Mapped[str] = mapped_column(String(20), default="informado")  # informado | calculado
    raw_import_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    stops: Mapped[list[RouteStop]] = relationship(back_populates="route", cascade="all, delete-orphan")
    events: Mapped[list[RouteEvent]] = relationship(back_populates="route", cascade="all, delete-orphan")
    tolls: Mapped[list["RouteToll"]] = relationship(back_populates="route", cascade="all, delete-orphan")
    dock_session: Mapped[DockSession | None] = relationship(
        back_populates="route", uselist=False, cascade="all, delete-orphan"
    )


class RouteToll(Base):
    """Lançamento individual de pedágio (ida ou volta) informado durante a rota."""
    __tablename__ = "route_tolls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # ida | volta
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    route: Mapped[Route] = relationship(back_populates="tolls")


class RouteStop(Base, TimestampMixin):
    __tablename__ = "route_stops"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    customer_name: Mapped[str] = mapped_column(String(160))
    customer_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    temperature: Mapped[str | None] = mapped_column(String(40), nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    pallets: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # pendente | em_rota | entregue | falha | devolvido
    status: Mapped[str] = mapped_column(String(30), default="pendente")
    failure_reason_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_failure_reasons.id"), nullable=True
    )
    checkin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    proof_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    return_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # total | parcial
    returned_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    warehouse_return_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    # Campos Fieldeas
    fieldeas_internal_code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    stop_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # carga | descarga
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    province: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Campos importados da Torre de Controle (planilha)
    client_name: Mapped[str | None] = mapped_column(String(160), nullable=True)  # CLIENTE (cobrança)
    invoicing_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # FATURAMENTO
    invoice_number: Mapped[str | None] = mapped_column(String(40), nullable=True)  # NOTA FISCAL
    remessa_code: Mapped[str | None] = mapped_column(String(40), nullable=True)  # REMESSA
    delivery_type: Mapped[str | None] = mapped_column(String(40), nullable=True)  # TIPO DE ENTREGA
    invoice_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # VALOR NF
    qty_saco: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty_bombona: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty_balde: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty_tambor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty_ibc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volumes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_protocol: Mapped[str | None] = mapped_column(String(60), nullable=True)  # PROTOCOLO
    raw_import_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    route: Mapped[Route] = relationship(back_populates="stops")
    proof_attachment: Mapped["Attachment | None"] = relationship(
        foreign_keys=[proof_attachment_id],
    )
    warehouse_return_attachment: Mapped["Attachment | None"] = relationship(
        foreign_keys=[warehouse_return_attachment_id],
    )
    operations: Mapped[list["RouteStopOperation"]] = relationship(
        back_populates="stop", cascade="all, delete-orphan"
    )


class RouteStopOperation(Base, TimestampMixin):
    """Operações dentro de cada parada Fieldeas (pedidos/volumes)."""
    __tablename__ = "route_stop_operations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_id: Mapped[int] = mapped_column(ForeignKey("route_stops.id"), index=True)
    fieldeas_code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    pallets_provided: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_provided: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)

    stop: Mapped[RouteStop] = relationship(back_populates="operations")


class DeliveryFailureReason(Base, TimestampMixin):
    """Motivos de falha de entrega (gerenciáveis na Configuração)."""
    __tablename__ = "delivery_failure_reasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160))
    label_pt_br: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class VehicleType(Base, TimestampMixin):
    """Tipologias de veículo (gerenciáveis na Configuração)."""
    __tablename__ = "vehicle_types"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160))
    label_pt_br: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DockSession(Base, TimestampMixin):
    __tablename__ = "dock_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), unique=True)
    arrival_cd_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dock_entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loading_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loading_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    departure_cd_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waiting_before_dock_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loading_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waiting_release_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cd_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    route: Mapped[Route] = relationship(back_populates="dock_session")


class RouteEvent(Base):
    __tablename__ = "route_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    stop_id: Mapped[int | None] = mapped_column(ForeignKey("route_stops.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="web")  # web | app | system
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    route: Mapped[Route] = relationship(back_populates="events")


class Manifest(Base, TimestampMixin):
    __tablename__ = "manifests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255))  # caminho no MinIO
    # RECEBIDO | PROCESSANDO_OCR | AGUARDANDO_CONFERENCIA | CONFERIDO | ROTA_GERADA | ERRO_OCR | CANCELADO
    status: Mapped[str] = mapped_column(String(30), default="RECEBIDO", index=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    ocr_result: Mapped[OcrResult | None] = relationship(
        back_populates="manifest", uselist=False, cascade="all, delete-orphan"
    )


class OcrResult(Base, TimestampMixin):
    __tablename__ = "ocr_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manifest_id: Mapped[int] = mapped_column(ForeignKey("manifests.id"), unique=True)
    engine: Mapped[str] = mapped_column(String(20))  # paddle | tesseract
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON estruturado extraído (campos + nível de confiança por campo)
    extracted_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True)

    manifest: Mapped[Manifest] = relationship(back_populates="ocr_result")


class Checkin(Base):
    __tablename__ = "checkins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_id: Mapped[int] = mapped_column(ForeignKey("route_stops.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    checkin_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeliveryProof(Base):
    __tablename__ = "delivery_proofs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_id: Mapped[int] = mapped_column(ForeignKey("route_stops.id"), index=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachments.id"))
    signature_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Toll(Base):
    __tablename__ = "tolls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # ida | volta
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OdometerReading(Base):
    __tablename__ = "odometer_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # inicial | final
    value_km: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket: Mapped[str] = mapped_column(String(60))
    storage_key: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrandingSettings(Base, TimestampMixin):
    """Personalização visual por cliente (tenant_id NULL = padrão da plataforma):
    nome, cores, logo e fundo do login."""
    __tablename__ = "branding_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True, unique=True)
    app_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    app_subtitle: Mapped[str | None] = mapped_column(String(160), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    enabled_locales: Mapped[str | None] = mapped_column(String(60), nullable=True)
    topbar_extends_sidebar: Mapped[bool] = mapped_column(Boolean, default=True)
    logo_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    logo_rail_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    background_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    favicon_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)

    logo_attachment: Mapped[Attachment | None] = relationship(foreign_keys=[logo_attachment_id])
    logo_rail_attachment: Mapped[Attachment | None] = relationship(foreign_keys=[logo_rail_attachment_id])
    background_attachment: Mapped[Attachment | None] = relationship(foreign_keys=[background_attachment_id])
    favicon_attachment: Mapped[Attachment | None] = relationship(foreign_keys=[favicon_attachment_id])


class Expense(Base, TimestampMixin):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True, index=True)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(String(30), index=True)
    amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nulo apenas para despesas importadas em lote (sem comprovante digitalizado).
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    odometer_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    odometer_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import

    driver: Mapped[Driver] = relationship(back_populates="expenses")
    vehicle: Mapped[Vehicle | None] = relationship()
    attachment: Mapped[Attachment | None] = relationship(foreign_keys=[attachment_id])
    odometer_attachment: Mapped[Attachment | None] = relationship(foreign_keys=[odometer_attachment_id])


class Revenue(Base, TimestampMixin):
    """Receita lançada por rota (ex.: valor faturado ao cliente) — contraparte do Expense."""
    __tablename__ = "revenues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    revenue_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import

    route: Mapped["Route | None"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), default="app")  # app | email | whatsapp
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Preenchimento automático de tenant_id (multiempresa) ---------------------
# Mantém tenant_id sincronizado com a filial (ou usuário) sem exigir que cada
# módulo informe o tenant explicitamente — herda de Branch.tenant_id.

def _fill_tenant_from_branch(mapper, connection, target) -> None:
    if target.tenant_id is None and target.branch_id is not None:
        row = connection.execute(
            select(Branch.__table__.c.tenant_id).where(Branch.__table__.c.id == target.branch_id)
        ).first()
        if row:
            target.tenant_id = row[0]


def _fill_tenant_from_user(mapper, connection, target) -> None:
    if target.tenant_id is None and target.user_id is not None:
        row = connection.execute(
            select(User.__table__.c.tenant_id).where(User.__table__.c.id == target.user_id)
        ).first()
        if row:
            target.tenant_id = row[0]


for _model in (User, Driver, Vehicle, Route, Manifest, Expense, Revenue):
    event.listen(_model, "before_insert", _fill_tenant_from_branch)

for _model in (AuditLog, Notification):
    event.listen(_model, "before_insert", _fill_tenant_from_user)

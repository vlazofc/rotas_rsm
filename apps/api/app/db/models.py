"""Modelos ORM — banco OPTISYS (PostgreSQL + PostGIS)."""
from __future__ import annotations

from datetime import datetime, date, time

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric,
    String, Text, Time, UniqueConstraint, event, func, select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.core.encrypted_types import EncryptedText


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OperationalSettings(Base, TimestampMixin):
    """Regras operacionais globais configuráveis pela administração."""
    __tablename__ = "operational_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    require_manual_justification: Mapped[bool] = mapped_column(Boolean, default=True)
    require_checkin_before_delivery: Mapped[bool] = mapped_column(Boolean, default=True)
    require_delivery_proof: Mapped[bool] = mapped_column(Boolean, default=True)
    require_failure_proof: Mapped[bool] = mapped_column(Boolean, default=True)
    require_warehouse_return_proof: Mapped[bool] = mapped_column(Boolean, default=True)
    require_failure_reason: Mapped[bool] = mapped_column(Boolean, default=True)
    require_returned_quantity: Mapped[bool] = mapped_column(Boolean, default=True)
    routing_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    alert_due_days: Mapped[int] = mapped_column(Integer, default=3)
    alert_document_days: Mapped[int] = mapped_column(Integer, default=30)
    tire_warning_mm: Mapped[float] = mapped_column(Float, default=3.0)
    tire_critical_mm: Mapped[float] = mapped_column(Float, default=1.6)


class Tenant(Base, TimestampMixin):
    """Empresa cliente da plataforma SaaS (ex.: Adeste, outros clientes da Admmendes)."""
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    country: Mapped[str] = mapped_column(String(2), default="BR")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Serviços que podem ser ligados/desligados por cliente.
    feature_sharepoint_sync: Mapped[bool] = mapped_column(Boolean, default=False)
    feature_financeiro: Mapped[bool] = mapped_column(Boolean, default=True)
    feature_rastreamento: Mapped[bool] = mapped_column(Boolean, default=True)
    feature_route_optimization: Mapped[bool] = mapped_column(Boolean, default=True)
    feature_km_calculation: Mapped[bool] = mapped_column(Boolean, default=True)
    help_assistant_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_carrier_masters: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    # Conta SaaS — plano, mensalidade e controle interno de vencimento.
    billing_plan: Mapped[str | None] = mapped_column(String(60), nullable=True)
    billing_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    billing_due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)  # dia do mês (1-28)
    billing_last_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    document: Mapped[str | None] = mapped_column(EncryptedText("tenants.document"), nullable=True, index=True)
    state_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedText("tenants.phone"), nullable=True)
    email: Mapped[str | None] = mapped_column(EncryptedText("tenants.email"), nullable=True)
    antt_number: Mapped[str | None] = mapped_column(EncryptedText("tenants.antt_number"), nullable=True, index=True)
    antt_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    partners: Mapped[str | None] = mapped_column(Text, nullable=True)

    branches: Mapped[list[Branch]] = relationship(back_populates="tenant")
    users: Mapped[list[User]] = relationship(back_populates="tenant")


class Branch(Base, TimestampMixin):
    __tablename__ = "branches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2), default="BR")
    locale: Mapped[str] = mapped_column(String(5), default="pt-BR")
    default_origin_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped[Tenant | None] = relationship(back_populates="branches")
    users: Mapped[list[User]] = relationship(back_populates="branch", foreign_keys="User.branch_id")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    email: Mapped[str] = mapped_column(EncryptedText("users.email"), unique=True, index=True)
    login: Mapped[str | None] = mapped_column(EncryptedText("users.login"), unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Perfil RBAC (ver core.permissions.Role)
    role: Mapped[str] = mapped_column(String(40), default="motorista")
    department: Mapped[str | None] = mapped_column(String(80), nullable=True)
    subgroup: Mapped[str | None] = mapped_column(String(80), nullable=True)
    permissions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    navigation_layout: Mapped[str] = mapped_column(String(20), default="sidebar", server_default="sidebar")
    acting_branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    acting_carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True)

    tenant: Mapped[Tenant | None] = relationship(back_populates="users")
    branch: Mapped[Branch | None] = relationship(back_populates="users", foreign_keys=[branch_id])


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
    """Arrendatário ou beneficiário responsável por veículos e motoristas."""
    __tablename__ = "carriers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    document: Mapped[str | None] = mapped_column(String(40), nullable=True)  # CNPJ
    person_type: Mapped[str] = mapped_column(String(20), default="pessoa_fisica")
    kind: Mapped[str] = mapped_column(String(20), default="arrendatario")  # arrendatario | beneficiario
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_agency: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bank_account_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pix_key_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pix_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    antt_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    antt_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_masters: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CarrierVehicleLink(Base, TimestampMixin):
    """Autoriza um arrendatário/beneficiário a operar e receber por uma placa."""
    __tablename__ = "carrier_vehicle_links"
    __table_args__ = (UniqueConstraint("carrier_id", "vehicle_id", name="uq_carrier_vehicle_link"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id", ondelete="CASCADE"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True, unique=True)
    antt_authorized: Mapped[bool] = mapped_column(Boolean, default=True)
    freight_beneficiary: Mapped[bool] = mapped_column(Boolean, default=False)


class CarrierBranch(Base, TimestampMixin):
    """Filiais Adimax que autorizaram uma transportadora a operar."""
    __tablename__ = "carrier_branches"
    __table_args__ = (UniqueConstraint("carrier_id", "branch_id", name="uq_carrier_branch"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class CarrierMaster(Base, TimestampMixin):
    """Masters pertencem à transportadora, não a uma filial (máximo 3 ativos)."""
    __tablename__ = "carrier_masters"
    __table_args__ = (
        UniqueConstraint("carrier_id", "user_id", name="uq_carrier_master"),
        UniqueConstraint("user_id", name="uq_carrier_master_user"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_first_master: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class CarrierUser(Base, TimestampMixin):
    """Vínculo de acesso de qualquer usuário operacional à transportadora."""
    __tablename__ = "carrier_users"
    __table_args__ = (
        UniqueConstraint("carrier_id", "user_id", name="uq_carrier_user"),
        UniqueConstraint("user_id", name="uq_carrier_user_account"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class BranchApprovalPolicy(Base, TimestampMixin):
    """Exigências graduais de aprovação configuradas por filial."""
    __tablename__ = "branch_approval_policies"
    __table_args__ = (UniqueConstraint("branch_id", name="uq_branch_approval_policy"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    require_driver_approval: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    require_vehicle_approval: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class UserBranchAccess(Base, TimestampMixin):
    """Escopo explícito de filial para colaboradores Adimax e usuários da transportadora."""
    __tablename__ = "user_branch_access"
    __table_args__ = (UniqueConstraint("user_id", "branch_id", name="uq_user_branch_access"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)


class UserAccessPolicy(Base, TimestampMixin):
    __tablename__ = "user_access_policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    all_branches_including_future: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Customer(Base, TimestampMixin):
    """Cliente final atendido pelo tenant (não confundir com o cliente SaaS)."""
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "document", name="uq_customer_tenant_document"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), index=True)
    customer_type: Mapped[str] = mapped_column(String(2), default="PJ", index=True)
    trade_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    document: Mapped[str | None] = mapped_column(String(40), nullable=True)
    state_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    municipal_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    identity_document: Mapped[str | None] = mapped_column(String(40), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    main_activity: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    financial_contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    financial_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    credit_limit: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    payment_term_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    commercial_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RouteOrigin(Base, TimestampMixin):
    """Centro de distribuição/origem informado na coluna V da Gestão Adimax."""
    __tablename__ = "route_origins"
    __table_args__ = (UniqueConstraint("tenant_id", "address", name="uq_route_origin_tenant_address"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DeliveryDestination(Base, TimestampMixin):
    """Endereço de entrega reutilizável de um cliente final."""
    __tablename__ = "delivery_destinations"
    __table_args__ = (UniqueConstraint("customer_id", "address", "number", "district", "city", name="uq_customer_destination"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    address: Mapped[str] = mapped_column(String(255))
    number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Driver(Base, TimestampMixin):
    __tablename__ = "drivers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    document: Mapped[str | None] = mapped_column(EncryptedText("drivers.document"), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedText("drivers.phone"), nullable=True)
    email: Mapped[str | None] = mapped_column(EncryptedText("drivers.email"), nullable=True)
    address: Mapped[str | None] = mapped_column(EncryptedText("drivers.address"), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(EncryptedText("drivers.postal_code"), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cnh_number: Mapped[str | None] = mapped_column(EncryptedText("drivers.cnh_number"), nullable=True, index=True)
    cnh_category: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cnh_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    antt_number: Mapped[str | None] = mapped_column(EncryptedText("drivers.antt_number"), nullable=True, index=True)
    antt_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    registration_updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    cnh_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(160), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(20), default="proprio", index=True)
    daily_rate: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    expenses: Mapped[list["Expense"]] = relationship(back_populates="driver")
    document_attachment: Mapped["Attachment | None"] = relationship(foreign_keys=[document_attachment_id])
    cnh_attachment: Mapped["Attachment | None"] = relationship(foreign_keys=[cnh_attachment_id])


class DriverBranch(Base):
    __tablename__ = "driver_branches"
    __table_args__ = (UniqueConstraint("driver_id", "branch_id", name="uq_driver_branch"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    approval_status: Mapped[str] = mapped_column(String(20), default="approved", server_default="approved")
    approval_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VehicleBranch(Base, TimestampMixin):
    """Disponibilidade e aprovação do veículo em cada filial autorizada."""
    __tablename__ = "vehicle_branches"
    __table_args__ = (UniqueConstraint("vehicle_id", "branch_id", name="uq_vehicle_branch"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    approval_status: Mapped[str] = mapped_column(String(20), default="approved", server_default="approved")
    approval_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DriverSettings(Base, TimestampMixin):
    __tablename__ = "driver_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True, index=True)
    cnh_alert_days: Mapped[int] = mapped_column(Integer, default=30)
    antt_alert_days: Mapped[int] = mapped_column(Integer, default=30)
    registration_renewal_months: Mapped[int] = mapped_column(Integer, default=12)
    registration_alert_days: Mapped[int] = mapped_column(Integer, default=30)
    statement_release_day: Mapped[int] = mapped_column(Integer, default=1)


class VehicleOwner(Base, TimestampMixin):
    __tablename__ = "vehicle_owners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    document: Mapped[str] = mapped_column(EncryptedText("vehicle_owners.document"), index=True)
    person_type: Mapped[str] = mapped_column(String(20), default="pessoa_fisica")
    phone: Mapped[str | None] = mapped_column(EncryptedText("vehicle_owners.phone"), nullable=True)
    email: Mapped[str | None] = mapped_column(EncryptedText("vehicle_owners.email"), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_agency: Mapped[str | None] = mapped_column(EncryptedText("vehicle_owners.bank_agency"), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(EncryptedText("vehicle_owners.bank_account"), nullable=True)
    bank_account_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pix_key_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pix_key: Mapped[str | None] = mapped_column(EncryptedText("vehicle_owners.pix_key"), nullable=True)
    is_tenant_company: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    plate: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vehicle_type_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_types.id"), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_owners.id"), nullable=True, index=True)
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True, index=True)
    freight_receiver_type: Mapped[str] = mapped_column(String(20), default="proprietario", index=True)
    renavam: Mapped[str | None] = mapped_column(EncryptedText("vehicles.renavam"), nullable=True, index=True)
    chassis: Mapped[str | None] = mapped_column(EncryptedText("vehicles.chassis"), nullable=True)
    registry_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacture_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fuel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    crlv_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    axles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rear_dual_wheels: Mapped[bool] = mapped_column(Boolean, default=True)
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    crlv_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    temperature_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    ownership_type: Mapped[str] = mapped_column(String(20), default="proprio", index=True)
    antt_number: Mapped[str | None] = mapped_column(EncryptedText("vehicles.antt_number"), nullable=True, index=True)
    antt_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner: Mapped[VehicleOwner | None] = relationship()
    crlv_attachment: Mapped["Attachment | None"] = relationship(foreign_keys=[crlv_attachment_id])


class VehicleChangeRequest(Base, TimestampMixin):
    __tablename__ = "vehicle_change_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    requested_renavam: Mapped[str | None] = mapped_column(EncryptedText("vehicle_change_requests.requested_renavam"), nullable=True)
    requested_vehicle_type_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_types.id"), nullable=True)
    requested_axles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_renavam: Mapped[str | None] = mapped_column(EncryptedText("vehicle_change_requests.previous_renavam"), nullable=True)
    previous_vehicle_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_axles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Tire(Base, TimestampMixin):
    """Pneu — rastreado por número de fogo, com histórico de sulco em TireInspection."""
    __tablename__ = "tires"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    fire_number: Mapped[str] = mapped_column(String(40), index=True)  # numeração de fogo/série
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    position: Mapped[str | None] = mapped_column(String(40), nullable=True)  # ex.: dianteiro_esq, traseiro_dir_ext
    # novo | em_uso | recapado | descartado
    status: Mapped[str] = mapped_column(String(20), default="novo", index=True)
    tread_depth_mm: Mapped[float | None] = mapped_column(Float, nullable=True)  # última medição de sulco
    install_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    install_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    recap_count: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    vehicle: Mapped[Vehicle | None] = relationship()
    inspections: Mapped[list["TireInspection"]] = relationship(back_populates="tire", cascade="all, delete-orphan")


class TireInspection(Base):
    """Medição periódica de sulco/estado de um pneu — histórico para cálculo de CPK."""
    __tablename__ = "tire_inspections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tire_id: Mapped[int] = mapped_column(ForeignKey("tires.id"), index=True)
    inspected_at: Mapped[date] = mapped_column(Date)
    odometer_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    tread_depth_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    checklist_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_checklists.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tire: Mapped[Tire] = relationship(back_populates="inspections")


class ServiceProvider(Base, TimestampMixin):
    """Prestador de serviço autorizado (oficina, borracharia, guincho etc.) —
    distinto de Carrier (transportadora/fornecedor de motorista e veículo).
    Lat/lng preenchidos no cadastro (manual em v1) para permitir busca por raio."""
    __tablename__ = "service_providers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    document: Mapped[str | None] = mapped_column(String(40), nullable=True)  # CNPJ
    # oficina_mecanica | borracharia | eletrica | guincho | posto_combustivel | lavagem | outros
    category: Mapped[str] = mapped_column(String(30), default="outros", index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    authorized: Mapped[bool] = mapped_column(Boolean, default=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MaintenancePlan(Base, TimestampMixin):
    """Plano de manutenção preventiva — dispara ordens de serviço por km ou tempo."""
    __tablename__ = "maintenance_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    service_name: Mapped[str] = mapped_column(String(120))  # ex.: "Troca de óleo", "Revisão de freios"
    interval_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_done_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_done_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    vehicle: Mapped[Vehicle] = relationship()


class MaintenanceOrder(Base, TimestampMixin):
    """Ordem de serviço — preventiva (ligada a um MaintenancePlan) ou corretiva (avulsa)."""
    __tablename__ = "maintenance_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("maintenance_plans.id"), nullable=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("service_providers.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="corretiva")  # preventiva | corretiva
    # aberta | em_andamento | concluida | cancelada
    status: Mapped[str] = mapped_column(String(20), default="aberta", index=True)
    description: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[date] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    odometer_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    # Orçamento do prestador (Fluxo D — homologação): anexado antes da aprovação,
    # separado do comprovante/nota final (attachment_id).
    budget_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    # pendente | aprovado | rejeitado — só relevante quando há orçamento anexado.
    approval_status: Mapped[str] = mapped_column(String(20), default="pendente")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    vehicle: Mapped[Vehicle] = relationship()
    plan: Mapped[MaintenancePlan | None] = relationship()
    provider: Mapped[ServiceProvider | None] = relationship()
    attachment: Mapped["Attachment | None"] = relationship(foreign_keys=[attachment_id])
    budget_attachment: Mapped["Attachment | None"] = relationship(foreign_keys=[budget_attachment_id])
    approved_by_user: Mapped["User | None"] = relationship(foreign_keys=[approved_by])
    expense: Mapped["Expense | None"] = relationship(foreign_keys="Expense.maintenance_order_id", uselist=False)


class ChecklistTemplateItem(Base, TimestampMixin):
    """Catálogo configurável de itens de checklist (Config → Frota)."""
    __tablename__ = "checklist_template_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160))
    label_pt_br: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # freios | pneus | eletrica | documentacao | fluidos | seguranca | outros
    category: Mapped[str] = mapped_column(String(30), default="outros")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class VehicleChecklist(Base, TimestampMixin):
    """Execução de um checklist de veículo (saída, retorno ou periódico)."""
    __tablename__ = "vehicle_checklists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="periodica")  # saida | retorno | periodica
    performed_at: Mapped[date] = mapped_column(Date)
    # aprovado | aprovado_com_ressalvas | reprovado
    overall_status: Mapped[str] = mapped_column(String(30), default="aprovado")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    vehicle: Mapped[Vehicle] = relationship()
    driver: Mapped["Driver | None"] = relationship()
    items: Mapped[list["VehicleChecklistItem"]] = relationship(back_populates="checklist", cascade="all, delete-orphan")


class VehicleChecklistItem(Base):
    """Resposta a um item do template dentro de um VehicleChecklist."""
    __tablename__ = "vehicle_checklist_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    checklist_id: Mapped[int] = mapped_column(ForeignKey("vehicle_checklists.id"), index=True)
    template_item_id: Mapped[int] = mapped_column(ForeignKey("checklist_template_items.id"))
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | nao_ok | nao_aplicavel
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)

    checklist: Mapped[VehicleChecklist] = relationship(back_populates="items")
    template_item: Mapped[ChecklistTemplateItem] = relationship()
    photo_attachment: Mapped["Attachment | None"] = relationship(foreign_keys=[photo_attachment_id])


class Route(Base, TimestampMixin):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True, index=True)
    carrier_assignment_status: Mapped[str] = mapped_column(String(30), default="pending_carrier", server_default="pending_carrier", index=True)
    carrier_assignment_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    codigo_ut: Mapped[str] = mapped_column(String(40), index=True)
    route_date: Mapped[date] = mapped_column(Date)
    origin_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    origin_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    origin_id: Mapped[int | None] = mapped_column(ForeignKey("route_origins.id"), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    driver_payment_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    driver_payment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # planejada | em_carregamento | liberada | em_rota | finalizada | cancelada
    status: Mapped[str] = mapped_column(String(30), default="planejada", index=True)
    planned_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    # Resultado da roteirização automática (Maestro/GraphHopper).
    routing_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | optimized | error
    routing_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    routing_optimized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    routing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    routing_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    spreadsheet_route: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    driver_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    vehicle_profile_sent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    vehicle_profile_requested: Mapped[str | None] = mapped_column(String(40), nullable=True)
    typology_view: Mapped[str | None] = mapped_column(String(60), nullable=True)
    overnight: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    overnight_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    administrative_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    helper_requested: Mapped[str | None] = mapped_column(String(40), nullable=True)
    helper_sent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    load_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cte_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    empty_truck_photo_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    loaded_return_photo_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)

    stops: Mapped[list[RouteStop]] = relationship(back_populates="route", cascade="all, delete-orphan")
    empty_truck_photo: Mapped["Attachment | None"] = relationship(foreign_keys=[empty_truck_photo_attachment_id])
    loaded_return_photo: Mapped["Attachment | None"] = relationship(foreign_keys=[loaded_return_photo_attachment_id])
    events: Mapped[list[RouteEvent]] = relationship(back_populates="route", cascade="all, delete-orphan")
    observations: Mapped[list["RouteObservation"]] = relationship(back_populates="route", cascade="all, delete-orphan", order_by="RouteObservation.sequence")
    dock_session: Mapped[DockSession | None] = relationship(
        back_populates="route", uselist=False, cascade="all, delete-orphan"
    )


class RouteObservation(Base, TimestampMixin):
    __tablename__ = "route_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    route: Mapped["Route"] = relationship(back_populates="observations")


class RouteCarrierChange(Base):
    """Log imutável da troca da transportadora executora."""
    __tablename__ = "route_carrier_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    previous_carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True)
    new_carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id"))
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str] = mapped_column(Text)
    previous_driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    previous_vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    route_status: Mapped[str] = mapped_column(String(30))


class RouteStop(Base, TimestampMixin):
    __tablename__ = "route_stops"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    spreadsheet_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    optimized_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    destination_id: Mapped[int | None] = mapped_column(ForeignKey("delivery_destinations.id"), nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(160))
    customer_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    temperature: Mapped[str | None] = mapped_column(String(40), nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    pallets: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cte_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes_3: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class ClientActionReceipt(Base):
    """Comprovante de idempotência para ações reenviadas pelo aplicativo offline."""
    __tablename__ = "client_action_receipts"
    action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


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
    login_intro_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    login_layout: Mapped[str] = mapped_column(String(30), default="centered")
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sidebar_background_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sidebar_text_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sidebar_active_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
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
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True, index=True)
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
    maintenance_order_id: Mapped[int | None] = mapped_column(ForeignKey("maintenance_orders.id"), nullable=True, unique=True, index=True)
    approval_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recurrence: Mapped[str] = mapped_column(String(20), default="none")
    recurrence_count: Mapped[int] = mapped_column(Integer, default=1)

    driver: Mapped[Driver] = relationship(back_populates="expenses")
    vehicle: Mapped[Vehicle | None] = relationship()
    attachment: Mapped[Attachment | None] = relationship(foreign_keys=[attachment_id])
    odometer_attachment: Mapped[Attachment | None] = relationship(foreign_keys=[odometer_attachment_id])
    submitter: Mapped[User | None] = relationship(foreign_keys=[user_id])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])


class ExpenseApprovalEvent(Base):
    """Histórico imutável do fluxo de aceite financeiro."""
    __tablename__ = "expense_approval_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Revenue(Base, TimestampMixin):
    """Receita faturada para um cliente, podendo consolidar várias rotas."""
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
    billed_customer_name: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)

    route: Mapped["Route | None"] = relationship()
    creator: Mapped["User | None"] = relationship(foreign_keys=[user_id])
    financial_account: Mapped["FinancialAccount | None"] = relationship(foreign_keys="FinancialAccount.revenue_id", uselist=False)


class RevenueRouteLink(Base):
    """Rotas reunidas em uma mesma receita/nota de serviço."""
    __tablename__ = "revenue_route_links"
    __table_args__ = (UniqueConstraint("revenue_id", "route_id", name="uq_revenue_route_link"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revenue_id: Mapped[int] = mapped_column(ForeignKey("revenues.id", ondelete="CASCADE"), index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)


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


class AlertRule(Base, TimestampMixin):
    """Preferências de alertas por usuário (in-app; preparado para push/e-mail)."""
    __tablename__ = "alert_rules"
    __table_args__ = (UniqueConstraint("user_id", "event_type", name="uq_alert_rule_user_event"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    channel_app: Mapped[bool] = mapped_column(Boolean, default=True)
    channel_push: Mapped[bool] = mapped_column(Boolean, default=False)


class AlertDismissal(Base):
    """Alerta operacional dispensado individualmente por um usuário."""
    __tablename__ = "alert_dismissals"
    __table_args__ = (UniqueConstraint("user_id", "alert_id", name="uq_alert_dismissal_user_alert"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    alert_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrackingConsent(Base, TimestampMixin):
    __tablename__ = "tracking_consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_version: Mapped[str] = mapped_column(String(20), default="1.0")


class AppPermissionConsent(Base, TimestampMixin):
    """Aceite do termo de câmera, localização e tratamento de evidências do app."""
    __tablename__ = "app_permission_consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_version: Mapped[str] = mapped_column(String(20), default="1.0")


class VehiclePosition(Base):
    __tablename__ = "vehicle_positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class TrackingIntegration(Base, TimestampMixin):
    """Configurações sensíveis de provedores de rastreamento (segredos sempre cifrados)."""
    __tablename__ = "tracking_integrations"
    __table_args__ = (UniqueConstraint("provider", name="uq_tracking_integration_provider"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), default="truckcontrol")
    base_url: Mapped[str] = mapped_column(String(255))
    login_encrypted: Mapped[str] = mapped_column(Text)
    password_encrypted: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=30)
    last_message_id: Mapped[int] = mapped_column(BigInteger, default=1)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_vehicle_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProviderVehicle(Base, TimestampMixin):
    __tablename__ = "provider_vehicles"
    __table_args__ = (UniqueConstraint("provider", "external_vehicle_id", name="uq_provider_vehicle"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    external_vehicle_id: Mapped[str] = mapped_column(String(80), index=True)
    plate: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProviderVehiclePosition(Base):
    __tablename__ = "provider_vehicle_positions"
    __table_args__ = (UniqueConstraint("provider", "external_message_id", name="uq_provider_position_message"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    external_message_id: Mapped[int] = mapped_column(BigInteger, index=True)
    external_vehicle_id: Mapped[str] = mapped_column(String(80), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    odometer_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentItem(Base, TimestampMixin):
    """Comunicados e treinamentos mantidos no ERP, substituindo conteúdo no SharePoint."""
    __tablename__ = "content_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default="comunicado")
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    attachment: Mapped[Attachment | None] = relationship()


class Part(Base, TimestampMixin):
    __tablename__ = "parts"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_part_tenant_sku"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    sku: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(160))
    unit: Mapped[str] = mapped_column(String(20), default="un")
    quantity: Mapped[float] = mapped_column(Float, default=0)
    minimum_quantity: Mapped[float] = mapped_column(Float, default=0)
    average_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # entrada | saida | ajuste
    quantity: Mapped[float] = mapped_column(Float)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RouteOccurrence(Base, TimestampMixin):
    """Relato livre feito pelo motorista durante uma rota."""
    __tablename__ = "route_occurrences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    reported_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category: Mapped[str] = mapped_column(String(40), default="outros")
    severity: Mapped[str] = mapped_column(String(20), default="media")
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="aberta", index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    treatment_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)


class OccurrenceCategory(Base, TimestampMixin):
    __tablename__ = "occurrence_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_occurrence_category_tenant_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    system: Mapped[bool] = mapped_column(Boolean, default=False)


class RouteOccurrenceEvent(Base):
    """Histórico imutável do tratamento operacional da ocorrência."""
    __tablename__ = "route_occurrence_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(ForeignKey("route_occurrences.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkflowTask(Base, TimestampMixin):
    """Ticket transversal vinculado a qualquer fluxo de negócio."""
    __tablename__ = "workflow_tasks"
    __table_args__ = (UniqueConstraint("tenant_id", "source_type", "source_id", name="uq_workflow_task_source"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    current_department: Mapped[str] = mapped_column(String(80), index=True)
    current_assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3, index=True)
    source_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class WorkflowTaskEvent(Base):
    """Trilha append-only de ações, setores e responsáveis do ticket."""
    __tablename__ = "workflow_task_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("workflow_tasks.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    from_department: Mapped[str | None] = mapped_column(String(80), nullable=True)
    to_department: Mapped[str | None] = mapped_column(String(80), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PurchaseTicket(Base, TimestampMixin):
    """Solicitação administrativa com ticket e aprovação antes da compra."""
    __tablename__ = "purchase_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    ticket: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    department: Mapped[str] = mapped_column(String(60), default="frota")
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("service_providers.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(80), default="outros")
    document: Mapped[str | None] = mapped_column(String(80), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    financial_account_id: Mapped[int | None] = mapped_column(ForeignKey("financial_accounts.id"), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(25), default="solicitada", index=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("tenant_id", "document", name="uq_supplier_tenant_document"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    legal_name: Mapped[str] = mapped_column(String(180))
    trade_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    document: Mapped[str] = mapped_column(String(40), index=True)
    state_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    municipal_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    supplier_type: Mapped[str] = mapped_column(String(20), default="product")
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pix_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchase_tickets.id"), index=True)
    description: Mapped[str] = mapped_column(String(180))
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), default=1)
    unit: Mapped[str] = mapped_column(String(20), default="un")
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2))


class FinancialAccount(Base, TimestampMixin):
    """Título financeiro previsto: conta a pagar ou a receber."""
    __tablename__ = "financial_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # payable | receivable
    description: Mapped[str] = mapped_column(String(180))
    counterparty: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(80), default="outros", index=True)
    document: Mapped[str | None] = mapped_column(String(80), nullable=True)
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="pendente", index=True)
    settled_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expense_id: Mapped[int | None] = mapped_column(ForeignKey("expenses.id"), nullable=True, unique=True, index=True)
    revenue_id: Mapped[int | None] = mapped_column(ForeignKey("revenues.id"), nullable=True, unique=True, index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), nullable=True, index=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True, index=True)
    discount_reason: Mapped[str | None] = mapped_column(String(180), nullable=True)
    payment_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    recurrence_group: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    recurrence_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurrence_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_invoice_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    service_invoice_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    service_invoice_attachment: Mapped["Attachment | None"] = relationship(foreign_keys=[service_invoice_attachment_id])


class FinancialCategory(Base, TimestampMixin):
    """Categoria selecionável para títulos a pagar ou a receber."""
    __tablename__ = "financial_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", "code", name="uq_financial_category_tenant_kind_code"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # payable | receivable
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    system: Mapped[bool] = mapped_column(Boolean, default=False)


class ExecutiveAIConversation(Base, TimestampMixin):
    __tablename__ = "executive_ai_conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ExecutiveAIMessage(Base):
    __tablename__ = "executive_ai_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("executive_ai_conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class CalculationMemory(Base):
    """Versao imutavel dos valores usados em um calculo financeiro."""
    __tablename__ = "calculation_memories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "content_hash", name="uq_calculation_memory_tenant_hash"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    calculation_type: Mapped[str] = mapped_column(String(40), default="financial_result", index=True)
    formula_version: Mapped[str] = mapped_column(String(20), default="1.0")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    inputs_json: Mapped[str] = mapped_column(Text)
    results_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class DriverStatementAdjustment(Base, TimestampMixin):
    """Crédito ou desconto explícito do extrato do motorista; nunca inferido de Expense."""
    __tablename__ = "driver_statement_adjustments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True, index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # earning | deduction
    reason: Mapped[str] = mapped_column(String(160))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    financial_account_id: Mapped[int | None] = mapped_column(ForeignKey("financial_accounts.id"), nullable=True, unique=True, index=True)
    voided: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class DriverStatementPeriod(Base, TimestampMixin):
    """Fechamento versionado submetido ao aceite do motorista."""
    __tablename__ = "driver_statement_periods"
    __table_args__ = (UniqueConstraint("driver_id", "period_start", "period_end", name="uq_driver_statement_period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    release_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30), default="released", index=True)
    snapshot_json: Mapped[str] = mapped_column(Text)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    released_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    contested_scope: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contested_item_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contest_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    contested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    signature_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    signature_document: Mapped[str | None] = mapped_column(String(40), nullable=True)
    signature_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_declaration: Mapped[str | None] = mapped_column(Text, nullable=True)
    payable_id: Mapped[int | None] = mapped_column(ForeignKey("financial_accounts.id"), nullable=True, unique=True)


class ChartAccount(Base, TimestampMixin):
    """Plano de contas hierárquico do tenant."""
    __tablename__ = "chart_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_chart_account_tenant_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("chart_accounts.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(160))
    account_type: Mapped[str] = mapped_column(String(20), index=True)  # asset|liability|equity|revenue|expense
    nature: Mapped[str] = mapped_column(String(10))  # debit|credit
    accepts_entries: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    system: Mapped[bool] = mapped_column(Boolean, default=False)


class TaxRule(Base, TimestampMixin):
    """Versão de regra tributária; alterações criam nova vigência."""
    __tablename__ = "tax_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    tax_code: Mapped[str] = mapped_column(String(40), index=True)
    applies_to: Mapped[str] = mapped_column(String(20), default="revenue")
    rate_percent: Mapped[float] = mapped_column(Numeric(8, 4))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    debit_account_code: Mapped[str] = mapped_column(String(30), default="6.1.01")
    credit_account_code: Mapped[str] = mapped_column(String(30), default="2.2.01")
    legal_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AccountingEntry(Base, TimestampMixin):
    __tablename__ = "accounting_entries"
    __table_args__ = (UniqueConstraint("source_type", "source_id", name="uq_accounting_entry_source"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    memo: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    posted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="posted", index=True)


class AccountingLine(Base):
    __tablename__ = "accounting_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("accounting_entries.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("chart_accounts.id"), index=True)
    debit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    credit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    tax_rule_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rules.id"), nullable=True)
    tax_code_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tax_rate_snapshot: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    tax_base_snapshot: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)


class AccountingPeriod(Base, TimestampMixin):
    __tablename__ = "accounting_periods"
    __table_args__ = (UniqueConstraint("tenant_id", "branch_id", "start_date", "end_date", name="uq_accounting_period_range"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    cadence: Mapped[str] = mapped_column(String(15), default="monthly")
    status: Mapped[str] = mapped_column(String(15), default="open", index=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)




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


for _model in (
    User, Driver, Vehicle, Route, Expense, Revenue, Tire, MaintenancePlan, MaintenanceOrder,
    ServiceProvider, VehicleChecklist, VehicleChangeRequest,
):
    event.listen(_model, "before_insert", _fill_tenant_from_branch)

for _model in (AuditLog, Notification, AlertRule, TrackingConsent):
    event.listen(_model, "before_insert", _fill_tenant_from_user)

for _model in (VehiclePosition, ContentItem, Part, RouteOccurrence, PurchaseTicket, FinancialAccount, DriverStatementAdjustment):
    event.listen(_model, "before_insert", _fill_tenant_from_branch)

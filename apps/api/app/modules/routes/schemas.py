from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StopIn(BaseModel):
    sequence: int = 1
    customer_name: str
    customer_address: str | None = None
    city: str | None = None
    planned_date: date | None = None
    planned_time: time | None = None
    temperature: str | None = None
    stop_type: Literal["carga", "descarga"] | None = None
    weight_kg: float | None = None
    pallets: float | None = None
    order_number: str | None = None


class StopOperationOut(BaseModel):
    id: int
    fieldeas_code: str | None = None
    order_id: str | None = None
    client_name: str | None = None
    pallets_provided: float | None = None
    weight_provided: float | None = None
    status: str | None = None

    class Config:
        from_attributes = True


class StopOut(StopIn):
    id: int
    status: str
    failure_reason_id: int | None = None
    checkin_at: datetime | None = None
    delivered_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    proof_attachment_id: int | None = None
    proof_filename: str | None = None
    proof_url: str | None = None
    return_type: Literal["total", "parcial"] | None = None
    returned_quantity: float | None = None
    warehouse_return_attachment_id: int | None = None
    warehouse_return_filename: str | None = None
    warehouse_return_url: str | None = None
    # Campos Fieldeas
    fieldeas_internal_code: str | None = None
    postal_code: str | None = None
    province: str | None = None
    operations: list[StopOperationOut] = Field(default_factory=list)
    # Campos importados da Torre de Controle (planilha)
    client_name: str | None = None
    invoicing_date: date | None = None
    invoice_number: str | None = None
    remessa_code: str | None = None
    delivery_type: str | None = None
    invoice_value: float | None = None
    qty_saco: int | None = None
    qty_bombona: int | None = None
    qty_balde: int | None = None
    qty_tambor: int | None = None
    qty_ibc: int | None = None
    volumes: int | None = None
    delivery_protocol: str | None = None

    class Config:
        from_attributes = True


class StopUpdate(BaseModel):
    sequence: int | None = None
    customer_name: str | None = None
    customer_address: str | None = None
    city: str | None = None
    planned_date: date | None = None
    planned_time: time | None = None
    temperature: str | None = None
    stop_type: Literal["carga", "descarga"] | None = None
    weight_kg: float | None = None
    pallets: float | None = None
    order_number: str | None = None


def _truncate_codigo_ut(v: str | None) -> str | None:
    return v[:40] if v else v


def _truncate_origin_name(v: str | None) -> str | None:
    return v[:160] if v else v


def _truncate_origin_address(v: str | None) -> str | None:
    return v[:255] if v else v


class RouteIn(BaseModel):
    branch_id: int
    codigo_ut: str
    route_date: date
    origin_name: str | None = None
    origin_address: str | None = None
    driver_id: int | None = None
    vehicle_id: int | None = None
    driver_payment_amount: float | None = None
    driver_payment_notes: str | None = None
    planned_departure_at: datetime | None = None
    toll_outbound: float | None = None
    toll_return: float | None = None
    km_total_informed: float | None = None
    km_outbound_informed: float | None = None
    km_return_informed: float | None = None
    stops: list[StopIn] = Field(default_factory=list)

    _v_codigo_ut = field_validator("codigo_ut")(_truncate_codigo_ut)
    _v_origin_name = field_validator("origin_name")(_truncate_origin_name)
    _v_origin_address = field_validator("origin_address")(_truncate_origin_address)


class RouteUpdate(BaseModel):
    codigo_ut: str | None = None
    route_date: date | None = None
    origin_name: str | None = None
    origin_address: str | None = None
    driver_id: int | None = None
    vehicle_id: int | None = None
    driver_payment_amount: float | None = None
    driver_payment_notes: str | None = None
    planned_departure_at: datetime | None = None
    toll_outbound: float | None = None
    toll_return: float | None = None
    km_total_informed: float | None = None
    km_outbound_informed: float | None = None
    km_return_informed: float | None = None
    vehicle_requested: str | None = None
    vehicle_sent: str | None = None
    helper_assigned: bool | None = None
    tracked: bool | None = None

    _v_codigo_ut = field_validator("codigo_ut")(_truncate_codigo_ut)
    _v_origin_name = field_validator("origin_name")(_truncate_origin_name)
    _v_origin_address = field_validator("origin_address")(_truncate_origin_address)


class RouteKmIn(BaseModel):
    km_outbound_informed: float | None = None
    km_return_informed: float | None = None


class DockOut(BaseModel):
    arrival_cd_at: datetime | None = None
    dock_entry_at: datetime | None = None
    loading_started_at: datetime | None = None
    loading_finished_at: datetime | None = None
    operator_released_at: datetime | None = None
    departure_cd_at: datetime | None = None
    waiting_before_dock_minutes: int | None = None
    loading_minutes: int | None = None
    waiting_release_minutes: int | None = None
    total_cd_minutes: int | None = None

    class Config:
        from_attributes = True


class RouteTollIn(BaseModel):
    direction: Literal["ida", "volta"]
    amount: float


class RouteTollOut(BaseModel):
    id: int
    direction: str
    amount: float
    created_at: datetime
    recorded_by: int | None = None

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    event_type: str
    event_time: datetime
    source: str
    notes: str | None = None

    class Config:
        from_attributes = True


class RouteOut(BaseModel):
    id: int
    branch_id: int
    codigo_ut: str
    route_date: date
    origin_name: str | None
    origin_address: str | None
    driver_id: int | None
    vehicle_id: int | None
    driver_payment_amount: float | None = None
    driver_payment_notes: str | None = None
    status: str
    planned_departure_at: datetime | None
    actual_departure_at: datetime | None
    toll_outbound: float | None
    toll_return: float | None
    km_total_informed: float | None
    km_outbound_informed: float | None
    km_return_informed: float | None
    closed_at: datetime | None
    # Campos Fieldeas
    source: str = "manual"
    fieldeas_description: str | None = None
    fieldeas_sync_at: datetime | None = None
    # Campos importados da Torre de Controle (planilha)
    vehicle_requested: str | None = None
    vehicle_sent: str | None = None
    helper_assigned: bool | None = None
    tracked: bool | None = None
    excluded: bool = False
    km_source: str = "informado"
    stops: list[StopOut] = Field(default_factory=list)
    dock_session: DockOut | None = None
    events: list[EventOut] = Field(default_factory=list)
    tolls: list[RouteTollOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CheckinIn(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None


class DeliverIn(BaseModel):
    success: bool = True
    failure_reason_id: int | None = None  # obrigatório quando success=False
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None
    return_type: Literal["total", "parcial"] | None = None
    returned_quantity: float | None = None


class AdminRouteCorrectionIn(BaseModel):
    status: Literal["planejada", "em_carregamento", "liberada", "em_rota", "finalizada", "cancelada"] | None = None
    reset_dock_flow: bool = False
    reset_all_stops: bool = False
    justification: str

    @field_validator("justification")
    @classmethod
    def _justification_required(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Justificativa obrigatória.")
        return value


class AdminStopCorrectionIn(BaseModel):
    status: Literal["pendente", "em_rota", "entregue", "falha", "devolvido"] | None = None
    clear_checkin: bool = False
    clear_delivery: bool = False
    clear_failure: bool = False
    clear_proofs: bool = False
    failure_reason_id: int | None = None
    return_type: Literal["total", "parcial"] | None = None
    returned_quantity: float | None = None
    justification: str

    @field_validator("justification")
    @classmethod
    def _justification_required(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Justificativa obrigatória.")
        return value

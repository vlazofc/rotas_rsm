"""Indicadores operacionais para o painel."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import Role, branch_scope_filter, operational_scope, scope_by_branch
from app.db.models import DeliveryFailureReason, DockSession, Route, RouteEvent, RouteStop, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.cache import get_json, set_json

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

OPEN_STATUSES = {"planejada", "em_carregamento", "liberada", "em_rota"}
CLOSED_STATUSES = {"finalizada", "cancelada"}
SUCCESS_STOP_STATUSES = {"entregue"}
FAILURE_STOP_STATUSES = {"falha", "devolvido"}


@router.get("/summary")
def summary(
    range: str = "day",
    status: str = "open",
    period_ref: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cache_key = f"dashboard:v4:{user.role}:{operational_scope(user, db).value}:{user.tenant_id}:{user.branch_id}:{range}:{status}:{period_ref or '-'}"
    cached = get_json(cache_key)
    if cached is not None:
        return cached

    branch_filter = [branch_scope_filter(Route.branch_id, user, db)]

    def count(*conds):
        return db.scalar(select(func.count(Route.id)).where(*branch_filter, *conds)) or 0

    selected_statuses = _status_set(status)
    today = date.today()
    start_date, end_date, bucket_range = _period_bounds(today, range, period_ref)

    routes = db.scalars(
        select(Route)
        .options(selectinload(Route.stops), selectinload(Route.events), selectinload(Route.dock_session))
        .where(*branch_filter, Route.route_date >= start_date, Route.route_date <= end_date, Route.status.in_(selected_statuses))
        .order_by(Route.route_date.asc(), Route.id.asc())
    ).all()

    stops = [stop for route in routes for stop in route.stops]
    total_routes = len(routes)
    total_deliveries = len(stops)
    successful_deliveries = sum(1 for stop in stops if stop.status in SUCCESS_STOP_STATUSES)
    failed_deliveries = sum(1 for stop in stops if stop.status in FAILURE_STOP_STATUSES)
    pending_deliveries = sum(1 for stop in stops if stop.status == "pendente")
    road_deliveries = sum(1 for stop in stops if stop.status == "em_rota")
    total_weight = round(sum(float(stop.weight_kg or 0) for stop in stops), 1)
    total_pallets = round(sum(float(stop.pallets or 0) for stop in stops), 1)
    avg_deliveries_per_route = round(total_deliveries / total_routes, 1) if total_routes else 0
    close_rate = round((sum(1 for route in routes if route.status == "finalizada") / total_routes) * 100, 1) if total_routes else 0
    closed_deliveries = successful_deliveries + failed_deliveries
    success_rate = round((successful_deliveries / closed_deliveries) * 100, 1) if closed_deliveries else 0
    failure_rate = round((failed_deliveries / closed_deliveries) * 100, 1) if closed_deliveries else 0
    cd_release_times = [_minutes_between(r.dock_session.arrival_cd_at, r.dock_session.operator_released_at)
                        for r in routes if r.dock_session]
    loading_times = [_loading_minutes(r.dock_session) for r in routes if r.dock_session]
    stop_intervals = [interval for route in routes for interval in _stop_intervals(route)]
    avg_cd_release = _avg([item for item in cd_release_times if item is not None])
    avg_loading = _avg([item for item in loading_times if item is not None])
    avg_stop_interval = _avg(stop_intervals)
    route_times = [_minutes_between(r.actual_departure_at or (r.dock_session.departure_cd_at if r.dock_session else None), r.closed_at)
                   for r in routes if r.status == "finalizada"]
    avg_route = _avg([minutes for minutes in route_times if minutes is not None])

    avg_dock = db.scalar(
        select(func.avg(DockSession.loading_minutes)).join(Route, Route.id == DockSession.route_id)
        .where(
            *branch_filter,
            Route.route_date >= start_date,
            Route.route_date <= end_date,
            Route.status.in_(selected_statuses),
            DockSession.loading_minutes.is_not(None),
        )
    )

    late = db.scalar(
        select(func.count(RouteStop.id)).join(Route, Route.id == RouteStop.route_id).where(
            *branch_filter,
            Route.route_date >= start_date,
            Route.route_date <= end_date,
            Route.status.in_(selected_statuses),
            RouteStop.status.in_(["pendente", "em_rota"]),
            RouteStop.planned_date < today,
        )
    ) or 0

    result = {
        "periodo": range,
        "filtro_status": status,
        "rotas_total": total_routes,
        "rotas_abertas": sum(1 for route in routes if route.status in OPEN_STATUSES),
        "rotas_fechadas": sum(1 for route in routes if route.status in CLOSED_STATUSES),
        "entregas_total": total_deliveries,
        "entregas_sucesso": successful_deliveries,
        "entregas_insucesso": failed_deliveries,
        "entregas_pendentes": pending_deliveries,
        "entregas_em_rota": road_deliveries,
        "taxa_sucesso": success_rate,
        "taxa_insucesso": failure_rate,
        "taxa_fechamento_rotas": close_rate,
        "media_entregas_por_rota": avg_deliveries_per_route,
        "peso_total_kg": total_weight,
        "paletes_total": total_pallets,
        "rotas_aguardando_carregamento": count(Route.status == "planejada"),
        "rotas_em_carregamento": count(Route.status == "em_carregamento"),
        "rotas_liberadas": count(Route.status == "liberada"),
        "rotas_em_rota": count(Route.status == "em_rota"),
        "rotas_finalizadas": count(Route.status == "finalizada"),
        "tempo_medio_doca_min": round(float(avg_dock), 1) if avg_dock is not None else None,
        "tempo_medio_carregamento_min": avg_loading,
        "tempo_medio_chegada_liberacao_min": avg_cd_release,
        "tempo_medio_entre_paradas_min": avg_stop_interval,
        "tempo_medio_rota_min": avg_route,
        "entregas_atrasadas": late,
        "status_rotas": _route_status_breakdown(routes),
        "status_entregas": _delivery_status_breakdown(stops),
        "motivos_insucesso": _failure_reason_breakdown(db, stops),
        "serie_volume": _build_series(routes, bucket_range, start_date, end_date),
        "serie_entregas": _build_delivery_series(routes, bucket_range, start_date, end_date),
        "serie_tempos": _build_time_series(routes, bucket_range, start_date, end_date),
        "serie_carga": _build_load_series(routes, bucket_range, start_date, end_date),
    }
    set_json(cache_key, result, 2)
    return result


def _status_set(status: str) -> set[str]:
    if status == "closed":
        return CLOSED_STATUSES
    if status == "all":
        return OPEN_STATUSES | CLOSED_STATUSES
    return OPEN_STATUSES


def _period_bounds(today: date, range_name: str, period_ref: str | None = None) -> tuple[date, date, str]:
    if range_name == "week":
        start = _parse_week(period_ref) if period_ref else today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6), "day"
    if range_name == "month":
        return _add_months(today.replace(day=1), -11), today, "month"
    return today - timedelta(days=13), today, "day"


def _period_start(today: date, range_name: str) -> date:
    return _period_bounds(today, range_name)[0]


def _bucket_label(value: date, range_name: str) -> str:
    if range_name == "month":
        return value.strftime("%m/%Y")
    if range_name == "week":
        monday = value - timedelta(days=value.weekday())
        return monday.strftime("%d/%m")
    return value.strftime("%d/%m")


def _build_empty_buckets(
    today: date,
    range_name: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, dict[str, int | str]]:
    buckets: dict[str, dict[str, int | str]] = {}
    if start_date and end_date and range_name == "day":
        current = start_date
        while current <= end_date:
            label = _bucket_label(current, range_name)
            buckets[label] = {"label": label, "rotas": 0, "entregas": 0, "sucesso": 0, "insucesso": 0}
            current += timedelta(days=1)
        return buckets
    if range_name == "month":
        current = _add_months(today.replace(day=1), -11)
        for _ in range(12):
            label = _bucket_label(current, range_name)
            buckets[label] = {"label": label, "rotas": 0, "entregas": 0, "sucesso": 0, "insucesso": 0}
            current = _add_months(current, 1)
        return buckets
    if range_name == "week":
        current = today - timedelta(days=55)
        current = current - timedelta(days=current.weekday())
        for _ in range(8):
            label = _bucket_label(current, range_name)
            buckets[label] = {"label": label, "rotas": 0, "entregas": 0, "sucesso": 0, "insucesso": 0}
            current += timedelta(days=7)
        return buckets
    for offset in range(13, -1, -1):
        current = today - timedelta(days=offset)
        label = _bucket_label(current, range_name)
        buckets[label] = {"label": label, "rotas": 0, "entregas": 0, "sucesso": 0, "insucesso": 0}
    return buckets


def _build_empty_metric_buckets(
    today: date,
    range_name: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, dict[str, float | int | str]]:
    return {
        label: {
            "label": label,
            "doca_sum": 0.0,
            "doca_count": 0,
            "carregamento_sum": 0.0,
            "carregamento_count": 0,
            "liberacao_sum": 0.0,
            "liberacao_count": 0,
            "paradas_sum": 0.0,
            "paradas_count": 0,
        }
        for label in _build_empty_buckets(today, range_name, start_date, end_date)
    }


def _build_series(routes: list[Route], range_name: str, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, int | str]]:
    buckets = _build_empty_buckets(date.today(), range_name, start_date, end_date)
    for route in routes:
        label = _bucket_label(route.route_date, range_name)
        if label in buckets:
            buckets[label]["rotas"] = int(buckets[label]["rotas"]) + 1
            buckets[label]["entregas"] = int(buckets[label]["entregas"]) + len(route.stops)
    return list(buckets.values())


def _build_delivery_series(routes: list[Route], range_name: str, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, int | str]]:
    buckets = _build_empty_buckets(date.today(), range_name, start_date, end_date)
    for route in routes:
        for stop in route.stops:
            planned_date = stop.planned_date or route.route_date
            label = _bucket_label(planned_date, range_name)
            if label not in buckets:
                continue
            buckets[label]["entregas"] = int(buckets[label]["entregas"]) + 1
            if stop.status in SUCCESS_STOP_STATUSES:
                buckets[label]["sucesso"] = int(buckets[label]["sucesso"]) + 1
            if stop.status in FAILURE_STOP_STATUSES:
                buckets[label]["insucesso"] = int(buckets[label]["insucesso"]) + 1
    return list(buckets.values())


def _build_time_series(routes: list[Route], range_name: str, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, float | str | None]]:
    buckets = _build_empty_metric_buckets(date.today(), range_name, start_date, end_date)
    for route in routes:
        label = _bucket_label(route.route_date, range_name)
        if label not in buckets:
            continue
        dock_minutes = route.dock_session.loading_minutes if route.dock_session else None
        loading_minutes = _loading_minutes(route.dock_session) if route.dock_session else None
        release_minutes = _minutes_between(
            route.dock_session.arrival_cd_at,
            route.dock_session.operator_released_at,
        ) if route.dock_session else None
        if dock_minutes is not None:
            buckets[label]["doca_sum"] = float(buckets[label]["doca_sum"]) + float(dock_minutes)
            buckets[label]["doca_count"] = int(buckets[label]["doca_count"]) + 1
        if loading_minutes is not None:
            buckets[label]["carregamento_sum"] = float(buckets[label]["carregamento_sum"]) + loading_minutes
            buckets[label]["carregamento_count"] = int(buckets[label]["carregamento_count"]) + 1
        if release_minutes is not None:
            buckets[label]["liberacao_sum"] = float(buckets[label]["liberacao_sum"]) + release_minutes
            buckets[label]["liberacao_count"] = int(buckets[label]["liberacao_count"]) + 1
        for interval in _stop_intervals(route):
            buckets[label]["paradas_sum"] = float(buckets[label]["paradas_sum"]) + interval
            buckets[label]["paradas_count"] = int(buckets[label]["paradas_count"]) + 1

    series: list[dict[str, float | str | None]] = []
    for bucket in buckets.values():
        series.append({
            "label": str(bucket["label"]),
            "doca": _ratio(bucket["doca_sum"], bucket["doca_count"]),
            "carregamento": _ratio(bucket["carregamento_sum"], bucket["carregamento_count"]),
            "chegada_liberacao": _ratio(bucket["liberacao_sum"], bucket["liberacao_count"]),
            "entre_paradas": _ratio(bucket["paradas_sum"], bucket["paradas_count"]),
        })
    return series


def _build_load_series(routes: list[Route], range_name: str, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, float | str]]:
    buckets = {
        label: {"label": label, "peso_kg": 0.0, "paletes": 0.0}
        for label in _build_empty_buckets(date.today(), range_name, start_date, end_date)
    }
    for route in routes:
        label = _bucket_label(route.route_date, range_name)
        if label not in buckets:
            continue
        buckets[label]["peso_kg"] = round(float(buckets[label]["peso_kg"]) + sum(float(stop.weight_kg or 0) for stop in route.stops), 1)
        buckets[label]["paletes"] = round(float(buckets[label]["paletes"]) + sum(float(stop.pallets or 0) for stop in route.stops), 1)
    return list(buckets.values())




def _failure_reason_breakdown(db: Session, stops: list[RouteStop]) -> list[dict[str, int | str]]:
    reason_ids = {stop.failure_reason_id for stop in stops if stop.status in FAILURE_STOP_STATUSES and stop.failure_reason_id}
    labels = {}
    if reason_ids:
        reasons = db.scalars(select(DeliveryFailureReason).where(DeliveryFailureReason.id.in_(reason_ids))).all()
        labels = {reason.id: reason.label for reason in reasons}
    counts: dict[str, int] = {}
    for stop in stops:
        if stop.status not in FAILURE_STOP_STATUSES:
            continue
        label = labels.get(stop.failure_reason_id, "Sem motivo informado")
        counts[label] = counts.get(label, 0) + 1
    return [{"label": label, "value": value} for label, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)]


def _route_status_breakdown(routes: list[Route]) -> list[dict[str, int | str]]:
    labels = {
        "planejada": "Planejadas",
        "em_carregamento": "Carregamento",
        "liberada": "Liberadas",
        "em_rota": "Em rota",
        "finalizada": "Finalizadas",
        "cancelada": "Canceladas",
    }
    counts = {key: 0 for key in labels}
    for route in routes:
        if route.status in counts:
            counts[route.status] += 1
    return [{"label": labels[key], "value": value} for key, value in counts.items()]


def _delivery_status_breakdown(stops: list[RouteStop]) -> list[dict[str, int | str]]:
    labels = {
        "pendente": "Pendentes",
        "em_rota": "Em rota",
        "entregue": "Entregues",
        "falha": "Falhas",
        "devolvido": "Devolvidas",
    }
    counts = {key: 0 for key in labels}
    for stop in stops:
        if stop.status in counts:
            counts[stop.status] += 1
    return [{"label": labels[key], "value": value} for key, value in counts.items()]


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def _parse_week(value: str | None) -> date:
    if not value:
        today = date.today()
        return today - timedelta(days=today.weekday())
    try:
        year_text, week_text = value.split("-W")
        return date.fromisocalendar(int(year_text), int(week_text), 1)
    except (ValueError, AttributeError):
        today = date.today()
        return today - timedelta(days=today.weekday())


def _minutes_between(start, end) -> float | None:
    if not start or not end:
        return None
    diff = (end - start).total_seconds() / 60
    if diff < 0:
        return None
    return round(diff, 1)


def _loading_minutes(session: DockSession) -> float | None:
    minutes = _minutes_between(session.loading_started_at, session.loading_finished_at)
    if minutes is not None:
        return minutes
    if session.loading_minutes is not None:
        return float(session.loading_minutes)
    return None


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _ratio(total, count) -> float | None:
    count_int = int(count)
    if not count_int:
        return None
    return round(float(total) / count_int, 1)


def _stop_intervals(route: Route) -> list[float]:
    closed_times = []
    event_times = _stop_close_event_times(route.events)
    for stop in sorted(route.stops, key=lambda item: item.sequence):
        closed_at = stop.delivered_at or event_times.get(stop.id)
        if closed_at:
            closed_times.append(closed_at)
    intervals = []
    for previous, current in zip(closed_times, closed_times[1:]):
        minutes = _minutes_between(previous, current)
        if minutes is not None:
            intervals.append(minutes)
    return intervals


def _stop_close_event_times(events: list[RouteEvent]) -> dict[int, object]:
    result = {}
    for event in events:
        if event.stop_id and event.event_type in {"DELIVERED", "FAILED_DELIVERY"}:
            result[event.stop_id] = event.event_time
    return result


@router.get("/map")
def map_points(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Pontos para o mapa com cor por status (verde/amarelo/vermelho/cinza/azul)."""
    stmt = scope_by_branch(select(Route).where(Route.status == "em_rota"), Route.branch_id, user, db)
    routes = db.scalars(stmt).all()
    return [{"route_id": r.id, "codigo_ut": r.codigo_ut, "status": r.status} for r in routes]

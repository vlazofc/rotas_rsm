import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import { usePolling } from "../hooks/usePolling";

const REFRESH_INTERVAL_MS = 30000;

type PeriodFilter = "day" | "week" | "month";
type RouteFilter = "open" | "closed" | "all";

interface SeriesPoint {
  label: string;
  rotas?: number;
  entregas?: number;
  sucesso?: number;
  insucesso?: number;
}

interface StatusPoint {
  label: string;
  value: number;
}

interface TimePoint {
  label: string;
  doca: number | null;
  carregamento: number | null;
  chegada_liberacao: number | null;
  entre_paradas: number | null;
}

interface LoadPoint {
  label: string;
  peso_kg: number;
  paletes: number;
}

interface TollPoint {
  label: string;
  ida: number;
  volta: number;
  total: number;
}

interface DashboardSummary {
  rotas_total: number;
  rotas_abertas: number;
  rotas_fechadas: number;
  entregas_total: number;
  entregas_sucesso: number;
  entregas_insucesso: number;
  entregas_pendentes: number;
  entregas_em_rota: number;
  taxa_sucesso: number;
  taxa_insucesso: number;
  taxa_fechamento_rotas: number;
  media_entregas_por_rota: number;
  peso_total_kg: number;
  paletes_total: number;
  pedagio_total: number;
  pedagio_ida: number;
  pedagio_volta: number;
  tempo_medio_doca_min: number | null;
  tempo_medio_carregamento_min: number | null;
  tempo_medio_chegada_liberacao_min: number | null;
  tempo_medio_entre_paradas_min: number | null;
  entregas_atrasadas: number;
  rotas_aguardando_carregamento: number;
  rotas_em_carregamento: number;
  rotas_liberadas: number;
  rotas_em_rota: number;
  rotas_finalizadas: number;
  status_rotas: StatusPoint[];
  status_entregas: StatusPoint[];
  motivos_insucesso: StatusPoint[];
  serie_volume: SeriesPoint[];
  serie_entregas: SeriesPoint[];
  serie_tempos: TimePoint[];
  serie_carga: LoadPoint[];
  serie_pedagio: TollPoint[];
}

export default function Dashboard() {
  const { t, i18n } = useTranslation();
  const [period, setPeriod] = useState<PeriodFilter>("day");
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("open");
  const [selectedWeek, setSelectedWeek] = useState(currentWeekValue());
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const periodLabels: Record<PeriodFilter, string> = {
    day: t("dashboard.period.day"),
    week: t("dashboard.period.week"),
    month: t("dashboard.period.month"),
  };
  const routeFilterLabels: Record<RouteFilter, string> = {
    open: t("route_filter.open"),
    closed: t("route_filter.closed"),
    all: t("route_filter.all"),
  };

  const load = (showLoading: boolean) => {
    if (showLoading) setLoading(true);
    api.get<DashboardSummary>("/dashboard/summary", {
      params: { range: period, status: routeFilter, period_ref: period === "week" ? selectedWeek : undefined },
    })
      .then((r) => setData(r.data))
      .catch(() => { if (showLoading) setData(null); })
      .finally(() => { if (showLoading) setLoading(false); });
  };

  useEffect(() => { load(true); }, [period, routeFilter, selectedWeek]);

  // Mantém os indicadores atualizados sem exigir F5.
  usePolling(() => load(false), REFRESH_INTERVAL_MS);

  const maxVolume = useMemo(() => {
    const values = data?.serie_volume.flatMap((item) => [item.rotas ?? 0, item.entregas ?? 0]) ?? [1];
    return Math.max(1, ...values);
  }, [data]);

  const maxDelivery = useMemo(() => {
    const values = data?.serie_entregas.flatMap((item) => [item.sucesso ?? 0, item.insucesso ?? 0]) ?? [1];
    return Math.max(1, ...values);
  }, [data]);

  const statusTotal = useMemo(() => {
    return data?.status_rotas.reduce((acc, item) => acc + item.value, 0) ?? 0;
  }, [data]);

  const deliveryStatusTotal = useMemo(() => {
    return data?.status_entregas.reduce((acc, item) => acc + item.value, 0) ?? 0;
  }, [data]);

  const failureTotal = useMemo(() => {
    return data?.motivos_insucesso.reduce((acc, item) => acc + item.value, 0) ?? 0;
  }, [data]);

  const maxTime = useMemo(() => {
    const values = data?.serie_tempos.flatMap((item) => [
      item.doca ?? 0,
      item.carregamento ?? 0,
      item.chegada_liberacao ?? 0,
      item.entre_paradas ?? 0,
    ]) ?? [1];
    return Math.max(1, ...values);
  }, [data]);

  const maxLoad = useMemo(() => {
    const values = data?.serie_carga.flatMap((item) => [item.peso_kg, item.paletes]) ?? [1];
    return Math.max(1, ...values);
  }, [data]);

  const maxToll = useMemo(() => {
    const values = data?.serie_pedagio.flatMap((item) => [item.ida, item.volta, item.total]) ?? [1];
    return Math.max(1, ...values);
  }, [data]);

  return (
    <div>
      <div className="page-header dashboard-header">
        <div>
          <h2>{t("dashboard.title")}</h2>
          <p className="page-subtitle">{t("dashboard.subtitle")}</p>
        </div>
        <div className="dashboard-controls">
          <SegmentedControl
            value={routeFilter}
            labels={routeFilterLabels}
            onChange={(value) => setRouteFilter(value as RouteFilter)}
          />
          <SegmentedControl
            value={period}
            labels={periodLabels}
            onChange={(value) => setPeriod(value as PeriodFilter)}
          />
          {period === "week" && (
            <label className="week-picker">
              <span>{t("dashboard.week")}</span>
              <input type="week" value={selectedWeek} onChange={(event) => setSelectedWeek(event.target.value)} />
            </label>
          )}
        </div>
      </div>

      {loading ? (
        <p>{t("common.loading")}</p>
      ) : !data ? (
        <div className="card-panel empty-state">{t("dashboard.load_error")}</div>
      ) : (
        <div className="dashboard-grid">
          <section className="dashboard-kpis">
            <KpiCard label={t("dashboard.kpi.delivery_success")} value={`${data.taxa_sucesso}%`} detail={t("dashboard.detail.deliveries", { count: data.entregas_sucesso })} tone="success" />
            <KpiCard label={t("dashboard.kpi.delivery_failure")} value={`${data.taxa_insucesso}%`} detail={t("dashboard.detail.occurrences", { count: data.entregas_insucesso })} tone="danger" />
            <KpiCard label={t("dashboard.kpi.total_routes")} value={data.rotas_total} detail={t("dashboard.detail.open_closed", { open: data.rotas_abertas, closed: data.rotas_fechadas })} />
            <KpiCard label={t("dashboard.kpi.deliveries")} value={data.entregas_total} detail={t("dashboard.detail.late", { count: data.entregas_atrasadas })} tone={data.entregas_atrasadas ? "warning" : "neutral"} />
            <KpiCard label={t("dashboard.kpi.pending")} value={data.entregas_pendentes} detail={t("dashboard.detail.on_route", { count: data.entregas_em_rota })} tone={data.entregas_pendentes ? "warning" : "neutral"} />
            <KpiCard label={t("dashboard.kpi.route_close_rate")} value={`${data.taxa_fechamento_rotas}%`} detail={t("dashboard.detail.closed_routes")} />
            <KpiCard label={t("dashboard.kpi.deliveries_per_route")} value={data.media_entregas_por_rota} detail={t("dashboard.detail.operational_average")} />
            <KpiCard label={t("dashboard.kpi.toll")} value={formatCurrency(data.pedagio_total, i18n.language)} detail={t("dashboard.detail.toll_split", { outbound: formatCurrency(data.pedagio_ida, i18n.language), return: formatCurrency(data.pedagio_volta, i18n.language) })} />
            <KpiCard label={t("dashboard.kpi.avg_dock")} value={formatMinutes(data.tempo_medio_doca_min, i18n.language)} detail={t("dashboard.detail.loading")} />
            <KpiCard label={t("dashboard.kpi.loading_time")} value={formatMinutes(data.tempo_medio_carregamento_min, i18n.language)} detail={t("dashboard.detail.loading_time")} />
            <KpiCard label={t("dashboard.kpi.arrival_release")} value={formatMinutes(data.tempo_medio_chegada_liberacao_min, i18n.language)} detail={t("dashboard.detail.warehouse_time")} />
            <KpiCard label={t("dashboard.kpi.between_stops")} value={formatMinutes(data.tempo_medio_entre_paradas_min, i18n.language)} detail={t("dashboard.detail.between_deliveries")} />
          </section>

          <section className="dashboard-ops-grid">
            <MiniMetric label={t("dashboard.ops.waiting_loading")} value={data.rotas_aguardando_carregamento} />
            <MiniMetric label={t("dashboard.ops.loading")} value={data.rotas_em_carregamento} />
            <MiniMetric label={t("dashboard.ops.released")} value={data.rotas_liberadas} />
            <MiniMetric label={t("dashboard.ops.on_route")} value={data.rotas_em_rota} />
            <MiniMetric label={t("dashboard.ops.finished")} value={data.rotas_finalizadas} />
          </section>

          <section className="card-panel dashboard-chart-card chart-wide">
            <div className="chart-head">
              <div>
                <h3>{t("dashboard.charts.volume")}</h3>
                <p>{t("dashboard.charts.volume_help", { period: periodLabels[period].toLowerCase() })}</p>
              </div>
            </div>
            <div className="combo-chart">
              {data.serie_volume.map((item) => (
                <div className="combo-bar" key={item.label}>
                  <div className="combo-stack" title={t("dashboard.titles.volume", { label: item.label, routes: item.rotas ?? 0, deliveries: item.entregas ?? 0 })}>
                    <span className="bar-routes" style={{ height: `${heightFor(item.rotas ?? 0, maxVolume)}%` }}>
                      <em>{labelFor(item.rotas)}</em>
                    </span>
                    <span className="bar-deliveries" style={{ height: `${heightFor(item.entregas ?? 0, maxVolume)}%` }}>
                      <em>{labelFor(item.entregas)}</em>
                    </span>
                  </div>
                  <small>{item.label}</small>
                </div>
              ))}
            </div>
            <ChartLegend items={[[t("dashboard.legend.routes"), "bar-routes"], [t("dashboard.legend.deliveries"), "bar-deliveries"]]} />
          </section>

          <section className="card-panel dashboard-chart-card chart-wide">
            <div className="chart-head">
              <div>
                <h3>{t("dashboard.charts.times")}</h3>
                <p>{t("dashboard.charts.times_help")}</p>
              </div>
            </div>
            <div className="combo-chart time-chart">
              {data.serie_tempos.map((item) => (
                <div className="combo-bar" key={item.label}>
                  <div className="combo-stack" title={t("dashboard.titles.times", {
                    label: item.label,
                    dock: formatMinutes(item.doca, i18n.language),
                    loading: formatMinutes(item.carregamento, i18n.language),
                    release: formatMinutes(item.chegada_liberacao, i18n.language),
                    stops: formatMinutes(item.entre_paradas, i18n.language),
                  })}>
                    <span className="bar-dock" style={{ height: `${heightFor(item.doca ?? 0, maxTime)}%` }}>
                      <em>{labelFor(item.doca)}</em>
                    </span>
                    <span className="bar-loading" style={{ height: `${heightFor(item.carregamento ?? 0, maxTime)}%` }}>
                      <em>{labelFor(item.carregamento)}</em>
                    </span>
                    <span className="bar-release" style={{ height: `${heightFor(item.chegada_liberacao ?? 0, maxTime)}%` }}>
                      <em>{labelFor(item.chegada_liberacao)}</em>
                    </span>
                    <span className="bar-stops" style={{ height: `${heightFor(item.entre_paradas ?? 0, maxTime)}%` }}>
                      <em>{labelFor(item.entre_paradas)}</em>
                    </span>
                  </div>
                  <small>{item.label}</small>
                </div>
              ))}
            </div>
            <ChartLegend items={[[t("dashboard.legend.dock"), "bar-dock"], [t("dashboard.legend.loading"), "bar-loading"], [t("dashboard.legend.arrival_release"), "bar-release"], [t("dashboard.legend.between_stops"), "bar-stops"]]} />
          </section>

          <section className="card-panel dashboard-chart-card chart-wide">
            <div className="chart-head">
              <div>
                <h3>{t("dashboard.charts.load")}</h3>
                <p>{t("dashboard.charts.load_help")}</p>
              </div>
            </div>
            <div className="combo-chart load-chart">
              {data.serie_carga.map((item) => (
                <div className="combo-bar" key={item.label}>
                  <div className="combo-stack" title={t("dashboard.titles.load", { label: item.label, weight: formatNumber(item.peso_kg, i18n.language), pallets: formatNumber(item.paletes, i18n.language) })}>
                    <span className="bar-weight" style={{ height: `${heightFor(item.peso_kg, maxLoad)}%` }}>
                      <em>{shortNumber(item.peso_kg)}</em>
                    </span>
                    <span className="bar-pallets" style={{ height: `${heightFor(item.paletes, maxLoad)}%` }}>
                      <em>{labelFor(item.paletes)}</em>
                    </span>
                  </div>
                  <small>{item.label}</small>
                </div>
              ))}
            </div>
            <ChartLegend items={[[t("dashboard.legend.weight"), "bar-weight"], [t("dashboard.legend.pallets"), "bar-pallets"]]} />
          </section>

          <section className="card-panel dashboard-chart-card chart-wide">
            <div className="chart-head">
              <div>
                <h3>{t("dashboard.charts.toll")}</h3>
                <p>{t("dashboard.charts.toll_help")}</p>
              </div>
            </div>
            <div className="combo-chart toll-chart">
              {data.serie_pedagio.map((item) => (
                <div className="combo-bar" key={item.label}>
                  <div className="combo-stack" title={t("dashboard.titles.toll", {
                    label: item.label,
                    outbound: formatCurrency(item.ida, i18n.language),
                    return: formatCurrency(item.volta, i18n.language),
                    total: formatCurrency(item.total, i18n.language),
                  })}>
                    <span className="bar-toll-out" style={{ height: `${heightFor(item.ida, maxToll)}%` }}>
                      <em>{shortCurrency(item.ida, i18n.language)}</em>
                    </span>
                    <span className="bar-toll-return" style={{ height: `${heightFor(item.volta, maxToll)}%` }}>
                      <em>{shortCurrency(item.volta, i18n.language)}</em>
                    </span>
                    <span className="bar-toll-total" style={{ height: `${heightFor(item.total, maxToll)}%` }}>
                      <em>{shortCurrency(item.total, i18n.language)}</em>
                    </span>
                  </div>
                  <small>{item.label}</small>
                </div>
              ))}
            </div>
            <ChartLegend items={[[t("dashboard.legend.outbound"), "bar-toll-out"], [t("dashboard.legend.return"), "bar-toll-return"], [t("dashboard.legend.total"), "bar-toll-total"]]} />
          </section>

          <section className="card-panel dashboard-chart-card">
            <div className="chart-head">
              <div>
                <h3>{t("dashboard.charts.delivery_performance")}</h3>
                <p>{t("dashboard.charts.delivery_performance_help")}</p>
              </div>
            </div>
            <div className="stack-chart">
              {data.serie_entregas.map((item) => (
                <div className="stack-row" key={item.label}>
                  <span>{item.label}</span>
                  <div className="stack-track">
                    <i className="stack-success" style={{ width: `${widthFor(item.sucesso ?? 0, maxDelivery)}%` }} />
                    <i className="stack-failure" style={{ width: `${widthFor(item.insucesso ?? 0, maxDelivery)}%` }} />
                  </div>
                  <strong>{(item.sucesso ?? 0) + (item.insucesso ?? 0)}</strong>
                </div>
              ))}
            </div>
            <ChartLegend items={[[t("dashboard.legend.success"), "stack-success"], [t("dashboard.legend.failure"), "stack-failure"]]} />
          </section>

          {routeFilter !== "closed" && (
            <section className="card-panel dashboard-chart-card">
              <div className="chart-head">
                <div>
                  <h3>{t("dashboard.charts.route_status")}</h3>
                  <p>{t("dashboard.charts.route_status_help")}</p>
                </div>
              </div>
              <div className="status-list">
                {data.status_rotas.filter((item) => item.value > 0).map((item) => (
                  <div className="status-row" key={item.label}>
                    <div>
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                    </div>
                    <div className="status-track">
                      <i style={{ width: `${widthFor(item.value, statusTotal)}%` }} />
                    </div>
                  </div>
                ))}
                {statusTotal === 0 && <div className="empty-state">{t("dashboard.empty.routes")}</div>}
              </div>
            </section>
          )}

          <section className="card-panel dashboard-chart-card">
            <div className="chart-head">
              <div>
                <h3>{t("dashboard.charts.delivery_status")}</h3>
                <p>{t("dashboard.charts.delivery_status_help")}</p>
              </div>
            </div>
            <div className="status-list">
              {data.status_entregas.filter((item) => item.value > 0).map((item) => (
                <div className="status-row delivery-status-row" key={item.label}>
                  <div>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                  <div className="status-track">
                    <i style={{ width: `${widthFor(item.value, deliveryStatusTotal)}%` }} />
                  </div>
                </div>
              ))}
              {deliveryStatusTotal === 0 && <div className="empty-state">{t("dashboard.empty.deliveries")}</div>}
            </div>
          </section>

          <section className="card-panel dashboard-chart-card">
            <div className="chart-head">
              <div>
                <h3>{t("dashboard.charts.failure_reasons")}</h3>
                <p>{t("dashboard.charts.failure_reasons_help")}</p>
              </div>
            </div>
            <div className="status-list">
              {data.motivos_insucesso.map((item) => (
                <div className="status-row failure-row" key={item.label}>
                  <div>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                  <div className="status-track">
                    <i style={{ width: `${widthFor(item.value, failureTotal)}%` }} />
                  </div>
                </div>
              ))}
              {failureTotal === 0 && <div className="empty-state">{t("dashboard.empty.failure_reasons")}</div>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function SegmentedControl<T extends string>({ value, labels, onChange }: {
  value: T;
  labels: Record<T, string>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="route-filter dashboard-filter">
      {(Object.keys(labels) as T[]).map((key) => (
        <button
          key={key}
          type="button"
          className={value === key ? "is-active" : ""}
          onClick={() => onChange(key)}
        >
          {labels[key]}
        </button>
      ))}
    </div>
  );
}

function KpiCard({ label, value, detail, tone = "neutral" }: {
  label: string;
  value: string | number;
  detail: string;
  tone?: "neutral" | "success" | "danger" | "warning";
}) {
  return (
    <div className={`stat-card dashboard-kpi tone-${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="kpi-detail">{detail}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="mini-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ChartLegend({ items }: { items: [string, string][] }) {
  return (
    <div className="chart-legend">
      {items.map(([label, className]) => (
        <span key={label}><i className={className} />{label}</span>
      ))}
    </div>
  );
}

function heightFor(value: number, max: number) {
  if (!value) return 4;
  return Math.max(10, Math.round((value / max) * 100));
}

function widthFor(value: number, max: number) {
  if (!value || !max) return 0;
  return Math.max(4, Math.round((value / max) * 100));
}

function formatMinutes(value: number | null, locale = "pt-BR") {
  if (value === null || value === undefined) return "—";
  if (value < 60) return `${formatNumber(value, locale)} min`;
  const hours = Math.floor(value / 60);
  const minutes = Math.round(value % 60);
  if (!minutes) return `${hours}h`;
  return `${hours}h ${minutes}min`;
}

function labelFor(value?: number | null) {
  if (value === null || value === undefined || value === 0) return "";
  return Number.isInteger(value) ? String(value) : String(value);
}

function formatNumber(value: number, locale = "pt-BR") {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value);
}

function formatCurrency(value: number, locale = "pt-BR") {
  return new Intl.NumberFormat(locale, { style: "currency", currency: locale === "pt-BR" ? "BRL" : "EUR", maximumFractionDigits: 2 }).format(value);
}

function shortNumber(value: number) {
  if (!value) return "";
  if (value >= 1000) return `${Math.round(value / 1000)}k`;
  return labelFor(value);
}

function shortCurrency(value: number, locale = "pt-BR") {
  if (!value) return "";
  const symbol = locale === "pt-BR" ? "R$" : "€";
  if (value >= 1000) return `${symbol}${Math.round(value / 1000)}k`;
  return `${symbol}${formatNumber(value, locale)}`;
}

function currentWeekValue() {
  const now = new Date();
  const date = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

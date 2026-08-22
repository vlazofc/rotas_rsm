import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../services/api";
import { useAuth } from "../context/AuthContext";
import { usePolling } from "../hooks/usePolling";
import RouteMap from "../components/RouteMap";

const REFRESH_INTERVAL_MS = 20000;

interface Stop {
  id: number; sequence?: number; customer_name: string; customer_address?: string | null;
  client_name?: string | null;
  city?: string | null; status: string; failure_reason_id?: number | null;
  planned_date?: string | null; planned_time?: string | null;
  checkin_at?: string | null; delivered_at?: string | null; latitude?: number | null; longitude?: number | null;
  stop_type?: string | null; return_type?: "total" | "parcial" | null; returned_quantity?: number | null;
  warehouse_return_attachment_id?: number | null;
}
interface Toll { id: number; direction: "ida" | "volta"; amount: number; }
interface RouteItem {
  id: number; branch_id: number; codigo_ut: string; route_date: string; origin_name?: string | null;
  origin_address?: string | null; driver_id?: number | null; vehicle_id?: number | null;
  status: string; stops: Stop[]; dock_session?: DockSession | null; tolls?: Toll[];
  source?: string; fieldeas_description?: string | null; fieldeas_sync_at?: string | null;
  km_outbound_informed?: number | null; km_return_informed?: number | null;
}
interface DockSession {
  arrival_cd_at?: string | null;
  dock_entry_at?: string | null;
  loading_started_at?: string | null;
  loading_finished_at?: string | null;
  operator_released_at?: string | null;
  departure_cd_at?: string | null;
}
interface RouteAction {
  path: string;
  label: string;
  primary?: boolean;
}
type RouteFilter = "open" | "closed" | "all";
interface Driver { id: number; name: string; active: boolean; }
interface Vehicle { id: number; plate: string; active: boolean; }
interface Reason { id: number; code: string; label: string; label_pt_br?: string | null; active: boolean; }
interface ManifestItem {
  id: number;
  route_id: number | null;
  original_filename: string;
  status: string;
}
interface ManifestSuggestions {
  codigo_ut: string[];
  origins: string[];
  addresses: string[];
  customers: string[];
  cities: string[];
  orders: string[];
}

const STATUS_COLOR: Record<string, string> = {
  planejada: "#64748b", em_carregamento: "#0ea5e9", liberada: "#a855f7",
  em_rota: "#16a34a", finalizada: "#f97316", cancelada: "#ef4444",
};
const emptySuggestions: ManifestSuggestions = {
  codigo_ut: [],
  origins: [],
  addresses: [],
  customers: [],
  cities: [],
  orders: [],
};

function routeCustomers(route: Pick<RouteItem, "stops">) {
  const names = route.stops
    .map((stop) => (stop.client_name || stop.customer_name).trim())
    .filter(Boolean);
  return [...new Set(names)].join(", ") || "—";
}

export default function RoutesPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, hasRole } = useAuth();
  const [routes, setRoutes] = useState<RouteItem[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [manifests, setManifests] = useState<ManifestItem[]>([]);
  const [suggestions, setSuggestions] = useState<ManifestSuggestions>(emptySuggestions);
  const [selectedRouteId, setSelectedRouteId] = useState<number | null>(null);
  const [proofStop, setProofStop] = useState<{ routeId: number; stop: Stop } | null>(null);
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [proofError, setProofError] = useState("");
  const [proofSaving, setProofSaving] = useState(false);
  const [failStop, setFailStop] = useState<{ routeId: number; stop: Stop } | null>(null);
  const [failFile, setFailFile] = useState<File | null>(null);
  const [failForm, setFailForm] = useState({ reason_id: "", notes: "", return_type: "total" as "total" | "parcial", returned_quantity: "" });
  const [warehouseBatchRoute, setWarehouseBatchRoute] = useState<RouteItem | null>(null);
  const [warehouseBatchFiles, setWarehouseBatchFiles] = useState<Record<number, File | null>>({});
  const [warehouseBatchError, setWarehouseBatchError] = useState("");
  const [warehouseBatchSaving, setWarehouseBatchSaving] = useState(false);
  const [tollRouteId, setTollRouteId] = useState<number | null>(null);
  const [tollForm, setTollForm] = useState({ direction: "ida" as "ida" | "volta", amount: "" });
  const [kmRouteId, setKmRouteId] = useState<number | null>(null);
  const [kmForm, setKmForm] = useState({ km_outbound_informed: "", km_return_informed: "" });
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("open");
  const [routeListExpanded, setRouteListExpanded] = useState(false);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [form, setForm] = useState({ codigo_ut: "", route_date: "", origin_name: "", origin_address: "", driver_id: "", vehicle_id: "" });
  const [error, setError] = useState("");
  const [importOpen, setImportOpen] = useState(false);

  const reload = () => api.get<RouteItem[]>("/routes").then((r) => setRoutes(r.data)).catch(() => setRoutes([]));
  const reloadManifests = () => api.get<ManifestItem[]>("/manifests").then((r) => setManifests(r.data)).catch(() => setManifests([]));
  useEffect(() => {
    reload();
    reloadManifests();
    api.get<ManifestSuggestions>("/manifests/suggestions").then((r) => setSuggestions(r.data)).catch(() => setSuggestions(emptySuggestions));
    api.get("/drivers").then((r) => setDrivers(r.data)).catch(() => setDrivers([]));
    api.get("/vehicles").then((r) => setVehicles(r.data)).catch(() => setVehicles([]));
    api.get("/failure-reasons", { params: { only_active: true } }).then((r) => setReasons(r.data)).catch(() => setReasons([]));
  }, []);

  // Mantém a lista de rotas e manifestos atualizada sem depender de F5,
  // já que outros utilizadores podem alterar o status em tempo real.
  usePolling(() => { reload(); reloadManifests(); }, REFRESH_INTERVAL_MS);

  useEffect(() => {
    if (!selectedRouteId && routes.length > 0) setSelectedRouteId(routes[0].id);
  }, [routes, selectedRouteId]);

  useEffect(() => {
    if ((location.state as { openNew?: boolean } | null)?.openNew && hasRole("admin_global", "gestor_brasil", "operador_logistico")) {
      startNew();
      navigate(location.pathname, { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  async function act(id: number, path: string) {
    setError("");
    const route = routes.find((item) => item.id === id);
    if (path === "close" && route) {
      const missing = missingWarehouseStops(route);
      if (missing.length > 0) {
        setWarehouseBatchRoute(route);
        setWarehouseBatchFiles(Object.fromEntries(missing.map((stop) => [stop.id, null])));
        setWarehouseBatchError("");
        return;
      }
    }
    try {
      await api.post(`/routes/${id}/${path}`);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.action_error"));
    }
  }

  async function checkinStop(routeId: number, stop: Stop) {
    setError("");
    try {
      await api.post(`/routes/${routeId}/stops/${stop.id}/checkin`, {});
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.action_error"));
    }
  }

  async function deliverStop(routeId: number, stop: Stop) {
    setError("");
    if (stop.stop_type !== "carga") {
      setProofFile(null);
      setProofError("");
      setProofStop({ routeId, stop });
      return;
    }
    try {
      await api.post(`/routes/${routeId}/stops/${stop.id}/deliver`, { success: true });
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.action_error"));
    }
  }

  async function confirmDeliveryProof(e: React.FormEvent) {
    e.preventDefault();
    if (!proofStop) return;
    setProofError("");
    if (!proofFile) {
      setProofError(t("rd.delivery_proof_required"));
      return;
    }
    const payload = new FormData();
    payload.set("success", "true");
    payload.set("proof", proofFile);
    setProofSaving(true);
    try {
      await api.post(`/routes/${proofStop.routeId}/stops/${proofStop.stop.id}/deliver-with-proof`, payload);
      setProofStop(null);
      setProofFile(null);
      reload();
    } catch (err: any) {
      setProofError(formatApiError(err?.response?.data?.detail) ?? t("route.action_error"));
    } finally {
      setProofSaving(false);
    }
  }

  function openFail(routeId: number, stop: Stop) {
    setError("");
    setFailFile(null);
    setFailForm({ reason_id: "", notes: "", return_type: "total", returned_quantity: "" });
    setFailStop({ routeId, stop });
  }

  function openToll(routeId: number) {
    setError("");
    setTollForm({ direction: "ida", amount: "" });
    setTollRouteId(routeId);
  }

  function openKm(route: RouteItem) {
    setError("");
    setKmForm({
      km_outbound_informed: route.km_outbound_informed != null ? String(route.km_outbound_informed) : "",
      km_return_informed: route.km_return_informed != null ? String(route.km_return_informed) : "",
    });
    setKmRouteId(route.id);
  }

  async function saveKm(e: React.FormEvent) {
    e.preventDefault();
    if (kmRouteId == null) return;
    const payload: Record<string, number | null> = {};
    if (kmForm.km_outbound_informed !== "") payload.km_outbound_informed = Number(kmForm.km_outbound_informed);
    if (kmForm.km_return_informed !== "") payload.km_return_informed = Number(kmForm.km_return_informed);
    try {
      await api.put(`/routes/${kmRouteId}/km`, payload);
      setKmRouteId(null);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.action_error"));
    }
  }

  async function addToll(e: React.FormEvent) {
    e.preventDefault();
    if (tollRouteId == null) return;
    const amount = Number(tollForm.amount);
    if (!amount || amount <= 0) {
      setError(t("rd.toll_amount_required"));
      return;
    }
    try {
      await api.post(`/routes/${tollRouteId}/tolls`, { direction: tollForm.direction, amount });
      setTollForm({ ...tollForm, amount: "" });
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.action_error"));
    }
  }

  async function deleteToll(tollId: number) {
    if (tollRouteId == null) return;
    try {
      await api.delete(`/routes/${tollRouteId}/tolls/${tollId}`);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.action_error"));
    }
  }

  async function confirmFail(e: React.FormEvent) {
    e.preventDefault();
    if (!failStop) return;
    if (!failForm.reason_id) {
      setError(t("rd.reason_required"));
      return;
    }
    if (failForm.return_type === "parcial" && !failForm.returned_quantity) {
      setError(t("rd.returned_quantity_required"));
      return;
    }
    if (!failFile) {
      setError(t("rd.fail_proof_required"));
      return;
    }
    const payload = new FormData();
    payload.set("success", "false");
    payload.set("proof", failFile);
    payload.set("failure_reason_id", failForm.reason_id);
    payload.set("return_type", failForm.return_type);
    if (failForm.returned_quantity) payload.set("returned_quantity", failForm.returned_quantity);
    if (failForm.notes.trim()) payload.set("notes", failForm.notes.trim());
    try {
      await api.post(`/routes/${failStop.routeId}/stops/${failStop.stop.id}/deliver-with-proof`, payload);
      setFailStop(null);
      setFailFile(null);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.action_error"));
    }
  }

  async function confirmWarehouseBatch(e: React.FormEvent) {
    e.preventDefault();
    if (!warehouseBatchRoute) return;
    setWarehouseBatchError("");
    const missing = missingWarehouseStops(warehouseBatchRoute);
    const missingFiles = missing.filter((stop) => !warehouseBatchFiles[stop.id]);
    if (missingFiles.length > 0) {
      setWarehouseBatchError(t("rd.warehouse_batch_required", { list: missingFiles.map((stop) => stop.sequence ?? stop.id).join(", ") }));
      return;
    }
    setWarehouseBatchSaving(true);
    try {
      for (const stop of missing) {
        const payload = new FormData();
        payload.set("proof", warehouseBatchFiles[stop.id] as File);
        await api.post(`/routes/${warehouseBatchRoute.id}/stops/${stop.id}/warehouse-return-proof`, payload);
      }
      await api.post(`/routes/${warehouseBatchRoute.id}/close`);
      setWarehouseBatchRoute(null);
      setWarehouseBatchFiles({});
      reload();
    } catch (err: any) {
      setWarehouseBatchError(formatApiError(err?.response?.data?.detail) ?? t("route.action_error"));
    } finally {
      setWarehouseBatchSaving(false);
    }
  }

  function startNew() {
    setError("");
    setForm({ codigo_ut: "", route_date: new Date().toISOString().slice(0, 10), origin_name: "", origin_address: "", driver_id: "", vehicle_id: "" });
    setEditing("new");
  }

  function startEdit(route: RouteItem) {
    setError("");
    setForm({
      codigo_ut: route.codigo_ut,
      route_date: route.route_date,
      origin_name: route.origin_name ?? "",
      origin_address: route.origin_address ?? "",
      driver_id: route.driver_id ? String(route.driver_id) : "",
      vehicle_id: route.vehicle_id ? String(route.vehicle_id) : "",
    });
    setEditing(route.id);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const payload = {
      codigo_ut: form.codigo_ut.trim() || `PROVISORIA-${Date.now()}`,
      route_date: form.route_date,
      origin_name: form.origin_name.trim() || null,
      origin_address: form.origin_address.trim() || null,
      driver_id: form.driver_id ? Number(form.driver_id) : null,
      vehicle_id: form.vehicle_id ? Number(form.vehicle_id) : null,
    };
    try {
      if (editing === "new") {
        await api.post("/routes", { branch_id: user?.branch_id ?? 1, ...payload, stops: [] });
      } else if (typeof editing === "number") {
        await api.put(`/routes/${editing}`, payload);
      }
      setEditing(null);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.save_error"));
    }
  }

  const driverName = (id?: number | null) => drivers.find((d) => d.id === id)?.name ?? "-";
  const vehiclePlate = (id?: number | null) => vehicles.find((v) => v.id === id)?.plate ?? "-";
  const selectedRoute = useMemo(
    () => routes.find((r) => r.id === selectedRouteId) ?? null,
    [routes, selectedRouteId],
  );
  const tollRoute = useMemo(
    () => routes.find((r) => r.id === tollRouteId) ?? null,
    [routes, tollRouteId],
  );
  const kmRoute = useMemo(
    () => routes.find((r) => r.id === kmRouteId) ?? null,
    [routes, kmRouteId],
  );
  const isStopClosed = (stop: Stop) => stop.status === "entregue" || stop.status === "falha";
  const isRouteDeparted = (route?: RouteItem | null) => Boolean(route?.dock_session?.departure_cd_at || route?.status === "em_rota" || route?.status === "finalizada");
  const areAllStopsClosed = (route?: RouteItem | null) => Boolean(route && route.stops.length > 0 && route.stops.every(isStopClosed));
  const canCloseRoute = (route?: RouteItem | null) => Boolean(route && route.status !== "finalizada" && route.status !== "cancelada" && areAllStopsClosed(route));
  const missingWarehouseStops = (route: RouteItem) => route.stops
    .filter((stop) => stop.status === "falha" && !stop.warehouse_return_attachment_id)
    .sort(compareStopsBySequence);
  const localizedReasonLabel = (r: Reason) => (i18n.language === "pt-BR" && r.label_pt_br) ? r.label_pt_br : r.label;
  const reasonLabel = (id?: number | null) => {
    const r = reasons.find((r) => r.id === id);
    return r ? localizedReasonLabel(r) : "-";
  };
  const canEdit = hasRole("admin_global", "gestor_brasil", "operador_logistico");
  const canRegisterToll = hasRole("admin_global", "gestor_brasil", "operador_logistico", "motorista");
  const sortedRoutes = useMemo(() => [...routes].sort(compareRoutesByDueDate), [routes]);
  const visibleRoutes = useMemo(() => sortedRoutes.filter((route) => {
    if (routeFilter === "all") return true;
    if (routeFilter === "closed") return route.status === "finalizada";
    return route.status !== "finalizada" && route.status !== "cancelada";
  }), [routeFilter, sortedRoutes]);
  const visibleSelectedRoute = selectedRoute && visibleRoutes.some((route) => route.id === selectedRoute.id)
    ? selectedRoute
    : visibleRoutes[0] ?? null;
  const activeMapRoutes = visibleRoutes.filter((route) => route.status === "em_rota" || route.status === "finalizada");
  const mapRoutes = activeMapRoutes.length > 0 ? activeMapRoutes : visibleRoutes;
  const selectedRouteManifest = useMemo(
    () => manifests.find((manifest) => manifest.route_id === visibleSelectedRoute?.id) ?? null,
    [manifests, visibleSelectedRoute?.id],
  );
  const routeActions = (route: RouteItem): RouteAction[] => {
    const dock = route.dock_session;
    if (!dock?.arrival_cd_at) return [{ path: "arrive-cd", label: t("route.arrive_cd_short") }];
    if (!dock.dock_entry_at) return [{ path: "enter-dock", label: t("route.dock_short") }];
    if (!dock.loading_started_at) return [{ path: "loading-start", label: t("route.loading_start_short") }];
    if (!dock.loading_finished_at) return [{ path: "loading-finish", label: t("route.loading_finish_short") }];
    if (!dock.operator_released_at) return [{ path: "release", label: t("route.release") }];
    if (!dock.departure_cd_at) return [{ path: "depart", label: t("route.start"), primary: true }];
    if (canCloseRoute(route)) return [{ path: "close", label: t("route.close"), primary: true }];
    return [];
  };
  const routeStats = {
    planning: visibleRoutes.filter((r) => r.status === "planejada").length,
    loading: visibleRoutes.filter((r) => r.status === "em_carregamento" || r.status === "liberada").length,
    road: visibleRoutes.filter((r) => r.status === "em_rota").length,
    closed: visibleRoutes.filter((r) => r.status === "finalizada").length,
  };
  const visibleToolbarActions = visibleSelectedRoute ? routeActions(visibleSelectedRoute) : [];

  return (
    <div>
      <div className="page-header">
        <div>
          <h2>{t("nav.routes")}</h2>
          <p className="page-subtitle">{t("route.subtitle")}</p>
        </div>
        {canEdit && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-ghost" onClick={() => setImportOpen(true)}>{t("route.import")}</button>
            <button className="btn-primary btn-add" onClick={startNew}><span className="btn-add-symbol">+</span><span>{t("route.new")}</span></button>
          </div>
        )}
      </div>
      {importOpen && <ImportRoutesModal onClose={() => setImportOpen(false)} onImported={reload} />}

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      {editing !== null && (
        <form onSubmit={save} className="card-panel form-panel">
          <h3 style={{ marginTop: 0 }}>{editing === "new" ? t("route.new") : t("route.edit")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("route.code")}</span>
              <input className="input" list="route-code-suggestions" value={form.codigo_ut} placeholder={t("route.code_optional") ?? ""} onChange={(e) => setForm({ ...form, codigo_ut: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("route.date")}</span>
              <input type="date" className="input" required value={form.route_date} onChange={(e) => setForm({ ...form, route_date: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("route.origin")}</span>
              <input className="input" list="route-origin-suggestions" value={form.origin_name} onChange={(e) => setForm({ ...form, origin_name: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("rd.address")}</span>
              <input className="input" list="route-address-suggestions" value={form.origin_address} onChange={(e) => setForm({ ...form, origin_address: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("route.driver")}</span>
              <select className="input" value={form.driver_id} onChange={(e) => setForm({ ...form, driver_id: e.target.value })}>
                <option value="">-</option>
                {drivers.filter((d) => d.active).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("route.vehicle")}</span>
              <select className="input" value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}>
                <option value="">-</option>
                {vehicles.filter((v) => v.active).map((v) => <option key={v.id} value={v.id}>{v.plate}</option>)}
              </select>
            </label>
          </div>
          <SuggestionList id="route-code-suggestions" values={suggestions.codigo_ut} />
          <SuggestionList id="route-origin-suggestions" values={suggestions.origins} />
          <SuggestionList id="route-address-suggestions" values={suggestions.addresses} />
          <div style={{ marginTop: 12 }}>
            <button type="submit" className="btn-primary">{t("common.save")}</button>
            <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form>
      )}

      <div className={`planning-board${selectedRouteId ? " has-selected-route" : ""}${routeListExpanded ? " is-route-list-expanded" : ""}`}>
        <aside className="card-panel route-list-panel">
          <div className="route-list-head">
            <div>
              <strong>{t("route.routes_today")}</strong>
              <div className="route-meta">{visibleRoutes.length} {t("route.routes_count")}</div>
            </div>
            <div className="route-filter">
              {(["open", "closed", "all"] as RouteFilter[]).map((filter) => (
                <button
                  key={filter}
                  className={routeFilter === filter ? "is-active" : ""}
                  onClick={() => setRouteFilter(filter)}
                >
                  {t(`route_filter.${filter}`)}
                </button>
              ))}
            </div>
            <button type="button" className="route-list-close" onClick={() => setRouteListExpanded(false)}>×</button>
          </div>
          <div className="route-list">
            {visibleRoutes.length === 0 && <div className="empty-state">{t("dashboard.empty.routes")}</div>}
            {visibleRoutes.map((r, index) => (
              <article
                key={r.id}
                className={`route-card${visibleSelectedRoute?.id === r.id ? " is-selected" : ""}`}
                style={{ borderLeftColor: STATUS_COLOR[r.status] ?? "#12a386" }}
                onClick={() => { setSelectedRouteId(r.id); setRouteListExpanded(false); }}
              >
                <div className="route-card-top">
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <button className="route-code" onClick={(e) => { e.stopPropagation(); navigate(`/routes/${r.id}`); }}>{routeLabel(r)}</button>
                      {r.source === "fieldeas" ? (
                        <span title="Fieldeas" style={{
                          display: "inline-block", width: 10, height: 10, borderRadius: "50%",
                          background: "#0ea5e9", flexShrink: 0,
                          boxShadow: "0 0 0 3px rgba(14,165,233,0.25)",
                        }} />
                      ) : r.source === "automatico" ? (
                        <span title={t("route.source_automatic")} style={{
                          display: "inline-block", width: 10, height: 10, borderRadius: "50%",
                          background: "#16a34a", flexShrink: 0,
                          boxShadow: "0 0 0 3px rgba(22,163,74,0.25)",
                        }} />
                      ) : (
                        <span title={t("route.source_manual")} style={{ color: "#f59e0b", fontWeight: 800, fontSize: 15, lineHeight: 1 }}>*</span>
                      )}
                    </div>
                    <div className="route-meta">{t("route.customer")}: {routeCustomers(r)}</div>
                    <div className="route-meta">{r.fieldeas_description ?? r.origin_name ?? t("route.no_origin")} · {r.route_date}</div>
                    <div className="route-meta">{driverName(r.driver_id)} · {vehiclePlate(r.vehicle_id)}</div>
                  </div>
                  <span className="status-pill" style={{ background: STATUS_COLOR[r.status] ?? "#667085" }}>
                    {t(`route_status.${r.status}`, { defaultValue: r.status })}
                  </span>
                </div>
                <div className="route-meta">{r.stops.length} {t("route.deliveries")} · #{index + 1}</div>
                <div className="route-actions">
                  {canEdit && <button className="btn-mini" onClick={(e) => { e.stopPropagation(); startEdit(r); }}>{t("users.edit")}</button>}
                  {canRegisterToll && (
                    <button className="btn-icon toll" title={t("rd.add_toll")} onClick={(e) => { e.stopPropagation(); openToll(r.id); }}>
                      <TollIcon />
                    </button>
                  )}
                  {canRegisterToll && (
                    <button className="btn-icon km" title={t("rd.km_title")} onClick={(e) => { e.stopPropagation(); openKm(r); }}>
                      <KmIcon />
                    </button>
                  )}
                  {canEdit && !isRouteDeparted(r) && r.status !== "cancelada" && (
                    <button className="btn-mini" title={t("route.force_start")} onClick={(e) => { e.stopPropagation(); act(r.id, "force-start"); }}>
                      {t("route.force_start")}
                    </button>
                  )}
                  {routeActions(r).map((action) => (
                    <button
                      key={action.path}
                      className={action.primary ? "btn-mini action-primary" : "btn-mini"}
                      onClick={(e) => { e.stopPropagation(); act(r.id, action.path); }}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </aside>

        <section className="planning-main">
          <div className="card-panel map-panel">
            <div className="map-tabs"><span>{t("route.map")}</span><span>{t("route.satellite")}</span></div>
            <button type="button" className="route-list-toggle" onClick={() => setRouteListExpanded((value) => !value)}>
              <ListIcon />
              <span>{t("route.routes_today")}</span>
            </button>
            <RouteMap routes={mapRoutes} selectedRouteId={visibleSelectedRoute?.id ?? null} onSelectRoute={setSelectedRouteId} />
            <div className="map-summary">
              <strong>{mapRoutes.length}</strong> {t("route.visible_routes")} · <strong>{mapRoutes.reduce((acc, r) => acc + r.stops.length, 0)}</strong> {t("route.deliveries").toLowerCase()}
            </div>
          </div>

          <div className="card-panel delivery-panel">
            <div className="delivery-head">
              <div>
                <strong>{t("route.delivery_flow")}</strong>
                <div className="route-meta">
                  {visibleSelectedRoute ? `${routeLabel(visibleSelectedRoute)} · ${visibleSelectedRoute.stops.length} ${t("route.deliveries").toLowerCase()}` : t("route.select_route")}
                </div>
                {selectedRouteManifest && (
                  <div className="manifest-status">
                    <span>{selectedRouteManifest.original_filename}</span>
                    <strong>{t(`manifest_status.${selectedRouteManifest.status}`, { defaultValue: selectedRouteManifest.status })}</strong>
                  </div>
                )}
              </div>
              {visibleSelectedRoute && (
                <div className="route-toolbar">
                  {visibleToolbarActions.map((action) => (
                    <button
                      key={action.path}
                      className={action.primary ? "btn-primary" : "btn-ghost"}
                      onClick={() => act(visibleSelectedRoute.id, action.path)}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {visibleSelectedRoute && !isRouteDeparted(visibleSelectedRoute) && (
              <div className="flow-notice">{t("route.departure_required")}</div>
            )}
            <div className="delivery-list">
              {visibleSelectedRoute?.stops.length ? [...visibleSelectedRoute.stops].sort(compareStopsBySequence).map((stop, index) => (
                <article key={stop.id} className="delivery-item">
                  <div className="delivery-seq">{stop.sequence ?? index + 1}</div>
                  <div className="delivery-info">
                    <strong>{stop.customer_name}</strong>
                    <span>{stop.city ?? stop.customer_address ?? "-"}</span>
                    {stop.status === "falha" && <small>{t("rd.reason")}: {reasonLabel(stop.failure_reason_id)}</small>}
                  </div>
                  <span className={`stop-badge stop-${stop.status}`}>{t(`stop_status.${stop.status}`, { defaultValue: stop.status })}</span>
                  <div className="delivery-actions">
                    <button className="btn-mini" disabled={!isRouteDeparted(visibleSelectedRoute) || Boolean(stop.checkin_at) || isStopClosed(stop)} onClick={() => checkinStop(visibleSelectedRoute.id, stop)}>
                      {t("route.checkin")}
                    </button>
                    <button className="btn-mini" disabled={!isRouteDeparted(visibleSelectedRoute) || !stop.checkin_at || isStopClosed(stop)} onClick={() => deliverStop(visibleSelectedRoute.id, stop)}>
                      {stop.stop_type === "carga" ? t("route.loaded") : t("route.deliver")}
                    </button>
                    <button className="btn-mini danger" disabled={!isRouteDeparted(visibleSelectedRoute) || !stop.checkin_at || isStopClosed(stop)} onClick={() => openFail(visibleSelectedRoute.id, stop)}>
                      {t("rd.fail")}
                    </button>
                  </div>
                </article>
              )) : (
                <div className="empty-state">{t("route.no_deliveries")}</div>
              )}
            </div>
          </div>

          <div className="card-panel" style={{ overflow: "hidden" }}>
            <div className="ops-tabs">
              <div className="ops-tab">{t("route.to_plan")} <strong>{routeStats.planning}</strong></div>
              <div className="ops-tab">{t("route.loading_group")} <strong>{routeStats.loading}</strong></div>
              <div className="ops-tab">{t("route.on_route_group")} <strong>{routeStats.road}</strong></div>
              <div className="ops-tab">{t("route.closed_group")} <strong>{routeStats.closed}</strong></div>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("route.code")}</th>
                    <th>{t("route.customer")}</th>
                    <th>{t("route.date")}</th>
                    <th>{t("route.origin")}</th>
                    <th>{t("route.driver")}</th>
                    <th>{t("route.vehicle")}</th>
                    <th>{t("route.status")}</th>
                    <th>{t("route.deliveries")}</th>
                    <th>{t("users.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRoutes.map((r) => (
                    <tr key={r.id}>
                      <td><button className="route-code" onClick={() => navigate(`/routes/${r.id}`)}>{r.codigo_ut}</button></td>
                      <td>{routeCustomers(r)}</td>
                      <td>{r.route_date}</td>
                      <td>{r.origin_name ?? "-"}</td>
                      <td>{driverName(r.driver_id)}</td>
                      <td>{vehiclePlate(r.vehicle_id)}</td>
                      <td>
                        <span className="status-pill" style={{ background: STATUS_COLOR[r.status] ?? "#667085" }}>
                          {t(`route_status.${r.status}`, { defaultValue: r.status })}
                        </span>
                      </td>
                      <td>{r.stops.length}</td>
                      <td>
                        {canEdit && <button className="btn-mini" onClick={() => startEdit(r)}>{t("users.edit")}</button>}
                        {routeActions(r).map((action) => (
                          <button
                            key={action.path}
                            className={action.primary ? "btn-mini action-primary" : "btn-mini"}
                            onClick={() => act(r.id, action.path)}
                          >
                            {action.label}
                          </button>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>

      {proofStop && (
        <div className="modal-backdrop" onClick={() => { if (!proofSaving) setProofStop(null); }}>
          <form className="modal-card modal-card-compact" onClick={(e) => e.stopPropagation()} onSubmit={confirmDeliveryProof}>
            <h3>{t("rd.delivery_proof_title")}</h3>
            <p>{proofStop.stop.customer_name}</p>
            {proofError && <p className="modal-error">{proofError}</p>}
            <div className="field">
              <span>{t("rd.delivery_proof_label")}</span>
              <UploadField
                accept="image/*,application/pdf"
                capture="environment"
                required
                file={proofFile}
                label={t("common.attach_proof")}
                selectedLabel={t("common.selected_file")}
                onChange={setProofFile}
              />
            </div>
            <div className="modal-actions">
              <button type="submit" className="btn-primary" disabled={proofSaving}>{proofSaving ? t("rd.sending") : t("rd.confirm_delivery")}</button>
              <button type="button" className="btn-ghost" disabled={proofSaving} onClick={() => setProofStop(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {warehouseBatchRoute && (
        <div className="modal-backdrop" onClick={() => { if (!warehouseBatchSaving) setWarehouseBatchRoute(null); }}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={confirmWarehouseBatch}>
            <h3>{t("rd.warehouse_batch_title")}</h3>
            <p>{warehouseBatchRoute.codigo_ut} · {t("rd.warehouse_batch_hint")}</p>
            {warehouseBatchError && <p className="modal-error">{warehouseBatchError}</p>}
            <div className="warehouse-proof-list">
              {missingWarehouseStops(warehouseBatchRoute).map((stop) => {
                const inputId = `warehouse-proof-${warehouseBatchRoute.id}-${stop.id}`;
                return (
                  <div className="field warehouse-proof-item" key={stop.id}>
                    <span>
                      {t("rd.stop_label")} {stop.sequence ?? stop.id} · {stop.customer_name}
                      {stop.return_type && <small>{t("rd.return_label")} {stop.return_type}{stop.return_type === "parcial" && stop.returned_quantity ? ` · qtd. ${stop.returned_quantity}` : ""}</small>}
                    </span>
                    <UploadField
                      id={inputId}
                      name={`warehouse_return_proof_${stop.id}`}
                      accept="image/*,application/pdf"
                      capture="environment"
                      required
                      file={warehouseBatchFiles[stop.id] ?? null}
                      label={t("common.attach_proof")}
                      selectedLabel={t("common.selected_file")}
                      onChange={(file) => setWarehouseBatchFiles((current) => ({ ...current, [stop.id]: file }))}
                    />
                  </div>
                );
              })}
            </div>
            <div className="modal-actions">
              <button type="submit" className="btn-primary" disabled={warehouseBatchSaving}>
                {warehouseBatchSaving ? t("rd.sending") : t("rd.send_close_route")}
              </button>
              <button type="button" className="btn-ghost" disabled={warehouseBatchSaving} onClick={() => setWarehouseBatchRoute(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {failStop && (
        <div className="modal-backdrop" onClick={() => setFailStop(null)}>
          <form className="modal-card modal-card-compact" onClick={(e) => e.stopPropagation()} onSubmit={confirmFail}>
            <h3>{t("rd.fail_title")}</h3>
            <p>{failStop.stop.customer_name}</p>
            <label className="field">
              <span>{t("rd.reason")}</span>
              <select className="input" required value={failForm.reason_id} onChange={(e) => setFailForm({ ...failForm, reason_id: e.target.value })}>
                <option value="">{t("rd.reason_placeholder")}</option>
                {reasons.map((reason) => <option key={reason.id} value={reason.id}>{localizedReasonLabel(reason)}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("rd.return_type_label")}</span>
              <select className="input" value={failForm.return_type} onChange={(e) => setFailForm({ ...failForm, return_type: e.target.value as "total" | "parcial" })}>
                <option value="total">{t("rd.return_total")}</option>
                <option value="parcial">{t("rd.return_partial")}</option>
              </select>
            </label>
            {failForm.return_type === "parcial" && (
              <label className="field">
                <span>{t("rd.returned_quantity_label")}</span>
                <input
                  className="input"
                  type="number"
                  min="0"
                  step="any"
                  required
                  value={failForm.returned_quantity}
                  onChange={(e) => setFailForm({ ...failForm, returned_quantity: e.target.value })}
                />
              </label>
            )}
            <div className="field">
              <span>{t("rd.fail_proof_label")}</span>
              <UploadField
                accept="image/*,application/pdf"
                capture="environment"
                required
                file={failFile}
                label={t("common.attach_proof")}
                selectedLabel={t("common.selected_file")}
                onChange={setFailFile}
              />
            </div>
            <label className="field">
              <span>{t("rd.notes")}</span>
              <textarea className="input" style={{ minHeight: 72, resize: "vertical" }} value={failForm.notes} onChange={(e) => setFailForm({ ...failForm, notes: e.target.value })} />
            </label>
            <div className="modal-actions">
              <button type="submit" className="btn-primary danger-bg">{t("rd.confirm_fail")}</button>
              <button type="button" className="btn-ghost" onClick={() => setFailStop(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {kmRouteId != null && (
        <div className="modal-backdrop" onClick={() => setKmRouteId(null)}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={saveKm}>
            <h3>{t("rd.km_title")}</h3>
            {kmRoute && (
              <p style={{ margin: "0 0 12px", fontSize: 13, color: "#64748b" }}>
                {kmRoute.codigo_ut} · {kmRoute.fieldeas_description ?? kmRoute.origin_name ?? ""}
              </p>
            )}
            <label className="field">
              <span>{t("rd.km_outbound")}</span>
              <input
                className="input"
                type="number"
                step="1"
                min="0"
                placeholder="0"
                value={kmForm.km_outbound_informed}
                onChange={(e) => setKmForm({ ...kmForm, km_outbound_informed: e.target.value })}
              />
            </label>
            <label className="field">
              <span>{t("rd.km_return")}</span>
              <input
                className="input"
                type="number"
                step="1"
                min="0"
                placeholder="0"
                value={kmForm.km_return_informed}
                onChange={(e) => setKmForm({ ...kmForm, km_return_informed: e.target.value })}
              />
            </label>
            {kmRoute && (kmRoute.km_outbound_informed != null || kmRoute.km_return_informed != null) && (
              <p style={{ fontSize: 12, color: "#64748b", margin: "4px 0 8px" }}>
                {t("rd.km_outbound")}: {kmRoute.km_outbound_informed ?? "—"} km &nbsp;·&nbsp;
                {t("rd.km_return")}: {kmRoute.km_return_informed ?? "—"} km
              </p>
            )}
            <div className="modal-actions">
              <button type="submit" className="btn-primary">{t("common.save")}</button>
              <button type="button" className="btn-ghost" onClick={() => setKmRouteId(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {tollRouteId != null && (
        <div className="modal-backdrop" onClick={() => setTollRouteId(null)}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={addToll}>
            <h3>{t("rd.add_toll")}</h3>
            {tollRoute && tollRoute.tolls && tollRoute.tolls.length > 0 && (
              <ul className="toll-list">
                {tollRoute.tolls.map((tl) => (
                  <li key={tl.id} className={tl.direction}>
                    <span className="toll-dir">{t(`rd.toll_${tl.direction}`)}</span>
                    <span className="toll-amount">{formatCurrency(tl.amount, i18n.language)}</span>
                    {canEdit && <button type="button" className="btn-icon" title={t("rd.delete")} onClick={() => deleteToll(tl.id)}>×</button>}
                  </li>
                ))}
              </ul>
            )}
            <label className="field">
              <span>{t("rd.toll_direction")}</span>
              <select className="input" value={tollForm.direction} onChange={(e) => setTollForm({ ...tollForm, direction: e.target.value as "ida" | "volta" })}>
                <option value="ida">{t("rd.toll_ida")}</option>
                <option value="volta">{t("rd.toll_volta")}</option>
              </select>
            </label>
            <label className="field">
              <span>{t("rd.toll_amount")}</span>
              <input className="input" type="number" step="0.01" min="0" value={tollForm.amount} onChange={(e) => setTollForm({ ...tollForm, amount: e.target.value })} />
            </label>
            <div className="modal-actions">
              <button type="submit" className="btn-primary">{t("common.save")}</button>
              <button type="button" className="btn-ghost" onClick={() => setTollRouteId(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

    </div>
  );
}

function TollIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <text x="12" y="16" textAnchor="middle" fontSize="11" fill="currentColor" stroke="none" fontWeight="700">€</text>
    </svg>
  );
}

function KmIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <text x="12" y="16" textAnchor="middle" fontSize="9" fill="currentColor" stroke="none" fontWeight="700">km</text>
    </svg>
  );
}

function ListIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 6h13" />
      <path d="M8 12h13" />
      <path d="M8 18h13" />
      <path d="M3 6h.01" />
      <path d="M3 12h.01" />
      <path d="M3 18h.01" />
    </svg>
  );
}

function UploadField({
  id,
  name,
  accept,
  capture,
  required,
  file,
  label,
  selectedLabel,
  onChange,
}: {
  id?: string;
  name?: string;
  accept: string;
  capture?: "environment";
  required?: boolean;
  file: File | null;
  label: string;
  selectedLabel: string;
  onChange: (file: File | null) => void;
}) {
  return (
    <label className="upload-pill" htmlFor={id}>
      <input
        id={id}
        name={name}
        type="file"
        accept={accept}
        capture={capture}
        required={required}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      <span className="upload-pill-icon"><UploadIcon /></span>
      <span>{file ? `${selectedLabel}: ${file.name}` : label}</span>
    </label>
  );
}

function UploadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v12" />
      <path d="m7 8 5-5 5 5" />
      <path d="M5 21h14" />
    </svg>
  );
}

function compareRoutesByDueDate(a: RouteItem, b: RouteItem) {
  const aDue = routeDueTime(a);
  const bDue = routeDueTime(b);
  if (aDue !== bDue) return aDue - bDue;
  return a.id - b.id;
}

function routeDueTime(route: RouteItem) {
  const stopDue = route.stops
    .map((stop) => dueTime(stop.planned_date, stop.planned_time))
    .filter((value) => Number.isFinite(value));
  if (stopDue.length) return Math.min(...stopDue);
  return dueTime(route.route_date, "");
}

function dueTime(date?: string | null, time?: string | null) {
  if (!date) return Number.MAX_SAFE_INTEGER;
  const normalizedTime = time ? time.slice(0, 5) : "23:59";
  const value = new Date(`${date}T${normalizedTime}:00`).getTime();
  return Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER;
}

function compareStopsBySequence(a: Stop, b: Stop) {
  return (a.sequence ?? 0) - (b.sequence ?? 0) || a.id - b.id;
}

function SuggestionList({ id, values }: { id: string; values: string[] }) {
  return (
    <datalist id={id}>
      {values.map((value) => <option key={`${id}-${value}`} value={value} />)}
    </datalist>
  );
}

interface ImportResult {
  rows_read: number; routes_created: number; routes_updated: number;
  stops_created: number; stops_updated: number; revenues_created: number; errors: string[];
}

function ImportRoutesModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");

  async function downloadTemplate() {
    const { data } = await api.get("/routes-import/template.xlsx", { responseType: "blob" });
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = "modelo-importacao-rotas.xlsx";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function upload() {
    if (!file) return;
    setUploading(true); setError(""); setResult(null);
    const payload = new FormData();
    payload.set("file", file);
    try {
      const { data } = await api.post<ImportResult>("/routes-import/upload", payload);
      setResult(data);
      onImported();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("route.import_error"));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => { if (!uploading) onClose(); }}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h3>{t("route.import")}</h3>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("route.import_help")}</p>
        {error && <p className="modal-error">{error}</p>}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <button type="button" className="btn-ghost" onClick={downloadTemplate}>{t("route.import_download_template")}</button>
          <label className="upload-pill" htmlFor="routes-import-file">
            <input id="routes-import-file" type="file" accept=".xlsx,.csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <span>{file ? file.name : t("route.import_pick_file")}</span>
          </label>
        </div>
        {result && (
          <div style={{ marginTop: 12, background: "var(--soft)", borderRadius: 8, padding: 12, fontSize: 13 }}>
            <p style={{ margin: 0 }}>
              {t("route.import_summary", {
                created: result.routes_created, updated: result.routes_updated,
                stops: result.stops_created + result.stops_updated, revenues: result.revenues_created,
              })}
            </p>
            {result.errors.length > 0 && (
              <ul style={{ margin: "6px 0 0", color: "#b91c1c" }}>
                {result.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="btn-ghost" onClick={onClose} disabled={uploading}>{t("common.cancel")}</button>
          <button type="button" className="btn-primary" onClick={upload} disabled={!file || uploading}>
            {uploading ? t("route.import_uploading") : t("route.import_upload")}
          </button>
        </div>
      </div>
    </div>
  );
}

function routeLabel(route: { codigo_ut: string; route_date: string }) {
  const [year, month, day] = route.route_date.split("-");
  return year && month && day ? `${day}/${month} - ${route.codigo_ut}` : route.codigo_ut;
}

function formatCurrency(value: number, locale = "pt-BR") {
  return new Intl.NumberFormat(locale, { style: "currency", currency: locale === "pt-BR" ? "BRL" : "EUR" }).format(value);
}

function formatApiError(detail: unknown) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: any) => item?.msg ?? String(item)).join("; ");
  return String(detail);
}

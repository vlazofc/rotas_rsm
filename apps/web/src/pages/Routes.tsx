import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../services/api";
import { importRoutes } from "../services/importRoutes";
import { applyTimemark } from "../services/timemark";
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
  proof_attachment_id?: number | null;
  warehouse_return_attachment_id?: number | null;
}
interface RouteItem {
  id: number; branch_id: number; codigo_ut: string; route_date: string; origin_name?: string | null;
  origin_address?: string | null; driver_id?: number | null; vehicle_id?: number | null;
  status: string; stops: Stop[]; dock_session?: DockSession | null;
  source?: string; fieldeas_description?: string | null; fieldeas_sync_at?: string | null;
  empty_truck_photo_attachment_id?: number | null;
  loaded_return_photo_attachment_id?: number | null;
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
type RouteFilter = "open" | "backlog" | "closed" | "all";
type RouteView = "map" | "assignments";
interface Driver { id: number; name: string; active: boolean; }
interface Vehicle { id: number; plate: string; active: boolean; }
interface Reason { id: number; code: string; label: string; label_pt_br?: string | null; active: boolean; }

interface SearchableAssignmentSelectProps {
  value: string;
  query: string;
  placeholder: string;
  emptyLabel: string;
  options: { id: number; label: string }[];
  onQueryChange: (query: string, selectedId: string) => void;
}

function SearchableAssignmentSelect({ value, query, placeholder, emptyLabel, options, onQueryChange }: SearchableAssignmentSelectProps) {
  const [open, setOpen] = useState(false);
  const normalizedQuery = query.trim().toLocaleLowerCase("pt-BR");
  const filtered = options.filter((option) => option.label.toLocaleLowerCase("pt-BR").includes(normalizedQuery)).slice(0, 30);

  return (
    <div className="assignment-search-select">
      <input
        required
        className="input"
        type="search"
        placeholder={placeholder}
        autoComplete="off"
        value={query}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onChange={(event) => {
          const nextQuery = event.target.value;
          const exact = options.find((option) => option.label.localeCompare(nextQuery.trim(), "pt-BR", { sensitivity: "accent" }) === 0);
          onQueryChange(nextQuery, exact ? String(exact.id) : "");
          setOpen(true);
        }}
      />
      {value && <span className="assignment-selected-mark" aria-label="Selecionado">✓</span>}
      {open && (
        <div className="assignment-search-options" role="listbox">
          {filtered.length ? filtered.map((option) => (
            <button
              key={option.id}
              type="button"
              className={String(option.id) === value ? "selected" : ""}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => { onQueryChange(option.label, String(option.id)); setOpen(false); }}
            >
              {option.label}
              {String(option.id) === value && <span>✓</span>}
            </button>
          )) : <p>{emptyLabel}</p>}
        </div>
      )}
    </div>
  );
}

const STATUS_COLOR: Record<string, string> = {
  planejada: "#64748b", em_carregamento: "#0ea5e9", liberada: "#a855f7",
  em_rota: "#16a34a", finalizada: "#f97316", cancelada: "#ef4444",
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
  const routeSelectionKey = `adimax:selected-route:${user?.id ?? "session"}`;
  const [routes, setRoutes] = useState<RouteItem[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [selectedRouteId, setSelectedRouteId] = useState<number | null>(() => {
    const stored = Number(localStorage.getItem(`adimax:selected-route:${user?.id ?? "session"}`));
    return Number.isInteger(stored) && stored > 0 ? stored : null;
  });
  const [proofStop, setProofStop] = useState<{ routeId: number; stop: Stop } | null>(null);
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [proofError, setProofError] = useState("");
  const [proofSaving, setProofSaving] = useState(false);
  const [processingEvidence, setProcessingEvidence] = useState<string | null>(null);
  const [processingMessage, setProcessingMessage] = useState("");
  const [failStop, setFailStop] = useState<{ routeId: number; stop: Stop } | null>(null);
  const [failFile, setFailFile] = useState<File | null>(null);
  const [failForm, setFailForm] = useState({ reason_id: "", notes: "", return_type: "total" as "total" | "parcial", returned_quantity: "" });
  const [warehouseBatchRoute, setWarehouseBatchRoute] = useState<RouteItem | null>(null);
  const [warehouseBatchFiles, setWarehouseBatchFiles] = useState<Record<number, File | null>>({});
  const [warehouseBatchError, setWarehouseBatchError] = useState("");
  const [warehouseBatchSaving, setWarehouseBatchSaving] = useState(false);
  const [emptyTruckFile, setEmptyTruckFile] = useState<File | null>(null);
  const [releasePhotoRoute, setReleasePhotoRoute] = useState<RouteItem | null>(null);
  const [releasePhotoFile, setReleasePhotoFile] = useState<File | null>(null);
  const [releasePhotoError, setReleasePhotoError] = useState("");
  const [releasePhotoSaving, setReleasePhotoSaving] = useState(false);
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("open");
  const [routeView, setRouteView] = useState<RouteView>("map");
  const [assignmentDate, setAssignmentDate] = useState("");
  const [assignmentSearch, setAssignmentSearch] = useState("");
  const [routeListExpanded, setRouteListExpanded] = useState(false);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [assigning, setAssigning] = useState<RouteItem | null>(null);
  const [assignmentForm, setAssignmentForm] = useState({ driver_id: "", vehicle_id: "" });
  const [assignmentDriverQuery, setAssignmentDriverQuery] = useState("");
  const [assignmentVehicleQuery, setAssignmentVehicleQuery] = useState("");
  const [form, setForm] = useState({ codigo_ut: "", route_date: "", origin_name: "", origin_address: "", driver_id: "", vehicle_id: "" });
  const [error, setError] = useState("");
  const [importOpen, setImportOpen] = useState(false);

  const reload = () => api.get<RouteItem[]>("/routes").then((r) => setRoutes(r.data)).catch(() => { setError("Sem conexão para atualizar as rotas. Exibindo os últimos dados recebidos."); });
  useEffect(() => {
    reload();
    api.get("/drivers").then((r) => setDrivers(r.data)).catch(() => setDrivers([]));
    api.get("/vehicles").then((r) => setVehicles(r.data)).catch(() => setVehicles([]));
    api.get("/failure-reasons", { params: { only_active: true } }).then((r) => setReasons(r.data)).catch(() => setReasons([]));
  }, []);

  // Mantém a lista de rotas atualizada sem depender de F5,
  // já que outros utilizadores podem alterar o status em tempo real.
  usePolling(reload, REFRESH_INTERVAL_MS);

  useEffect(() => {
    if (!routes.length) return;
    if (selectedRouteId && routes.some((route) => route.id === selectedRouteId)) return;
    const stored = Number(localStorage.getItem(routeSelectionKey));
    const storedRoute = routes.find((route) => route.id === stored);
    const activeRoute = routes.find((route) => route.status === "em_rota");
    setSelectedRouteId((storedRoute ?? activeRoute ?? routes[0]).id);
  }, [routes, routeSelectionKey, selectedRouteId]);

  useEffect(() => {
    if (selectedRouteId) localStorage.setItem(routeSelectionKey, String(selectedRouteId));
  }, [routeSelectionKey, selectedRouteId]);

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
    if (path === "release" && route && !route.loaded_return_photo_attachment_id) {
      setReleasePhotoRoute(route);
      setReleasePhotoFile(null);
      setReleasePhotoError("");
      return;
    }
    if (path === "close" && route) {
      const missing = missingWarehouseStops(route);
      if (missing.length > 0 || !route.empty_truck_photo_attachment_id) {
        setWarehouseBatchRoute(route);
        setWarehouseBatchFiles(Object.fromEntries(missing.map((stop) => [stop.id, null])));
        setEmptyTruckFile(null);
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
    if (!proofStop || proofSaving || processingEvidence) return;
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
      const endpoint=isStopClosed(proofStop.stop)?"replacement-proof":"deliver-with-proof";
      const response=await api.post<RouteItem>(`/routes/${proofStop.routeId}/stops/${proofStop.stop.id}/${endpoint}`, payload);
      setRoutes(current=>current.map(route=>route.id===response.data.id?response.data:route));
      setProofStop(null);
      setProofFile(null);
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
    if (!warehouseBatchRoute.empty_truck_photo_attachment_id && !emptyTruckFile) {
      setWarehouseBatchError(t("rd.empty_truck_photo_required"));
      return;
    }
    setWarehouseBatchSaving(true);
    try {
      for (const stop of missing) {
        const payload = new FormData();
        payload.set("proof", warehouseBatchFiles[stop.id] as File);
        await api.post(`/routes/${warehouseBatchRoute.id}/stops/${stop.id}/warehouse-return-proof`, payload);
      }
      if (!warehouseBatchRoute.empty_truck_photo_attachment_id && emptyTruckFile) {
        const tagged = await applyTimemark(emptyTruckFile, {routeCode:warehouseBatchRoute.codigo_ut,driverName:user?.role==="motorista"?user.name:drivers.find(d=>d.id===warehouseBatchRoute.driver_id)?.name,vehiclePlate:vehicles.find(v=>v.id===warehouseBatchRoute.vehicle_id)?.plate});
        const payload = new FormData(); payload.set("photo", tagged);
        await api.post(`/routes/${warehouseBatchRoute.id}/empty-truck-photo`, payload);
      }
      await api.post(`/routes/${warehouseBatchRoute.id}/close`);
      setWarehouseBatchRoute(null);
      setWarehouseBatchFiles({});
      setEmptyTruckFile(null);
      reload();
    } catch (err: any) {
      setWarehouseBatchError(formatApiError(err?.response?.data?.detail) ?? t("route.action_error"));
    } finally {
      setWarehouseBatchSaving(false);
    }
  }

  async function confirmReleasePhoto(e: React.FormEvent) {
    e.preventDefault();
    if (!releasePhotoRoute || !releasePhotoFile) { setReleasePhotoError(t("rd.loaded_photo_required")); return; }
    setReleasePhotoSaving(true); setReleasePhotoError("");
    try {
      const tagged = await applyTimemark(releasePhotoFile, {routeCode:releasePhotoRoute.codigo_ut,driverName:user?.role==="motorista"?user.name:drivers.find(d=>d.id===releasePhotoRoute.driver_id)?.name,vehiclePlate:vehicles.find(v=>v.id===releasePhotoRoute.vehicle_id)?.plate});
      const payload = new FormData(); payload.set("photo", tagged);
      await api.post(`/routes/${releasePhotoRoute.id}/loaded-return-photo`, payload);
      await api.post(`/routes/${releasePhotoRoute.id}/release`);
      setReleasePhotoRoute(null); setReleasePhotoFile(null); reload();
    } catch (err: any) { setReleasePhotoError(formatApiError(err?.response?.data?.detail) ?? t("route.action_error")); }
    finally { setReleasePhotoSaving(false); }
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

  function startAssignment(route: RouteItem) {
    setError("");
    setAssignmentForm({ driver_id: route.driver_id ? String(route.driver_id) : "", vehicle_id: route.vehicle_id ? String(route.vehicle_id) : "" });
    setAssignmentDriverQuery(drivers.find((driver) => driver.id === route.driver_id)?.name ?? "");
    setAssignmentVehicleQuery(vehicles.find((vehicle) => vehicle.id === route.vehicle_id)?.plate ?? "");
    setAssigning(route);
  }

  async function saveAssignment(e: React.FormEvent) {
    e.preventDefault();
    if (!assigning) return;
    setError("");
    try {
      await api.put(`/routes/${assigning.id}/assignment`, {
        driver_id: assignmentForm.driver_id ? Number(assignmentForm.driver_id) : null,
        vehicle_id: assignmentForm.vehicle_id ? Number(assignmentForm.vehicle_id) : null,
      });
      setAssigning(null); await reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível salvar a escala."); }
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
  const canPlanRoute = (route: RouteItem) => hasRole("admin_global") || (route.status === "planejada" && route.route_date >= new Date().toISOString().slice(0, 10));
  const canUseManagementView = hasRole("admin_global", "gestor_brasil", "operador_logistico");

  useEffect(() => {
    if (!canUseManagementView && routeView !== "map") setRouteView("map");
  }, [canUseManagementView, routeView]);
  const sortedRoutes = useMemo(() => [...routes].sort(compareRoutesByDueDate), [routes]);
  const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const visibleRoutes = useMemo(() => sortedRoutes.filter((route) => {
    if (routeFilter === "all") return true;
    if (routeFilter === "closed") return route.status === "finalizada";
    if (route.status === "finalizada" || route.status === "cancelada") return false;
    return routeFilter === "backlog" ? route.route_date < today : route.route_date >= today;
  }), [routeFilter, sortedRoutes, today]);
  const visibleSelectedRoute = selectedRoute && visibleRoutes.some((route) => route.id === selectedRoute.id)
    ? selectedRoute
    : visibleRoutes[0] ?? null;
  // A rota selecionada nunca pode desaparecer do mapa por causa do status.
  // Todas as rotas do filtro atual permanecem disponíveis e as demais são
  // Ao selecionar uma carga, o mapa mostra exclusivamente suas paradas.
  // Isso impede pontos de outras cargas de interferirem no foco e na leitura.
  const mapRoutes = visibleSelectedRoute ? [visibleSelectedRoute] : visibleRoutes;
  const routeActions = (route: RouteItem): RouteAction[] => {
    const dock = route.dock_session;
    if (!dock?.arrival_cd_at) return [{ path: "arrive-cd", label: t("route.arrive_cd_short") }];
    if (!dock.operator_released_at || !dock.departure_cd_at) return [{ path: "release", label: t("route.release"), primary: true }];
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
  const assignmentRoutes = useMemo(() => visibleRoutes.filter((route) => {
    if (assignmentDate && route.route_date !== assignmentDate) return false;
    const query = assignmentSearch.trim().toLocaleLowerCase("pt-BR");
    if (!query) return true;
    return [route.codigo_ut, route.origin_name, route.fieldeas_description, routeCustomers(route), driverName(route.driver_id), vehiclePlate(route.vehicle_id)]
      .some((value) => String(value ?? "").toLocaleLowerCase("pt-BR").includes(query));
  }), [visibleRoutes, assignmentDate, assignmentSearch, drivers, vehicles]);
  const assignedRoutes = assignmentRoutes.filter((route) => route.driver_id && route.vehicle_id).length;

  return (
    <div>
      <div className="page-header">
        <div>
          <h2>{t("nav.routes")}</h2>
          <p className="page-subtitle">{t("route.subtitle")}</p>
        </div>
        <div className="route-header-actions">
          {canUseManagementView && (
            <div className={`route-view-switch is-${routeView}`} role="group" aria-label="Visualização de rotas">
              <span className="route-view-slider" aria-hidden="true" />
              <button className={routeView === "map" ? "is-active" : ""} onClick={() => setRouteView("map")} aria-pressed={routeView === "map"}>
                <MapViewIcon /><span>Mapa</span>
              </button>
              <button className={routeView === "assignments" ? "is-active" : ""} onClick={() => setRouteView("assignments")} aria-pressed={routeView === "assignments"}>
                <AssignmentIcon /><span>Gestão</span>
              </button>
            </div>
          )}
          {canEdit && <>
            <button className="btn-ghost" onClick={() => setImportOpen(true)}>{t("route.import")}</button>
            <button className="btn-primary btn-add" onClick={startNew}><span className="btn-add-symbol">+</span><span>{t("route.new")}</span></button>
          </>}
        </div>
      </div>
      {importOpen && <ImportRoutesModal onClose={() => setImportOpen(false)} onImported={reload} />}

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      {editing !== null && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
        <form onSubmit={save} className="modal-card" onClick={(event) => event.stopPropagation()}>
          <h3 style={{ marginTop: 0 }}>{editing === "new" ? t("route.new") : t("route.edit")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("route.code")}</span>
              <input className="input" value={form.codigo_ut} placeholder={t("route.code_optional") ?? ""} onChange={(e) => setForm({ ...form, codigo_ut: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("route.date")}</span>
              <input type="date" className="input" required value={form.route_date} onChange={(e) => setForm({ ...form, route_date: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("route.origin")}</span>
              <input className="input" value={form.origin_name} onChange={(e) => setForm({ ...form, origin_name: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("rd.address")}</span>
              <input className="input" value={form.origin_address} onChange={(e) => setForm({ ...form, origin_address: e.target.value })} />
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
          <div style={{ marginTop: 12 }}>
            <button type="submit" className="btn-primary">{t("common.save")}</button>
            <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form>
        </div>
      )}

      {assigning && (
        <div className="modal-backdrop" onClick={() => setAssigning(null)}>
          <form onSubmit={saveAssignment} className="modal-card assignment-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-heading"><div><h3>Escalar rota {assigning.codigo_ut}</h3><p>Selecione somente recursos previamente cadastrados.</p></div><button type="button" className="modal-close" onClick={() => setAssigning(null)}>×</button></div>
            <label className="field assignment-combobox">
              <span>Motorista</span>
              <SearchableAssignmentSelect
                value={assignmentForm.driver_id}
                query={assignmentDriverQuery}
                placeholder="Pesquise pelo nome do motorista"
                emptyLabel="Nenhum motorista encontrado."
                options={drivers.filter((driver) => driver.active).map((driver) => ({ id: driver.id, label: driver.name }))}
                onQueryChange={(query, selectedId) => {
                  setAssignmentDriverQuery(query);
                  setAssignmentForm((current) => ({ ...current, driver_id: selectedId }));
                }}
              />
              {assignmentDriverQuery && !assignmentForm.driver_id && <small>Selecione um motorista cadastrado na lista.</small>}
            </label>
            <label className="field assignment-combobox">
              <span>Veículo</span>
              <SearchableAssignmentSelect
                value={assignmentForm.vehicle_id}
                query={assignmentVehicleQuery}
                placeholder="Pesquise pela placa do veículo"
                emptyLabel="Nenhum veículo encontrado."
                options={vehicles.filter((vehicle) => vehicle.active).map((vehicle) => ({ id: vehicle.id, label: vehicle.plate }))}
                onQueryChange={(value, selectedId) => {
                  const query = value.toUpperCase();
                  setAssignmentVehicleQuery(query);
                  setAssignmentForm((current) => ({ ...current, vehicle_id: selectedId }));
                }}
              />
              {assignmentVehicleQuery && !assignmentForm.vehicle_id && <small>Selecione um veículo cadastrado na lista.</small>}
            </label>
            <small className="assignment-hint">Motorista e veículo podem ser atribuídos separadamente.</small>
            <div className="modal-actions"><button type="button" className="btn-ghost" onClick={() => setAssigning(null)}>Cancelar</button><button type="submit" className="btn-primary">Confirmar escala</button></div>
          </form>
        </div>
      )}

      {routeView === "assignments" && canUseManagementView ? (
        <section className="assignment-board">
          <div className="card-panel assignment-filters">
            <div>
              <strong>Painel de atribuições</strong>
              <span>Planeje motoristas e veículos e acompanhe o andamento das rotas.</span>
              <div className="route-filter" role="group" aria-label="Filtrar rotas por situação" style={{ marginTop: 10, flexWrap: "wrap", width: "fit-content" }}>
                {(["open", "backlog", "closed", "all"] as RouteFilter[]).map(filter => (
                  <button type="button" key={filter} aria-pressed={routeFilter === filter} className={routeFilter === filter ? "is-active" : ""} onClick={() => setRouteFilter(filter)}>
                    {filter === "backlog" ? "Backlog" : t(`route_filter.${filter}`)}
                  </button>
                ))}
              </div>
            </div>
            <label><span>Data programada</span><input className="input" type="date" value={assignmentDate} onChange={(e) => setAssignmentDate(e.target.value)} /></label>
            <label className="assignment-search"><span>Buscar</span><input className="input" placeholder="Rota, cliente, motorista ou veículo" value={assignmentSearch} onChange={(e) => setAssignmentSearch(e.target.value)} /></label>
          </div>
          <div className="assignment-summary">
            <div><strong>{assignmentRoutes.length}</strong><span>Rotas listadas</span></div>
            <div className="is-success"><strong>{assignedRoutes}</strong><span>Atribuídas</span></div>
            <div className="is-warning"><strong>{assignmentRoutes.length - assignedRoutes}</strong><span>Pendentes</span></div>
            <div><strong>{routeStats.road}</strong><span>Em rota</span></div>
          </div>
          <div className="card-panel assignment-table-card">
            <div className="assignment-table-head"><div><strong>Lista de rotas</strong><span>{assignmentRoutes.length} resultado(s)</span></div></div>
            <div className="table-wrap">
              <table className="data-table assignment-table">
                <thead><tr><th>Rota</th><th>Cliente / origem</th><th>Data</th><th>Motorista</th><th>Veículo</th><th>Andamento</th><th>Entregas</th><th>Ações</th></tr></thead>
                <tbody>
                  {assignmentRoutes.map((route) => (
                    <tr key={route.id}>
                      <td><button className="route-code" onClick={() => navigate(`/routes/${route.id}`)}>{route.codigo_ut}</button></td>
                      <td><strong>{routeCustomers(route)}</strong><small>{route.origin_name ?? "Origem não informada"}</small></td>
                      <td>{formatDate(route.route_date)}</td>
                      <td className={!route.driver_id ? "assignment-pending" : ""}>{route.driver_id ? driverName(route.driver_id) : "A definir"}</td>
                      <td className={!route.vehicle_id ? "assignment-pending" : ""}>{route.vehicle_id ? vehiclePlate(route.vehicle_id) : "A definir"}</td>
                      <td><span className="status-pill" style={{ background: STATUS_COLOR[route.status] ?? "#667085" }}>{t(`route_status.${route.status}`, { defaultValue: route.status })}</span></td>
                      <td>{route.stops.length}</td>
                      <td><div className="assignment-actions"><button className="btn-mini" onClick={() => { setSelectedRouteId(route.id); setRouteView("map"); }}>Ver rota</button>{canPlanRoute(route) && <button className="btn-mini assignment-scale" onClick={() => startAssignment(route)}><AssignmentIcon /> Escalar</button>}</div></td>
                    </tr>
                  ))}
                  {!assignmentRoutes.length && <tr><td colSpan={8} className="empty-state">Nenhuma rota encontrada para os filtros selecionados.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : <div className={`planning-board${selectedRouteId ? " has-selected-route" : ""}${routeListExpanded ? " is-route-list-expanded" : ""}`}>
        <aside className="card-panel route-list-panel">
          <div className="route-list-head">
            <div>
              <strong>{t("route.routes_today")}</strong>
              <div className="route-meta">{visibleRoutes.length} {t("route.routes_count")}</div>
            </div>
            <div className="route-filter route-list-filters">
              {(["open", "backlog", "closed", "all"] as RouteFilter[]).map((filter) => (
                <button
                  key={filter}
                  className={routeFilter === filter ? "is-active" : ""}
                  onClick={() => setRouteFilter(filter)}
                >
                  {filter === "backlog" ? "Backlog" : t(`route_filter.${filter}`)}
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
                      <button className="route-code" onClick={(e) => { e.stopPropagation(); setSelectedRouteId(r.id); navigate(`/routes/${r.id}`); }}>{routeLabel(r)}</button>
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
                  {canEdit && canPlanRoute(r) && (
                    <button
                      className="btn-mini assignment-scale assignment-scale-icon"
                      title="Escalar"
                      aria-label="Escalar"
                      onClick={(e) => { e.stopPropagation(); startAssignment(r); }}
                    >
                      <AssignmentIcon />
                    </button>
                  )}
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
                    {isStopClosed(stop)&&!stop.proof_attachment_id&&<button className="btn-mini action-primary" onClick={() => {setProofFile(null);setProofError("");setProofStop({routeId:visibleSelectedRoute.id,stop});}}>Enviar nova foto</button>}
                    <button className="btn-mini" disabled={!isRouteDeparted(visibleSelectedRoute) || Boolean(stop.checkin_at) || isStopClosed(stop)} onClick={() => checkinStop(visibleSelectedRoute.id, stop)}>
                      {t("route.checkin")}
                    </button>
                    <button className="btn-mini" disabled={!isRouteDeparted(visibleSelectedRoute) || isStopClosed(stop)} onClick={() => deliverStop(visibleSelectedRoute.id, stop)}>
                      {stop.stop_type === "carga" ? t("route.loaded") : t("route.deliver")}
                    </button>
                    <button className="btn-mini danger" disabled={!isRouteDeparted(visibleSelectedRoute) || isStopClosed(stop)} onClick={() => openFail(visibleSelectedRoute.id, stop)}>
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
      </div>}

      {proofStop && (
        <div className="modal-backdrop" onClick={() => { if (!proofSaving && !processingEvidence) setProofStop(null); }}>
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
                processing={processingEvidence==="proof"}
                processingMessage={processingMessage}
                onChange={async (file) => {
                  if(!file){setProofFile(null);return;}
                  setProcessingEvidence("proof");setProofFile(null);
                  try{const proofRoute=routes.find(r=>r.id===proofStop.routeId);setProofFile(await applyTimemark(file,{routeCode:proofRoute?.codigo_ut,stopSequence:proofStop.stop.sequence,address:[proofStop.stop.customer_address,proofStop.stop.city].filter(Boolean).join(" · "),driverName:user?.role==="motorista"?user.name:drivers.find(d=>d.id===proofRoute?.driver_id)?.name,vehiclePlate:vehicles.find(v=>v.id===proofRoute?.vehicle_id)?.plate},stage=>setProcessingMessage(stage==="location"?"Obtendo localização…":stage==="image"?"Aplicando registro na foto…":"Finalizando imagem…")))}
                  catch{setProofError("Não foi possível preparar a foto. Tente novamente.")}
                  finally{setProcessingEvidence(null);setProcessingMessage("")}
                }}
              />
            </div>
            <div className="modal-actions">
              <button type="submit" className="btn-primary" disabled={proofSaving||processingEvidence==="proof"}>{proofSaving ? "Enviando comprovante…" : processingEvidence==="proof" ? "Preparando foto…" : t("rd.confirm_delivery")}</button>
              <button type="button" className="btn-ghost" disabled={proofSaving||processingEvidence==="proof"} onClick={() => setProofStop(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {releasePhotoRoute && (
        <div className="modal-backdrop" onClick={() => { if (!releasePhotoSaving) setReleasePhotoRoute(null); }}>
          <form className="modal-card modal-card-compact" onClick={(e) => e.stopPropagation()} onSubmit={confirmReleasePhoto}>
            <h3>{t("rd.loaded_return_photo_label")}</h3>
            <p>{releasePhotoRoute.codigo_ut} · {t("rd.loaded_photo_release_hint")}</p>
            {releasePhotoError && <p className="modal-error">{releasePhotoError}</p>}
            <UploadField id={`loaded-photo-${releasePhotoRoute.id}`} name="loaded_photo" accept="image/*" capture="environment" required file={releasePhotoFile} label={t("common.attach_proof")} selectedLabel={t("common.selected_file")} onChange={setReleasePhotoFile}/>
            <div className="modal-actions">
              <button type="submit" className="btn-primary" disabled={releasePhotoSaving}>{releasePhotoSaving ? t("rd.sending") : t("rd.send_and_release")}</button>
              <button type="button" className="btn-ghost" disabled={releasePhotoSaving} onClick={() => setReleasePhotoRoute(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {warehouseBatchRoute && (
        <div className="modal-backdrop" onClick={() => { if (!warehouseBatchSaving) setWarehouseBatchRoute(null); }}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={confirmWarehouseBatch}>
            <h3>{t("rd.close_route_title")}</h3>
            <p>{warehouseBatchRoute.codigo_ut} · {t("rd.close_route_photo_hint")}</p>
            {warehouseBatchError && <p className="modal-error">{warehouseBatchError}</p>}
            {!warehouseBatchRoute.empty_truck_photo_attachment_id && (
              <div className="field warehouse-proof-item">
                <span>{t("rd.empty_truck_photo_label")}</span>
                <UploadField id={`empty-truck-${warehouseBatchRoute.id}`} name="empty_truck_photo" accept="image/*" capture="environment" required file={emptyTruckFile} label={t("common.attach_proof")} selectedLabel={t("common.selected_file")} onChange={setEmptyTruckFile}/>
              </div>
            )}
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
                      onChange={async (file) => { const marked = file ? await applyTimemark(file,{routeCode:warehouseBatchRoute.codigo_ut,stopSequence:stop.sequence,address:[stop.customer_address,stop.city].filter(Boolean).join(" · "),driverName:user?.role==="motorista"?user.name:drivers.find(d=>d.id===warehouseBatchRoute.driver_id)?.name,vehiclePlate:vehicles.find(v=>v.id===warehouseBatchRoute.vehicle_id)?.plate}) : null; setWarehouseBatchFiles((current) => ({ ...current, [stop.id]: marked })); }}
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
                onChange={async (file) => {const failRoute=routes.find(r=>r.id===failStop.routeId);setFailFile(file ? await applyTimemark(file,{routeCode:failRoute?.codigo_ut,stopSequence:failStop.stop.sequence,address:[failStop.stop.customer_address,failStop.stop.city].filter(Boolean).join(" · "),driverName:user?.role==="motorista"?user.name:drivers.find(d=>d.id===failRoute?.driver_id)?.name,vehiclePlate:vehicles.find(v=>v.id===failRoute?.vehicle_id)?.plate}) : null)}}
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

    </div>
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

function MapViewIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z"/><path d="M9 3v15M15 6v15"/></svg>;
}

function AssignmentIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/></svg>;
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
  processing=false,
  processingMessage="Preparando foto…",
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
  processing?: boolean;
  processingMessage?: string;
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
        disabled={processing}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      <span className="upload-pill-icon"><UploadIcon /></span>
      <span>{processing ? processingMessage : file ? `${selectedLabel}: ${file.name}` : label}</span>
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

interface ImportResult {
  rows_read: number; routes_created: number; routes_updated: number;
  stops_created: number; stops_updated: number; routes_optimized: number; routing_errors: number; route_ids: number[]; errors: string[];
}

function ImportRoutesModal({ onClose, onImported }: { onClose: () => void; onImported: () => void | Promise<void> }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!result) return;
    const timer = window.setTimeout(onClose, 3000);
    return () => window.clearTimeout(timer);
  }, [result, onClose]);

  async function downloadTemplate() {
    const { data } = await api.get("/routes-import/template.xlsx", { responseType: "blob" });
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = "modelo-importacao-gestao-adimax.xlsx";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function upload() {
    if (!file) return;
    setUploading(true); setError(""); setResult(null);
    const payload = new FormData();
    payload.set("file", file);
    try {
      const data = await importRoutes<ImportResult>(payload);
      if (!data) return;
      await onImported();
      setResult(data);
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
        <p style={{ color: "var(--muted)", fontSize: 13 }}>{result ? "Importação concluída. Esta janela fechará automaticamente em 3 segundos." : t("route.import_help")}</p>
        {error && <p className="modal-error">{error}</p>}
        {!result && <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <button type="button" className="btn-ghost" onClick={downloadTemplate}>{t("route.import_download_template")}</button>
          <label className="upload-pill" htmlFor="routes-import-file">
            <input id="routes-import-file" type="file" accept=".xlsx,.xlsm,.csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <span>{file ? file.name : t("route.import_pick_file")}</span>
          </label>
        </div>}
        {result && (
          <div style={{ marginTop: 12, background: "var(--soft)", borderRadius: 8, padding: 12, fontSize: 13 }}>
            <p style={{ margin: 0 }}>{result.routes_created} rota(s) criada(s), {result.routes_updated} atualizada(s) e {result.stops_created + result.stops_updated} parada(s) processada(s). Os mapas estão sendo atualizados em segundo plano.</p>
            {result.errors.length > 0 && (
              <ul style={{ margin: "6px 0 0", color: "#b91c1c" }}>
                {result.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
          </div>
        )}
        <div className="modal-actions">
          {result ? <button autoFocus type="button" className="btn-primary" onClick={onClose}>OK</button> : <>
          <button type="button" className="btn-ghost" onClick={onClose} disabled={uploading}>{t("common.cancel")}</button>
          <button type="button" className="btn-primary" onClick={upload} disabled={!file || uploading}>
            {uploading ? t("route.import_uploading") : t("route.import_upload")}
          </button>
          </>}
        </div>
      </div>
    </div>
  );
}

function routeLabel(route: { codigo_ut: string; route_date: string }) {
  const [year, month, day] = route.route_date.split("-");
  return year && month && day ? `${day}/${month} - ${route.codigo_ut}` : route.codigo_ut;
}

function formatDate(value: string) {
  const [year, month, day] = value.split("-");
  return year && month && day ? `${day}/${month}/${year}` : value;
}

function formatApiError(detail: unknown) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: any) => item?.msg ?? String(item)).join("; ");
  return String(detail);
}

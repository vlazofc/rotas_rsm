import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import api from "../services/api";
import {appConfirm} from "../components/AppDialog";
import { applyTimemark } from "../services/timemark";
import { useAuth } from "../context/AuthContext";
import { usePolling } from "../hooks/usePolling";

const REFRESH_INTERVAL_MS = 20000;

// Best-effort: usada para preencher a última posição conhecida do veículo
// (route_events/checkins), consumida pela busca de prestadores por raio de km.
function getCurrentPosition(): Promise<{ latitude: number; longitude: number } | null> {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) { resolve(null); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 60000 },
    );
  });
}

interface StopOperation {
  id: number; fieldeas_code?: string | null; order_id?: string | null;
  client_name?: string | null; pallets_provided?: number | null;
  weight_provided?: number | null; status?: string | null;
}
interface Stop {
  id: number; sequence: number; customer_name: string; customer_address?: string | null;
  city?: string | null; planned_date?: string | null; planned_time?: string | null;
  weight_kg?: number | null; pallets?: number | null; order_number?: string | null;
  status: string; failure_reason_id?: number | null; checkin_at?: string | null; delivered_at?: string | null;
  proof_attachment_id?: number | null; proof_filename?: string | null; proof_url?: string | null;
  return_type?: "total" | "parcial" | null; returned_quantity?: number | null;
  warehouse_return_attachment_id?: number | null; warehouse_return_filename?: string | null; warehouse_return_url?: string | null;
  fieldeas_internal_code?: string | null; stop_type?: string | null;
  postal_code?: string | null; province?: string | null;
  operations?: StopOperation[];
  delivery_protocol?: string | null; client_name?: string | null; invoice_value?: number | null;
}
interface Dock {
  arrival_cd_at?: string | null; dock_entry_at?: string | null; loading_started_at?: string | null;
  loading_finished_at?: string | null; operator_released_at?: string | null; departure_cd_at?: string | null;
  loading_minutes?: number | null; total_cd_minutes?: number | null;
}
interface RouteData {
  id: number; codigo_ut: string; route_date: string; origin_name?: string | null;
  origin_address?: string | null; driver_id?: number | null; vehicle_id?: number | null;
  status: string; stops: Stop[]; dock_session?: Dock | null;
  source?: string; fieldeas_description?: string | null; fieldeas_sync_at?: string | null;
  vehicle_requested?: string | null; vehicle_sent?: string | null;
  helper_assigned?: boolean | null; tracked?: boolean | null;
  driver_payment_amount?: number | null; driver_payment_notes?: string | null;
  empty_truck_photo_attachment_id?: number | null; empty_truck_photo_url?: string | null;
  loaded_return_photo_attachment_id?: number | null; loaded_return_photo_url?: string | null;
}
interface Driver { id: number; name: string; employment_type?: "proprio" | "agregado"; daily_rate?: number | null; }
interface Vehicle { id: number; plate: string; vehicle_type_code?: string | null; vehicle_type_label?: string | null; }
interface Reason { id: number; code: string; label: string; label_pt_br?: string | null; active: boolean; }

const STATUS_COLOR: Record<string, string> = {
  planejada: "#64748b", em_carregamento: "#0ea5e9", liberada: "#a855f7",
  em_rota: "#16a34a", finalizada: "#334155", cancelada: "#ef4444",
};
const STOP_COLOR: Record<string, string> = {
  pendente: "#64748b", em_rota: "#0ea5e9", entregue: "#16a34a", falha: "#ef4444", devolvido: "#f59e0b",
};

const EMPTY_STOP = { customer_name: "", customer_address: "", city: "", planned_date: "", planned_time: "", stop_type:"" as ""|"carga"|"descarga", weight_kg: "", pallets: "", order_number: "" };

export default function RouteDetail() {
  const { t, i18n } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, hasRole } = useAuth();
  const [route, setRoute] = useState<RouteData | null>(null);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [vehicleTypes, setVehicleTypes] = useState<{code: string; label: string}[]>([]);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [proofStop, setProofStop] = useState<Stop | null>(null);
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [proofError, setProofError] = useState("");
  const [proofSaving, setProofSaving] = useState(false);
  const [failStop, setFailStop] = useState<Stop | null>(null);
  const [failFile, setFailFile] = useState<File | null>(null);
  const [failForm, setFailForm] = useState({ reason_id: "", notes: "", return_type: "total" as "total" | "parcial", returned_quantity: "" });
  const [warehouseStop, setWarehouseStop] = useState<Stop | null>(null);
  const [warehouseFile, setWarehouseFile] = useState<File | null>(null);
  const [uploadingClosingPhoto, setUploadingClosingPhoto] = useState<"empty-truck-photo" | "loaded-return-photo" | null>(null);
  const [routeCorrectionOpen, setRouteCorrectionOpen] = useState(false);
  const [routeCorrection, setRouteCorrection] = useState({ status: "", reset_dock_flow: false, reset_all_stops: false, arrival_cd_at: "", operator_released_at: "", departure_cd_at: "", justification: "" });
  const [stopCorrection, setStopCorrection] = useState<Stop | null>(null);
  const [stopCorrectionForm, setStopCorrectionForm] = useState({
    status: "",
    clear_checkin: false,
    clear_delivery: false,
    clear_failure: false,
    clear_proofs: false,
    failure_reason_id: "",
    return_type: "",
    returned_quantity: "",
    justification: "",
  });
  const [editHeader, setEditHeader] = useState(false);
  const [header, setHeader] = useState({ origin_name: "", origin_address: "", route_date: "", driver_id: "", vehicle_id: "", status: "", status_justification: "", vehicle_requested: "", vehicle_sent: "", helper_assigned: false, tracked: false, driver_payment_amount: "", driver_payment_notes: "" });
  const [editingStop, setEditingStop] = useState<"new" | number | null>(null);
  const [stopForm, setStopForm] = useState({ ...EMPTY_STOP });
  const [error, setError] = useState("");
  const [modalError, setModalError] = useState("");
  const [expandedOperations, setExpandedOperations] = useState<Record<number, boolean>>({});
  const [optimizing, setOptimizing] = useState(false);
  const [tenantFeatures, setTenantFeatures] = useState({ feature_route_optimization: true, feature_km_calculation: true });
  useEffect(() => {
    api.get("/tenants/me").then((r) => setTenantFeatures({
      feature_route_optimization: r.data.feature_route_optimization ?? true,
      feature_km_calculation: r.data.feature_km_calculation ?? true,
    })).catch(() => {});
  }, []);

  const reload = () => api.get(`/routes/${id}`).then((r) => setRoute(r.data)).catch(() => {
    // Em refresh de fundo, não sobrepõe a tela já carregada com mensagem de erro.
    setRoute((prev) => { if (prev === null) setError(t("rd.load_error")); return prev; });
  });

  useEffect(() => {
    reload();
    api.get("/drivers").then((r) => setDrivers(r.data)).catch(() => {});
    api.get("/vehicles").then((r) => setVehicles(r.data)).catch(() => {});
    api.get("/vehicle-types", { params: { only_active: true } }).then(r => setVehicleTypes(r.data)).catch(() => {});
    api.get("/failure-reasons").then((r) => setReasons(r.data)).catch(() => {});
  }, [id]);

  // Mantém os dados da rota e das paradas atualizados sem exigir F5,
  // já que outros utilizadores (motorista, operador) podem alterar o status em paralelo.
  usePolling(reload, REFRESH_INTERVAL_MS);

  if (!route) return <p>{error || t("common.loading")}</p>;

  const driverName = (i?: number | null) => drivers.find((d) => d.id === i)?.name ?? "—";
  const vehiclePlate = (i?: number | null) => vehicles.find((v) => v.id === i)?.plate ?? "—";
  const salvesenPallets = (s: Stop) => {
    const fromOperations = (s.operations ?? []).reduce((sum, op) => sum + Number(op.pallets_provided ?? 0), 0);
    return fromOperations > 0 ? fromOperations : Number(s.pallets ?? 0);
  };
  const salvesenPalletsTotal = route.stops.reduce((sum, stop) => sum + salvesenPallets(stop), 0);
  const formatQty = (value: number) => value ? new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 2 }).format(value) : "—";
  const toggleOperations = (stopId: number) => {
    setExpandedOperations((current) => ({ ...current, [stopId]: !current[stopId] }));
  };

  function startEditHeader() {
    setHeader({
      origin_name: route!.origin_name ?? "", origin_address: route!.origin_address ?? "",
      route_date: route!.route_date ?? "", driver_id: route!.driver_id ? String(route!.driver_id) : "",
      vehicle_id: route!.vehicle_id ? String(route!.vehicle_id) : "", status: route!.status, status_justification: "",
      vehicle_requested: route!.vehicle_requested ?? "", vehicle_sent: route!.vehicle_sent ?? "",
      helper_assigned: route!.helper_assigned ?? false, tracked: route!.tracked ?? false,
      driver_payment_amount: route!.driver_payment_amount != null ? String(route!.driver_payment_amount) : "",
      driver_payment_notes: route!.driver_payment_notes ?? "",
    });
    setEditHeader(true);
  }
  async function saveHeader(e: React.FormEvent) {
    e.preventDefault(); setError("");
    try {
      await api.put(`/routes/${id}`, {
        origin_name: header.origin_name || null, origin_address: header.origin_address || null,
        route_date: header.route_date || null,
        driver_id: header.driver_id ? Number(header.driver_id) : null,
        vehicle_id: header.vehicle_id ? Number(header.vehicle_id) : null,
        vehicle_requested: header.vehicle_requested || null,
        vehicle_sent: header.vehicle_sent || null,
        helper_assigned: header.helper_assigned,
        tracked: header.tracked,
      });
      if (isAdmin && header.status && header.status !== route!.status) {
        if (header.status_justification.trim().length < 3) {
          setError(t("rd.status_justification_required"));
          return;
        }
        await api.post(`/routes/${id}/admin-correction`, {
          status: header.status,
          reset_dock_flow: false,
          reset_all_stops: false,
          justification: header.status_justification.trim(),
        });
      }
      setEditHeader(false); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.save_error")); }
  }

  async function dock(action: string) {
    setError("");
    try { await api.post(`/routes/${id}/${action}`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.action_error")); }
  }

  async function excludeRoute() {
    if (!await appConfirm(t("rd.exclude_confirm", { code: route!.codigo_ut }),{title:"Excluir rota",confirmLabel:"Sim, excluir",danger:true})) return;
    setError("");
    try { await api.delete(`/routes/${id}/exclude`); navigate("/routes"); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.action_error")); }
  }

  function startNewStop() { setError(""); setStopForm({ ...EMPTY_STOP }); setEditingStop("new"); }
  function startEditStop(s: Stop) {
    setError("");
    setStopForm({
      customer_name: s.customer_name, customer_address: s.customer_address ?? "", city: s.city ?? "",
      planned_date: s.planned_date ?? "", planned_time: (s.planned_time ?? "").slice(0, 5),
      stop_type:(s.stop_type??"") as ""|"carga"|"descarga",
      weight_kg: s.weight_kg != null ? String(s.weight_kg) : "", pallets: s.pallets != null ? String(s.pallets) : "",
      order_number: s.order_number ?? "",
    });
    setEditingStop(s.id);
  }
  async function saveStop(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const body = {
      customer_name: stopForm.customer_name, customer_address: stopForm.customer_address || null,
      city: stopForm.city || null, planned_date: stopForm.planned_date || null,
      planned_time: stopForm.planned_time || null,
      stop_type:stopForm.stop_type||null,
      weight_kg: stopForm.weight_kg ? Number(stopForm.weight_kg) : null,
      pallets: stopForm.pallets ? Number(stopForm.pallets) : null,
      order_number: stopForm.order_number || null,
    };
    try {
      if (editingStop === "new") await api.post(`/routes/${id}/stops`, body);
      else if (typeof editingStop === "number") await api.put(`/routes/${id}/stops/${editingStop}`, body);
      setEditingStop(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.save_error")); }
  }
  async function optimizeSequence() {
    setError(""); setOptimizing(true);
    try { await api.post(`/routes/${id}/optimize-sequence`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.action_error")); }
    finally { setOptimizing(false); }
  }
  async function deleteStop(s: Stop) {
    if (!await appConfirm(t("rd.confirm_delete", { name: s.customer_name }) ?? "",{title:"Excluir parada",confirmLabel:"Sim, excluir",danger:true})) return;
    try { await api.delete(`/routes/${id}/stops/${s.id}`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.save_error")); }
  }
  async function checkin(s: Stop) {
    try {
      const pos = await getCurrentPosition();
      await api.post(`/routes/${id}/stops/${s.id}/checkin`, pos ?? {});
      reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.action_error")); }
  }
  function openProof(s: Stop) {
    if (s.stop_type === "carga") {
      deliverLoaded(s);
      return;
    }
    setError(""); setProofError(""); setProofFile(null); setProofStop(s);
  }
  async function deliverLoaded(s: Stop) {
    try {
      const pos = await getCurrentPosition();
      await api.post(`/routes/${id}/stops/${s.id}/deliver`, { success: true, ...(pos ?? {}) });
      reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.action_error")); }
  }
  async function confirmDeliveryProof(e: React.FormEvent) {
    e.preventDefault();
    setProofError("");
    if (!proofFile) { setProofError(t("rd.delivery_proof_required")); return; }
    const payload = new FormData();
    payload.set("success", "true");
    payload.set("proof", proofFile);
    setProofSaving(true);
    try {
      const pos = await getCurrentPosition();
      if (pos) { payload.set("latitude", String(pos.latitude)); payload.set("longitude", String(pos.longitude)); }
      await api.post(`/routes/${id}/stops/${proofStop!.id}/deliver-with-proof`, payload);
      setProofStop(null); setProofFile(null); reload();
    } catch (err: any) { setProofError(formatApiError(err?.response?.data?.detail) ?? t("rd.action_error")); }
    finally { setProofSaving(false); }
  }
  function openFail(s: Stop) {
    setError(""); setFailFile(null); setFailForm({ reason_id: "", notes: "", return_type: "total", returned_quantity: "" }); setFailStop(s);
  }
  async function confirmFail(e: React.FormEvent) {
    e.preventDefault();
    if (!failForm.reason_id) { setError(t("rd.reason_required")); return; }
    if (failForm.return_type === "parcial" && !failForm.returned_quantity) {
      setError(t("rd.returned_quantity_required"));
      return;
    }
    if (!failFile) { setError(t("rd.fail_proof_required")); return; }
    const payload = new FormData();
    payload.set("success", "false");
    payload.set("proof", failFile);
    payload.set("failure_reason_id", failForm.reason_id);
    payload.set("return_type", failForm.return_type);
    if (failForm.returned_quantity) payload.set("returned_quantity", failForm.returned_quantity);
    if (failForm.notes.trim()) payload.set("notes", failForm.notes.trim());
    try {
      const pos = await getCurrentPosition();
      if (pos) { payload.set("latitude", String(pos.latitude)); payload.set("longitude", String(pos.longitude)); }
      await api.post(`/routes/${id}/stops/${failStop!.id}/deliver-with-proof`, payload);
      setFailStop(null); setFailFile(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.action_error")); }
  }
  function openWarehouseProof(s: Stop) {
    setError(""); setWarehouseFile(null); setWarehouseStop(s);
  }
  async function confirmWarehouseProof(e: React.FormEvent) {
    e.preventDefault();
    if (!warehouseFile) { setError(t("rd.warehouse_proof_required")); return; }
    const payload = new FormData();
    payload.set("proof", warehouseFile);
    try {
      await api.post(`/routes/${id}/stops/${warehouseStop!.id}/warehouse-return-proof`, payload);
      setWarehouseStop(null); setWarehouseFile(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.action_error")); }
  }
  async function uploadClosingPhoto(kind: "empty-truck-photo" | "loaded-return-photo", file: File) {
    setError("");
    const tagged = await applyTimemark(file, {
      routeCode: route!.codigo_ut,
      driverName: user?.role === "motorista" ? user.name : drivers.find((d) => d.id === route!.driver_id)?.name,
      vehiclePlate: vehicles.find((v) => v.id === route!.vehicle_id)?.plate,
    });
    const payload = new FormData();
    payload.set("photo", tagged);
    setUploadingClosingPhoto(kind);
    try {
      await api.post(`/routes/${id}/${kind}`, payload);
      reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("rd.action_error")); }
    finally { setUploadingClosingPhoto(null); }
  }
  function openRouteCorrection() {
    setError(""); setModalError("");
    const dock = route!.dock_session;
    setRouteCorrection({
      status: route!.status, reset_dock_flow: false, reset_all_stops: false,
      arrival_cd_at: toDatetimeLocal(dock?.arrival_cd_at),
      operator_released_at: toDatetimeLocal(dock?.operator_released_at),
      departure_cd_at: toDatetimeLocal(dock?.departure_cd_at),
      justification: "",
    });
    setRouteCorrectionOpen(true);
  }
  async function confirmRouteCorrection(e: React.FormEvent) {
    e.preventDefault();
    setModalError("");
    if (routeCorrection.justification.trim().length < 3) { setModalError(t("rd.correction_justification_required")); return; }
    try {
      await api.post(`/routes/${id}/admin-correction`, {
        status: routeCorrection.status || null,
        reset_dock_flow: routeCorrection.reset_dock_flow,
        reset_all_stops: routeCorrection.reset_all_stops,
        arrival_cd_at: fromDatetimeLocal(routeCorrection.arrival_cd_at),
        operator_released_at: fromDatetimeLocal(routeCorrection.operator_released_at),
        departure_cd_at: fromDatetimeLocal(routeCorrection.departure_cd_at),
        justification: routeCorrection.justification.trim(),
      });
      setRouteCorrectionOpen(false); reload();
    } catch (err: any) { setModalError(formatApiError(err?.response?.data?.detail) ?? t("rd.action_error")); }
  }
  function openStopCorrection(s: Stop) {
    setError(""); setModalError("");
    setStopCorrection(s);
    setStopCorrectionForm({
      status: s.status,
      clear_checkin: false,
      clear_delivery: false,
      clear_failure: false,
      clear_proofs: false,
      failure_reason_id: s.failure_reason_id ? String(s.failure_reason_id) : "",
      return_type: s.return_type ?? "",
      returned_quantity: s.returned_quantity != null ? String(s.returned_quantity) : "",
      justification: "",
    });
  }
  async function confirmStopCorrection(e: React.FormEvent) {
    e.preventDefault();
    if (!stopCorrection) return;
    setModalError("");
    if (stopCorrectionForm.justification.trim().length < 3) { setModalError(t("rd.correction_justification_required")); return; }
    try {
      await api.post(`/routes/${id}/stops/${stopCorrection.id}/admin-correction`, {
        status: stopCorrectionForm.status || null,
        clear_checkin: stopCorrectionForm.clear_checkin,
        clear_delivery: stopCorrectionForm.clear_delivery,
        clear_failure: stopCorrectionForm.clear_failure,
        clear_proofs: stopCorrectionForm.clear_proofs,
        failure_reason_id: stopCorrectionForm.failure_reason_id ? Number(stopCorrectionForm.failure_reason_id) : null,
        return_type: stopCorrectionForm.return_type || null,
        returned_quantity: stopCorrectionForm.returned_quantity ? Number(stopCorrectionForm.returned_quantity) : null,
        justification: stopCorrectionForm.justification.trim(),
      });
      setStopCorrection(null); reload();
    } catch (err: any) { setModalError(formatApiError(err?.response?.data?.detail) ?? t("rd.action_error")); }
  }

  const localizedReasonLabel = (r: Reason) => (i18n.language === "pt-BR" && r.label_pt_br) ? r.label_pt_br : r.label;
  const reasonLabel = (rid?: number | null) => {
    const r = reasons.find((r) => r.id === rid);
    return r ? localizedReasonLabel(r) : "—";
  };
  const activeReasons = reasons.filter((r) => r.active);
  const isAdmin = user?.role === "admin_global";
  const canRelease = hasRole("operador_logistico");
  const canClose = hasRole("gestor_brasil", "operador_logistico");
  const canOperateDock = hasRole("motorista", "operador_logistico");
  const canEditRoute = isAdmin;
  const isRouteDeparted = Boolean(route.dock_session?.departure_cd_at || route.status === "em_rota" || route.status === "finalizada");
  const isStopClosed = (s: Stop) => s.status === "entregue" || s.status === "falha" || s.status === "devolvido";
  const allStopsClosed = route.stops.length > 0 && route.stops.every(isStopClosed);
  const missingWarehouseProofs = route.stops.filter((s) => s.status === "falha" && !s.warehouse_return_attachment_id);
  const missingClosingPhotos = !route.empty_truck_photo_attachment_id;

  const d = route.dock_session;
  const dockSteps = [
    { action: "arrive-cd", label: t("route.arrive_cd"), field: "arrival_cd_at", allowed: canOperateDock },
    { action: "release", label: t("route.release"), field: "operator_released_at", allowed: canRelease },
    { action: "close", label: t("route.close"), field: null, allowed: canClose },
  ];
  const firstPendingDockAction = dockSteps.find((step) => {
    if (step.action === "close") return route.status !== "finalizada" && Boolean(d?.departure_cd_at) && allStopsClosed && !missingClosingPhotos;
    return !d?.[step.field as keyof Dock];
  })?.action;
  const isClosed = route.status === "finalizada" || route.status === "cancelada";

  return (
    <div>
      <button style={ghost} onClick={() => navigate("/routes")}>← {t("rd.back")}</button>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>{routeLabel(route)}</h2>
        <span style={{ background: STATUS_COLOR[route.status] ?? "#999", color: "#fff", padding: "2px 10px", borderRadius: 12, fontSize: 13 }}>
          {t(`route_status.${route.status}`, { defaultValue: route.status })}
        </span>
        {route.source === "fieldeas" ? (
          <span title="Fieldeas" style={{
            display: "inline-block", width: 12, height: 12, borderRadius: "50%",
            background: "#0ea5e9", flexShrink: 0,
            boxShadow: "0 0 0 4px rgba(14,165,233,0.25)",
          }} />
        ) : route.source === "manual" ? (
          <span title="Manual" style={{ color: "#f59e0b", fontWeight: 800, fontSize: 18, lineHeight: 1 }}>*</span>
        ) : null}
        {isAdmin && <button style={mini} onClick={openRouteCorrection}>{t("rd.admin_correction")}</button>}
        {(isAdmin || hasRole("gestor_brasil")) && (
          <button style={miniDanger} onClick={excludeRoute}>{t("rd.exclude_route")}</button>
        )}
      </div>
      {error && <p style={{ color: "#c00" }}>{error}</p>}

      {/* ---------- Cabeçalho ---------- */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <h3 style={{ marginTop: 0 }}>{t("rd.route_info")}</h3>
          {!editHeader && canEditRoute && <button style={mini} onClick={startEditHeader}>{t("users.edit")}</button>}
        </div>
        {!editHeader ? (
          <div style={infoGrid}>
            <Info label={t("route.code")} value={route.codigo_ut} />
            <Info label={t("route.customer")} value={routeCustomers(route)} />
            <Info label={t("route.date")} value={route.route_date} />
            <Info label={t("route.origin")} value={route.origin_name ?? "—"} />
            <Info label={t("rd.address")} value={route.origin_address ?? "—"} />
            <Info label={t("route.driver")} value={driverName(route.driver_id)} />
            <Info label={t("route.vehicle")} value={vehiclePlate(route.vehicle_id)} />
            {(route.vehicle_requested || route.vehicle_sent) && (
              <>
                <Info label={t("rd.vehicle_requested")} value={route.vehicle_requested ?? "—"} />
                <Info label={t("rd.vehicle_sent")} value={route.vehicle_sent ?? "—"} />
              </>
            )}
            {route.helper_assigned != null && (
              <Info label={t("rd.helper_assigned")} value={route.helper_assigned ? t("common.yes") : t("common.no")} />
            )}
            {route.tracked != null && (
              <Info label={t("rd.tracked")} value={route.tracked ? t("common.yes") : t("common.no")} />
            )}
            {route.source === "automatico" && (
              <Info label={t("rd.destination_main")} value={
                route.stops.length > 0
                  ? [route.stops[0].postal_code, route.stops[0].city].filter(Boolean).join(" — ")
                  : "—"
              } />
            )}
            {route.source === "fieldeas" && (
              <>
                <Info label={t("fieldeas.description")} value={route.fieldeas_description ?? "—"} />
                <Info label={t("fieldeas.sync_at")} value={fmt(route.fieldeas_sync_at)} />
              </>
            )}
          </div>
        ) : (
          <div className="modal-backdrop" onClick={() => setEditHeader(false)}>
          <form className="modal-card driver-modal" onSubmit={saveHeader} onClick={(event) => event.stopPropagation()}>
            <h3>{t("rd.route_info")}</h3>
            <div style={infoGrid}>
              <Field label={t("route.date")}><input type="date" style={input} value={header.route_date}
                onChange={(e) => setHeader({ ...header, route_date: e.target.value })} /></Field>
              <Field label={t("route.origin")}><input style={input} value={header.origin_name}
                onChange={(e) => setHeader({ ...header, origin_name: e.target.value })} /></Field>
              <Field label={t("rd.address")}><input style={input} value={header.origin_address}
                onChange={(e) => setHeader({ ...header, origin_address: e.target.value })} /></Field>
              <Field label={t("route.driver")}>
                <select style={input} value={header.driver_id} onChange={(e) => setHeader({ ...header, driver_id: e.target.value })}>
                  <option value="">—</option>
                  {drivers.map((dr) => <option key={dr.id} value={dr.id}>{dr.name}</option>)}
                </select>
              </Field>
              <Field label={t("route.vehicle")}>
                <select style={input} value={header.vehicle_id} onChange={(e) => {
                  const vehicleId = e.target.value;
                  const v = vehicles.find((v) => String(v.id) === vehicleId);
                  setHeader({ ...header, vehicle_id: vehicleId, vehicle_sent: v?.vehicle_type_label || v?.vehicle_type_code || header.vehicle_sent });
                }}>
                  <option value="">—</option>
                  {vehicles.map((v) => <option key={v.id} value={v.id}>{v.plate}</option>)}
                </select>
              </Field>
              {(["vehicle_requested", "vehicle_sent"] as const).map(field => <Field key={field} label={t(`rd.${field}`)}>
                <select style={input} value={header[field]} onChange={e => setHeader({ ...header, [field]: e.target.value })}>
                  <option value="">Selecione o tipo de veículo</option>
                  {header[field] && !vehicleTypes.some(type => type.label === header[field]) && <option value={header[field]}>{header[field]}</option>}
                  {vehicleTypes.map(type => <option key={type.code} value={type.label}>{type.label}</option>)}
                </select>
              </Field>)}
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--muted)" }}>
                <input type="checkbox" checked={header.helper_assigned} onChange={(e) => setHeader({ ...header, helper_assigned: e.target.checked })} />
                {t("rd.helper_assigned")}
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--muted)" }}>
                <input type="checkbox" checked={header.tracked} onChange={(e) => setHeader({ ...header, tracked: e.target.checked })} />
                {t("rd.tracked")}
              </label>
              {isAdmin && (
                <>
                  <Field label={t("rd.route_status_label")}>
                    <select style={input} value={header.status} onChange={(e) => setHeader({ ...header, status: e.target.value })}>
                      {["planejada", "em_carregamento", "liberada", "em_rota", "finalizada", "cancelada"].map((status) => (
                        <option key={status} value={status}>{t(`route_status.${status}`, { defaultValue: status })}</option>
                      ))}
                    </select>
                  </Field>
                  {header.status !== route.status && (
                    <Field label={t("rd.status_justification_label")}>
                      <textarea style={{ ...input, minHeight: 56 }} required value={header.status_justification}
                        onChange={(e) => setHeader({ ...header, status_justification: e.target.value })} />
                    </Field>
                  )}
                </>
              )}
            </div>
            <div style={{ marginTop: 12 }}>
              <button type="submit" style={primary}>{t("common.save")}</button>
              <button type="button" style={ghost} onClick={() => setEditHeader(false)}>{t("common.cancel")}</button>
            </div>
          </form>
          </div>
        )}
      </div>

      {/* ---------- Doca / CD (nível da rota) ---------- */}
      <div style={card}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h3 style={{ marginTop: 0 }}>{t("rd.dock_title")}</h3>
          {isAdmin && <button style={mini} onClick={openRouteCorrection}>{t("rd.edit_dock_times")}</button>}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {dockSteps.map((step) => {
            if (step.action === "close" && !allStopsClosed) return null;
            const completed = step.field ? Boolean(d?.[step.field as keyof Dock]) : isClosed;
            const loadedPhotoReady = step.action !== "release" || Boolean(route.loaded_return_photo_attachment_id);
            const enabled = !isClosed && !completed && firstPendingDockAction === step.action && step.allowed && loadedPhotoReady;
            return (
              <button
                key={step.action}
                style={enabled ? mini : disabledMini}
                disabled={!enabled}
                onClick={() => dock(step.action)}
                title={completed ? t("rd.step_done") : !step.allowed ? t("rd.no_permission") : t("rd.follow_sequence")}
              >
                {step.label}
              </button>
            );
          })}
        </div>
        {!isClosed && d?.arrival_cd_at && !d?.operator_released_at && (
          <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, padding: 10, marginBottom: 12 }}>
            <p style={{ margin: "0 0 8px", fontSize: 13, color: "#1d4ed8" }}>{t("rd.loaded_photo_release_hint")}</p>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>{t("rd.loaded_return_photo_label")}</div>
            {route.loaded_return_photo_url ? (
              <a href={route.loaded_return_photo_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>{t("rd.view_photo")}</a>
            ) : (
              <span style={{ fontSize: 13, color: "#b91c1c" }}>{t("rd.photo_pending")}</span>
            )}
            <div>
              <input
                style={input}
                type="file"
                accept="image/*"
                capture="environment"
                disabled={uploadingClosingPhoto !== null}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadClosingPhoto("loaded-return-photo", f); e.target.value = ""; }}
              />
            </div>
          </div>
        )}
        {!isClosed && allStopsClosed && (
          <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 8, padding: 10, marginBottom: 12 }}>
            <p style={{ margin: "0 0 8px", fontSize: 13, color: "#9a3412" }}>{t("rd.closing_photos_hint")}</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
              <div>
                <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>{t("rd.empty_truck_photo_label")}</div>
                {route.empty_truck_photo_url ? (
                  <a href={route.empty_truck_photo_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>{t("rd.view_photo")}</a>
                ) : (
                  <span style={{ fontSize: 13, color: "#b91c1c" }}>{t("rd.photo_pending")}</span>
                )}
                <div>
                  <input
                    style={input}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    disabled={uploadingClosingPhoto !== null}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadClosingPhoto("empty-truck-photo", f); e.target.value = ""; }}
                  />
                </div>
              </div>
            </div>
          </div>
        )}
        {isClosed && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 8, padding: "8px 12px", marginBottom: 12 }}>
            <span style={{ fontSize: 13, color: "#9a3412" }}>{t("rd.closed_notice")}</span>
            {isAdmin && (
              <button style={{ ...primary, background: "#ea580c", marginRight: 0 }} onClick={() => dock("reopen")}>
                {t("route.reopen")}
              </button>
            )}
          </div>
        )}
        <div style={infoGrid}>
          <Info label={t("route.arrive_cd")} value={fmt(d?.arrival_cd_at)} />
          <Info label={t("route.release")} value={fmt(d?.operator_released_at)} />
          <Info label={t("dashboard.avg_dock")} value={d?.loading_minutes != null ? String(d.loading_minutes) : "—"} />
          {isClosed && (route.empty_truck_photo_url || route.loaded_return_photo_url) && (
            <>
              <div>
                <div style={{ fontSize: 12, color: "#64748b" }}>{t("rd.empty_truck_photo_label")}</div>
                {route.empty_truck_photo_url ? <a href={route.empty_truck_photo_url} target="_blank" rel="noreferrer" style={{ fontSize: 14 }}>{t("rd.view_photo")}</a> : "—"}
              </div>
              <div>
                <div style={{ fontSize: 12, color: "#64748b" }}>{t("rd.loaded_return_photo_label")}</div>
                {route.loaded_return_photo_url ? <a href={route.loaded_return_photo_url} target="_blank" rel="noreferrer" style={{ fontSize: 14 }}>{t("rd.view_photo")}</a> : "—"}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ---------- Paradas ---------- */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ marginTop: 0 }}>{t("rd.stops")} ({route.stops.length})</h3>
          <div>
            {canEditRoute && route.stops.length > 1 && tenantFeatures.feature_route_optimization && (
              <button style={ghost} disabled={optimizing} onClick={optimizeSequence}>
                {optimizing ? t("rd.optimizing_sequence") : t("rd.optimize_sequence")}
              </button>
            )}
            {canEditRoute && <button style={primary} onClick={startNewStop}>{t("rd.add_stop")}</button>}
          </div>
        </div>
        {!isRouteDeparted && (
          <p style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, padding: 10, color: "#1d4ed8", fontSize: 13 }}>
            {t("route.departure_required")}
          </p>
        )}
        {missingWarehouseProofs.length > 0 && (
          <p style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 8, padding: 10, color: "#9a3412", fontSize: 13 }}>
            {t("rd.close_route_warehouse_warning", { list: missingWarehouseProofs.map((s) => s.sequence).join(", ") })}
          </p>
        )}

        {editingStop !== null && (
          <div className="modal-backdrop" onClick={() => setEditingStop(null)}>
          <form className="modal-card driver-modal" onSubmit={saveStop} onClick={(event) => event.stopPropagation()}>
            <h4 style={{ marginTop: 0 }}>{editingStop === "new" ? t("rd.add_stop") : t("rd.edit_stop")}</h4>
            <div style={infoGrid}>
              <Field label={t("rd.customer")}><input style={input} required value={stopForm.customer_name}
                onChange={(e) => setStopForm({ ...stopForm, customer_name: e.target.value })} /></Field>
              <Field label={t("rd.address")}><input style={input} value={stopForm.customer_address}
                onChange={(e) => setStopForm({ ...stopForm, customer_address: e.target.value })} /></Field>
              <Field label={t("rd.city")}><input style={input} value={stopForm.city}
                onChange={(e) => setStopForm({ ...stopForm, city: e.target.value })} /></Field>
              <Field label={t("route.deadline_date")}><input type="date" style={input} value={stopForm.planned_date}
                onChange={(e) => setStopForm({ ...stopForm, planned_date: e.target.value })} /></Field>
              <Field label={t("route.deadline_time")}><input type="time" style={input} value={stopForm.planned_time}
                onChange={(e) => setStopForm({ ...stopForm, planned_time: e.target.value })} /></Field>
              <Field label={t("route.weight")}><input type="number" step="any" style={input} value={stopForm.weight_kg}
                onChange={(e) => setStopForm({ ...stopForm, weight_kg: e.target.value })} /></Field>
              <Field label={t("route.order")}><input style={input} value={stopForm.order_number}
                onChange={(e) => setStopForm({ ...stopForm, order_number: e.target.value })} /></Field>
            </div>
            <div style={{ marginTop: 12 }}>
              <button type="submit" style={primary}>{t("common.save")}</button>
              <button type="button" style={ghost} onClick={() => setEditingStop(null)}>{t("common.cancel")}</button>
            </div>
          </form>
          </div>
        )}

        <div className="route-detail-table-wrap">
        <table style={table}>
          <thead>
            <tr style={{ background: "var(--soft)", textAlign: "left" }}>
              <th style={th}>#</th>
              <th style={th}>{t("rd.customer")}</th>
              <th style={th}>{t("rd.address")}</th>
              <th style={th}>{t("rd.city")}</th>
              <th style={th}>{t("route.status")}</th>
              <th style={th}>{t("users.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {route.stops.sort((a, b) => a.sequence - b.sequence).map((s) => {
              const operations = s.operations ?? [];
              const isOpsExpanded = Boolean(expandedOperations[s.id]);
              return (
              <Fragment key={s.id}>
                <tr style={{ borderTop: "1px solid var(--line)" }}>
                  <td style={td}>{s.sequence}</td>
                  <td style={td}>
                    {s.customer_name}
                    {s.fieldeas_internal_code && (
                      <div style={{ fontSize: 11, color: "#94a3b8" }}>#{s.fieldeas_internal_code}</div>
                    )}
                    {(s.delivery_protocol || s.order_number) && (
                      <div style={{ fontSize: 11, color: "#94a3b8" }}>
                        {t("rd.protocol", { defaultValue: "Protocolo" })}: {s.delivery_protocol || s.order_number}
                      </div>
                    )}
                  </td>
                  <td style={td}>{s.customer_address ?? "—"}</td>
                  <td style={td}>{s.city ?? "—"}</td>
                  <td style={td}>
                    <span style={{ background: STOP_COLOR[s.status] ?? "#999", color: "#fff", padding: "2px 8px", borderRadius: 12, fontSize: 12 }}>
                      {t(`stop_status.${s.status}`, { defaultValue: s.status })}
                    </span>
                    {s.status === "falha" && (
                      <>
                        <div style={{ fontSize: 12, color: "#b91c1c", marginTop: 4 }}>{reasonLabel(s.failure_reason_id)}</div>
                        <div style={{ fontSize: 12, color: "#92400e", marginTop: 3 }}>
                          {t("rd.return_label")} {s.return_type === "parcial" ? `${t("rd.return_partial").toLowerCase()} (${s.returned_quantity ?? "?"})` : t("rd.return_total").toLowerCase()}
                        </div>
                      </>
                    )}
                    {s.proof_url && (
                      <div style={{ marginTop: 4 }}>
                        <a href={s.proof_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>{t("rd.proof_delivery_link")}</a>
                      </div>
                    )}
                    {s.warehouse_return_url && (
                      <div style={{ marginTop: 4 }}>
                        <a href={s.warehouse_return_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>{t("rd.warehouse_return_link")}</a>
                      </div>
                    )}
                  </td>
                  <td style={td}>
                    {canEditRoute && <button style={mini} onClick={() => startEditStop(s)}>{t("users.edit")}</button>}
                    <button style={!isRouteDeparted || s.checkin_at || isClosed ? disabledMini : mini} disabled={!isRouteDeparted || Boolean(s.checkin_at) || isClosed} onClick={() => checkin(s)}>{t("route.checkin")}</button>
                    <button style={!isRouteDeparted || isStopClosed(s) || isClosed ? disabledMini : mini} disabled={!isRouteDeparted || isStopClosed(s) || isClosed} onClick={() => openProof(s)}>
                      {s.stop_type === "carga" ? t("route.loaded") : t("route.deliver")}
                    </button>
                    <button style={!isRouteDeparted || isStopClosed(s) || isClosed ? disabledMiniDanger : miniDanger} disabled={!isRouteDeparted || isStopClosed(s) || isClosed} onClick={() => openFail(s)}>{t("rd.fail")}</button>
                    {s.status === "falha" && !isClosed && (
                      <button style={!s.warehouse_return_attachment_id ? mini : disabledMini} disabled={Boolean(s.warehouse_return_attachment_id)} onClick={() => openWarehouseProof(s)}>
                        {t("rd.warehouse_return_link")}
                      </button>
                    )}
                    {isAdmin && <button style={mini} onClick={() => openStopCorrection(s)}>{t("rd.admin_correction")}</button>}
                    {canEditRoute && <button style={miniDanger} onClick={() => deleteStop(s)}>{t("rd.delete")}</button>}
                  </td>
                </tr>
                {operations.length > 0 && (
                  <tr key={`ops-${s.id}`} style={{ background: "var(--soft)" }}>
                    <td colSpan={6} style={{ padding: "6px 10px 10px 32px" }}>
                      <button type="button" style={opsToggle} aria-expanded={isOpsExpanded} onClick={() => toggleOperations(s.id)}>
                        <span style={opsToggleIcon}>{isOpsExpanded ? "-" : "+"}</span>
                        {t("fieldeas.operations")} ({operations.length})
                      </button>
                      {isOpsExpanded && (
                        <table style={opsTable}>
                          <colgroup>
                            <col style={{ width: "13%" }} />
                            <col style={{ width: "28%" }} />
                            <col style={{ width: "32%" }} />
                            <col style={{ width: "14%" }} />
                            <col style={{ width: "13%" }} />
                          </colgroup>
                          <thead>
                            <tr style={{ color: "#64748b" }}>
                              <th style={opsTh}>{t("fieldeas.op_code")}</th>
                              <th style={opsTh}>{t("fieldeas.op_order_id")}</th>
                              <th style={opsTh}>{t("fieldeas.op_client")}</th>
                              <th style={{ ...opsTh, textAlign: "center" }}>{t("fieldeas.op_pallets")}</th>
                              <th style={{ ...opsTh, textAlign: "center" }}>{t("route.status")}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {operations.map((op) => (
                              <tr key={op.id} style={{ borderTop: "1px solid var(--line)" }}>
                                <td style={opsCodeTd}>{op.fieldeas_code ?? "—"}</td>
                                <td style={opsCodeTd}>{op.order_id ?? "—"}</td>
                                <td style={opsTd}>{op.client_name ?? "—"}</td>
                                <td style={opsCenterTd}>{op.pallets_provided ?? "—"}</td>
                                <td style={opsCenterTd}>{op.status ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
            })}
          </tbody>
        </table>
        </div>
      </div>

      {/* ---------- Modal de correção admin da rota ---------- */}
      {routeCorrectionOpen && (
        <div style={overlay} onClick={() => setRouteCorrectionOpen(false)}>
          <form style={{ ...modal, width: 460 }} onClick={(e) => e.stopPropagation()} onSubmit={confirmRouteCorrection}>
            <h3 style={{ marginTop: 0 }}>{t("rd.correction_admin_route_title")}</h3>
            <p style={{ color: "#475569", fontSize: 14, marginTop: 0 }}>{route.codigo_ut}</p>
            {modalError && <p style={modalErrorStyle}>{modalError}</p>}
            <Field label={t("rd.route_status_label")}>
              <select style={input} value={routeCorrection.status} onChange={(e) => setRouteCorrection({ ...routeCorrection, status: e.target.value })}>
                {["planejada", "em_carregamento", "liberada", "em_rota", "finalizada", "cancelada"].map((status) => (
                  <option key={status} value={status}>{t(`route_status.${status}`, { defaultValue: status })}</option>
                ))}
              </select>
            </Field>
            <label style={{ ...field, flexDirection: "row", alignItems: "center", marginTop: 10 }}>
              <input type="checkbox" checked={routeCorrection.reset_dock_flow} onChange={(e) => setRouteCorrection({ ...routeCorrection, reset_dock_flow: e.target.checked })} />
              <span>{t("rd.reset_dock_flow")}</span>
            </label>
            <label style={{ ...field, flexDirection: "row", alignItems: "center", marginTop: 8 }}>
              <input type="checkbox" checked={routeCorrection.reset_all_stops} onChange={(e) => setRouteCorrection({ ...routeCorrection, reset_all_stops: e.target.checked })} />
              <span>{t("rd.reset_all_stops")}</span>
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
              <Field label={t("rd.dock_arrival_at_label")}>
                <input style={input} type="datetime-local" value={routeCorrection.arrival_cd_at}
                  onChange={(e) => setRouteCorrection({ ...routeCorrection, arrival_cd_at: e.target.value })} />
              </Field>
              <Field label={t("rd.dock_release_at_label")}>
                <input style={input} type="datetime-local" value={routeCorrection.operator_released_at}
                  onChange={(e) => setRouteCorrection({ ...routeCorrection, operator_released_at: e.target.value })} />
              </Field>
              <Field label={t("rd.dock_departure_at_label")}>
                <input style={input} type="datetime-local" value={routeCorrection.departure_cd_at}
                  onChange={(e) => setRouteCorrection({ ...routeCorrection, departure_cd_at: e.target.value })} />
              </Field>
            </div>
            <Field label={t("rd.justification_label")}>
              <textarea style={{ ...input, minHeight: 72 }} required value={routeCorrection.justification}
                onChange={(e) => setRouteCorrection({ ...routeCorrection, justification: e.target.value })} />
            </Field>
            <div style={{ marginTop: 12 }}>
              <button type="submit" style={{ ...primary, background: "#ea580c" }}>{t("rd.apply_correction")}</button>
              <button type="button" style={ghost} onClick={() => setRouteCorrectionOpen(false)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {/* ---------- Modal de correção admin da parada ---------- */}
      {stopCorrection && (
        <div style={overlay} onClick={() => setStopCorrection(null)}>
          <form style={{ ...modal, width: 500 }} onClick={(e) => e.stopPropagation()} onSubmit={confirmStopCorrection}>
            <h3 style={{ marginTop: 0 }}>{t("rd.correction_admin_stop_title")}</h3>
            <p style={{ color: "#475569", fontSize: 14, marginTop: 0 }}>{stopCorrection.customer_name}</p>
            {modalError && <p style={modalErrorStyle}>{modalError}</p>}
            <Field label={t("rd.stop_status_label")}>
              <select style={input} value={stopCorrectionForm.status} onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, status: e.target.value })}>
                {["pendente", "em_rota", "entregue", "falha"].map((status) => (
                  <option key={status} value={status}>{t(`stop_status.${status}`, { defaultValue: status })}</option>
                ))}
              </select>
            </Field>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10 }}>
              <label style={{ ...field, flexDirection: "row", alignItems: "center" }}>
                <input type="checkbox" checked={stopCorrectionForm.clear_checkin} onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, clear_checkin: e.target.checked })} />
                <span>{t("rd.clear_checkin")}</span>
              </label>
              <label style={{ ...field, flexDirection: "row", alignItems: "center" }}>
                <input type="checkbox" checked={stopCorrectionForm.clear_delivery} onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, clear_delivery: e.target.checked })} />
                <span>{t("rd.clear_delivery")}</span>
              </label>
              <label style={{ ...field, flexDirection: "row", alignItems: "center" }}>
                <input type="checkbox" checked={stopCorrectionForm.clear_failure} onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, clear_failure: e.target.checked })} />
                <span>{t("rd.clear_failure")}</span>
              </label>
              <label style={{ ...field, flexDirection: "row", alignItems: "center" }}>
                <input type="checkbox" checked={stopCorrectionForm.clear_proofs} onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, clear_proofs: e.target.checked })} />
                <span>{t("rd.clear_proofs")}</span>
              </label>
            </div>
            {stopCorrectionForm.status === "falha" && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
                <Field label={t("rd.failure_reason_label")}>
                  <select style={input} value={stopCorrectionForm.failure_reason_id}
                    onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, failure_reason_id: e.target.value })}>
                    <option value="">{t("rd.select_placeholder")}</option>
                    {activeReasons.map((r) => <option key={r.id} value={r.id}>{localizedReasonLabel(r)}</option>)}
                  </select>
                </Field>
                <Field label={t("rd.return_type_label")}>
                  <select style={input} value={stopCorrectionForm.return_type}
                    onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, return_type: e.target.value })}>
                    <option value="">-</option>
                    <option value="total">{t("rd.return_total")}</option>
                    <option value="parcial">{t("rd.return_partial")}</option>
                  </select>
                </Field>
                {stopCorrectionForm.return_type === "parcial" && (
                  <Field label={t("rd.returned_quantity_label")}>
                    <input style={input} type="number" step="any" min="0" value={stopCorrectionForm.returned_quantity}
                      onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, returned_quantity: e.target.value })} />
                  </Field>
                )}
              </div>
            )}
            <Field label={t("rd.justification_label")}>
              <textarea style={{ ...input, minHeight: 72 }} required value={stopCorrectionForm.justification}
                onChange={(e) => setStopCorrectionForm({ ...stopCorrectionForm, justification: e.target.value })} />
            </Field>
            <div style={{ marginTop: 12 }}>
              <button type="submit" style={{ ...primary, background: "#ea580c" }}>{t("rd.apply_correction")}</button>
              <button type="button" style={ghost} onClick={() => setStopCorrection(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {/* ---------- Modal de comprovante de entrega ---------- */}
      {proofStop && (
        <div style={overlay} onClick={() => { if (!proofSaving) setProofStop(null); }}>
          <form style={modal} onClick={(e) => e.stopPropagation()} onSubmit={confirmDeliveryProof}>
            <h3 style={{ marginTop: 0 }}>{t("rd.delivery_proof_title")}</h3>
            <p style={{ color: "#475569", fontSize: 14, marginTop: 0 }}>{proofStop.customer_name}</p>
            {proofError && <p style={modalErrorStyle}>{proofError}</p>}
            <Field label={t("rd.delivery_proof_label")}>
              <input
                style={input}
                type="file"
                accept="image/*,application/pdf"
                capture="environment"
                required
                onChange={async (e) => setProofFile(e.target.files?.[0] ? await applyTimemark(e.target.files[0], {routeCode:route.codigo_ut,stopSequence:proofStop.sequence,address:[proofStop.customer_address,proofStop.city].filter(Boolean).join(" · "),driverName:user?.role==="motorista"?user.name:drivers.find(d=>d.id===route.driver_id)?.name,vehiclePlate:vehicles.find(v=>v.id===route.vehicle_id)?.plate}) : null)}
              />
            </Field>
            <div style={{ marginTop: 12 }}>
              <button type="submit" style={primary} disabled={proofSaving}>{proofSaving ? t("rd.sending") : t("rd.confirm_delivery")}</button>
              <button type="button" style={ghost} disabled={proofSaving} onClick={() => setProofStop(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {/* ---------- Modal de falha (motivo obrigatório) ---------- */}
      {failStop && (
        <div style={overlay} onClick={() => setFailStop(null)}>
          <form style={modal} onClick={(e) => e.stopPropagation()} onSubmit={confirmFail}>
            <h3 style={{ marginTop: 0 }}>{t("rd.fail_title")}</h3>
            <p style={{ color: "#475569", fontSize: 14, marginTop: 0 }}>{failStop.customer_name}</p>
            <Field label={t("rd.reason")}>
              <select style={input} value={failForm.reason_id} required
                onChange={(e) => setFailForm({ ...failForm, reason_id: e.target.value })}>
                <option value="">{t("rd.reason_placeholder")}</option>
                {activeReasons.map((r) => <option key={r.id} value={r.id}>{localizedReasonLabel(r)}</option>)}
              </select>
            </Field>
            <Field label={t("rd.return_type_label")}>
              <select style={input} value={failForm.return_type}
                onChange={(e) => setFailForm({ ...failForm, return_type: e.target.value as "total" | "parcial" })}>
                <option value="total">{t("rd.return_total")}</option>
                <option value="parcial">{t("rd.return_partial")}</option>
              </select>
            </Field>
            {failForm.return_type === "parcial" && (
              <Field label={t("rd.returned_quantity_label")}>
                <input
                  style={input}
                  type="number"
                  step="any"
                  min="0"
                  required
                  value={failForm.returned_quantity}
                  onChange={(e) => setFailForm({ ...failForm, returned_quantity: e.target.value })}
                />
              </Field>
            )}
            <Field label={t("rd.fail_proof_label")}>
              <input
                style={input}
                type="file"
                accept="image/*,application/pdf"
                capture="environment"
                required
                onChange={async (e) => setFailFile(e.target.files?.[0] ? await applyTimemark(e.target.files[0], {routeCode:route.codigo_ut,stopSequence:failStop.sequence,address:[failStop.customer_address,failStop.city].filter(Boolean).join(" · "),driverName:user?.role==="motorista"?user.name:drivers.find(d=>d.id===route.driver_id)?.name,vehiclePlate:vehicles.find(v=>v.id===route.vehicle_id)?.plate}) : null)}
              />
            </Field>
            <Field label={t("rd.notes")}>
              <textarea style={{ ...input, minHeight: 60 }} value={failForm.notes}
                onChange={(e) => setFailForm({ ...failForm, notes: e.target.value })} />
            </Field>
            <div style={{ marginTop: 12 }}>
              <button type="submit" style={{ ...primary, background: "#b91c1c" }}>{t("rd.confirm_fail")}</button>
              <button type="button" style={ghost} onClick={() => setFailStop(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

      {/* ---------- Modal de devolução ao armazém ---------- */}
      {warehouseStop && (
        <div style={overlay} onClick={() => setWarehouseStop(null)}>
          <form style={modal} onClick={(e) => e.stopPropagation()} onSubmit={confirmWarehouseProof}>
            <h3 style={{ marginTop: 0 }}>{t("rd.warehouse_return_title")}</h3>
            <p style={{ color: "#475569", fontSize: 14, marginTop: 0 }}>{warehouseStop.customer_name}</p>
            <Field label={t("rd.warehouse_evidence_label")}>
              <input
                style={input}
                type="file"
                accept="image/*,application/pdf"
                capture="environment"
                required
                onChange={async (e) => setWarehouseFile(e.target.files?.[0] ? await applyTimemark(e.target.files[0], {routeCode:route.codigo_ut,stopSequence:warehouseStop.sequence,address:[warehouseStop.customer_address,warehouseStop.city].filter(Boolean).join(" · "),driverName:user?.role==="motorista"?user.name:drivers.find(d=>d.id===route.driver_id)?.name,vehiclePlate:vehicles.find(v=>v.id===route.vehicle_id)?.plate}) : null)}
              />
            </Field>
            <div style={{ marginTop: 12 }}>
              <button type="submit" style={primary}>{t("rd.save_proof")}</button>
              <button type="button" style={ghost} onClick={() => setWarehouseStop(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}

    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><div style={{ fontSize: 12, color: "#64748b" }}>{label}</div><div style={{ fontSize: 14 }}>{value}</div></div>;
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label style={field}><span>{label}</span>{children}</label>;
}
function fmt(s?: string | null) {
  if (!s) return "—";
  const dt = new Date(s);
  return isNaN(dt.getTime()) ? "—" : dt.toLocaleString();
}
function toDatetimeLocal(s?: string | null) {
  if (!s) return "";
  const dt = new Date(s);
  if (isNaN(dt.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}
function fromDatetimeLocal(s: string): string | null {
  if (!s) return null;
  const dt = new Date(s);
  return isNaN(dt.getTime()) ? null : dt.toISOString();
}
function routeLabel(route: { codigo_ut: string; route_date: string }) {
  const [year, month, day] = route.route_date.split("-");
  return year && month && day ? `${day}/${month} - ${route.codigo_ut}` : route.codigo_ut;
}
function routeCustomers(route: Pick<RouteData, "stops">) {
  const names = route.stops
    .map((stop) => (stop.client_name || stop.customer_name).trim())
    .filter(Boolean);
  return [...new Set(names)].join(", ") || "—";
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

const card: React.CSSProperties = { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 12, padding: 18, boxShadow: "0 2px 10px rgba(0,0,0,.05)", marginTop: 16 };
const panel: React.CSSProperties = { background: "var(--soft)", borderRadius: 12, padding: 16 };
const infoGrid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(200px,1fr))", gap: 12 };
const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse", marginTop: 12 };
const th: React.CSSProperties = { padding: 10, fontSize: 13, color: "var(--muted)" };
const td: React.CSSProperties = { padding: 10, fontSize: 14, color: "var(--ink)" };
const opsToggle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  minHeight: 28,
  marginBottom: 6,
  padding: "4px 8px",
  border: "1px solid transparent",
  borderRadius: 6,
  background: "transparent",
  color: "#31527a",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};
const opsToggleIcon: React.CSSProperties = {
  display: "inline-grid",
  placeItems: "center",
  width: 16,
  height: 16,
  borderRadius: 4,
  border: "1px solid var(--line)",
  background: "var(--panel)",
  color: "#31527a",
  lineHeight: 1,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
};
const opsTable: React.CSSProperties = {
  width: "100%",
  tableLayout: "fixed",
  borderCollapse: "collapse",
  fontSize: 12,
};
const opsTh: React.CSSProperties = {
  padding: "6px 8px",
  fontSize: 11,
  color: "var(--muted)",
  fontWeight: 700,
  textAlign: "left",
  whiteSpace: "nowrap",
};
const opsTd: React.CSSProperties = {
  padding: "6px 8px",
  fontSize: 12,
  color: "var(--ink)",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  verticalAlign: "middle",
};
const opsCodeTd: React.CSSProperties = {
  ...opsTd,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  fontVariantNumeric: "tabular-nums",
};
const opsCenterTd: React.CSSProperties = {
  ...opsTd,
  textAlign: "center",
  fontVariantNumeric: "tabular-nums",
};
const field: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4, fontSize: 13, color: "var(--muted)" };
const input: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontSize: 14 };
const mini: React.CSSProperties = { marginRight: 4, marginBottom: 4, padding: "4px 8px", fontSize: 12, border: "1px solid var(--line)", borderRadius: 6, background: "var(--panel)", color: "var(--ink)", cursor: "pointer" };
const disabledMini: React.CSSProperties = { ...mini, color: "#94a3b8", background: "var(--soft)", cursor: "not-allowed", opacity: 0.75 };
const miniDanger: React.CSSProperties = { ...mini, borderColor: "#fca5a5", color: "#b91c1c" };
const disabledMiniDanger: React.CSSProperties = { ...disabledMini, borderColor: "#fecaca", color: "#fca5a5" };
const primary: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "none", background: "#0a58ca", color: "#fff", cursor: "pointer", marginRight: 8 };
const ghost: React.CSSProperties = { padding: "6px 12px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", cursor: "pointer" };
const overlay: React.CSSProperties = { position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "grid", alignItems: "start", justifyItems: "center", zIndex: 5000, overflowY: "auto", padding: "max(16px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left))" };
const modal: React.CSSProperties = { background: "var(--panel)", color: "var(--ink)", borderRadius: 12, padding: 22, width: "min(380px, 100%)", maxWidth: "100%", maxHeight: "calc(100dvh - 32px - env(safe-area-inset-top) - env(safe-area-inset-bottom))", overflowY: "auto", boxShadow: "0 12px 40px rgba(0,0,0,.2)" };
const modalErrorStyle: React.CSSProperties = { color: "#b91c1c", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 8, fontSize: 13 };

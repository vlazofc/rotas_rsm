import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import RouteMap from "../components/RouteMap";
import api from "../services/api";
import { importRoutes } from "../services/importRoutes";
import { useAuth } from "../context/AuthContext";
import "./Routing.css";

interface Stop { id: number; sequence: number; spreadsheet_sequence?: number | null; optimized_sequence?: number | null; customer_name: string; customer_address?: string | null; city?: string | null; status: string; latitude?: number | null; longitude?: number | null; order_number?: string | null; invoice_number?: string | null; cte_number?: string | null; customer_notes?: string | null; customer_notes_2?: string | null; }
interface RouteObservation { id:number; sequence:number; text:string; created_at:string; created_by?:number|null }
interface RouteItem { id: number; codigo_ut: string; spreadsheet_route?: string | null; route_date: string; delivery_date?: string | null; status: string; origin_address?: string | null; driver_id?: number | null; vehicle_id?: number | null; stops: Stop[]; routing_status?: string; routing_distance_km?: number | null; routing_duration_minutes?: number | null; routing_optimized_at?: string | null; routing_error?: string | null; routing_geometry_json?: string | null; suggested_geometry_json?: string | null; overnight?: boolean | null; overnight_count?:number|null; daily_count?:number|null; daily_value?: string | null; administrative_notes?: string | null; cte_number?:string|null; observations?:RouteObservation[]; }
interface RouteItem { tracked?: boolean | null; helper_assigned?: boolean | null; }
interface Driver { id: number; name: string; active: boolean; blocked?: boolean; }
interface Vehicle { id: number; plate: string; active: boolean; blocked?: boolean; }
interface ImportResult { rows_read: number; routes_created: number; routes_updated: number; stops_created: number; stops_updated: number; routes_optimized: number; routing_errors: number; route_ids: number[]; errors: string[]; }

export default function Routing() {
  const { hasRole } = useAuth();
  const navigate = useNavigate();
  const [routes, setRoutes] = useState<RouteItem[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [originAddress, setOriginAddress] = useState("");
  const [newStop, setNewStop] = useState({ customer_name: "", customer_address: "", city: "" });
  const [observation,setObservation]=useState("");
  const [mapOpen, setMapOpen] = useState(true);
  const [search, setSearch] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [statusTab, setStatusTab] = useState<"aberto" | "finalizada">("aberto");
  const CLOSED_ROUTE_STATUSES = useMemo(() => new Set(["finalizada", "cancelada"]), []);
  const openRoutes = useMemo(() => routes.filter(route => !CLOSED_ROUTE_STATUSES.has(route.status)), [routes, CLOSED_ROUTE_STATUSES]);
  const closedRoutes = useMemo(() => routes.filter(route => CLOSED_ROUTE_STATUSES.has(route.status)), [routes, CLOSED_ROUTE_STATUSES]);
  const normalizeSearch = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const filteredRoutes = useMemo(() => (statusTab === "aberto" ? openRoutes : closedRoutes).filter(route => {
    if (startDate && route.route_date < startDate) return false;
    if (endDate && route.route_date > endDate) return false;
    const text = [route.codigo_ut, route.origin_address, drivers.find(d => d.id === route.driver_id)?.name, vehicles.find(v => v.id === route.vehicle_id)?.plate, ...route.stops.flatMap(s => [s.customer_name, s.city])].filter(Boolean).join(" ");
    return normalizeSearch(text).includes(normalizeSearch(search.trim()));
  }), [openRoutes, closedRoutes, statusTab, drivers, vehicles, search, startDate, endDate]);
  const [savingFlags, setSavingFlags] = useState(false);
  async function updateFlag(field: "tracked" | "helper_assigned", value: string) {
    if (!selected || savingFlags) return;
    setSavingFlags(true); setError(""); setMessage("");
    try {
      const { data } = await api.put<RouteItem>(`/routes/${selected.id}/administrative`, { [field]: value === "true" });
      setRoutes(current => current.map(route => route.id === data.id ? data : route));
      setMessage("Dados da rota salvos.");
    } catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível salvar. Tente novamente."); }
    finally { setSavingFlags(false); }
  }

  async function reload(preferred?: number) {
    const { data } = await api.get<RouteItem[]>("/routes");
    const candidates = data.filter((route) => route.status === "planejada" || hasRole("admin_global"));
    setRoutes(candidates);
    setSelectedId((current) => preferred ?? current ?? candidates[0]?.id ?? null);
  }
  useEffect(() => { void reload(); api.get("/drivers").then((r) => setDrivers(r.data)); api.get("/vehicles").then((r) => setVehicles(r.data)); }, []);
  const selected = filteredRoutes.find((route) => route.id === selectedId) ?? filteredRoutes[0] ?? null;
  useEffect(() => { setOriginAddress(selected?.origin_address ?? ""); }, [selected?.id, selected?.origin_address]);
  const totals = useMemo(() => ({ routes: openRoutes.length, stops: openRoutes.reduce((sum, route) => sum + route.stops.length, 0), optimized: openRoutes.filter((route) => route.routing_status === "optimized").length, pending: openRoutes.filter((route) => route.routing_status !== "optimized").length }), [openRoutes]);

  async function downloadTemplate() {
    const { data } = await api.get("/routes-import/template.xlsx", { responseType: "blob" });
    const url = URL.createObjectURL(data); const link = document.createElement("a");
    link.href = url; link.download = "modelo-importacao-gestao-adimax.xlsx"; link.click(); URL.revokeObjectURL(url);
  }
  async function upload() {
    if (!file) return;
    setBusy(true); setError(""); setMessage("");
    const body = new FormData(); body.set("file", file);
    try {
      const data = await importRoutes<ImportResult>(body);
      if (!data) return;
      await reload(data.route_ids[0]);
      setMessage(`${data.routes_created + data.routes_updated} rota(s) importada(s). Os mapas estão sendo atualizados em segundo plano.`);
      if (data.errors.length) setError(data.errors.join("\n"));
    } catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível importar a planilha."); }
    finally { setBusy(false); }
  }
  async function optimize() {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try { await api.post(`/routes/${selected.id}/optimize-sequence`); await reload(selected.id); setMessage("Nova sequência calculada como sugestão. A ordem original foi preservada."); }
    catch (err: any) { setError(err?.response?.data?.detail ?? "Falha ao consultar o roteirizador."); }
    finally { setBusy(false); }
  }
  async function refreshMap() {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try { await api.post(`/routes/${selected.id}/refresh-map`); await reload(selected.id); [3000, 10000, 25000].forEach(delay => window.setTimeout(() => void reload(), delay)); setMessage("Atualização iniciada. O Maestro processará os pontos em segundo plano sem alterar a sequência."); }
    catch (err: any) { setError(err?.response?.data?.detail ?? "O Maestro não conseguiu validar todos os pontos."); }
    finally { setBusy(false); }
  }
  async function applySuggestion() {
    if (!selected) return; setBusy(true); setError("");
    try { await api.post(`/routes/${selected.id}/apply-optimized-sequence`); await reload(selected.id); setMessage("Sugestão aplicada à sequência operacional."); }
    catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível aplicar a sugestão."); }
    finally { setBusy(false); }
  }
  async function updateAdministrative(payload: Record<string, unknown>) {
    if (!selected) return;
    try { await api.put(`/routes/${selected.id}/administrative`, payload); await reload(selected.id); }
    catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível salvar o campo administrativo."); }
  }
  async function updateStopAdministrative(stop: Stop, payload: Record<string, unknown>) {
    if (!selected) return;
    try { await api.put(`/routes/${selected.id}/stops/${stop.id}/administrative`, payload); await reload(selected.id); }
    catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível salvar NF/CTE."); }
  }
  async function addObservation() {
    if(!selected||!observation.trim())return;
    try{await api.post(`/routes/${selected.id}/observations`,{text:observation.trim()});setObservation("");await reload(selected.id);setMessage("Observação registrada no histórico.")}
    catch(err:any){setError(err?.response?.data?.detail??"Não foi possível registrar a observação.")}
  }
  async function assign(field: "driver_id" | "vehicle_id", value: string) {
    if (!selected) return;
    setError("");
    try { await api.put(`/routes/${selected.id}/assignment`, { driver_id: field === "driver_id" ? (value ? Number(value) : null) : selected.driver_id ?? null, vehicle_id: field === "vehicle_id" ? (value ? Number(value) : null) : selected.vehicle_id ?? null }); await reload(selected.id); }
    catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível salvar a atribuição."); }
  }
  async function saveOrigin() {
    if (!selected || !originAddress.trim()) return;
    setBusy(true); setError("");
    try { await api.put(`/routes/${selected.id}`, { origin_address: originAddress.trim() }); await api.post(`/routes/${selected.id}/refresh-map`); await reload(selected.id); window.setTimeout(() => void reload(), 5000); setMessage("Ponto de partida salvo. O mapa está sendo atualizado em segundo plano."); }
    catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível salvar o ponto de partida."); }
    finally { setBusy(false); }
  }
  async function addStop(event: React.FormEvent) {
    event.preventDefault();
    if (!selected || !newStop.customer_name.trim() || !newStop.customer_address.trim()) return;
    setBusy(true); setError("");
    try {
      await api.post(`/routes/${selected.id}/stops`, { sequence: selected.stops.length + 1, customer_name: newStop.customer_name.trim(), customer_address: newStop.customer_address.trim(), city: newStop.city.trim() || null });
      await api.post(`/routes/${selected.id}/refresh-map`);
      setNewStop({ customer_name: "", customer_address: "", city: "" }); await reload(selected.id); window.setTimeout(() => void reload(), 5000); setMessage("Parada adicionada. O endereço e o mapa estão sendo validados em segundo plano.");
    } catch (err: any) { setError(err?.response?.data?.detail ?? "Não foi possível adicionar a parada."); }
    finally { setBusy(false); }
  }

  return <div className="routing-page">
    <header className="routing-hero">
      <div><span>GESTÃO OPERACIONAL</span><h1>Monitoramento de rotas</h1><p>Acompanhe cargas importadas, documentos, diárias, pernoites e observações.</p></div>
      <div className="routing-upload">
        <button className="btn-ghost" type="button" onClick={downloadTemplate}>Baixar modelo</button>
        <label className="btn-ghost routing-file">{file?.name ?? "Selecionar planilha"}<input type="file" accept=".xlsx,.xlsm,.csv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
        <button className="btn-primary" type="button" disabled={!file || busy} onClick={upload}>{busy ? "Processando…" : "Importar e roteirizar"}</button>
      </div>
    </header>
    {(message || error) && <div className={`routing-feedback ${error ? "error" : "success"}`}>{error || message}</div>}
    <section className="routing-metrics">
      <article><small>ROTAS ABERTAS</small><strong>{totals.routes}</strong></article><article><small>PARADAS</small><strong>{totals.stops}</strong></article><article><small>OTIMIZADAS</small><strong>{totals.optimized}</strong></article><article><small>PENDÊNCIAS</small><strong>{totals.pending}</strong></article>
    </section>
    <section className="routing-search-filters" aria-label="Filtros de rotas">
      <label>Buscar<input className="input" type="search" placeholder="Rota, cliente, cidade, motorista ou placa" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label>Data inicial<input className="input" type="date" value={startDate} max={endDate || undefined} onChange={e => setStartDate(e.target.value)} /></label>
      <label>Data final<input className="input" type="date" value={endDate} min={startDate || undefined} onChange={e => setEndDate(e.target.value)} /></label>
      <button className="btn-ghost" onClick={() => { setSearch(""); setStartDate(""); setEndDate(""); }}>Limpar</button>
    </section>
    <section className="routing-workspace">
      <aside className="routing-list-frame"><div className="routing-list"><header><strong>Rotas para planejar</strong><small>{filteredRoutes.length} de {(statusTab === "aberto" ? openRoutes : closedRoutes).length} encontrada(s)</small></header>
        <div className="routing-status-tabs">
          <button type="button" className={statusTab === "aberto" ? "active" : ""} onClick={() => setStatusTab("aberto")}>Aberto ({openRoutes.length})</button>
          <button type="button" className={statusTab === "finalizada" ? "active" : ""} onClick={() => setStatusTab("finalizada")}>Finalizada ({closedRoutes.length})</button>
        </div>
        {filteredRoutes.map((route) => <button type="button" className={route.id === selected?.id ? "active" : ""} key={route.id} onClick={() => setSelectedId(route.id)}>
          <span><strong>{route.codigo_ut}</strong><small>{new Date(`${route.route_date}T12:00`).toLocaleDateString("pt-BR")} · {route.stops.length} paradas</small></span>
          <em className={route.routing_status === "optimized" ? "ok" : "pending"}>{route.routing_status === "optimized" ? "Otimizada" : "Pendente"}</em>
        </button>)}
        {!filteredRoutes.length && <p className="routing-empty">{routes.length ? "Nenhuma rota encontrada para os filtros." : "Importe uma planilha para começar."}</p>}
      </div></aside>
      <main className="routing-detail" key={selected?.id ?? "empty"}>
        {selected ? <>
          <div className="routing-detail-head"><div><small>CARGA · {selected.spreadsheet_route || "ROTA"}</small><h2>{selected.codigo_ut}</h2><p>{selected.origin_address || "Origem não informada"}</p></div><div><button className="btn-ghost" onClick={() => navigate(`/routes/${selected.id}`)}>Abrir rota</button><button className="btn-ghost" disabled={busy} onClick={refreshMap}>Atualizar mapa</button></div></div>
          <div className="routing-assignments"><label>Motorista<select value={selected.driver_id ?? ""} onChange={(e) => assign("driver_id", e.target.value)}><option value="">Não atribuído</option>{drivers.filter((item) => item.active && !item.blocked).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Veículo<select value={selected.vehicle_id ?? ""} onChange={(e) => assign("vehicle_id", e.target.value)}><option value="">Não atribuído</option>{vehicles.filter((item) => item.active && !item.blocked).map((item) => <option key={item.id} value={item.id}>{item.plate}</option>)}</select></label><div><small>DISTÂNCIA ESTIMADA</small><strong>{selected.routing_distance_km != null ? `${selected.routing_distance_km} km` : "—"}</strong></div><div><small>TEMPO ESTIMADO</small><strong>{selected.routing_duration_minutes != null ? `${Math.floor(selected.routing_duration_minutes / 60)}h ${selected.routing_duration_minutes % 60}min` : "—"}</strong></div></div>
          {selected.routing_error && !selected.routing_error.includes("Informe a origem (CD)") && <div className="routing-inline-error">{selected.routing_error}</div>}
          <div className="routing-assignments" aria-busy={savingFlags}>
            <label>Rastreada<select value={selected.tracked == null ? "" : String(selected.tracked)} disabled={savingFlags || !hasRole("admin_global", "gestor_brasil", "operador_logistico", "torre_controle")} onChange={e => void updateFlag("tracked", e.target.value)}><option value="" disabled>Não informado</option><option value="true">Sim</option><option value="false">Não</option></select></label>
            <label>Ajudante<select value={selected.helper_assigned == null ? "" : String(selected.helper_assigned)} disabled={savingFlags || !hasRole("admin_global", "gestor_brasil", "operador_logistico", "torre_controle")} onChange={e => void updateFlag("helper_assigned", e.target.value)}><option value="" disabled>Não informado</option><option value="true">Sim</option><option value="false">Não</option></select></label>
            {savingFlags && <span role="status">Salvando…</span>}
          </div>
          {hasRole("admin_global", "gestor_brasil", "operador_logistico", "torre_controle") && <><div className="routing-admin routing-admin-monitor"><strong>Dados operacionais</strong><label>Qtd. pernoites<input type="number" min="0" className="input" defaultValue={selected.overnight_count ?? 0} onBlur={(e)=>updateAdministrative({overnight_count:Number(e.target.value)||0,overnight:Number(e.target.value)>0})}/></label><label>Qtd. diárias<input type="number" min="0" step="1" className="input" defaultValue={selected.daily_count ?? 0} onBlur={(e)=>updateAdministrative({daily_count:Number(e.target.value)||0})}/></label><label>Número do CT-e<input className="input" defaultValue={selected.cte_number??""} onBlur={(e)=>updateAdministrative({cte_number:e.target.value||null})}/></label></div><div className={`routing-observations ${selected.observations?.length ? "has-history" : "is-empty"}`}><div className="routing-observation-compose"><label>Nova observação<textarea className="input" value={observation} onChange={e=>setObservation(e.target.value)} placeholder="Registre uma nova informação operacional"/></label><button className="btn-primary" disabled={!observation.trim()} onClick={addObservation}>Registrar observação</button></div><div className="routing-observation-history">{[...(selected.observations??[])].reverse().map(item=><article key={item.id}><b>#{item.sequence}</b><span>{item.text}<small>{new Date(item.created_at).toLocaleString("pt-BR")}</small></span></article>)}{!selected.observations?.length&&<small>Nenhuma observação registrada.</small>}</div></div></>}
          <section className={`routing-map-card ${mapOpen ? "is-open" : "is-collapsed"}`}><header><div><strong>Mapa da rota</strong><small>Trajeto e sequência das paradas</small></div><button type="button" className="btn-ghost" onClick={() => setMapOpen((open) => !open)}>{mapOpen ? "Recolher mapa" : "Exibir mapa"}</button></header>{mapOpen && <div className="routing-map"><RouteMap routes={[selected]} selectedRouteId={selected.id} onSelectRoute={setSelectedId} /></div>}</section>
          <div className="routing-stops"><h3>Sequência original e sugestão</h3><article className="routing-origin-stop"><b>0</b><span><strong>Carregamento no CD</strong><small>{selected.origin_address || "Origem não informada — preencha a coluna V da planilha."}</small><small>Ponto inicial do cálculo de distância e tempo até as entregas.</small></span></article>{[...selected.stops].sort((a,b) => a.sequence-b.sequence).map((stop) => <article key={stop.id}><b>{stop.spreadsheet_sequence ?? stop.sequence}</b><span><strong>{stop.customer_name}</strong><small>{[stop.customer_address, stop.city].filter(Boolean).join(" · ") || "Endereço não informado"}{stop.order_number ? ` · Pedido ${stop.order_number}` : ""}</small>{stop.optimized_sequence != null && <em>Sugestão: parada {stop.optimized_sequence}</em>}{(stop.customer_notes || stop.customer_notes_2) && <small>Obs. cliente: {[stop.customer_notes, stop.customer_notes_2].filter(Boolean).join(" · ")}</small>}</span>{hasRole("admin_global", "gestor_brasil") && <span className="routing-docs"><input className="input" placeholder="Nota fiscal" defaultValue={stop.invoice_number ?? ""} onBlur={(e) => updateStopAdministrative(stop,{invoice_number:e.target.value||null})}/><input className="input" placeholder="CTE" defaultValue={stop.cte_number ?? ""} onBlur={(e) => updateStopAdministrative(stop,{cte_number:e.target.value||null})}/></span>}</article>)}</div>
        </> : <div className="routing-empty">Selecione uma rota para revisar o planejamento.</div>}
      </main>
    </section>
  </div>;
}

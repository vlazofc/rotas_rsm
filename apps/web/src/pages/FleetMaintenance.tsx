import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import api from "../services/api";
import {appConfirm,appPrompt} from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";
import "./FleetMaintenance.css";

interface Vehicle {
  id: number;
  plate: string;
  description?: string | null;
  active: boolean;
  axles?: number | null;
  rear_dual_wheels?: boolean;
}

interface Tire {
  id: number;
  vehicle_id?: number | null;
  vehicle_plate?: string | null;
  fire_number: string;
  brand?: string | null;
  model?: string | null;
  position?: string | null;
  status: string;
  tread_depth_mm?: number | null;
  install_date?: string | null;
  install_km?: number | null;
  recap_count: number;
  cost?: number | string | null;
  latest_odometer_km?: number | null;
  km_rodado?: number | null;
  cpk?: number | null;
}

interface TireInspection {
  id: number;
  inspected_at: string;
  odometer_km?: number | null;
  tread_depth_mm?: number | null;
  notes?: string | null;
}

interface MaintenancePlan {
  id: number;
  vehicle_id: number;
  vehicle_plate?: string | null;
  service_name: string;
  interval_km?: number | null;
  interval_days?: number | null;
  last_done_at?: string | null;
  last_done_km?: number | null;
  active: boolean;
  due: boolean;
}

interface MaintenanceOrder {
  id: number;
  vehicle_id: number;
  vehicle_plate?: string | null;
  plan_id?: number | null;
  provider_id?: number | null;
  provider_name?: string | null;
  kind: string;
  status: string;
  description: string;
  opened_at: string;
  closed_at?: string | null;
  expected_completion_date?: string | null;
  sla_status: string;
  sla_days_remaining?: number | null;
  odometer_km?: number | null;
  cost?: number | string | null;
  attachment_filename?: string | null;
  attachment_url?: string | null;
  attachment_id?: number | null;
  budget_filename?: string | null;
  budget_url?: string | null;
  budget_attachment_id?: number | null;
  approval_status: string;
  approved_by_name?: string | null;
  approved_at?: string | null;
  expense_id?: number | null;
}

interface ServiceProvider {
  id: number;
  branch_id?: number | null;
  name: string;
  document?: string | null;
  category: string;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  authorized: boolean;
  active: boolean;
}

interface ServiceProviderNearby extends ServiceProvider {
  distance_km: number;
}

interface ChecklistTemplateItem {
  id: number;
  code: string;
  label: string;
  label_pt_br?: string | null;
  category: string;
  required: boolean;
}

interface ChecklistItemResult {
  id: number;
  template_item_id: number;
  item_label?: string | null;
  status: string;
  notes?: string | null;
}

interface VehicleChecklist {
  id: number;
  vehicle_id: number;
  vehicle_plate?: string | null;
  driver_id?: number | null;
  driver_name?: string | null;
  route_id?: number | null;
  kind: string;
  performed_at: string;
  overall_status: string;
  notes?: string | null;
  items: ChecklistItemResult[];
  tire_measurements?: {tire_id:number;tread_depth_mm:number;fire_number?:string|null;position?:string|null}[];
}

interface Driver {
  id: number;
  name: string;
  active: boolean;
}

const TIRE_STATUSES = ["novo", "em_uso", "recapado", "descartado"];
const ORDER_KINDS = ["preventiva", "corretiva"];
const ORDER_STATUSES = ["aberta", "em_andamento", "concluida", "cancelada"];
const TIRE_POSITIONS = ["dianteiro_esq", "dianteiro_dir", "traseiro_esq_int", "traseiro_esq_ext", "traseiro_dir_int", "traseiro_dir_ext", "estepe"];
const PROVIDER_CATEGORIES = ["oficina_mecanica", "borracharia", "eletrica", "guincho", "posto_combustivel", "lavagem", "outros"];
const CHECKLIST_KINDS = ["saida", "retorno", "periodica"];
const ITEM_STATUSES = ["ok", "nao_ok", "nao_aplicavel"];

function getBrowserPosition(): Promise<{ latitude: number; longitude: number } | null> {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) { resolve(null); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 60000 },
    );
  });
}

type Tab = "tires" | "orders" | "plans" | "providers" | "checklist";

const VALID_TABS: Tab[] = ["tires", "orders", "plans", "providers", "checklist"];

export default function FleetMaintenance() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") as Tab | null;
  const tab: Tab = requestedTab && VALID_TABS.includes(requestedTab) ? requestedTab : "tires";
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [error, setError] = useState("");

  function setTab(next: Tab) {
    setSearchParams({ tab: next }, { replace: true });
  }

  useEffect(() => {
    api.get<Vehicle[]>("/vehicles").then((r) => setVehicles(r.data)).catch(() => setVehicles([]));
  }, []);

  return (
    <div>
      <div className="page-header">
        <div>
          <h2>{tab === "orders" ? "Ordens de serviço" : tab === "checklist" ? "Checklist da frota" : tab === "tires" ? "Gestão de pneus" : tab === "plans" ? "Manutenções" : t("fleet.title")}</h2>
          <p className="page-subtitle">{tab === "orders" ? "Abertura, acompanhamento e homologação dos serviços da frota." : tab === "checklist" ? "Inspeções rápidas, intuitivas e organizadas por veículo." : tab === "tires" ? "Controle de posição, desgaste, recapagens e custo por quilômetro." : tab === "plans" ? "Acompanhamento preventivo e corretivo de toda a frota." : t("fleet.subtitle")}</p>
        </div>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      {tab === "providers" && <div style={tabsWrap}>
        <button style={{ ...tabBtn, ...(tab === "providers" ? tabActive : {}) }} onClick={() => setTab("providers")}>{t("fleet.tab_providers")}</button>
      </div>}

      {tab === "tires" && <TiresTab vehicles={vehicles} onError={setError} />}
      {tab === "orders" && <OrdersTab vehicles={vehicles} onError={setError} />}
      {tab === "plans" && <PlansTab vehicles={vehicles} onError={setError} />}
      {tab === "providers" && <ProvidersTab vehicles={vehicles} onError={setError} />}
      {tab === "checklist" && <ChecklistTab vehicles={vehicles} onError={setError} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pneus
// ---------------------------------------------------------------------------

function TiresTab({ vehicles, onError }: { vehicles: Vehicle[]; onError: (msg: string) => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [tires, setTires] = useState<Tire[]>([]);
  const [editing, setEditing] = useState<Tire | "new" | null>(null);
  const [inspecting, setInspecting] = useState<Tire | null>(null);
  const [inspections, setInspections] = useState<TireInspection[]>([]);
  const [filters, setFilters] = useState({ query: "", vehicle_id: "", status: "" });
  const [mapVehicleId, setMapVehicleId] = useState("");
  const [mapOpen, setMapOpen] = useState(false);
  const [form, setForm] = useState({
    vehicle_id: "", fire_number: "", brand: "", model: "", position: "", status: "novo",
    tread_depth_mm: "", install_date: new Date().toISOString().slice(0, 10), install_km: "", recap_count: "0", cost: "",
  });
  const [inspectionForm, setInspectionForm] = useState({ inspected_at: new Date().toISOString().slice(0, 10), odometer_km: "", tread_depth_mm: "", notes: "" });

  function reload() {
    api.get<Tire[]>("/fleet-maintenance/tires").then((r) => setTires(r.data)).catch(() => setTires([]));
  }
  useEffect(reload, []);

  function startNew(vehicleId = "", position = "") {
    setForm({ vehicle_id: vehicleId, fire_number: "", brand: "", model: "", position, status: vehicleId ? "em_uso" : "novo", tread_depth_mm: "", install_date: new Date().toISOString().slice(0, 10), install_km: "", recap_count: "0", cost: "" });
    setEditing("new");
  }

  function startEdit(tire: Tire) {
    setForm({
      vehicle_id: tire.vehicle_id ? String(tire.vehicle_id) : "",
      fire_number: tire.fire_number, brand: tire.brand ?? "", model: tire.model ?? "", position: tire.position ?? "",
      status: tire.status, tread_depth_mm: tire.tread_depth_mm != null ? String(tire.tread_depth_mm) : "",
      install_date: tire.install_date ?? "", install_km: tire.install_km != null ? String(tire.install_km) : "",
      recap_count: String(tire.recap_count), cost: tire.cost != null ? String(tire.cost) : "",
    });
    setEditing(tire);
  }

  function openMap(vehicleId?: number | null) {
    const selected=vehicleId ? String(vehicleId) : filters.vehicle_id;
    setMapVehicleId(selected || "");
    setMapOpen(true);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    onError("");
    const payload: Record<string, unknown> = {
      vehicle_id: form.vehicle_id ? Number(form.vehicle_id) : null,
      fire_number: form.fire_number, brand: form.brand || null, model: form.model || null, position: form.position || null,
      status: form.status, tread_depth_mm: form.tread_depth_mm ? Number(form.tread_depth_mm) : null,
      install_date: form.install_date || null, install_km: form.install_km ? Number(form.install_km) : null,
      recap_count: Number(form.recap_count || 0), cost: form.cost ? Number(form.cost) : null,
    };
    try {
      if (editing === "new") {
        await api.post("/fleet-maintenance/tires", { ...payload, branch_id: user?.branch_id ?? 1 });
      } else if (editing) {
        await api.put(`/fleet-maintenance/tires/${editing.id}`, payload);
      }
      setEditing(null);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function remove(tire: Tire) {
    if (!await appConfirm(t("fleet.delete_confirm") ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
    try {
      await api.delete(`/fleet-maintenance/tires/${tire.id}`);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_delete"));
    }
  }

  function openInspections(tire: Tire) {
    setInspecting(tire);
    setInspectionForm({ inspected_at: new Date().toISOString().slice(0, 10), odometer_km: "", tread_depth_mm: "", notes: "" });
    api.get<TireInspection[]>(`/fleet-maintenance/tires/${tire.id}/inspections`).then((r) => setInspections(r.data)).catch(() => setInspections([]));
  }

  async function saveInspection(e: React.FormEvent) {
    e.preventDefault();
    if (!inspecting) return;
    try {
      await api.post(`/fleet-maintenance/tires/${inspecting.id}/inspections`, {
        inspected_at: inspectionForm.inspected_at,
        odometer_km: inspectionForm.odometer_km ? Number(inspectionForm.odometer_km) : null,
        tread_depth_mm: inspectionForm.tread_depth_mm ? Number(inspectionForm.tread_depth_mm) : null,
        notes: inspectionForm.notes || null,
      });
      openInspections(inspecting);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function moveTire(tireId:number, vehicleId:number|null, position:string|null) {
    try {
      await api.post(`/fleet-maintenance/tires/${tireId}/move`, { vehicle_id: vehicleId, position });
      reload();
    } catch (err:any) {
      onError(err?.response?.data?.detail ?? "Não foi possível movimentar o pneu.");
    }
  }

  const filteredTires = tires.filter(tire =>
    (!filters.query || `${tire.fire_number} ${tire.brand || ""} ${tire.model || ""}`.toLowerCase().includes(filters.query.toLowerCase())) &&
    (!filters.vehicle_id || tire.vehicle_id === Number(filters.vehicle_id)) &&
    (!filters.status || tire.status === filters.status)
  );
  const tireStats = {
    total: tires.length,
    installed: tires.filter(tire => tire.vehicle_id != null && tire.status === "em_uso").length,
    stock: tires.filter(tire => tire.vehicle_id == null && tire.status !== "descartado").length,
    attention: tires.filter(tire => tire.status !== "descartado" && tire.tread_depth_mm != null && tire.tread_depth_mm <= 3).length,
  };

  return (
    <div>
      <div className="tire-summary"><article><span>Pneus cadastrados</span><strong>{tireStats.total}</strong></article><article><span>Em uso</span><strong>{tireStats.installed}</strong></article><article><span>Em estoque</span><strong>{tireStats.stock}</strong></article><article className={tireStats.attention?"tire-alert":""}><span>Sulco em atenção</span><strong>{tireStats.attention}</strong></article></div>
      <div className="tire-toolbar"><div className="tire-filters"><input className="input" placeholder="Buscar nº de fogo, marca ou modelo..." value={filters.query} onChange={e=>setFilters({...filters,query:e.target.value})}/><select className="input" value={filters.vehicle_id} onChange={e=>setFilters({...filters,vehicle_id:e.target.value})}><option value="">Todos os veículos</option>{vehicles.filter(v=>v.active).map(v=><option key={v.id} value={v.id}>{v.plate}</option>)}</select><select className="input" value={filters.status} onChange={e=>setFilters({...filters,status:e.target.value})}><option value="">Todos os status</option>{TIRE_STATUSES.map(status=><option key={status} value={status}>{t(`fleet.tire_statuses.${status}`)}</option>)}</select></div><div className="tire-toolbar-actions"><button className="btn-ghost" onClick={()=>openMap()}>Mapa de pneus</button><button className="btn-primary btn-add" onClick={()=>startNew()}><span className="btn-add-symbol">+</span><span>Novo pneu</span></button></div></div>

      {mapOpen&&<div className="modal-backdrop" onClick={()=>setMapOpen(false)}><div className="modal-card tire-map-modal" onClick={event=>event.stopPropagation()}><TireVehicleMap vehicles={vehicles} tires={tires} vehicleId={mapVehicleId} onVehicleChange={setMapVehicleId} onEdit={startEdit} onAdd={(position)=>startNew(mapVehicleId,position)} onMove={moveTire}/><div className="modal-actions"><button type="button" className="btn-ghost" onClick={()=>setMapOpen(false)}>Fechar mapa</button></div></div></div>}

      {editing && (
        <div className="modal-backdrop" onClick={()=>setEditing(null)}><form className="modal-card tire-modal" onSubmit={save} onClick={event=>event.stopPropagation()}>
          <h3 style={{ marginTop: 0 }}>{editing === "new" ? "Novo pneu" : "Editar pneu"}</h3><p>Informe a identificação, aplicação e dados de vida útil do pneu.</p>
          <div className="form-grid">
            <label className="field">
              <span>{t("fleet.vehicle")}</span>
              <select className="input" value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}>
                <option value="">{t("fleet.no_vehicle")}</option>
                {vehicles.filter((v) => v.active).map((v) => <option key={v.id} value={v.id}>{v.plate}{v.description ? ` · ${v.description}` : ""}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.fire_number")}</span>
              <input className="input" required value={form.fire_number} onChange={(e) => setForm({ ...form, fire_number: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.brand")}</span>
              <input className="input" value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.model")}</span>
              <input className="input" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.position")}</span>
              <select className="input" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })}>
                <option value="">-</option>
                {TIRE_POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.status")}</span>
              <select className="input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {TIRE_STATUSES.map((s) => <option key={s} value={s}>{t(`fleet.tire_statuses.${s}`)}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.tread_depth")}</span>
              <input className="input" type="number" min="0" step="0.1" value={form.tread_depth_mm} onChange={(e) => setForm({ ...form, tread_depth_mm: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.install_date")}</span>
              <input className="input" type="date" value={form.install_date} onChange={(e) => setForm({ ...form, install_date: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.install_km")}</span>
              <input className="input" type="number" min="0" value={form.install_km} onChange={(e) => setForm({ ...form, install_km: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.recap_count")}</span>
              <input className="input" type="number" min="0" value={form.recap_count} onChange={(e) => setForm({ ...form, recap_count: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.cost")}</span>
              <input className="input" type="number" min="0" step="0.01" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} />
            </label>
          </div>
          <div className="modal-actions">
            <button className="btn-primary" type="submit">{t("common.save")}</button>
            <button className="btn-ghost" type="button" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form></div>
      )}

      {inspecting && (
        <div className="modal-backdrop" onClick={()=>setInspecting(null)}><div className="modal-card tire-modal" onClick={event=>event.stopPropagation()}>
          <h3 style={{ marginTop: 0 }}>{t("fleet.inspections_history")} — {inspecting.fire_number}</h3>
          <form onSubmit={saveInspection} className="form-grid" style={{ marginBottom: 12 }}>
            <label className="field">
              <span>{t("fleet.inspection_date")}</span>
              <input className="input" type="date" required value={inspectionForm.inspected_at} onChange={(e) => setInspectionForm({ ...inspectionForm, inspected_at: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.inspection_odometer")}</span>
              <input className="input" type="number" min="0" value={inspectionForm.odometer_km} onChange={(e) => setInspectionForm({ ...inspectionForm, odometer_km: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.tread_depth")}</span>
              <input className="input" type="number" min="0" step="0.1" value={inspectionForm.tread_depth_mm} onChange={(e) => setInspectionForm({ ...inspectionForm, tread_depth_mm: e.target.value })} />
            </label>
            <div className="field" style={{ display: "flex", alignItems: "flex-end" }}>
              <button className="btn-primary" type="submit">{t("fleet.add_inspection")}</button>
            </div>
          </form>
          <table className="data-table">
            <thead><tr><th>{t("fleet.inspection_date")}</th><th>{t("fleet.inspection_odometer")}</th><th>{t("fleet.tread_depth")}</th></tr></thead>
            <tbody>
              {inspections.map((i) => (
                <tr key={i.id}><td>{i.inspected_at}</td><td>{i.odometer_km ?? "-"}</td><td>{i.tread_depth_mm ?? "-"}</td></tr>
              ))}
              {inspections.length === 0 && <tr><td colSpan={3} className="empty-state">-</td></tr>}
            </tbody>
          </table>
          <div className="modal-actions">
            <button className="btn-ghost" type="button" onClick={() => setInspecting(null)}>{t("common.close")}</button>
          </div>
        </div></div>
      )}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("fleet.fire_number")}</th>
              <th>{t("fleet.vehicle")}</th>
              <th>Posição</th>
              <th>{t("fleet.status")}</th>
              <th>{t("fleet.tread_depth")}</th>
              <th>{t("fleet.km_rodado")}</th>
              <th>{t("fleet.cpk")}</th>
              <th>{t("users.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {filteredTires.map((tire) => (
              <tr key={tire.id}>
                <td>{tire.fire_number}</td>
                <td>{tire.vehicle_id?<button type="button" className="tire-vehicle-link" onClick={()=>openMap(tire.vehicle_id)}>{tire.vehicle_plate ?? "Ver mapa"}</button>:"Estoque"}</td>
                <td>{tire.position ? tire.position.replaceAll("_"," ") : "Estoque"}</td>
                <td>{t(`fleet.tire_statuses.${tire.status}`)}</td>
                <td><span className={tire.tread_depth_mm != null && tire.tread_depth_mm <= 3 ? "tire-depth danger" : "tire-depth"}>{tire.tread_depth_mm != null ? `${tire.tread_depth_mm} mm` : "-"}</span></td>
                <td>{tire.km_rodado != null ? `${tire.km_rodado} km` : "-"}</td>
                <td>{tire.cpk != null ? tire.cpk.toFixed(3) : "-"}</td>
                <td>
                  <button className="btn-mini" onClick={() => openInspections(tire)}>{t("fleet.inspections_history")}</button>
                  <button className="btn-mini" onClick={() => startEdit(tire)}>{t("users.edit")}</button>
                  <button className="btn-mini danger" onClick={() => remove(tire)}>{t("common.delete")}</button>
                </td>
              </tr>
            ))}
            {filteredTires.length === 0 && <tr><td colSpan={8} className="empty-state">{tires.length ? "Nenhum pneu encontrado com os filtros informados." : t("fleet.empty_tires")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type MapPosition = {position:string;label:string};
function vehicleAxles(vehicle:Vehicle) {
  const count=Math.min(5,Math.max(2,vehicle.axles??2));
  const dual=vehicle.rear_dual_wheels??true;
  return Array.from({length:count},(_,index)=>{
    const axle=index+1;
    if(axle===1)return {axle,label:"Eixo dianteiro",left:[{position:"dianteiro_esq",label:"Dianteiro esquerdo"}],right:[{position:"dianteiro_dir",label:"Dianteiro direito"}]};
    const prefix=axle===2?"traseiro":`eixo_${axle}`;
    const left:MapPosition[]=dual?[{position:`${prefix}_esq_ext`,label:`Eixo ${axle} · esq. externo`},{position:`${prefix}_esq_int`,label:`Eixo ${axle} · esq. interno`}]:[{position:`${prefix}_esq`,label:`Eixo ${axle} · esquerdo`}];
    const right:MapPosition[]=dual?[{position:`${prefix}_dir_int`,label:`Eixo ${axle} · dir. interno`},{position:`${prefix}_dir_ext`,label:`Eixo ${axle} · dir. externo`}]:[{position:`${prefix}_dir`,label:`Eixo ${axle} · direito`}];
    return {axle,label:`Eixo traseiro ${axle-1}`,left,right};
  });
}

function TireVehicleMap({vehicles,tires,vehicleId,onVehicleChange,onEdit,onAdd,onMove}:{vehicles:Vehicle[];tires:Tire[];vehicleId:string;onVehicleChange:(value:string)=>void;onEdit:(tire:Tire)=>void;onAdd:(position:string)=>void;onMove:(tireId:number,vehicleId:number|null,position:string|null)=>void}) {
  const vehicle=vehicles.find(item=>item.id===Number(vehicleId));
  const installed=tires.filter(item=>item.vehicle_id===Number(vehicleId)&&item.status!=="descartado");
  const stock=tires.filter(item=>item.vehicle_id==null&&item.status!=="descartado");
  const byPosition=new Map(installed.map(item=>[item.position,item]));
  const spare=byPosition.get("estepe");
  const axles=vehicle?vehicleAxles(vehicle):[];
  return <section className="tire-map-panel">
    <div className="tire-map-heading"><div><h3>Mapa de pneus do veículo</h3><p>Arraste pneus para instalar, trocar posições ou devolver ao estoque.</p></div><select className="input" value={vehicleId} onChange={event=>onVehicleChange(event.target.value)}><option value="">Selecione um veículo</option>{vehicles.filter(item=>item.active).map(item=><option key={item.id} value={item.id}>{item.plate}{item.description?` · ${item.description}`:""}</option>)}</select></div>
    {!vehicle?<div className="tire-map-empty"><span className="tire-map-empty-icon">🚚</span><strong>Selecione uma placa para abrir o mapa</strong><small>Os pneus instalados serão posicionados automaticamente.</small></div>:<div className="tire-map-workspace">
      <div className="tire-map-vehicle">
        <div className="tire-map-plate">{vehicle.plate}</div>
        <div className="tire-map-dynamic">
          <div className="tire-map-cab"><div className="vehicle-windshield"></div><div className="vehicle-grille"></div><strong>FRENTE</strong></div>
          {axles.map(row=><div className={`tire-axle-row ${row.axle===1?"front":"rear"}`} key={row.axle}>
            <div className="tire-side-group left">{row.left.map(item=><TireSlot key={item.position} vehicleId={vehicle.id} position={item.position} label={item.label} tire={byPosition.get(item.position)} onEdit={onEdit} onAdd={onAdd} onMove={onMove}/>)}</div>
            <div className="tire-axle-drawing"><span></span><b>{row.axle}</b><span></span><small>{row.label}</small></div>
            <div className="tire-side-group right">{row.right.map(item=><TireSlot key={item.position} vehicleId={vehicle.id} position={item.position} label={item.label} tire={byPosition.get(item.position)} onEdit={onEdit} onAdd={onAdd} onMove={onMove}/>)}</div>
          </div>)}
        </div>
      </div>
      <div className="tire-map-side">
        <aside className="tire-spare"><span>Estepe</span><TireSlot vehicleId={vehicle.id} position="estepe" label="Pneu reserva" tire={spare} onEdit={onEdit} onAdd={onAdd} onMove={onMove}/><small>{installed.length} pneu(s) vinculados a esta placa</small></aside>
        <aside className="tire-map-stock" onDragOver={event=>{event.preventDefault();event.currentTarget.classList.add("drag-over")}} onDragLeave={event=>event.currentTarget.classList.remove("drag-over")} onDrop={event=>{event.preventDefault();event.currentTarget.classList.remove("drag-over");const id=Number(event.dataTransfer.getData("application/x-tire-id"));if(id)onMove(id,null,null)}}>
          <div className="tire-stock-title"><span>Estoque</span><strong>{stock.length}</strong></div><small>Arraste para cá para remover do veículo.</small>
          <div className="tire-stock-list">{stock.map(tire=><button key={tire.id} type="button" draggable onDragStart={event=>{event.dataTransfer.setData("application/x-tire-id",String(tire.id));event.dataTransfer.effectAllowed="move"}} onClick={()=>onEdit(tire)}><span className="tire-map-rubber"></span><span><strong>{tire.fire_number}</strong><small>{tire.tread_depth_mm!=null?`${tire.tread_depth_mm} mm`:(tire.brand||"Sem medição")}</small></span></button>)}{stock.length===0&&<em>Estoque vazio</em>}</div>
        </aside>
      </div>
    </div>}
  </section>;
}

function TireSlot({vehicleId,position,label,tire,onEdit,onAdd,onMove}:{vehicleId:number;position:string;label:string;tire?:Tire;onEdit:(tire:Tire)=>void;onAdd:(position:string)=>void;onMove:(tireId:number,vehicleId:number,position:string)=>void}){
  const attention=tire?.tread_depth_mm!=null&&tire.tread_depth_mm<=3;
  return <button type="button" draggable={Boolean(tire)} data-position={position} className={`tire-map-slot ${tire?"occupied":"empty"} ${attention?"attention":""}`} onDragStart={event=>{if(!tire)return;event.dataTransfer.setData("application/x-tire-id",String(tire.id));event.dataTransfer.effectAllowed="move"}} onDragOver={event=>{event.preventDefault();event.currentTarget.classList.add("drag-over")}} onDragLeave={event=>event.currentTarget.classList.remove("drag-over")} onDrop={event=>{event.preventDefault();event.currentTarget.classList.remove("drag-over");const id=Number(event.dataTransfer.getData("application/x-tire-id"));if(id&&id!==tire?.id)onMove(id,vehicleId,position)}} onClick={()=>tire?onEdit(tire):onAdd(position)}><span className="tire-map-rubber"></span><span className="tire-map-slot-copy"><small>{label}</small><strong>{tire?tire.fire_number:"Solte o pneu aqui"}</strong>{tire&&<em>{tire.tread_depth_mm!=null?`${tire.tread_depth_mm} mm de sulco`:"Sem medição"}</em>}</span><span className="tire-drag-handle" aria-hidden="true">⠿</span></button>
}

// ---------------------------------------------------------------------------
// Ordens de serviço
// ---------------------------------------------------------------------------

function OrdersTab({ vehicles, onError }: { vehicles: Vehicle[]; onError: (msg: string) => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [orders, setOrders] = useState<MaintenanceOrder[]>([]);
  const [plans, setPlans] = useState<MaintenancePlan[]>([]);
  const [providers, setProviders] = useState<ServiceProvider[]>([]);
  const [editing, setEditing] = useState<MaintenanceOrder | "new" | null>(null);
  const [filters, setFilters] = useState({ date: "", vehicle_id: "", plan_id: "", provider_id: "" });
  const [form, setForm] = useState({
    vehicle_id: "", plan_id: "", provider_id: "", kind: "corretiva", description: "",
    opened_at: new Date().toISOString().slice(0, 10), expected_completion_date: new Date().toISOString().slice(0, 10), odometer_km: "", cost: "", attachment: null as File | null, budget: null as File | null,
  });

  function reload() {
    api.get<MaintenanceOrder[]>("/fleet-maintenance/maintenance-orders").then((r) => setOrders(r.data)).catch(() => setOrders([]));
    api.get<MaintenancePlan[]>("/fleet-maintenance/maintenance-plans").then((r) => setPlans(r.data)).catch(() => setPlans([]));
    api.get<ServiceProvider[]>("/service-providers").then((r) => setProviders(r.data)).catch(() => setProviders([]));
  }
  useEffect(reload, []);

  function startNew() {
    setForm({ vehicle_id: "", plan_id: "", provider_id: "", kind: "corretiva", description: "", opened_at: new Date().toISOString().slice(0, 10), expected_completion_date: new Date().toISOString().slice(0, 10), odometer_km: "", cost: "", attachment: null, budget: null });
    setEditing("new");
  }

  function startEdit(order: MaintenanceOrder) {
    setForm({
      vehicle_id: String(order.vehicle_id), plan_id: order.plan_id ? String(order.plan_id) : "", provider_id: order.provider_id ? String(order.provider_id) : "",
      kind: order.kind, description: order.description, opened_at: order.opened_at, expected_completion_date: order.expected_completion_date||order.opened_at, odometer_km: order.odometer_km != null ? String(order.odometer_km) : "",
      cost: order.cost != null ? String(order.cost) : "", attachment: null, budget: null,
    });
    setEditing(order);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    onError("");
    const payload = new FormData();
    payload.set("branch_id", String(user?.branch_id ?? 1));
    payload.set("vehicle_id", form.vehicle_id);
    payload.set("kind", form.kind);
    payload.set("description", form.description);
    payload.set("opened_at", form.opened_at);
    payload.set("expected_completion_date", form.expected_completion_date);
    if (form.plan_id) payload.set("plan_id", form.plan_id);
    if (form.provider_id) payload.set("provider_id", form.provider_id);
    if (form.odometer_km) payload.set("odometer_km", form.odometer_km);
    if (form.cost) payload.set("cost", form.cost);
    if (form.attachment) payload.set("attachment", form.attachment);
    if (form.budget) payload.set("budget", form.budget);
    try {
      if (editing === "new") await api.post("/fleet-maintenance/maintenance-orders", payload);
      else if (editing) await api.put(`/fleet-maintenance/maintenance-orders/${editing.id}`, {
        vehicle_id: Number(form.vehicle_id), plan_id: form.plan_id ? Number(form.plan_id) : null,
        provider_id: form.provider_id ? Number(form.provider_id) : null, kind: form.kind,
        description: form.description, opened_at: form.opened_at, expected_completion_date: form.expected_completion_date,
        odometer_km: form.odometer_km ? Number(form.odometer_km) : null, cost: form.cost ? Number(form.cost) : null,
      });
      setEditing(null);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function setStatus(order: MaintenanceOrder, status: string) {
    try {
      await api.put(`/fleet-maintenance/maintenance-orders/${order.id}`, { status });
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function uploadBudget(order: MaintenanceOrder, file: File) {
    const payload = new FormData();
    payload.set("budget", file);
    try {
      await api.post(`/fleet-maintenance/maintenance-orders/${order.id}/budget`, payload);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function openAttachment(attachmentId:number|undefined|null) {
    if (!attachmentId) { onError("Documento não localizado."); return; }
    onError("");
    const documentWindow=window.open("","_blank");
    try {
      const {data}=await api.get(`/gallery/files/${attachmentId}`,{responseType:"blob"});
      const objectUrl=URL.createObjectURL(data);if(documentWindow)documentWindow.location.href=objectUrl;else window.location.href=objectUrl;
      window.setTimeout(()=>URL.revokeObjectURL(objectUrl),60000);
    } catch(err:any) { documentWindow?.close();onError(err?.response?.data?.detail||"Não foi possível abrir o documento."); }
  }

  async function decideApproval(order: MaintenanceOrder, decision: "approve" | "reject") {
    if (decision === "approve" && (!order.cost || Number(order.cost) <= 0)) { onError("Informe o custo da OS antes de aprovar."); return; }
    const notes = await appPrompt(decision === "approve" ? "Registre uma observação para a aprovação, se necessário." : "Informe por que esta ordem de serviço está sendo rejeitada.",{title:decision === "approve"?"Aprovar ordem de serviço":"Rejeitar ordem de serviço",label:decision === "approve"?"Observação (opcional)":"Motivo da rejeição",required:decision === "reject",confirmLabel:"Continuar"});
    if (notes === null || (decision === "reject" && !notes.trim())) return;
    if (!await appConfirm(decision === "approve" ? `Aprovar a OS e lançar ${Number(order.cost).toLocaleString("pt-BR",{style:"currency",currency:"BRL"})} em Despesas?` : "Confirmar a rejeição desta OS?",{title:decision === "approve"?"Confirmar aprovação":"Confirmar rejeição",confirmLabel:decision === "approve"?"Aprovar e lançar despesa":"Rejeitar OS",danger:decision === "reject"})) return;
    try {
      await api.post(`/fleet-maintenance/maintenance-orders/${order.id}/${decision}`, {notes:notes.trim()||null});
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function remove(order: MaintenanceOrder) {
    if (!await appConfirm(t("fleet.delete_confirm") ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
    try {
      await api.delete(`/fleet-maintenance/maintenance-orders/${order.id}`);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_delete"));
    }
  }

  const filteredOrders = orders.filter((order) =>
    (!filters.date || order.opened_at === filters.date) &&
    (!filters.vehicle_id || order.vehicle_id === Number(filters.vehicle_id)) &&
    (!filters.plan_id || order.plan_id === Number(filters.plan_id)) &&
    (!filters.provider_id || order.provider_id === Number(filters.provider_id))
  );

  return (
    <div>
      <div className="order-toolbar">
        <div className="order-filters">
          <label className="field"><span>Data</span><input className="input" type="date" value={filters.date} onChange={(e)=>setFilters({...filters,date:e.target.value})}/></label>
          <label className="field"><span>{t("fleet.vehicle")}</span><select className="input" value={filters.vehicle_id} onChange={(e)=>setFilters({...filters,vehicle_id:e.target.value})}><option value="">Todos</option>{vehicles.filter(v=>v.active).map(v=><option key={v.id} value={v.id}>{v.plate}</option>)}</select></label>
          <label className="field"><span>Plano</span><select className="input" value={filters.plan_id} onChange={(e)=>setFilters({...filters,plan_id:e.target.value})}><option value="">Todos</option>{plans.map(p=><option key={p.id} value={p.id}>{p.service_name} — {p.vehicle_plate}</option>)}</select></label>
          <label className="field"><span>Prestador</span><select className="input" value={filters.provider_id} onChange={(e)=>setFilters({...filters,provider_id:e.target.value})}><option value="">Todos</option>{providers.filter(p=>p.active).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          {(filters.date||filters.vehicle_id||filters.plan_id||filters.provider_id)&&<button type="button" className="btn-ghost" onClick={()=>setFilters({date:"",vehicle_id:"",plan_id:"",provider_id:""})}>Limpar</button>}
        </div>
        <button className="btn-primary btn-add" onClick={startNew}><span className="btn-add-symbol">+</span><span>{t("fleet.new")}</span></button>
      </div>

      {editing && (
        <div className="modal-backdrop" onClick={()=>setEditing(null)}><form className="modal-card order-modal" onSubmit={save} onClick={e=>e.stopPropagation()}>
          <h3 style={{ marginTop: 0 }}>{editing === "new" ? "Nova ordem de serviço" : "Editar ordem de serviço"}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("fleet.vehicle")}</span>
              <select className="input" required value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}>
                <option value="">{t("fleet.select_vehicle")}</option>
                {vehicles.filter((v) => v.active).map((v) => <option key={v.id} value={v.id}>{v.plate}{v.description ? ` · ${v.description}` : ""}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.order_kind")}</span>
              <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {ORDER_KINDS.map((k) => <option key={k} value={k}>{t(`fleet.order_kinds.${k}`)}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.plan_link")}</span>
              <select className="input" value={form.plan_id} onChange={(e) => setForm({ ...form, plan_id: e.target.value })}>
                <option value="">{t("fleet.no_plan")}</option>
                {plans.filter((p) => p.active && (!form.vehicle_id || p.vehicle_id === Number(form.vehicle_id))).map((p) => (
                  <option key={p.id} value={p.id}>{p.service_name} — {p.vehicle_plate}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.tab_providers")}</span>
              <select className="input" value={form.provider_id} onChange={(e) => setForm({ ...form, provider_id: e.target.value })}>
                <option value="">-</option>
                {providers.filter((p) => p.active).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.opened_at")}</span>
              <input className="input" type="date" required value={form.opened_at} onChange={(e) => setForm({ ...form, opened_at: e.target.value })} />
            </label>
            <label className="field"><span>Previsão de conclusão</span><input className="input" type="date" required min={form.opened_at} value={form.expected_completion_date} onChange={(e)=>setForm({...form,expected_completion_date:e.target.value})}/></label>
            <label className="field">
              <span>{t("fleet.odometer")}</span>
              <input className="input" type="number" min="0" value={form.odometer_km} onChange={(e) => setForm({ ...form, odometer_km: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.cost")}</span>
              <input className="input" type="number" min="0" step="0.01" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} />
            </label>
            {editing === "new" && <div className="field">
              <span>{t("fleet.attachment")}</span>
              <input type="file" accept="image/*,application/pdf" onChange={(e) => setForm({ ...form, attachment: e.target.files?.[0] ?? null })} />
            </div>}
            {editing === "new" && <div className="field">
              <span>{t("fleet.order_budget")}</span>
              <input type="file" accept="image/*,application/pdf" onChange={(e) => setForm({ ...form, budget: e.target.files?.[0] ?? null })} />
            </div>}
          </div>
          <label className="field" style={{ marginTop: 10 }}>
            <span>{t("fleet.description")}</span>
            <textarea className="input" required style={{ minHeight: 74, resize: "vertical" }} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </label>
          <div className="modal-actions">
            <button className="btn-primary" type="submit">{t("common.save")}</button>
            <button className="btn-ghost" type="button" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form></div>
      )}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("fleet.opened_at")}</th>
              <th>{t("fleet.vehicle")}</th>
              <th>{t("fleet.order_kind")}</th>
              <th>{t("fleet.tab_providers")}</th>
              <th>{t("fleet.description")}</th>
              <th>{t("fleet.cost")}</th>
              <th>{t("fleet.order_status")}</th>
              <th>SLA</th>
              <th>{t("fleet.attachment")}</th>
              <th>{t("fleet.order_budget")} / {t("fleet.order_approval")}</th>
              <th>{t("users.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {filteredOrders.map((o) => (
              <tr key={o.id}>
                <td>{o.opened_at}</td>
                <td>{o.vehicle_plate ?? "-"}</td>
                <td>{t(`fleet.order_kinds.${o.kind}`)}</td>
                <td>{o.provider_name ?? "-"}</td>
                <td>{o.description}</td>
                <td>{o.cost ?? "-"}</td>
                <td>
                  <select className="input" value={o.status} onChange={(e) => setStatus(o, e.target.value)} style={{ padding: "2px 6px" }}>
                    {ORDER_STATUSES.map((s) => <option key={s} value={s}>{t(`fleet.order_statuses.${s}`)}</option>)}
                  </select>
                </td>
                <td><span className={`driver-status ${o.sla_status==="overdue"?"expired":o.sla_status==="attention"||o.sla_status==="pending"?"warning":"ok"}`}>{o.sla_status==="overdue"?"Vencido":o.sla_status==="attention"?"Atenção":o.sla_status==="on_time"?"No prazo":"Sem previsão"}</span><small className="order-approval-meta">{o.expected_completion_date||"—"}</small></td>
                <td>{o.attachment_id ? <button type="button" className="attachment-link" onClick={()=>void openAttachment(o.attachment_id)}>{o.attachment_filename ?? t("fleet.attachment")}</button> : "-"}</td>
                <td>
                  {o.budget_attachment_id ? (
                    <>
                      <button type="button" className="attachment-link" onClick={()=>void openAttachment(o.budget_attachment_id)}>{o.budget_filename ?? t("fleet.order_budget")}</button>
                      {" · "}
                      <span style={o.approval_status === "aprovado" ? okBadge : o.approval_status === "rejeitado" ? dueBadge : undefined}>
                        {t(`fleet.approval_statuses.${o.approval_status}`)}
                      </span>
                      {o.approved_by_name&&o.approved_at&&<small className="order-approval-meta">{o.approval_status==="aprovado"?"Aprovada":"Rejeitada"} por {o.approved_by_name}<br/>{new Date(o.approved_at).toLocaleString("pt-BR")}{o.expense_id&&<> · Despesa #{o.expense_id}</>}</small>}
                      {o.approval_status === "pendente" && (
                        <div style={{ marginTop: 4, display: "flex", gap: 4 }}>
                          <button type="button" className="btn-mini" onClick={() => decideApproval(o, "approve")}>{t("fleet.approve")}</button>
                          <button type="button" className="btn-mini danger" onClick={() => decideApproval(o, "reject")}>{t("fleet.reject")}</button>
                        </div>
                      )}
                    </>
                  ) : (
                    <label className="btn-mini" style={{ cursor: "pointer" }}>
                      {t("fleet.order_budget_upload")}
                      <input type="file" accept="image/*,application/pdf" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadBudget(o, f); }} />
                    </label>
                  )}
                </td>
                <td><div className="occurrence-actions"><button className="btn-mini" onClick={()=>startEdit(o)}>{t("users.edit")}</button><button className="btn-mini danger" onClick={() => remove(o)}>{t("common.delete")}</button></div></td>
              </tr>
            ))}
            {filteredOrders.length === 0 && <tr><td colSpan={11} className="empty-state">{orders.length ? "Nenhuma ordem encontrada com os filtros informados." : t("fleet.empty_orders")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Planos preventivos
// ---------------------------------------------------------------------------

function PlansTab({ vehicles, onError }: { vehicles: Vehicle[]; onError: (msg: string) => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [plans, setPlans] = useState<MaintenancePlan[]>([]);
  const [correctiveOrders, setCorrectiveOrders] = useState<MaintenanceOrder[]>([]);
  const [maintenanceView, setMaintenanceView] = useState<"preventive"|"corrective">("preventive");
  const [editing, setEditing] = useState<MaintenancePlan | "new" | null>(null);
  const [filters, setFilters] = useState({ query: "", vehicle_id: "", status: "" });
  const [form, setForm] = useState({ vehicle_id: "", service_name: "", interval_km: "", interval_days: "", last_done_at: "", last_done_km: "" });

  function reload() {
    api.get<MaintenancePlan[]>("/fleet-maintenance/maintenance-plans").then((r) => setPlans(r.data)).catch(() => setPlans([]));
    api.get<MaintenanceOrder[]>("/fleet-maintenance/maintenance-orders").then((r)=>setCorrectiveOrders(r.data.filter(order=>order.kind==="corretiva"))).catch(()=>setCorrectiveOrders([]));
  }
  useEffect(reload, []);

  function startNew() {
    setForm({ vehicle_id: "", service_name: "", interval_km: "", interval_days: "", last_done_at: "", last_done_km: "" });
    setEditing("new");
  }

  function startEdit(plan: MaintenancePlan) {
    setForm({ vehicle_id:String(plan.vehicle_id), service_name:plan.service_name, interval_km:plan.interval_km!=null?String(plan.interval_km):"", interval_days:plan.interval_days!=null?String(plan.interval_days):"", last_done_at:plan.last_done_at||"", last_done_km:plan.last_done_km!=null?String(plan.last_done_km):"" });
    setEditing(plan);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    onError("");
    if (!form.interval_km && !form.interval_days) {
      onError(t("fleet.err_interval_required"));
      return;
    }
    try {
      const payload = {
        branch_id: user?.branch_id ?? 1,
        vehicle_id: Number(form.vehicle_id), service_name: form.service_name,
        interval_km: form.interval_km ? Number(form.interval_km) : null,
        interval_days: form.interval_days ? Number(form.interval_days) : null,
        last_done_at: form.last_done_at || null,
        last_done_km: form.last_done_km ? Number(form.last_done_km) : null,
      };
      if (editing === "new") await api.post("/fleet-maintenance/maintenance-plans", payload);
      else if (editing) await api.put(`/fleet-maintenance/maintenance-plans/${editing.id}`, payload);
      setEditing(null);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function toggleActive(plan: MaintenancePlan) {
    try {
      await api.put(`/fleet-maintenance/maintenance-plans/${plan.id}`, { active: !plan.active });
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function updateCorrectiveStatus(order: MaintenanceOrder, status: string) {
    try { await api.put(`/fleet-maintenance/maintenance-orders/${order.id}`, {status}); reload(); }
    catch (err:any) { onError(err?.response?.data?.detail ?? t("fleet.err_save")); }
  }

  async function remove(plan: MaintenancePlan) {
    if (!await appConfirm(t("fleet.delete_confirm") ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
    try {
      await api.delete(`/fleet-maintenance/maintenance-plans/${plan.id}`);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_delete"));
    }
  }

  const filteredPlans = plans.filter(plan =>
    (!filters.query || plan.service_name.toLowerCase().includes(filters.query.toLowerCase())) &&
    (!filters.vehicle_id || plan.vehicle_id === Number(filters.vehicle_id)) &&
    (!filters.status || (filters.status === "due" ? plan.due : !plan.due))
  );
  const maintenanceStats = { total:plans.length, due:plans.filter(plan=>plan.due&&plan.active).length, current:plans.filter(plan=>!plan.due&&plan.active).length, corrective:correctiveOrders.filter(order=>!["concluida","cancelada"].includes(order.status)).length };
  const filteredCorrectives = correctiveOrders.filter(order => (!filters.query || order.description.toLowerCase().includes(filters.query.toLowerCase())) && (!filters.vehicle_id || order.vehicle_id===Number(filters.vehicle_id)) && (!filters.status || order.status===filters.status));

  return (
    <div>
      <div className="maintenance-summary"><article><span>Planos preventivos</span><strong>{maintenanceStats.total}</strong></article><article className={maintenanceStats.due?"maintenance-alert":""}><span>Preventivas vencidas</span><strong>{maintenanceStats.due}</strong></article><article><span>Preventivas em dia</span><strong>{maintenanceStats.current}</strong></article><article className={maintenanceStats.corrective?"maintenance-alert":""}><span>Corretivas abertas</span><strong>{maintenanceStats.corrective}</strong></article></div>
      <div className="maintenance-switch"><button className={maintenanceView==="preventive"?"active":""} onClick={()=>{setMaintenanceView("preventive");setFilters({...filters,status:""})}}>Preventivas</button><button className={maintenanceView==="corrective"?"active":""} onClick={()=>{setMaintenanceView("corrective");setFilters({...filters,status:""})}}>Corretivas</button></div>
      <div className="maintenance-toolbar"><div className="maintenance-filters"><input className="input" placeholder="Buscar serviço..." value={filters.query} onChange={e=>setFilters({...filters,query:e.target.value})}/><select className="input" value={filters.vehicle_id} onChange={e=>setFilters({...filters,vehicle_id:e.target.value})}><option value="">Todos os veículos</option>{vehicles.filter(v=>v.active).map(v=><option key={v.id} value={v.id}>{v.plate}</option>)}</select><select className="input" value={filters.status} onChange={e=>setFilters({...filters,status:e.target.value})}>{maintenanceView==="preventive"?<><option value="">Todas as situações</option><option value="due">Vencidas</option><option value="current">Em dia</option></>:<><option value="">Todos os status</option>{ORDER_STATUSES.map(status=><option key={status} value={status}>{t(`fleet.order_statuses.${status}`)}</option>)}</>}</select></div><button className="btn-primary btn-add" onClick={maintenanceView==="preventive"?startNew:()=>{window.location.href="/fleet-maintenance?tab=orders"}}><span className="btn-add-symbol">+</span><span>{maintenanceView==="preventive"?"Novo plano":"Nova corretiva"}</span></button></div>

      {editing && (
        <div className="modal-backdrop" onClick={()=>setEditing(null)}><form className="modal-card maintenance-modal" onSubmit={save} onClick={event=>event.stopPropagation()}>
          <h3 style={{ marginTop: 0 }}>{editing === "new" ? "Novo plano preventivo" : "Editar plano preventivo"}</h3><p>Configure a recorrência por quilometragem, dias ou pelos dois critérios.</p>
          <div className="form-grid">
            <label className="field">
              <span>{t("fleet.vehicle")}</span>
              <select className="input" required value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}>
                <option value="">{t("fleet.select_vehicle")}</option>
                {vehicles.filter((v) => v.active).map((v) => <option key={v.id} value={v.id}>{v.plate}{v.description ? ` · ${v.description}` : ""}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.plan_service")}</span>
              <input className="input" required value={form.service_name} onChange={(e) => setForm({ ...form, service_name: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.interval_km")}</span>
              <input className="input" type="number" min="0" value={form.interval_km} onChange={(e) => setForm({ ...form, interval_km: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.interval_days")}</span>
              <input className="input" type="number" min="0" value={form.interval_days} onChange={(e) => setForm({ ...form, interval_days: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.last_done_at")}</span>
              <input className="input" type="date" value={form.last_done_at} onChange={(e) => setForm({ ...form, last_done_at: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.last_done_km")}</span>
              <input className="input" type="number" min="0" value={form.last_done_km} onChange={(e) => setForm({ ...form, last_done_km: e.target.value })} />
            </label>
          </div>
          <div className="modal-actions">
            <button className="btn-primary" type="submit">{t("common.save")}</button>
            <button className="btn-ghost" type="button" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form></div>
      )}

      {maintenanceView==="preventive"&&<div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("fleet.vehicle")}</th>
              <th>{t("fleet.plan_service")}</th>
              <th>{t("fleet.interval_km")}</th>
              <th>{t("fleet.interval_days")}</th>
              <th>{t("fleet.last_done_at")}</th>
              <th>{t("fleet.status")}</th>
              <th>{t("users.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {filteredPlans.map((p) => (
              <tr key={p.id}>
                <td>{p.vehicle_plate ?? "-"}</td>
                <td>{p.service_name}</td>
                <td>{p.interval_km != null ? `${p.interval_km.toLocaleString("pt-BR")} km` : "-"}</td>
                <td>{p.interval_days != null ? `${p.interval_days} dias` : "-"}</td>
                <td>{p.last_done_at ?? "-"}</td>
                <td>
                  <span style={p.due ? dueBadge : okBadge}>{p.due ? t("fleet.due") : t("fleet.up_to_date")}</span>
                </td>
                <td>
                  <button className="btn-mini" onClick={()=>startEdit(p)}>{t("users.edit")}</button>
                  <button className="btn-mini" onClick={() => toggleActive(p)}>{p.active ? "Desativar" : "Ativar"}</button>
                  <button className="btn-mini danger" onClick={() => remove(p)}>{t("common.delete")}</button>
                </td>
              </tr>
            ))}
            {filteredPlans.length === 0 && <tr><td colSpan={7} className="empty-state">{plans.length ? "Nenhum plano encontrado com os filtros informados." : t("fleet.empty_plans")}</td></tr>}
          </tbody>
        </table>
      </div>}
      {maintenanceView==="corrective"&&<div className="table-scroll"><table className="data-table"><thead><tr><th>Aberta em</th><th>Veículo</th><th>Descrição</th><th>Prestador</th><th>Custo</th><th>Status</th></tr></thead><tbody>{filteredCorrectives.map(order=><tr key={order.id}><td>{order.opened_at}</td><td><strong>{order.vehicle_plate||"-"}</strong></td><td>{order.description}</td><td>{order.provider_name||"-"}</td><td>{order.cost!=null?Number(order.cost).toLocaleString("pt-BR",{style:"currency",currency:"BRL"}):"-"}</td><td><select className="input" value={order.status} onChange={event=>void updateCorrectiveStatus(order,event.target.value)}>{ORDER_STATUSES.map(status=><option key={status} value={status}>{t(`fleet.order_statuses.${status}`)}</option>)}</select></td></tr>)}{filteredCorrectives.length===0&&<tr><td colSpan={6} className="empty-state">Nenhuma manutenção corretiva encontrada.</td></tr>}</tbody></table></div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Prestadores de serviço + busca por raio de km
// ---------------------------------------------------------------------------

function ProvidersTab({ vehicles, onError }: { vehicles: Vehicle[]; onError: (msg: string) => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [providers, setProviders] = useState<ServiceProvider[]>([]);
  const [editing, setEditing] = useState<"new" | null>(null);
  const [form, setForm] = useState({
    name: "", document: "", category: "oficina_mecanica", phone: "", email: "", address: "", latitude: "", longitude: "", authorized: true,
  });

  const [radiusKm, setRadiusKm] = useState("25");
  const [nearbyCategory, setNearbyCategory] = useState("");
  const [searchVehicleId, setSearchVehicleId] = useState("");
  const [results, setResults] = useState<ServiceProviderNearby[] | null>(null);
  const [searching, setSearching] = useState(false);

  function reload() {
    api.get<ServiceProvider[]>("/service-providers").then((r) => setProviders(r.data)).catch(() => setProviders([]));
  }
  useEffect(reload, []);

  function startNew() {
    setForm({ name: "", document: "", category: "oficina_mecanica", phone: "", email: "", address: "", latitude: "", longitude: "", authorized: true });
    setEditing("new");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    onError("");
    try {
      await api.post("/service-providers", {
        branch_id: user?.branch_id ?? null,
        name: form.name, document: form.document || null, category: form.category,
        phone: form.phone || null, email: form.email || null, address: form.address || null,
        latitude: form.latitude ? Number(form.latitude) : null, longitude: form.longitude ? Number(form.longitude) : null,
        authorized: form.authorized,
      });
      setEditing(null);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function remove(provider: ServiceProvider) {
    if (!await appConfirm(t("fleet.delete_confirm") ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
    try {
      await api.delete(`/service-providers/${provider.id}`);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_delete"));
    }
  }

  async function searchByMyLocation() {
    onError("");
    setSearching(true);
    setResults(null);
    const pos = await getBrowserPosition();
    setSearching(false);
    if (!pos) { onError(t("fleet.nearby_location_denied")); return; }
    await runSearch(pos.latitude, pos.longitude);
  }

  async function searchByVehicle() {
    if (!searchVehicleId) { onError(t("fleet.nearby_need_location")); return; }
    onError("");
    setSearching(true);
    setResults(null);
    try {
      const { data } = await api.get(`/service-providers/vehicle-position/${searchVehicleId}`);
      if (!data.latitude || !data.longitude) {
        setSearching(false);
        onError(t("fleet.nearby_no_vehicle_position"));
        return;
      }
      await runSearch(data.latitude, data.longitude);
    } catch (err: any) {
      setSearching(false);
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function runSearch(lat: number, lng: number) {
    try {
      const { data } = await api.get<ServiceProviderNearby[]>("/service-providers/nearby", {
        params: { lat, lng, radius_km: Number(radiusKm) || 25, category: nearbyCategory || undefined },
      });
      setResults(data);
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    } finally {
      setSearching(false);
    }
  }

  return (
    <div>
      <section className="card-panel form-panel" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("fleet.nearby_title")}</h3>
        <div className="form-grid">
          <label className="field">
            <span>{t("fleet.nearby_radius")}</span>
            <input className="input" type="number" min="1" max="500" value={radiusKm} onChange={(e) => setRadiusKm(e.target.value)} />
          </label>
          <label className="field">
            <span>{t("fleet.provider_category")}</span>
            <select className="input" value={nearbyCategory} onChange={(e) => setNearbyCategory(e.target.value)}>
              <option value="">-</option>
              {PROVIDER_CATEGORIES.map((c) => <option key={c} value={c}>{t(`fleet.provider_categories.${c}`)}</option>)}
            </select>
          </label>
          <label className="field">
            <span>{t("fleet.vehicle")}</span>
            <select className="input" value={searchVehicleId} onChange={(e) => setSearchVehicleId(e.target.value)}>
              <option value="">{t("fleet.select_vehicle")}</option>
              {vehicles.filter((v) => v.active).map((v) => <option key={v.id} value={v.id}>{v.plate}</option>)}
            </select>
          </label>
          <div className="field" style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
            <button type="button" className="btn-primary" disabled={searching} onClick={searchByMyLocation}>{t("fleet.nearby_use_my_location")}</button>
            <button type="button" className="btn-ghost" disabled={searching} onClick={searchByVehicle}>{t("fleet.nearby_use_vehicle")}</button>
          </div>
        </div>

        {results && (
          <div className="table-scroll" style={{ marginTop: 12 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("fleet.provider_name")}</th>
                  <th>{t("fleet.provider_category")}</th>
                  <th>{t("fleet.nearby_distance")}</th>
                  <th>{t("fleet.provider_phone")}</th>
                  <th>{t("fleet.provider_address")}</th>
                </tr>
              </thead>
              <tbody>
                {results.map((p) => (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td>{t(`fleet.provider_categories.${p.category}`)}</td>
                    <td>{p.distance_km} km</td>
                    <td>{p.phone ?? "-"}</td>
                    <td>{p.address ?? "-"}</td>
                  </tr>
                ))}
                {results.length === 0 && <tr><td colSpan={5} className="empty-state">{t("fleet.nearby_empty")}</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <button className="btn-primary btn-add" onClick={startNew}><span className="btn-add-symbol">+</span><span>{t("fleet.new")}</span></button>
      </div>

      {editing && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
        <form className="modal-card driver-modal" onSubmit={save} onClick={(event) => event.stopPropagation()}>
          <h3 style={{ marginTop: 0 }}>{t("fleet.new")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("fleet.provider_name")}</span>
              <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.provider_document")}</span>
              <input className="input" value={form.document} onChange={(e) => setForm({ ...form, document: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.provider_category")}</span>
              <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {PROVIDER_CATEGORIES.map((c) => <option key={c} value={c}>{t(`fleet.provider_categories.${c}`)}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.provider_phone")}</span>
              <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.provider_email")}</span>
              <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.provider_address")}</span>
              <input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.provider_lat")}</span>
              <input className="input" type="number" step="0.000001" value={form.latitude} onChange={(e) => setForm({ ...form, latitude: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("fleet.provider_lng")}</span>
              <input className="input" type="number" step="0.000001" value={form.longitude} onChange={(e) => setForm({ ...form, longitude: e.target.value })} />
            </label>
            <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={form.authorized} onChange={(e) => setForm({ ...form, authorized: e.target.checked })} />
              <span>{t("fleet.provider_authorized")}</span>
            </label>
          </div>
          <div className="modal-actions">
            <button className="btn-primary" type="submit">{t("common.save")}</button>
            <button className="btn-ghost" type="button" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form>
        </div>
      )}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("fleet.provider_name")}</th>
              <th>{t("fleet.provider_category")}</th>
              <th>{t("fleet.provider_phone")}</th>
              <th>{t("fleet.provider_address")}</th>
              <th>{t("fleet.provider_authorized")}</th>
              <th>{t("users.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>{t(`fleet.provider_categories.${p.category}`)}</td>
                <td>{p.phone ?? "-"}</td>
                <td>{p.address ?? "-"}</td>
                <td>{p.authorized ? t("common.yes") : t("common.no")}</td>
                <td><button className="btn-mini danger" onClick={() => remove(p)}>{t("common.delete")}</button></td>
              </tr>
            ))}
            {providers.length === 0 && <tr><td colSpan={6} className="empty-state">{t("fleet.empty_providers")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Checklist de veículo
// ---------------------------------------------------------------------------

function ChecklistTab({ vehicles, onError }: { vehicles: Vehicle[]; onError: (msg: string) => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [checklists, setChecklists] = useState<VehicleChecklist[]>([]);
  const [templateItems, setTemplateItems] = useState<ChecklistTemplateItem[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [editing, setEditing] = useState<VehicleChecklist | "new" | null>(null);
  const [form, setForm] = useState({
    vehicle_id: "", driver_id: "", kind: "saida", performed_at: new Date().toISOString().slice(0, 10), notes: "",
  });
  const [itemStatus, setItemStatus] = useState<Record<number, { status: string; notes: string }>>({});
  const [checklistTires,setChecklistTires]=useState<Tire[]>([]);
  const [tireMeasurements,setTireMeasurements]=useState<Record<number,string>>({});

  function reload() {
    api.get<VehicleChecklist[]>("/vehicle-checklist").then((r) => setChecklists(r.data)).catch(() => setChecklists([]));
  }
  useEffect(reload, []);
  useEffect(() => {
    api.get<ChecklistTemplateItem[]>("/vehicle-checklist/template-items").then((r) => setTemplateItems(r.data)).catch(() => setTemplateItems([]));
  }, []);
  useEffect(() => {
    api.get<Driver[]>("/drivers").then((r) => setDrivers(r.data)).catch(() => setDrivers([]));
  }, []);
  useEffect(()=>{
    if(!form.vehicle_id){setChecklistTires([]);return;}
    api.get<Tire[]>("/fleet-maintenance/tires").then(r=>setChecklistTires(r.data.filter(tire=>tire.vehicle_id===Number(form.vehicle_id)&&tire.status!=="descartado"))).catch(()=>setChecklistTires([]));
  },[form.vehicle_id]);

  function startNew() {
    setForm({ vehicle_id: "", driver_id: "", kind: "saida", performed_at: new Date().toISOString().slice(0, 10), notes: "" });
    const initial: Record<number, { status: string; notes: string }> = {};
    templateItems.forEach((item) => { initial[item.id] = { status: "ok", notes: "" }; });
    setItemStatus(initial);
    setTireMeasurements({});
    setEditing("new");
  }

  function startEdit(checklist: VehicleChecklist) {
    setForm({ vehicle_id:String(checklist.vehicle_id), driver_id:checklist.driver_id ? String(checklist.driver_id) : "", kind:checklist.kind, performed_at:checklist.performed_at, notes:checklist.notes || "" });
    const answers: Record<number,{status:string;notes:string}> = {};
    templateItems.forEach(item => {
      const saved = checklist.items.find(answer => answer.template_item_id === item.id);
      answers[item.id] = { status:saved?.status || "ok", notes:saved?.notes || "" };
    });
    setItemStatus(answers); setTireMeasurements(Object.fromEntries((checklist.tire_measurements||[]).map(item=>[item.tire_id,String(item.tread_depth_mm)]))); setEditing(checklist);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    onError("");
    try {
      const payload = {
        branch_id: user?.branch_id ?? 1,
        vehicle_id: Number(form.vehicle_id),
        driver_id: form.driver_id ? Number(form.driver_id) : null,
        kind: form.kind,
        performed_at: form.performed_at,
        notes: form.notes || null,
        items: templateItems.map((item) => ({
          template_item_id: item.id,
          status: itemStatus[item.id]?.status ?? "ok",
          notes: itemStatus[item.id]?.notes || null,
        })),
        tire_measurements: checklistTires.map(tire=>({tire_id:tire.id,tread_depth_mm:Number(tireMeasurements[tire.id])})),
      };
      if (editing === "new") await api.post("/vehicle-checklist", payload);
      else if (editing) await api.put(`/vehicle-checklist/${editing.id}`, payload);
      setEditing(null);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_save"));
    }
  }

  async function remove(checklist: VehicleChecklist) {
    if (!await appConfirm(t("fleet.delete_confirm") ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
    try {
      await api.delete(`/vehicle-checklist/${checklist.id}`);
      reload();
    } catch (err: any) {
      onError(err?.response?.data?.detail ?? t("fleet.err_delete"));
    }
  }

  const itemsByCategory: Record<string, ChecklistTemplateItem[]> = {};
  templateItems.forEach((item) => {
    (itemsByCategory[item.category] ??= []).push(item);
  });

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <button className="btn-primary btn-add" onClick={startNew}><span className="btn-add-symbol">+</span><span>{t("fleet.checklist_new")}</span></button>
      </div>

      {editing && (
        <div className="modal-backdrop" onClick={()=>setEditing(null)}><form className="modal-card checklist-modal" onSubmit={save} onClick={event=>event.stopPropagation()}>
          <div className="checklist-modal-head"><div><h3>{editing === "new" ? t("fleet.checklist_new") : "Editar checklist"}</h3><p>Marque a condição de cada item antes de salvar a inspeção.</p></div><button className="checklist-close" type="button" onClick={()=>setEditing(null)} aria-label="Fechar">×</button></div>
          <div className="form-grid">
            <label className="field">
              <span>{t("fleet.vehicle")}</span>
              <select className="input" required value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}>
                <option value="">{t("fleet.select_vehicle")}</option>
                {vehicles.filter((v) => v.active).map((v) => <option key={v.id} value={v.id}>{v.plate}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.checklist_driver")}</span>
              <select className="input" value={form.driver_id} onChange={(e) => setForm({ ...form, driver_id: e.target.value })}>
                <option value="">-</option>
                {drivers.filter((d) => d.active).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.checklist_kind")}</span>
              <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {CHECKLIST_KINDS.map((k) => <option key={k} value={k}>{t(`fleet.checklist_kinds.${k}`)}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("fleet.checklist_performed_at")}</span>
              <input className="input" type="date" required value={form.performed_at} onChange={(e) => setForm({ ...form, performed_at: e.target.value })} />
            </label>
          </div>

          <div className="checklist-sections">{Object.entries(itemsByCategory).map(([category, items]) => (
            <section className="checklist-section" key={category}>
              <h4>{t(`fleet.checklist_item_categories.${category}`)}</h4>
              <div className="checklist-items">{items.map(item => {
                const answer = itemStatus[item.id] || {status:"ok",notes:""};
                return <article className={`checklist-item-card checklist-item-${answer.status}`} key={item.id}>
                  <div className="checklist-item-row"><span className="checklist-item-label">{item.label_pt_br||item.label}{item.required&&<b title="Obrigatório"> *</b>}</span>
                    <div className="checklist-choice" role="group" aria-label={`Condição de ${item.label_pt_br||item.label}`}>
                      {ITEM_STATUSES.map(status=><button key={status} type="button" title={t(`fleet.checklist_item_status.${status}`)} className={`checklist-choice-btn ${answer.status===status?"active":""} ${status}`} onClick={()=>setItemStatus({...itemStatus,[item.id]:{...answer,status}})}>{status==="ok"?"✓":status==="nao_ok"?"×":"—"}</button>)}
                    </div>
                  </div>
                  <input className="input checklist-item-note" placeholder={answer.status==="nao_ok"?"Descreva o problema encontrado":"Observação (opcional)"} value={answer.notes} onChange={event=>setItemStatus({...itemStatus,[item.id]:{...answer,notes:event.target.value}})}/>
                </article>;
              })}</div>
              {category==="pneus"&&form.vehicle_id&&<div className="checklist-tread-section"><div className="checklist-tread-heading"><div><strong>Profundidade do sulco</strong><small>Informe a medida de cada pneu instalado, em milímetros.</small></div><span>≤ 3 mm: atenção</span></div>{checklistTires.length?<div className="checklist-tread-grid">{checklistTires.map(tire=>{const value=tireMeasurements[tire.id]??"";const critical=value!==""&&Number(value)<=3;return <label className={`checklist-tread-card ${critical?"critical":""}`} key={tire.id}><span className="tire-map-rubber"></span><span><strong>{tire.fire_number}</strong><small>{tire.position?.replaceAll("_"," ")||"Posição não definida"}</small></span><span className="checklist-tread-input"><input className="input" type="number" required min="0" max="30" step="0.1" placeholder="0,0" value={value} onChange={event=>setTireMeasurements({...tireMeasurements,[tire.id]:event.target.value})}/><b>mm</b></span></label>})}</div>:<p className="checklist-tread-empty">Nenhum pneu está instalado neste veículo. Cadastre ou movimente os pneus pelo mapa.</p>}</div>}
            </section>
          ))}</div>

          <label className="field" style={{ marginTop: 10 }}>
            <span>{t("fleet.checklist_notes")}</span>
            <textarea className="input" style={{ minHeight: 60, resize: "vertical" }} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </label>
          <div className="modal-actions">
            <button className="btn-primary" type="submit">{t("common.save")}</button>
            <button className="btn-ghost" type="button" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form></div>
      )}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("fleet.checklist_performed_at")}</th>
              <th>{t("fleet.vehicle")}</th>
              <th>{t("fleet.checklist_driver")}</th>
              <th>{t("fleet.checklist_kind")}</th>
              <th>{t("fleet.checklist_overall_status")}</th>
              <th>{t("users.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {checklists.map((c) => (
              <Fragment key={c.id}>
                <tr>
                  <td>{c.performed_at}</td>
                  <td>{c.vehicle_plate ?? "-"}</td>
                  <td>{c.driver_name ?? "-"}</td>
                  <td>{t(`fleet.checklist_kinds.${c.kind}`)}</td>
                  <td>
                    <span style={c.overall_status === "reprovado" ? dueBadge : okBadge}>
                      {t(`fleet.checklist_overall_statuses.${c.overall_status}`)}
                    </span>
                  </td>
                  <td>
                    <button className="btn-mini" onClick={() => setExpanded(expanded === c.id ? null : c.id)}>{t("fleet.checklist_view")}</button>
                    <button className="btn-mini" onClick={()=>startEdit(c)}>{t("users.edit")}</button>
                    <button className="btn-mini danger" onClick={() => remove(c)}>{t("common.delete")}</button>
                  </td>
                </tr>
                {expanded === c.id && (
                  <tr>
                    <td colSpan={6}>
                      <table className="data-table">
                        <thead><tr><th>{t("fleet.description")}</th><th>{t("fleet.checklist_overall_status")}</th><th>{t("fleet.checklist_item_notes")}</th></tr></thead>
                        <tbody>
                          {c.items.map((i) => (
                            <tr key={i.id}>
                              <td>{i.item_label ?? i.template_item_id}</td>
                              <td>{t(`fleet.checklist_item_status.${i.status}`)}</td>
                              <td>{i.notes ?? "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {checklists.length === 0 && <tr><td colSpan={6} className="empty-state">{t("fleet.empty_checklists")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const tabsWrap: React.CSSProperties = { display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", background: "var(--panel)", padding: 6, borderRadius: 10, border: "1px solid var(--line)" };
const tabBtn: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "1px solid transparent", background: "transparent", cursor: "pointer", color: "var(--muted)", fontWeight: 600 };
const tabActive: React.CSSProperties = { background: "#0f172a", color: "#fff", border: "1px solid #0f172a" };
const dueBadge: React.CSSProperties = { background: "#fef3c7", color: "#92400e", padding: "2px 8px", borderRadius: 999, fontSize: 12, fontWeight: 600 };
const okBadge: React.CSSProperties = { background: "#dcfce7", color: "#166534", padding: "2px 8px", borderRadius: 999, fontSize: 12, fontWeight: 600 };

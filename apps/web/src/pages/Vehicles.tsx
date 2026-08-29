import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "../services/api";
import { useAuth } from "../context/AuthContext";
import {appPrompt} from "../components/AppDialog";

type Owner = {
  id: number;
  name: string;
  document: string;
  phone?: string;
  email?: string;
  address?: string;
  person_type: "pessoa_fisica" | "pessoa_juridica";
  bank_name?: string; bank_agency?: string; bank_account?: string; bank_account_type?: string;
  pix_key_type?: string; pix_key?: string;
  active: boolean;
  blocked: boolean;
  status_reason?: string;
  is_tenant_company?: boolean;
};
type Kind = { id: number; label: string; label_pt_br?: string };
type Carrier = { id:number; name:string; document?:string; kind:string; antt_number?:string; active:boolean; vehicles:{id:number;plate:string}[] };
type Vehicle = {
  id: number;
  branch_id: number;
  plate: string;
  description?: string;
  owner_id?: number;
  owner_name?: string;
  renavam?: string;
  chassis?: string;
  registry_state?: string;
  brand?: string;
  model?: string;
  manufacture_year?: number;
  model_year?: number;
  color?: string;
  fuel?: string;
  crlv_expiry_date?: string;
  vehicle_type_id?: number;
  vehicle_type_label?: string;
  axles?: number;
  length_m?: number;
  width_m?: number;
  height_m?: number;
  gross_weight_kg?: number;
  temperature_controlled: boolean;
  crlv_url?: string;
  age?: number;
  active: boolean;
  blocked: boolean;
  status_reason?: string;
  ownership_type: "proprio" | "agregado";
  freight_receiver_type: "proprietario" | "terceiro";
  carrier_id?: number;
  carrier_name?: string;
  antt_number?: string;
  antt_expiry_date?: string;
};
type Request = {
  id: number;
  vehicle_id: number;
  plate: string;
  requested_by_name: string;
  reason: string;
  status: string;
  requested_renavam?: string;
  requested_vehicle_type_id?: number;
  requested_axles?: number;
  previous_renavam?: string;
  previous_vehicle_type_id?: number;
  previous_axles?: number;
  reviewed_by_name?: string;
  reviewed_at?: string;
  decision_note?: string;
  created_at: string;
};
const blank: any = {
  plate: "",
  description: "",
  owner_id: "",
  renavam: "",
  chassis: "",
  registry_state: "",
  brand: "",
  model: "",
  manufacture_year: "",
  model_year: "",
  color: "",
  fuel: "",
  crlv_expiry_date: "",
  vehicle_type_id: "",
  axles: "",
  length_m: "",
  width_m: "",
  height_m: "",
  gross_weight_kg: "",
  temperature_controlled: false,
  ownership_type: "proprio",
  freight_receiver_type: "proprietario",
  carrier_id: "",
  antt_number: "",
  antt_expiry_date: "",
  change_reason: "",
};
const ownerBlank = {
  person_type: "pessoa_fisica",
  name: "",
  document: "",
  phone: "",
  email: "",
  address: "",
  bank_name: "",
  bank_agency: "",
  bank_account: "",
  bank_account_type: "corrente",
  pix_key_type: "cpf_cnpj",
  pix_key: "",
};
const statusLabel: Record<string, string> = {
  pending: "Pendente",
  approved: "Aprovada",
  rejected: "Recusada",
};

export default function Vehicles() {
  const { user, hasRole } = useAuth(),
    manager = hasRole("admin_global", "gestor_brasil"),
    [rows, setRows] = useState<Vehicle[]>([]),
    [owners, setOwners] = useState<Owner[]>([]),
    [carriers, setCarriers] = useState<Carrier[]>([]),
    [ownerResults, setOwnerResults] = useState<Owner[]>([]),
    [kinds, setKinds] = useState<Kind[]>([]),
    [requests, setRequests] = useState<Request[]>([]),
    [tab, setTab] = useState("vehicles"),
    [editing, setEditing] = useState<Vehicle | "new" | null>(null),
    [ownerOpen, setOwnerOpen] = useState(false),
    [inlineOwnerOpen, setInlineOwnerOpen] = useState(false),
    [ownerSearch, setOwnerSearch] = useState(""),
    [form, setForm] = useState<any>(blank),
    [ownerForm, setOwnerForm] = useState(ownerBlank),
    [crlv, setCrlv] = useState<File | null>(null),
    [query, setQuery] = useState(""),
    [error, setError] = useState("");
  const load = () =>
    Promise.all([
      api.get<Vehicle[]>("/vehicles"),
      api.get<Owner[]>("/vehicles/owners"),
      api.get<Kind[]>("/vehicle-types?only_active=true"),
      api.get<Request[]>("/vehicles/change-requests"),
      api.get<Carrier[]>("/carriers?only_active=true"),
    ]).then(([v, o, k, r, c]) => {
      setRows(v.data);
      setOwners(o.data);
      setKinds(k.data);
      setRequests(r.data);
      setCarriers(c.data);
    });
  useEffect(() => {
    load().catch(() => {});
  }, []);
  const filtered = useMemo(
    () =>
      rows.filter((v) =>
        `${v.plate} ${v.renavam || ""} ${v.owner_name || ""} ${v.brand || ""} ${v.model || ""}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [rows, query],
  );
  const suggestedOwners = useMemo(() => {
    const term = ownerSearch.trim().toLowerCase();
    if (term.length < 3) return [];
    return ownerResults.filter((owner) => `${owner.name} ${owner.document}`.toLowerCase().includes(term)).slice(0, 6);
  }, [ownerResults, ownerSearch]);
  useEffect(() => {
    const term = ownerSearch.trim();
    if (term.length < 3 || form.owner_id) { setOwnerResults([]); return; }
    const timer = window.setTimeout(() => {
      api.get<Owner[]>("/vehicles/owners", { params: { q: term } }).then((response) => setOwnerResults(response.data)).catch(() => setOwnerResults([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [ownerSearch, form.owner_id]);
  function edit(row?: Vehicle) {
    setError("");
    setCrlv(null);
    if (!row) {
      setForm({ ...blank });
      setOwnerSearch("");
      setInlineOwnerOpen(false);
      setEditing("new");
      return;
    }
    setForm({
      ...blank,
      ...Object.fromEntries(
        Object.keys(blank).map((key) => [
          key,
          (row as any)[key] ?? (key === "temperature_controlled" ? false : ""),
        ]),
      ),
    });
    setOwnerSearch(row.owner_name ? `${row.owner_name}` : "");
    setInlineOwnerOpen(false);
    setEditing(row);
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      if (form.ownership_type === "agregado" && !form.owner_id) throw new Error("Selecione ou cadastre o proprietário do veículo agregado.");
      if (form.ownership_type === "agregado" && !String(form.antt_number || "").trim()) throw new Error("Informe a ANTT vinculada ao veículo agregado.");
      if (form.ownership_type === "agregado" && form.freight_receiver_type === "terceiro" && !form.carrier_id) throw new Error("Selecione o arrendatário/beneficiário que receberá o frete.");
      if (editing === "new") {
        if (!crlv) throw new Error("O arquivo do CRLV é obrigatório.");
        const data = new FormData();
        Object.entries({ ...form, branch_id: user?.branch_id || 1 }).forEach(
          ([k, v]) => {
            if (v !== "" && k !== "change_reason") data.set(k, String(v));
          },
        );
        data.set("crlv", crlv);
        await api.post("/vehicles/with-crlv", data);
      } else {
        const payload = Object.fromEntries(
          Object.entries(form).map(([k, v]) => [k, v === "" ? null : v]),
        );
        await api.put(`/vehicles/${(editing as Vehicle).id}`, payload);
        if (crlv) {
          const data = new FormData();
          data.set("crlv", crlv);
          if (form.change_reason) data.set("reason", form.change_reason);
          await api.post(`/vehicles/${(editing as Vehicle).id}/crlv`, data);
        }
      }
      setEditing(null);
      await load();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          err.message ||
          "Não foi possível salvar o veículo.",
      );
    }
  }
  async function createInlineOwner() {
    setError("");
    try {
      const response = await api.post<Owner>("/vehicles/owners", ownerForm);
      setOwners((current) => [...current, response.data].sort((a, b) => a.name.localeCompare(b.name)));
      setForm({ ...form, owner_id: response.data.id });
      setOwnerSearch(response.data.name);
      setOwnerForm(ownerBlank);
      setInlineOwnerOpen(false);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Não foi possível cadastrar o proprietário.");
    }
  }
  async function changeStatus(kind:"vehicle"|"owner",item:Vehicle|Owner,action:"activate"|"deactivate"|"block"|"unblock") {
    let reason="";
    if (["deactivate","block"].includes(action)) {
      const value=await appPrompt(`Informe o motivo para ${action==="block"?"bloquear":"desativar"} ${kind==="vehicle"?"este veículo":"este proprietário"}.`,{title:action==="block"?"Confirmar bloqueio":"Confirmar desativação",label:"Motivo obrigatório",required:true,confirmLabel:action==="block"?"Bloquear":"Desativar"});
      if(value===null)return;reason=value;
    }
    try { await api.post(kind==="vehicle"?`/vehicles/${item.id}/status`:`/vehicles/owners/${item.id}/status`,{action,reason:reason||null});await load(); }
    catch(err:any){setError(err?.response?.data?.detail||"Não foi possível alterar a situação.");}
  }
  async function saveOwner(e: FormEvent) {
    e.preventDefault();
    try {
      await api.post("/vehicles/owners", ownerForm);
      setOwnerForm(ownerBlank);
      setOwnerOpen(false);
      await load();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          "Não foi possível cadastrar o proprietário.",
      );
    }
  }
  async function decide(id: number, decision: string) {
    const answer = await appPrompt(
      decision === "approved" ? "Registre uma observação para a aprovação, se necessário." : "Informe o motivo da recusa.",
      {title:decision === "approved"?"Aprovar alteração":"Recusar alteração",label:decision === "approved"?"Observação (opcional)":"Motivo da recusa",required:decision !== "approved",confirmLabel:decision === "approved"?"Aprovar":"Recusar"},
    );
    if(answer===null)return;
    const note=answer;
    await api.post(`/vehicles/change-requests/${id}/decision`, {
      decision,
      note,
    });
    load();
  }
  return (
    <div>
      <div className="page-header">
        <div>
          <h2>Veículos</h2>
          <p className="page-subtitle">
            Cadastro técnico, CRLV, proprietários e alterações controladas.
          </p>
        </div>
        <div className="driver-header-actions">
          <button className="btn-ghost" onClick={() => { setOwnerForm(ownerBlank); setError(""); setOwnerOpen(true); }}>
            Novo proprietário
          </button>
          <button className="btn-primary btn-add" onClick={() => edit()}>
            <span className="btn-add-symbol">+</span>Novo veículo
          </button>
        </div>
      </div>
      {error && <p className="modal-error">{error}</p>}
      <div className="vehicle-tabs">
        <button
          className={tab === "vehicles" ? "active" : ""}
          onClick={() => setTab("vehicles")}
        >
          Frota <span>{rows.length}</span>
        </button>
        <button
          className={tab === "owners" ? "active" : ""}
          onClick={() => setTab("owners")}
        >
          Proprietários <span>{owners.length}</span>
        </button>
        <button
          className={tab === "approvals" ? "active" : ""}
          onClick={() => setTab("approvals")}
        >
          Aprovações{" "}
          <span>{requests.filter((r) => r.status === "pending").length}</span>
        </button>
      </div>
      {tab === "vehicles" && (
        <>
          <section className="card-panel vehicle-search">
            <input
              className="input"
              placeholder="Buscar por placa, RENAVAM, proprietário, marca ou modelo"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </section>
          <div className="vehicle-grid">
            {filtered.map((v) => (
              <article className="vehicle-card" key={v.id}>
                <header>
                  <div>
                    <strong>{v.plate}</strong>
                    <span>
                      {v.brand || "Marca"} {v.model || "/ modelo não informado"}
                    </span>
                  </div>
                  <span className={`stock-badge ${v.active ? "ok" : v.blocked ? "expired" : ""}`} title={v.status_reason||""}>
                    {v.blocked ? "Bloqueado" : v.active ? "Ativo" : "Inativo"}
                  </span>
                </header>
                <div className="vehicle-specs">
                  <span>
                    <small>Proprietário</small>
                    {v.owner_name || "—"}
                  </span>
                  <span>
                    <small>Vínculo</small>
                    {v.ownership_type === "agregado" ? "Agregado" : "Frota própria"}
                  </span>
                  <span>
                    <small>Recebedor do frete</small>
                    {v.freight_receiver_type === "terceiro" ? (v.carrier_name || "Terceiro") : (v.owner_name || "Proprietário")}
                  </span>
                  <span>
                    <small>ANTT do vínculo</small>
                    {v.antt_number || "—"}
                  </span>
                  <span>
                    <small>RENAVAM</small>
                    {v.renavam || "—"}
                  </span>
                  <span>
                    <small>Tipologia</small>
                    {v.vehicle_type_label || "—"}
                  </span>
                  <span>
                    <small>Idade</small>
                    {v.age != null ? `${v.age} anos` : "—"}
                  </span>
                  <span>
                    <small>Eixos</small>
                    {v.axles || "—"}
                  </span>
                  <span>
                    <small>Dimensões</small>
                    {v.length_m || "—"} × {v.width_m || "—"} ×{" "}
                    {v.height_m || "—"} m
                  </span>
                </div>
                <footer>
                  {v.crlv_url ? (
                    <a
                      className="btn-mini"
                      href={v.crlv_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Abrir CRLV
                    </a>
                  ) : (
                    <span className="driver-status expired">CRLV pendente</span>
                  )}
                  <button className="btn-mini" onClick={() => edit(v)}>
                    Editar
                  </button>
                  {v.active&&<><button className="btn-mini" onClick={()=>void changeStatus("vehicle",v,"deactivate")}>Desativar</button><button className="btn-mini danger" onClick={()=>void changeStatus("vehicle",v,"block")}>Bloquear</button></>}
                  {!v.active&&<button className="btn-mini" onClick={()=>void changeStatus("vehicle",v,v.blocked?"unblock":"activate")}>{v.blocked?"Desbloquear":"Ativar"}</button>}
                </footer>
              </article>
            ))}
          </div>
        </>
      )}
      {tab === "owners" && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Proprietário</th>
                <th>CPF/CNPJ</th>
                <th>Telefone</th>
                <th>E-mail</th>
                <th>Endereço</th>
                <th>Situação</th><th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {owners.map((o) => (
                <tr key={o.id}>
                  <td>{o.name}</td>
                  <td>{o.document}</td>
                  <td>{o.phone || "—"}</td>
                  <td>{o.email || "—"}</td>
                  <td>{o.address || "—"}</td>
                  <td><span className={`stock-badge ${o.active?"ok":o.blocked?"expired":""}`} title={o.status_reason||""}>{o.blocked?"Bloqueado":o.active?"Ativo":"Inativo"}</span></td>
                  <td>{!o.is_tenant_company&&<>{o.active?<><button className="btn-mini" onClick={()=>void changeStatus("owner",o,"deactivate")}>Desativar</button><button className="btn-mini danger" onClick={()=>void changeStatus("owner",o,"block")}>Bloquear</button></>:<button className="btn-mini" onClick={()=>void changeStatus("owner",o,o.blocked?"unblock":"activate")}>{o.blocked?"Desbloquear":"Ativar"}</button>}</>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab === "approvals" && (
        <div className="approval-grid">
          {requests.map((r) => (
            <article className="approval-card" key={r.id}>
              <header>
                <strong>{r.plate}</strong>
                <span
                  className={`driver-status ${r.status === "approved" ? "ok" : r.status === "rejected" ? "expired" : "warning"}`}
                >
                  {statusLabel[r.status]}
                </span>
              </header>
              <p>
                <b>{r.requested_by_name}</b> solicitou em{" "}
                {new Date(r.created_at).toLocaleString("pt-BR")}
              </p>
              <p>{r.reason}</p>
              <div className="change-comparison">
                <span>
                  RENAVAM: {r.previous_renavam || "—"} →{" "}
                  {r.requested_renavam || "—"}
                </span>
                <span>
                  Tipologia: {r.previous_vehicle_type_id || "—"} →{" "}
                  {r.requested_vehicle_type_id || "—"}
                </span>
                <span>
                  Eixos: {r.previous_axles || "—"} → {r.requested_axles || "—"}
                </span>
              </div>
              {r.reviewed_by_name && (
                <small>
                  Decidida por {r.reviewed_by_name} ·{" "}
                  {r.decision_note || "Sem observação"}
                </small>
              )}
              {manager && r.status === "pending" && (
                <footer>
                  <button
                    className="btn-primary"
                    onClick={() => decide(r.id, "approved")}
                  >
                    Aprovar
                  </button>
                  <button
                    className="btn-mini danger"
                    onClick={() => decide(r.id, "rejected")}
                  >
                    Recusar
                  </button>
                </footer>
              )}
            </article>
          ))}
        </div>
      )}
      {editing && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
          <form
            className="modal-card driver-modal"
            onSubmit={save}
            onClick={(e) => e.stopPropagation()}
          >
            <h3>{editing === "new" ? "Novo veículo" : "Editar veículo"}</h3>
            <h4>CRLV e identificação</h4>
            <div className="form-grid">
              <F label="Placa">
                <input
                  className="input"
                  required
                  value={form.plate}
                  onChange={(e) =>
                    setForm({ ...form, plate: e.target.value.toUpperCase() })
                  }
                />
              </F>
              <F label="RENAVAM">
                <input
                  className="input"
                  required
                  value={form.renavam}
                  onChange={(e) =>
                    setForm({ ...form, renavam: e.target.value })
                  }
                />
              </F>
              <F label="Chassi">
                <input
                  className="input"
                  required
                  value={form.chassis}
                  onChange={(e) =>
                    setForm({ ...form, chassis: e.target.value.toUpperCase() })
                  }
                />
              </F>
              <F label="UF de registro">
                <input
                  className="input"
                  maxLength={2}
                  value={form.registry_state}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      registry_state: e.target.value.toUpperCase(),
                    })
                  }
                />
              </F>
              <F label="Validade/licenciamento">
                <input
                  className="input"
                  type="date"
                  value={form.crlv_expiry_date}
                  onChange={(e) =>
                    setForm({ ...form, crlv_expiry_date: e.target.value })
                  }
                />
              </F>
              <F label={`CRLV em PDF ou foto${editing === "new" ? " *" : ""}`}>
                <input
                  className="input"
                  required={editing === "new"}
                  type="file"
                  accept="application/pdf,image/*"
                  onChange={(e) => setCrlv(e.target.files?.[0] || null)}
                />
              </F>
            </div>
            <h4>Propriedade e características</h4>
            <div className="form-grid">
              <F label="Vínculo do veículo">
                <select className="input" value={form.ownership_type} onChange={(e) => setForm({ ...form, ownership_type: e.target.value, ...(e.target.value === "proprio" ? { antt_number: "", antt_expiry_date: "", freight_receiver_type:"proprietario", carrier_id:"" } : {}) })}>
                  <option value="proprio">Frota própria</option>
                  <option value="agregado">Veículo agregado</option>
                </select>
              </F>
              {form.ownership_type === "agregado" ? <div className="vehicle-owner-picker">
                <label className="field"><span>Proprietário {form.ownership_type === "agregado" ? "*" : "(opcional)"}</span>
                  <input className="input" required={form.ownership_type === "agregado"} value={ownerSearch} placeholder="Digite nome ou CPF/CNPJ" autoComplete="off" onChange={(e) => { setOwnerSearch(e.target.value); setForm({ ...form, owner_id: "" }); setInlineOwnerOpen(false); }} />
                </label>
                {ownerSearch.trim().length > 0 && ownerSearch.trim().length < 3 && <small className="owner-search-hint">Digite pelo menos 3 caracteres para pesquisar.</small>}
                <button type="button" className="owner-create-trigger" onClick={() => {
                  setOwnerForm({ ...ownerBlank, name: ownerSearch });
                  setInlineOwnerOpen(true);
                  window.setTimeout(() => document.getElementById("inline-owner-form")?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
                }}>+ Cadastrar novo proprietário</button>
                {ownerSearch.trim().length >= 3 && !form.owner_id && <div className="owner-suggestions">
                  {suggestedOwners.map((owner) => <button type="button" key={owner.id} onClick={() => { setForm({ ...form, owner_id: owner.id }); setOwnerSearch(owner.name); setInlineOwnerOpen(false); }}><strong>{owner.name}</strong><span>{owner.person_type === "pessoa_juridica" ? "CNPJ" : "CPF"} · {owner.document}</span></button>)}
                  {!suggestedOwners.length && <div className="owner-not-found"><span>Nenhum proprietário encontrado.</span><button type="button" className="btn-mini" onClick={() => { setOwnerForm({ ...ownerBlank, name: ownerSearch }); setInlineOwnerOpen(true); }}>+ Cadastrar agora</button></div>}
                </div>}
              </div> : <div className="company-owner-auto"><strong>Empresa contratante</strong><span>O proprietário e a ANTT serão preenchidos automaticamente usando os Dados da empresa em Configuração.</span></div>}
              {form.ownership_type === "agregado" && <div className="freight-receiver-picker"><span>Quem recebe o frete? *</span><div className="owner-person-toggle"><button type="button" className={form.freight_receiver_type==="proprietario"?"active":""} onClick={()=>setForm({...form,freight_receiver_type:"proprietario",carrier_id:""})}><strong>PRO</strong><span>Proprietário</span></button><button type="button" className={form.freight_receiver_type==="terceiro"?"active":""} onClick={()=>setForm({...form,freight_receiver_type:"terceiro"})}><strong>3º</strong><span>Terceiro</span></button></div>{form.freight_receiver_type==="terceiro"&&<select className="input" required value={form.carrier_id} onChange={e=>setForm({...form,carrier_id:Number(e.target.value)})}><option value="">Selecione o arrendatário/beneficiário</option>{carriers.filter(c=>c.antt_number).map(c=><option key={c.id} value={c.id}>{c.name} · {c.kind==="beneficiario"?"Beneficiário":"Arrendatário"} · ANTT {c.antt_number}</option>)}</select>}{editing!=="new"&&(editing as Vehicle).carrier_id&&<small className="receiver-lock-note">Para trocar o terceiro atual, selecione Proprietário e salve primeiro. Depois reabra o veículo e vincule o novo responsável.</small>}</div>}
              <F label="Tipologia">
                <select
                  className="input"
                  required
                  value={form.vehicle_type_id}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      vehicle_type_id: Number(e.target.value),
                    })
                  }
                >
                  <option value="">Selecione</option>
                  {kinds.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.label_pt_br || k.label}
                    </option>
                  ))}
                </select>
              </F>
              {form.ownership_type === "agregado" && <>
                <F label="ANTT vinculada ao veículo *"><input className="input" required value={form.antt_number} placeholder="Número do RNTRC/ANTT" onChange={(e) => setForm({ ...form, antt_number: e.target.value.toUpperCase() })} /></F>
                <F label="Validade da ANTT"><input className="input" type="date" value={form.antt_expiry_date} onChange={(e) => setForm({ ...form, antt_expiry_date: e.target.value })} /></F>
                <div className="vehicle-antt-notice">A ANTT informada ficará vinculada a este veículo agregado e será mantida no histórico de auditoria.</div>
              </>}
              <F label="Eixos">
                <input
                  className="input"
                  type="number"
                  min="1"
                  required
                  value={form.axles}
                  onChange={(e) =>
                    setForm({ ...form, axles: Number(e.target.value) })
                  }
                />
              </F>
              <F label="Marca">
                <input
                  className="input"
                  value={form.brand}
                  onChange={(e) => setForm({ ...form, brand: e.target.value })}
                />
              </F>
              <F label="Modelo">
                <input
                  className="input"
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                />
              </F>
              <F label="Ano fabricação">
                <input
                  className="input"
                  type="number"
                  value={form.manufacture_year}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      manufacture_year: Number(e.target.value),
                    })
                  }
                />
              </F>
              <F label="Ano modelo">
                <input
                  className="input"
                  type="number"
                  value={form.model_year}
                  onChange={(e) =>
                    setForm({ ...form, model_year: Number(e.target.value) })
                  }
                />
              </F>
              <F label="Cor">
                <input
                  className="input"
                  value={form.color}
                  onChange={(e) => setForm({ ...form, color: e.target.value })}
                />
              </F>
              <F label="Combustível">
                <input
                  className="input"
                  value={form.fuel}
                  onChange={(e) => setForm({ ...form, fuel: e.target.value })}
                />
              </F>
              <F label="Descrição">
                <input
                  className="input"
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
              </F>
            </div>
            {inlineOwnerOpen && <section className="inline-owner-form" id="inline-owner-form">
              <header><div><strong>Novo proprietário</strong><span>Complete os dados sem sair do cadastro do veículo.</span></div><button type="button" onClick={() => setInlineOwnerOpen(false)}>×</button></header>
              <div className="form-grid">
                <F label="Tipo de pessoa *"><select className="input" value={ownerForm.person_type} onChange={(e) => setOwnerForm({ ...ownerForm, person_type: e.target.value })}><option value="pessoa_fisica">Pessoa física</option><option value="pessoa_juridica">Pessoa jurídica</option></select></F>
                <F label="Nome / Razão social *"><input className="input" required value={ownerForm.name} onChange={(e) => setOwnerForm({ ...ownerForm, name: e.target.value })} /></F>
                <F label={`${ownerForm.person_type === "pessoa_juridica" ? "CNPJ" : "CPF"} *`}><input className="input" required inputMode="numeric" value={ownerForm.document} onChange={(e) => setOwnerForm({ ...ownerForm, document: e.target.value })} /></F>
                <F label="Telefone"><input className="input" value={ownerForm.phone} onChange={(e) => setOwnerForm({ ...ownerForm, phone: e.target.value })} /></F>
                <F label="E-mail"><input className="input" type="email" value={ownerForm.email} onChange={(e) => setOwnerForm({ ...ownerForm, email: e.target.value })} /></F>
                <F label="Endereço"><input className="input" value={ownerForm.address} onChange={(e) => setOwnerForm({ ...ownerForm, address: e.target.value })} /></F>
                <F label="Banco"><input className="input" value={ownerForm.bank_name} onChange={(e) => setOwnerForm({ ...ownerForm, bank_name: e.target.value })} /></F>
                <F label="Agência"><input className="input" value={ownerForm.bank_agency} onChange={(e) => setOwnerForm({ ...ownerForm, bank_agency: e.target.value })} /></F>
                <F label="Conta"><input className="input" value={ownerForm.bank_account} onChange={(e) => setOwnerForm({ ...ownerForm, bank_account: e.target.value })} /></F>
                <F label="Tipo da conta"><select className="input" value={ownerForm.bank_account_type} onChange={(e) => setOwnerForm({ ...ownerForm, bank_account_type: e.target.value })}><option value="corrente">Conta corrente</option><option value="poupanca">Poupança</option><option value="pagamento">Conta pagamento</option></select></F>
                <F label="Tipo da chave Pix"><select className="input" value={ownerForm.pix_key_type} onChange={(e) => setOwnerForm({ ...ownerForm, pix_key_type: e.target.value })}><option value="cpf_cnpj">CPF/CNPJ</option><option value="email">E-mail</option><option value="telefone">Telefone</option><option value="aleatoria">Chave aleatória</option></select></F>
                <F label="Chave Pix"><input className="input" value={ownerForm.pix_key} onChange={(e) => setOwnerForm({ ...ownerForm, pix_key: e.target.value })} /></F>
              </div>
              <button type="button" className="btn-primary" onClick={() => void createInlineOwner()}>Cadastrar e vincular</button>
            </section>}
            <h4>Dimensões e capacidade</h4>
            <div className="form-grid">
              {[
                ["length_m", "Comprimento (m)"],
                ["width_m", "Largura (m)"],
                ["height_m", "Altura (m)"],
                ["gross_weight_kg", "Peso bruto (kg)"],
              ].map(([key, label]) => (
                <F label={label} key={key}>
                  <input
                    className="input"
                    type="number"
                    step="0.01"
                    value={form[key]}
                    onChange={(e) =>
                      setForm({ ...form, [key]: Number(e.target.value) })
                    }
                  />
                </F>
              ))}
            </div>
            {editing !== "new" && !manager && (
              <F label="Motivo para alterar RENAVAM, tipologia ou eixos">
                <textarea
                  className="input"
                  rows={3}
                  placeholder="Obrigatório apenas se um desses dados protegidos for alterado"
                  value={form.change_reason}
                  onChange={(e) =>
                    setForm({ ...form, change_reason: e.target.value })
                  }
                />
              </F>
            )}
            {error && <p className="modal-error">{error}</p>}
            <div className="modal-actions">
              <button className="btn-primary">
                {editing !== "new" && !manager
                  ? "Salvar / solicitar aprovação"
                  : "Salvar veículo"}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setEditing(null)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}
      {ownerOpen && (
        <div className="modal-backdrop" onClick={() => setOwnerOpen(false)}>
          <form
            className="modal-card owner-modal"
            onSubmit={saveOwner}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="owner-modal-heading"><div><span>CADASTRO DE PROPRIETÁRIO</span><h3>Novo proprietário</h3><p>Informe os dados cadastrais e financeiros para vinculação à frota.</p></div><button type="button" aria-label="Fechar" onClick={()=>setOwnerOpen(false)}>×</button></div>
            <section className="owner-form-section"><h4>Tipo de cadastro</h4><div className="owner-person-toggle">
              <button type="button" className={ownerForm.person_type==="pessoa_fisica"?"active":""} onClick={()=>setOwnerForm({...ownerForm,person_type:"pessoa_fisica",document:""})}><strong>CPF</strong><span>Pessoa física</span></button>
              <button type="button" className={ownerForm.person_type==="pessoa_juridica"?"active":""} onClick={()=>setOwnerForm({...ownerForm,person_type:"pessoa_juridica",document:""})}><strong>CNPJ</strong><span>Pessoa jurídica</span></button>
            </div></section>
            <section className="owner-form-section"><h4>Identificação e contato</h4><div className="form-grid">
              <F label={ownerForm.person_type==="pessoa_juridica"?"Razão social *":"Nome completo *"}><input className="input" required value={ownerForm.name} onChange={e=>setOwnerForm({...ownerForm,name:e.target.value})}/></F>
              <F label={`${ownerForm.person_type==="pessoa_juridica"?"CNPJ":"CPF"} *`}><input className="input" required inputMode="numeric" placeholder={ownerForm.person_type==="pessoa_juridica"?"00.000.000/0000-00":"000.000.000-00"} value={ownerForm.document} onChange={e=>setOwnerForm({...ownerForm,document:e.target.value})}/></F>
              <F label="Telefone"><input className="input" type="tel" value={ownerForm.phone} onChange={e=>setOwnerForm({...ownerForm,phone:e.target.value})}/></F>
              <F label="E-mail"><input className="input" type="email" value={ownerForm.email} onChange={e=>setOwnerForm({...ownerForm,email:e.target.value})}/></F>
              <label className="field owner-address"><span>Endereço completo</span><input className="input" value={ownerForm.address} onChange={e=>setOwnerForm({...ownerForm,address:e.target.value})}/></label>
            </div></section>
            <section className="owner-form-section"><h4>Dados bancários</h4><div className="form-grid">
              <F label="Banco"><input className="input" placeholder="Nome ou código do banco" value={ownerForm.bank_name} onChange={e=>setOwnerForm({...ownerForm,bank_name:e.target.value})}/></F>
              <F label="Agência"><input className="input" value={ownerForm.bank_agency} onChange={e=>setOwnerForm({...ownerForm,bank_agency:e.target.value})}/></F>
              <F label="Conta"><input className="input" value={ownerForm.bank_account} onChange={e=>setOwnerForm({...ownerForm,bank_account:e.target.value})}/></F>
              <F label="Tipo de conta"><select className="input" value={ownerForm.bank_account_type} onChange={e=>setOwnerForm({...ownerForm,bank_account_type:e.target.value})}><option value="corrente">Conta corrente</option><option value="poupanca">Poupança</option><option value="pagamento">Conta pagamento</option></select></F>
              <F label="Tipo de chave Pix"><select className="input" value={ownerForm.pix_key_type} onChange={e=>setOwnerForm({...ownerForm,pix_key_type:e.target.value})}><option value="cpf_cnpj">CPF/CNPJ</option><option value="email">E-mail</option><option value="telefone">Telefone</option><option value="aleatoria">Chave aleatória</option></select></F>
              <F label="Chave Pix"><input className="input" value={ownerForm.pix_key} onChange={e=>setOwnerForm({...ownerForm,pix_key:e.target.value})}/></F>
            </div></section>
            {error&&<p className="modal-error owner-modal-error">{error}</p>}
            <div className="modal-actions">
              <button className="btn-primary">Cadastrar</button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setOwnerOpen(false)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
function F({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

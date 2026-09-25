import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "../services/api";
import { appConfirm } from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";

type VehicleLink = { id:number; plate:string; description?:string|null };
type Carrier = { id:number; tenant_id:number|null; name:string; document?:string|null; person_type:string; kind:string; phone?:string|null; email?:string|null; address?:string|null; antt_number?:string|null; antt_expiry_date?:string|null; max_masters?:number|null; active:boolean; vehicles:VehicleLink[] };
type Vehicle = { id:number; plate:string; description?:string|null; ownership_type:string; active:boolean; blocked:boolean; carrier_id?:number|null };
type Branch = { id:number; name:string; tenant_id:number|null; active:boolean };
type Tenant = { id:number; name:string; active:boolean };

const blank = { tenant_id:"", name:"", document:"", person_type:"pessoa_juridica", kind:"arrendatario", phone:"", email:"", address:"", antt_number:"", antt_expiry_date:"", max_masters:"", active:true, vehicle_ids:[] as number[], branch_ids:[] as number[] };

export default function Carriers() {
  const { user, hasRole } = useAuth();
  const [rows,setRows]=useState<Carrier[]>([]), [vehicles,setVehicles]=useState<Vehicle[]>([]), [branches,setBranches]=useState<Branch[]>([]), [tenants,setTenants]=useState<Tenant[]>([]);
  const [linkedBranches,setLinkedBranches]=useState<Record<number,number[]>>({}), [editing,setEditing]=useState<Carrier|"new"|null>(null), [form,setForm]=useState({...blank});
  const [query,setQuery]=useState(""), [status,setStatus]=useState("active"), [error,setError]=useState(""), [saving,setSaving]=useState(false);
  const isGlobal=hasRole("admin_global"), canDelete=user?.role==="admin_global";

  async function load(){
    const [carrierResponse,vehicleResponse,branchResponse]=await Promise.all([api.get<Carrier[]>("/carriers"),api.get<Vehicle[]>("/vehicles"),api.get<Branch[]>("/branches")]);
    setRows(carrierResponse.data); setVehicles(vehicleResponse.data); setBranches(branchResponse.data.filter(item=>item.active));
    const links:Record<number,number[]>={};
    await Promise.all(branchResponse.data.filter(item=>item.active).map(async branch=>{try{const response=await api.get(`/access-model/branches/${branch.id}`);for(const carrier of response.data.carriers.filter((item:any)=>item.active)){(links[carrier.id]??=[]).push(branch.id)}}catch{/* sem acesso à filial */}}));
    setLinkedBranches(links);
  }
  useEffect(()=>{load().catch(()=>setError("Não foi possível carregar as transportadoras."));if(isGlobal)api.get<Tenant[]>("/tenants").then(r=>setTenants(r.data.filter(t=>t.active))).catch(()=>setTenants([]));},[]);
  const filtered=useMemo(()=>rows.filter(row=>(!query||`${row.name} ${row.document||""} ${row.antt_number||""}`.toLowerCase().includes(query.toLowerCase()))&&(status==="all"||(status==="active"?row.active:!row.active))),[rows,query,status]);
  const tenantBranches=branches.filter(branch=>branch.tenant_id===Number(form.tenant_id||user?.tenant_id));
  const editingId=editing&&editing!=="new"?editing.id:undefined;
  const availableVehicles=vehicles.filter(vehicle=>vehicle.ownership_type==="agregado"&&vehicle.active&&!vehicle.blocked&&(!vehicle.carrier_id||vehicle.carrier_id===editingId));

  function open(row?:Carrier){setError("");if(!row){setForm({...blank,tenant_id:user?.tenant_id?String(user.tenant_id):""});setEditing("new");return}setForm({tenant_id:String(row.tenant_id||""),name:row.name,document:row.document||"",person_type:row.person_type,kind:row.kind,phone:row.phone||"",email:row.email||"",address:row.address||"",antt_number:row.antt_number||"",antt_expiry_date:row.antt_expiry_date||"",max_masters:row.max_masters?String(row.max_masters):"",active:row.active,vehicle_ids:row.vehicles.map(v=>v.id),branch_ids:linkedBranches[row.id]||[]});setEditing(row)}
  async function save(event:FormEvent){event.preventDefault();if(!editing)return;setError("");setSaving(true);try{
    const {branch_ids:_,...fields}=form;const payload={...fields,max_masters:form.max_masters?Number(form.max_masters):null,tenant_id:Number(form.tenant_id||user?.tenant_id),document:form.document.replace(/\D/g,""),phone:form.phone||null,email:form.email||null,address:form.address||null,antt_number:form.antt_number||null,antt_expiry_date:form.antt_expiry_date||null,vehicle_ids:form.vehicle_ids};
    const response=editing==="new"?await api.post<Carrier>("/carriers",payload):await api.put<Carrier>(`/carriers/${editing.id}`,payload);
    const previous=editing==="new"?[]:(linkedBranches[response.data.id]||[]);for(const branchId of form.branch_ids.filter(id=>!previous.includes(id)))await api.put(`/access-model/carriers/${response.data.id}/branches/${branchId}`);
    setEditing(null);await load();
  }catch(err:any){setError(err?.response?.data?.detail||err.message||"Não foi possível salvar a transportadora.")}finally{setSaving(false)}}
  async function remove(row:Carrier){if(!await appConfirm(`Excluir ${row.name}?`,{title:"Excluir transportadora",confirmLabel:"Excluir",danger:true}))return;try{await api.delete(`/carriers/${row.id}`);await load()}catch(err:any){setError(err?.response?.data?.detail||"Não foi possível excluir. Inative o cadastro se ele já estiver em uso.")}}
  const toggle=(key:"vehicle_ids"|"branch_ids",id:number)=>setForm(current=>({...current,[key]:current[key].includes(id)?current[key].filter(item=>item!==id):[...current[key],id]}));

  return <div>
    <div className="page-header"><div><h2>Transportadoras</h2><p className="page-subtitle">Cadastre transportadoras, documentação, filiais atendidas e veículos agregados.</p></div><button className="btn-primary" onClick={()=>open()}>Nova transportadora</button></div>
    {error&&<div className="form-error">{error}</div>}
    <div className="driver-filters"><input className="input" placeholder="Buscar por nome, CPF/CNPJ ou ANTT" value={query} onChange={e=>setQuery(e.target.value)}/><select className="input" value={status} onChange={e=>setStatus(e.target.value)}><option value="active">Ativas</option><option value="inactive">Inativas</option><option value="all">Todas</option></select></div>
    <div className="card-panel table-wrap"><table className="data-table"><thead><tr><th>Transportadora</th><th>Documento</th><th>ANTT/RNTRC</th><th>Filiais</th><th>Veículos</th><th>Situação</th><th>Ações</th></tr></thead><tbody>
      {filtered.map(row=><tr key={row.id}><td><strong>{row.name}</strong><small>{row.kind==="beneficiario"?"Beneficiário":"Arrendatário"}</small></td><td>{row.document||"—"}</td><td>{row.antt_number||"—"}</td><td>{(linkedBranches[row.id]||[]).map(id=>branches.find(b=>b.id===id)?.name).filter(Boolean).join(", ")||"Não vinculada"}</td><td><div className="carrier-plates">{row.vehicles.map(v=><span key={v.id}>{v.plate}</span>)}{!row.vehicles.length&&<em>Nenhum</em>}</div></td><td><span className={`driver-status ${row.active?"ok":"missing"}`}>{row.active?"Ativa":"Inativa"}</span></td><td><button className="btn-mini" onClick={()=>open(row)}>Editar</button>{canDelete&&<button className="btn-mini danger" onClick={()=>void remove(row)}>Excluir</button>}</td></tr>)}
      {!filtered.length&&<tr><td colSpan={7} className="empty-state">Nenhuma transportadora encontrada.</td></tr>}
    </tbody></table></div>
    {editing&&<div className="modal-backdrop"><form className="modal-card carrier-modal" onSubmit={save}><div className="modal-heading"><div><h3>{editing==="new"?"Nova transportadora":"Editar transportadora"}</h3><p>Informe os dados legais e operacionais.</p></div><button type="button" className="modal-close" onClick={()=>setEditing(null)}>×</button></div>
      {error&&<div className="modal-error">{error}</div>}<div className="form-grid">
        {isGlobal&&<label className="field"><span>Empresa *</span><select className="input" required value={form.tenant_id} onChange={e=>setForm({...form,tenant_id:e.target.value,branch_ids:[]})}><option value="">Selecione</option>{tenants.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>}
        <label className="field"><span>Nome / razão social *</span><input className="input" required value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
        <label className="field"><span>Tipo de pessoa *</span><select className="input" value={form.person_type} onChange={e=>setForm({...form,person_type:e.target.value,document:""})}><option value="pessoa_juridica">Pessoa jurídica (CNPJ)</option><option value="pessoa_fisica">Pessoa física (CPF)</option></select></label>
        <label className="field"><span>{form.person_type==="pessoa_juridica"?"CNPJ":"CPF"} *</span><input className="input" required value={form.document} onChange={e=>setForm({...form,document:e.target.value})}/></label>
        <label className="field"><span>Classificação *</span><select className="input" value={form.kind} onChange={e=>setForm({...form,kind:e.target.value})}><option value="arrendatario">Arrendatário</option><option value="beneficiario">Beneficiário do frete</option></select></label>
        <label className="field"><span>ANTT/RNTRC</span><input className="input" value={form.antt_number} onChange={e=>setForm({...form,antt_number:e.target.value})}/></label><label className="field"><span>Validade ANTT</span><input className="input" type="date" value={form.antt_expiry_date} onChange={e=>setForm({...form,antt_expiry_date:e.target.value})}/></label>
        <label className="field"><span>Telefone</span><input className="input" value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})}/></label><label className="field"><span>E-mail</span><input className="input" type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/></label><label className="field"><span>Endereço</span><input className="input" value={form.address} onChange={e=>setForm({...form,address:e.target.value})}/></label>
        <label className="field"><span>Situação</span><select className="input" value={String(form.active)} onChange={e=>setForm({...form,active:e.target.value==="true"})}><option value="true">Ativa</option><option value="false">Inativa</option></select></label>
        <label className="field"><span>Limite de masters</span><input className="input" type="number" min={1} max={20} placeholder="Padrão da empresa" value={form.max_masters} onChange={e=>setForm({...form,max_masters:e.target.value})}/><small>Em branco usa o limite padrão da empresa.</small></label>
      </div>
      <h4>Filiais atendidas</h4><div className="carrier-vehicle-list">{tenantBranches.map(branch=><label key={branch.id} className={form.branch_ids.includes(branch.id)?"selected":""}><input type="checkbox" checked={form.branch_ids.includes(branch.id)} disabled={editing!=="new"&&(linkedBranches[editing.id]||[]).includes(branch.id)} onChange={()=>toggle("branch_ids",branch.id)}/><span>{branch.name}<small>{editing!=="new"&&(linkedBranches[editing.id]||[]).includes(branch.id)?"Vínculo ativo":"Liberar operação"}</small></span></label>)}</div>
      <h4>Veículos agregados</h4>{form.vehicle_ids.length>0&&!form.antt_number&&<div className="carrier-antt-note">Informe a ANTT/RNTRC antes de vincular veículos.</div>}<div className="carrier-vehicle-list">{availableVehicles.map(vehicle=><label key={vehicle.id} className={form.vehicle_ids.includes(vehicle.id)?"selected":""}><input type="checkbox" checked={form.vehicle_ids.includes(vehicle.id)} onChange={()=>toggle("vehicle_ids",vehicle.id)}/><span>{vehicle.plate}<small>{vehicle.description||"Veículo agregado"}</small></span></label>)}{!availableVehicles.length&&<div className="empty-state">Nenhum veículo agregado disponível.</div>}</div>
      <div className="modal-actions"><button type="button" className="btn-ghost" onClick={()=>setEditing(null)}>Cancelar</button><button className="btn-primary" disabled={saving}>{saving?"Salvando…":"Salvar transportadora"}</button></div>
    </form></div>}
  </div>
}

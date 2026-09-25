import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "../services/api";
import { appConfirm } from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";

type Branch={id:number;name:string;country:string;locale:string;tenant_id:number|null;active:boolean};
type Tenant={id:number;name:string;active:boolean};
const blank={name:"",country:"BR",locale:"pt-BR",tenant_id:"",active:true};

export default function Branches(){
  const {user,hasRole}=useAuth();
  const [rows,setRows]=useState<Branch[]>([]),[tenants,setTenants]=useState<Tenant[]>([]),[editing,setEditing]=useState<Branch|"new"|null>(null),[form,setForm]=useState({...blank}),[query,setQuery]=useState(""),[status,setStatus]=useState("all"),[error,setError]=useState(""),[saving,setSaving]=useState(false);
  const isGlobal=hasRole("admin_global"),canDelete=user?.role==="admin_global";
  const load=()=>api.get<Branch[]>("/branches").then(response=>setRows(response.data));
  useEffect(()=>{load().catch(()=>setError("Não foi possível carregar as filiais."));if(isGlobal)api.get<Tenant[]>("/tenants").then(response=>setTenants(response.data.filter(item=>item.active))).catch(()=>setTenants([]));},[]);
  const filtered=useMemo(()=>rows.filter(row=>(!query||`${row.name} ${row.country}`.toLowerCase().includes(query.toLowerCase()))&&(status==="all"||(status==="active"?row.active:!row.active))),[rows,query,status]);
  function open(row?:Branch){setError("");if(!row){setForm({...blank,tenant_id:user?.tenant_id?String(user.tenant_id):""});setEditing("new");return}setForm({name:row.name,country:row.country,locale:row.locale,tenant_id:String(row.tenant_id||""),active:row.active});setEditing(row)}
  async function save(event:FormEvent){event.preventDefault();if(!editing||saving)return;setSaving(true);setError("");try{if(editing==="new")await api.post("/branches",{name:form.name.trim(),country:form.country,locale:form.locale,tenant_id:Number(form.tenant_id||user?.tenant_id)});else await api.put(`/branches/${editing.id}`,{name:form.name.trim(),locale:form.locale,active:form.active});setEditing(null);await load()}catch(err:any){setError(err?.response?.data?.detail||"Não foi possível salvar a filial.")}finally{setSaving(false)}}
  async function remove(row:Branch){if(!await appConfirm(`Excluir definitivamente a filial ${row.name}?`,{title:"Excluir filial",confirmLabel:"Excluir",danger:true}))return;try{await api.delete(`/branches/${row.id}`);await load()}catch(err:any){setError(err?.response?.data?.detail||"A filial possui vínculos. Inative-a para preservar o histórico.")}}
  async function toggle(row:Branch){try{await api.put(`/branches/${row.id}`,{active:!row.active});await load()}catch(err:any){setError(err?.response?.data?.detail||"Não foi possível alterar a situação da filial.")}}
  const tenantName=(id:number|null)=>tenants.find(item=>item.id===id)?.name||(id===user?.tenant_id?"Empresa atual":"—");

  return <div><div className="page-header"><div><h2>Filiais Adimax</h2><p className="page-subtitle">Gerencie as unidades utilizadas nos usuários, transportadoras, veículos e rotas.</p></div><button className="btn-primary" onClick={()=>open()}>Nova filial</button></div>
    {error&&<div className="form-error">{error}</div>}
    <div className="driver-filters"><input className="input" placeholder="Buscar filial" value={query} onChange={event=>setQuery(event.target.value)}/><select className="input" value={status} onChange={event=>setStatus(event.target.value)}><option value="all">Todas</option><option value="active">Ativas</option><option value="inactive">Inativas</option></select></div>
    <div className="card-panel table-wrap"><table className="data-table"><thead><tr><th>Filial</th>{isGlobal&&<th>Empresa</th>}<th>País</th><th>Idioma</th><th>Situação</th><th>Ações</th></tr></thead><tbody>{filtered.map(row=><tr key={row.id}><td><strong>{row.name}</strong><small>ID #{row.id}</small></td>{isGlobal&&<td>{tenantName(row.tenant_id)}</td>}<td>{row.country}</td><td>{row.locale}</td><td><span className={`driver-status ${row.active?"ok":"missing"}`}>{row.active?"Ativa":"Inativa"}</span></td><td><button className="btn-mini" onClick={()=>open(row)}>Editar</button><button className="btn-mini" onClick={()=>void toggle(row)}>{row.active?"Inativar":"Ativar"}</button>{canDelete&&<button className="btn-mini danger" onClick={()=>void remove(row)}>Excluir</button>}</td></tr>)}{!filtered.length&&<tr><td colSpan={isGlobal?6:5} className="empty-state">Nenhuma filial encontrada.</td></tr>}</tbody></table></div>
    {editing&&<div className="modal-backdrop" onClick={()=>setEditing(null)}><form className="modal-card modal-card-compact" onSubmit={save} onClick={event=>event.stopPropagation()}><div className="modal-heading"><div><h3>{editing==="new"?"Nova filial":"Editar filial"}</h3><p>Defina a identificação da unidade operacional.</p></div><button type="button" className="modal-close" onClick={()=>setEditing(null)}>×</button></div>{error&&<div className="modal-error">{error}</div>}<div className="form-grid">
      {isGlobal&&editing==="new"&&<label className="field"><span>Empresa *</span><select className="input" required value={form.tenant_id} onChange={event=>setForm({...form,tenant_id:event.target.value})}><option value="">Selecione</option>{tenants.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      <label className="field"><span>Nome da filial *</span><input className="input" required value={form.name} onChange={event=>setForm({...form,name:event.target.value})}/></label>
      {editing==="new"&&<label className="field"><span>País</span><select className="input" value={form.country} onChange={event=>setForm({...form,country:event.target.value})}><option value="BR">Brasil</option><option value="PT">Portugal</option></select></label>}
      <label className="field"><span>Idioma</span><select className="input" value={form.locale} onChange={event=>setForm({...form,locale:event.target.value})}><option value="pt-BR">Português (Brasil)</option><option value="pt-PT">Português (Portugal)</option></select></label>
      {editing!=="new"&&<label className="field"><span>Situação</span><select className="input" value={String(form.active)} onChange={event=>setForm({...form,active:event.target.value==="true"})}><option value="true">Ativa</option><option value="false">Inativa</option></select></label>}
    </div><div className="modal-actions"><button type="button" className="btn-ghost" onClick={()=>setEditing(null)}>Cancelar</button><button className="btn-primary" disabled={saving}>{saving?"Salvando…":"Salvar filial"}</button></div></form></div>}
  </div>
}

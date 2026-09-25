import { useEffect, useState } from "react";
import api from "../services/api";

type Profile = { value:string; label:string; description?:string|null; permissions:string[]; sort_order:number; active:boolean; system:boolean };
const MODULES = [
  ["scope.tenant","Todas as filiais da empresa"],
  ["module.dashboard","Painel"], ["module.routes","Rotas"], ["module.routing","Roteirização manual"],
  ["module.monitoring","Monitoramento de rotas"], ["module.occurrences","Ocorrências"],
  ["module.gallery","Galeria"], ["module.tracking","Acompanhamento"], ["module.drivers","Motoristas"],
  ["module.vehicles","Veículos"], ["module.reports","Relatórios"], ["module.users","Usuários"],
  ["module.carriers","Transportadoras"], ["module.branches","Filiais"],
] as const;
const EMPTY:Profile={value:"",label:"",description:"",permissions:[],sort_order:100,active:true,system:false};

export default function Profiles(){
  const [profiles,setProfiles]=useState<Profile[]>([]); const [editing,setEditing]=useState<Profile|null>(null);
  const [error,setError]=useState(""); const [saving,setSaving]=useState(false);
  const load=()=>api.get("/users/role-profiles").then(r=>setProfiles(r.data)).catch(()=>setError("Não foi possível carregar os perfis."));
  useEffect(()=>{void load()},[]);
  function toggle(permission:string){if(!editing)return;setEditing({...editing,permissions:editing.permissions.includes(permission)?editing.permissions.filter(p=>p!==permission):[...editing.permissions,permission]})}
  async function save(event:React.FormEvent){event.preventDefault();if(!editing)return;setSaving(true);setError("");try{const body={label:editing.label,description:editing.description||null,permissions:editing.permissions,sort_order:editing.sort_order,active:editing.active};if(editing.system||profiles.some(p=>p.value===editing.value))await api.put(`/users/role-profiles/${editing.value}`,body);else await api.post("/users/role-profiles",{value:editing.value,...body});setEditing(null);await load()}catch(e:any){setError(e?.response?.data?.detail||"Não foi possível salvar o perfil.")}finally{setSaving(false)}}
  return <div><div style={header}><div><h2 style={{margin:0}}>Perfis de acesso</h2><p style={muted}>Defina os módulos e o alcance operacional de cada perfil.</p></div><button style={primary} onClick={()=>setEditing({...EMPTY})}>Novo perfil</button></div>
    {error&&<p style={{color:"#b42318"}}>{error}</p>}
    <div style={cards}>{profiles.map(profile=><article key={profile.value} style={card}><div><strong>{profile.label}</strong><span style={badge}>{profile.active?"Ativo":"Inativo"}</span></div><p style={muted}>{profile.description||"Sem descrição"}</p><small>{profile.permissions.filter(p=>p.startsWith("module.")).length} módulos liberados</small><button style={ghost} onClick={()=>setEditing({...profile,permissions:[...profile.permissions]})}>Gerenciar</button></article>)}</div>
    {editing&&<div className="modal-backdrop" onClick={()=>setEditing(null)}><form className="modal-card" style={{maxWidth:760}} onSubmit={save} onClick={e=>e.stopPropagation()}><h3>{profiles.some(p=>p.value===editing.value)?"Editar perfil":"Novo perfil"}</h3><div style={grid}><label style={field}>Nome<input className="input" required value={editing.label} onChange={e=>setEditing({...editing,label:e.target.value})}/></label><label style={field}>Código<input className="input" required disabled={editing.system||profiles.some(p=>p.value===editing.value)} value={editing.value} onChange={e=>setEditing({...editing,value:e.target.value.toLowerCase().replace(/[^a-z0-9_]/g,"_")})}/></label><label style={{...field,gridColumn:"1/-1"}}>Descrição<input className="input" value={editing.description||""} onChange={e=>setEditing({...editing,description:e.target.value})}/></label></div><h4>Acessos da operação</h4><div style={modules}>{MODULES.map(([key,label])=><label key={key} style={check}><input type="checkbox" checked={editing.permissions.includes(key)} onChange={()=>toggle(key)}/><span><b>{label}</b><small>{key}</small></span></label>)}</div><label style={{...check,marginTop:14}}><input type="checkbox" checked={editing.active} onChange={e=>setEditing({...editing,active:e.target.checked})}/><span><b>Perfil ativo</b></span></label><div style={{marginTop:18}}><button style={primary} disabled={saving}>{saving?"Salvando…":"Salvar perfil"}</button><button type="button" style={ghost} onClick={()=>setEditing(null)}>Cancelar</button></div></form></div>}
  </div>
}
const header:React.CSSProperties={display:"flex",justifyContent:"space-between",gap:16,alignItems:"flex-start",marginBottom:18};
const muted:React.CSSProperties={color:"var(--muted)",fontSize:13,margin:"6px 0"};
const cards:React.CSSProperties={display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(250px,1fr))",gap:12};
const card:React.CSSProperties={display:"grid",gap:9,padding:16,border:"1px solid var(--line)",borderRadius:12,background:"var(--panel)"};
const badge:React.CSSProperties={float:"right",fontSize:10,padding:"3px 7px",borderRadius:10,background:"var(--soft)"};
const primary:React.CSSProperties={padding:"9px 14px",border:0,borderRadius:8,background:"var(--brand,#0a58ca)",color:"white",fontWeight:700,cursor:"pointer",marginRight:8};
const ghost:React.CSSProperties={padding:"8px 12px",border:"1px solid var(--line)",borderRadius:8,background:"var(--panel)",color:"var(--ink)",cursor:"pointer"};
const grid:React.CSSProperties={display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}; const field:React.CSSProperties={display:"grid",gap:5,fontSize:12};
const modules:React.CSSProperties={display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(205px,1fr))",gap:8}; const check:React.CSSProperties={display:"flex",alignItems:"center",gap:9,padding:9,border:"1px solid var(--line)",borderRadius:8};

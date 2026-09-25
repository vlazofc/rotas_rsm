import { FormEvent, useCallback, useEffect, useState } from "react";
import api from "../services/api";
import {appAlert,appConfirm,appPrompt} from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";

type Occurrence = { id:number; route_id:number; codigo_ut:string; plate?:string; driver?:string; category:string; severity:string; description:string; status:string; resolution?:string; assigned_to?:string; evidence_url?:string; treatment_started_at?:string; resolved_at?:string; finalized_at?:string; created_at:string };
type History = {id:number;from_status?:string;to_status:string;description?:string;actor?:string;created_at:string};
type OccurrenceRoute = { id:number; codigo_ut:string; route_date:string; status:string };
type OccurrenceCategory = { id:number; code:string; name:string; active:boolean; system:boolean };
type FormState = { route_id:string; category:string; severity:string; description:string; status:string; resolution:string; treatment_note:string };
const emptyForm: FormState = { route_id:"", category:"outros", severity:"media", description:"", status:"aberta", resolution:"", treatment_note:"" };
const labels: Record<string,string> = {
  avaria:"Avaria", acidente:"Acidente", atraso:"Atraso", seguranca:"Segurança", outros:"Outros",
  baixa:"Baixa", media:"Média", alta:"Alta", critica:"Crítica",
  aberta:"Aberta", em_analise:"Em tratamento", em_tratamento:"Em tratamento", resolvida:"Resolvida", finalizada:"Finalizada", cancelada:"Cancelada",
};

export default function Occurrences() {
  const { user, hasRole } = useAuth();
  const [rows,setRows] = useState<Occurrence[]>([]);
  const [form,setForm] = useState<FormState>(emptyForm);
  const [editing,setEditing] = useState<Occurrence|null>(null);
  const [modalOpen,setModalOpen] = useState(false);
  const [loading,setLoading] = useState(true);
  const [saving,setSaving] = useState(false);
  const [error,setError] = useState("");
  const [statusFilter,setStatusFilter] = useState("pendentes");
  const [history,setHistory] = useState<History[]>([]);
  const [dayRoutes,setDayRoutes] = useState<OccurrenceRoute[]>([]);
  const [routesLoading,setRoutesLoading] = useState(false);
  const [categories,setCategories] = useState<OccurrenceCategory[]>([]);
  const [categoryManagerOpen,setCategoryManagerOpen] = useState(false);
  const [evidenceFile,setEvidenceFile] = useState<File|null>(null);
  const manager = hasRole("admin_global","gestor_brasil","torre_controle","operador_logistico");
  const canManageCategories = manager && !user?.is_carrier_master;
  const canReport = hasRole("admin_global","gestor_brasil","torre_controle","motorista");

  const loadCategories = useCallback(async () => {
    const response = await api.get<OccurrenceCategory[]>("/erp/occurrence-categories", { params:{include_inactive:canManageCategories} });
    setCategories(response.data);
  },[canManageCategories]);

  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await api.get<Occurrence[]>("/erp/occurrences"); setRows(response.data); }
    finally { setLoading(false); }
  },[]);
  useEffect(() => { void load(); void loadCategories().catch(() => setCategories([])); },[load,loadCategories]);
  useEffect(() => {
    if (!modalOpen || editing) return;
    let cancelled = false;
    setRoutesLoading(true);
    setDayRoutes([]);
    api.get<OccurrenceRoute[]>("/routes").then(({data}) => {
      if (cancelled) return;
      const today = new Intl.DateTimeFormat("sv-SE", {timeZone:"America/Sao_Paulo"}).format(new Date());
      setDayRoutes(data.filter(route => route.route_date === today && route.status !== "cancelada")
        .sort((a,b) => Number(b.status === "em_rota") - Number(a.status === "em_rota") || String(a.codigo_ut).localeCompare(String(b.codigo_ut), "pt-BR", {numeric:true})));
    }).catch(() => { if (!cancelled) setError("Não foi possível carregar as rotas. Feche e abra o formulário para tentar novamente."); })
      .finally(() => { if (!cancelled) setRoutesLoading(false); });
    return () => { cancelled = true; };
  },[modalOpen,editing]);

  function openCreate() { setEditing(null); setForm(emptyForm); setEvidenceFile(null); setError(""); setModalOpen(true); }
  function openEdit(row: Occurrence) {
    setEditing(row);
    setForm({ route_id:String(row.route_id), category:row.category, severity:row.severity, description:row.description, status:row.status==="em_analise"?"em_tratamento":row.status, resolution:row.resolution||"", treatment_note:"" });
    api.get<History[]>(`/erp/occurrences/${row.id}/history`).then(response=>setHistory(response.data)).catch(()=>setHistory([]));
    setEvidenceFile(null); setError(""); setModalOpen(true);
  }

  async function assume(row:Occurrence){try{await api.put(`/erp/occurrences/${row.id}`,{status:"em_tratamento",treatment_note:"Tratamento assumido pela operação."});await load()}catch(requestError:any){await appAlert(requestError?.response?.data?.detail||"Não foi possível assumir a tarefa.",{title:"Falha ao assumir ocorrência"})}}

  async function save(event: FormEvent) {
    if (!editing && (routesLoading || !dayRoutes.some(route => String(route.id) === form.route_id))) {
      event.preventDefault(); setError("Selecione uma rota do dia."); return;
    }
    event.preventDefault();
    if (form.category === "sobra" && !evidenceFile && !editing?.evidence_url) { setError("A evidência é obrigatória para ocorrência de sobra."); return; }
    setError(""); setSaving(true);
    try {
      if (editing) {
        await api.put(`/erp/occurrences/${editing.id}`, {
          route_id:Number(form.route_id), category:form.category, severity:form.severity, description:form.description,
          ...(manager && { status:form.status, resolution:form.resolution||null, treatment_note:form.treatment_note||null }),
        });
        if (evidenceFile) { const evidence=new FormData(); evidence.set("evidence",evidenceFile); await api.post(`/erp/occurrences/${editing.id}/evidence`,evidence); }
      } else {
        let position: GeolocationPosition|null = null;
        try { position = await new Promise((resolve,reject) => navigator.geolocation.getCurrentPosition(resolve,reject,{timeout:5000})); } catch { /* localização opcional */ }
        if (form.category === "sobra") {
          const payload=new FormData(); payload.set("route_id",form.route_id); payload.set("category",form.category); payload.set("severity",form.severity); payload.set("description",form.description); payload.set("evidence",evidenceFile!);
          if(position){payload.set("latitude",String(position.coords.latitude));payload.set("longitude",String(position.coords.longitude));}
          await api.post("/erp/occurrences-with-evidence",payload);
        } else {
          const created=await api.post<Occurrence>("/erp/occurrences", { route_id:Number(form.route_id), category:form.category, severity:form.severity, description:form.description, latitude:position?.coords.latitude, longitude:position?.coords.longitude });
          if (evidenceFile) { const evidence=new FormData(); evidence.set("evidence",evidenceFile); await api.post(`/erp/occurrences/${created.data.id}/evidence`,evidence); }
        }
      }
      setModalOpen(false); await load();
    } catch (requestError:any) { setError(requestError?.response?.data?.detail||"Não foi possível salvar a ocorrência."); }
    finally { setSaving(false); }
  }

  async function remove(row: Occurrence) {
    if (!await appConfirm(`Excluir a ocorrência da rota ${row.codigo_ut}? Esta ação não pode ser desfeita.`,{title:"Excluir ocorrência",confirmLabel:"Sim, excluir",danger:true})) return;
    try { await api.delete(`/erp/occurrences/${row.id}`); await load(); }
    catch (requestError:any) { await appAlert(requestError?.response?.data?.detail||"Não foi possível excluir a ocorrência.",{title:"Falha ao excluir"}); }
  }
  async function addCategory() {
    const name=await appPrompt("Informe o nome da nova categoria.",{title:"Nova categoria de ocorrência",label:"Nome",required:true,confirmLabel:"Adicionar"});
    if(!name)return;
    try{await api.post("/erp/occurrence-categories",{name});await loadCategories()}
    catch(requestError:any){await appAlert(requestError?.response?.data?.detail||"Não foi possível adicionar a categoria.",{title:"Falha ao adicionar"})}
  }
  async function renameCategory(category:OccurrenceCategory) {
    const name=await appPrompt("Altere o nome exibido desta categoria.",{title:"Editar categoria",label:"Nome",initial:category.name,required:true,confirmLabel:"Salvar"});
    if(!name||name===category.name)return;
    try{await api.put(`/erp/occurrence-categories/${category.id}`,{name});await loadCategories()}
    catch(requestError:any){await appAlert(requestError?.response?.data?.detail||"Não foi possível editar a categoria.",{title:"Falha ao editar"})}
  }
  async function toggleCategory(category:OccurrenceCategory) {
    const action=category.active?"inativar":"reativar";
    if(!await appConfirm(`${action[0].toUpperCase()+action.slice(1)} a categoria ${category.name}?`,{title:`${category.active?"Inativar":"Reativar"} categoria`,confirmLabel:category.active?"Inativar":"Reativar",danger:category.active}))return;
    try{await api.put(`/erp/occurrence-categories/${category.id}/toggle`);await loadCategories()}
    catch(requestError:any){await appAlert(requestError?.response?.data?.detail||"Não foi possível alterar a categoria.",{title:"Falha ao alterar"})}
  }
  function canChange(row: Occurrence) { return manager || (user?.role === "motorista" && row.status === "aberta"); }
  const filtered=rows.filter(row=>statusFilter==="todos"||(statusFilter==="pendentes"?!["finalizada","cancelada"].includes(row.status):row.status===statusFilter));
  const nextStatuses=(status:string)=>status==="aberta"?["aberta","em_tratamento","cancelada"]:status==="em_tratamento"||status==="em_analise"?["em_tratamento","resolvida","cancelada"]:status==="resolvida"?["resolvida","finalizada","em_tratamento"]:[status];

  const categoryName=(code:string)=>categories.find(category=>category.code===code)?.name||labels[code]||code;
  return <div className="page-card">
    <div className="page-header"><div><h2>Tarefas de ocorrências</h2><p className="page-subtitle">Registre, atribua, resolva e finalize ocorrências da operação com histórico completo.</p></div><div className="occurrence-actions">{canManageCategories&&<button className="btn-ghost" type="button" onClick={()=>setCategoryManagerOpen(true)}>Gerenciar categorias</button>}{canReport&&<button className="btn-primary" type="button" onClick={openCreate}>Nova ocorrência</button>}</div></div>
    <div className="occurrence-summary"><article><span>Abertas</span><strong>{rows.filter(r=>r.status==="aberta").length}</strong></article><article><span>Em tratamento</span><strong>{rows.filter(r=>["em_analise","em_tratamento"].includes(r.status)).length}</strong></article><article><span>Resolvidas</span><strong>{rows.filter(r=>r.status==="resolvida").length}</strong></article><article><span>Finalizadas</span><strong>{rows.filter(r=>r.status==="finalizada").length}</strong></article></div>
    <div className="occurrence-task-filter"><select className="input" value={statusFilter} onChange={event=>setStatusFilter(event.target.value)}><option value="pendentes">Tarefas pendentes</option><option value="todos">Todas as ocorrências</option><option value="aberta">Abertas</option><option value="em_tratamento">Em tratamento</option><option value="resolvida">Resolvidas</option><option value="finalizada">Finalizadas</option><option value="cancelada">Canceladas</option></select></div>
    <div className="table-scroll"><table className="data-table">
      <thead><tr><th>Data</th><th>Rota / veículo</th><th>Motorista</th><th>Categoria</th><th>Gravidade</th><th>Ocorrência / solução</th><th>Responsável</th><th>Status</th><th>Ações</th></tr></thead>
      <tbody>{filtered.map(row=><tr key={row.id}>
        <td>{new Date(row.created_at).toLocaleString("pt-BR")}</td><td><strong>{row.codigo_ut}</strong></td><td>{row.driver||"-"}</td>
        <td>{categoryName(row.category)}</td><td><span className={`stock-badge ${row.severity==="critica"||row.severity==="alta"?"low":"warning"}`}>{labels[row.severity]||row.severity}</span></td><td><strong>{row.description}</strong>{row.resolution&&<small>Solução: {row.resolution}</small>}{row.evidence_url&&<small><a href={row.evidence_url} target="_blank" rel="noreferrer">Abrir evidência</a></small>}</td><td>{row.assigned_to||"Não atribuída"}</td><td><span className={`stock-badge ${row.status==="finalizada"?"ok":row.status==="cancelada"?"low":"warning"}`}>{labels[row.status]||row.status}</span></td>
        <td>{canChange(row)&&<div className="occurrence-actions">{manager&&row.status==="aberta"&&<button className="btn-primary btn-mini" type="button" onClick={()=>void assume(row)}>Assumir</button>}<button className="btn-ghost btn-mini" type="button" onClick={()=>openEdit(row)}>{manager?"Tratar":"Editar"}</button>{user?.role==="motorista"&&row.status==="aberta"&&<button className="btn-danger btn-mini" type="button" onClick={()=>void remove(row)}>Excluir</button>}</div>}</td>
      </tr>)}
      {!loading&&filtered.length===0&&<tr><td colSpan={9} className="empty-state">Nenhuma tarefa encontrada neste filtro.</td></tr>}
      {loading&&<tr><td colSpan={9} className="empty-state">Carregando ocorrências...</td></tr>}</tbody>
    </table></div>
    {modalOpen&&<div className="modal-backdrop" onClick={()=>!saving&&setModalOpen(false)}><form className="modal-card occurrence-modal" onSubmit={save} onClick={event=>event.stopPropagation()}>
      <h3>{editing?"Editar ocorrência":"Nova ocorrência"}</h3><p>{editing?"Atualize os dados e o andamento da ocorrência.":"Informe os dados encontrados durante a rota."}</p>
      <div className="form-grid">
        <label className="field"><span>Rota</span><select className="input" required disabled={Boolean(editing) || routesLoading || saving} value={form.route_id} onChange={event=>setForm({...form,route_id:event.target.value})}>
          {editing ? <option value={editing.route_id}>{editing.codigo_ut}</option> : <>
            <option value="">{routesLoading ? "Carregando rotas..." : dayRoutes.length ? "Selecione uma rota do dia" : "Nenhuma rota disponível hoje"}</option>
            {dayRoutes.map(route => <option key={route.id} value={route.id}>{route.codigo_ut} · {route.status === "em_rota" ? "Em andamento" : route.status === "finalizada" ? "Finalizada" : "Planejada"}</option>)}
          </>}
        </select></label>
        <label className="field"><span>Categoria {manager&&<button className="link-button" type="button" onClick={()=>setCategoryManagerOpen(true)}>Gerenciar</button>}</span><select className="input" value={form.category} onChange={event=>setForm({...form,category:event.target.value})}>{categories.filter(category=>category.active||category.code===form.category).map(category=><option value={category.code} key={category.id}>{category.name}{!category.active?" (inativa)":""}</option>)}</select></label>
        <label className="field"><span>Gravidade</span><select className="input" value={form.severity} onChange={event=>setForm({...form,severity:event.target.value})}><option value="baixa">Baixa</option><option value="media">Média</option><option value="alta">Alta</option><option value="critica">Crítica</option></select></label>
        {editing&&manager&&<label className="field"><span>Próxima etapa</span><select className="input" value={form.status} onChange={event=>setForm({...form,status:event.target.value})}>{nextStatuses(editing.status).map(status=><option value={status} key={status}>{labels[status]}</option>)}</select></label>}
        <label className="field occurrence-wide"><span>Descrição</span><textarea className="input" required minLength={3} rows={4} value={form.description} onChange={event=>setForm({...form,description:event.target.value})}/></label>
        <label className="field occurrence-wide"><span>Evidência da ocorrência {form.category==="sobra"?"*":"(opcional)"}</span><input className="input" type="file" accept="image/*,application/pdf" capture="environment" required={form.category==="sobra"&&!editing?.evidence_url} onChange={event=>setEvidenceFile(event.target.files?.[0]||null)}/>{editing?.evidence_url&&<small><a href={editing.evidence_url} target="_blank" rel="noreferrer">Abrir evidência atual</a></small>}</label>
        {editing&&manager&&<><label className="field occurrence-wide"><span>O que foi feito para resolver {(["resolvida","finalizada"].includes(form.status))&&"*"}</span><textarea className="input" required={["resolvida","finalizada"].includes(form.status)} minLength={5} rows={3} value={form.resolution} onChange={event=>setForm({...form,resolution:event.target.value})}/></label><label className="field occurrence-wide"><span>Nota desta movimentação</span><textarea className="input" rows={2} placeholder="Contato realizado, orientação dada, providência tomada..." value={form.treatment_note} onChange={event=>setForm({...form,treatment_note:event.target.value})}/></label></>}
      </div>
      {editing&&history.length>0&&<div className="occurrence-history"><h4>Histórico da tarefa</h4>{history.map(item=><div key={item.id}><span>{new Date(item.created_at).toLocaleString("pt-BR")}</span><strong>{labels[item.to_status]||item.to_status}</strong><small>{item.actor||"Sistema"}{item.description?` · ${item.description}`:""}</small></div>)}</div>}
      {error&&<p className="modal-error">{error}</p>}<div className="modal-actions"><button className="btn-primary" disabled={saving}>{saving?"Salvando...":editing?"Salvar alterações":"Registrar ocorrência"}</button><button className="btn-ghost" type="button" disabled={saving} onClick={()=>setModalOpen(false)}>Cancelar</button></div>
    </form></div>}
    {categoryManagerOpen&&<div className="modal-backdrop" onClick={()=>setCategoryManagerOpen(false)}><section className="modal-card" onClick={event=>event.stopPropagation()}>
      <div className="page-header"><div><h3>Categorias de ocorrências</h3><p>Adicione, renomeie, inative ou reative as opções usadas nos formulários.</p></div><button className="btn-primary" type="button" onClick={()=>void addCategory()}>Nova categoria</button></div>
      <div className="category-manager-list">{categories.map(category=><div key={category.id}><span><strong>{category.name}</strong><small>{category.active?"Ativa":"Inativa"}</small></span><div className="occurrence-actions"><button className="btn-ghost btn-mini" type="button" onClick={()=>void renameCategory(category)}>Editar</button><button className={category.active?"btn-danger btn-mini":"btn-ghost btn-mini"} type="button" onClick={()=>void toggleCategory(category)}>{category.active?"Inativar":"Reativar"}</button></div></div>)}</div>
      <div className="modal-actions"><button className="btn-ghost" type="button" onClick={()=>setCategoryManagerOpen(false)}>Fechar</button></div>
    </section></div>}
  </div>;
}

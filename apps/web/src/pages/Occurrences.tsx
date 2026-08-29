import { FormEvent, useCallback, useEffect, useState } from "react";
import api from "../services/api";
import {appAlert,appConfirm} from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";

type Occurrence = { id:number; route_id:number; codigo_ut:string; plate?:string; driver?:string; category:string; severity:string; description:string; status:string; resolution?:string; assigned_to?:string; treatment_started_at?:string; resolved_at?:string; finalized_at?:string; created_at:string };
type History = {id:number;from_status?:string;to_status:string;description?:string;actor?:string;created_at:string};
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
  const manager = hasRole("admin_global","gestor_brasil","torre_controle","operador_logistico");
  const canReport = hasRole("admin_global","gestor_brasil","torre_controle","motorista");

  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await api.get<Occurrence[]>("/erp/occurrences"); setRows(response.data); }
    finally { setLoading(false); }
  },[]);
  useEffect(() => { void load(); },[load]);

  function openCreate() { setEditing(null); setForm(emptyForm); setError(""); setModalOpen(true); }
  function openEdit(row: Occurrence) {
    setEditing(row);
    setForm({ route_id:String(row.route_id), category:row.category, severity:row.severity, description:row.description, status:row.status==="em_analise"?"em_tratamento":row.status, resolution:row.resolution||"", treatment_note:"" });
    api.get<History[]>(`/erp/occurrences/${row.id}/history`).then(response=>setHistory(response.data)).catch(()=>setHistory([]));
    setError(""); setModalOpen(true);
  }

  async function assume(row:Occurrence){try{await api.put(`/erp/occurrences/${row.id}`,{status:"em_tratamento",treatment_note:"Tratamento assumido pela operação."});await load()}catch(requestError:any){await appAlert(requestError?.response?.data?.detail||"Não foi possível assumir a tarefa.",{title:"Falha ao assumir ocorrência"})}}

  async function save(event: FormEvent) {
    event.preventDefault(); setError(""); setSaving(true);
    try {
      if (editing) {
        await api.put(`/erp/occurrences/${editing.id}`, {
          route_id:Number(form.route_id), category:form.category, severity:form.severity, description:form.description,
          ...(manager && { status:form.status, resolution:form.resolution||null, treatment_note:form.treatment_note||null }),
        });
      } else {
        let position: GeolocationPosition|null = null;
        try { position = await new Promise((resolve,reject) => navigator.geolocation.getCurrentPosition(resolve,reject,{timeout:5000})); } catch { /* localização opcional */ }
        await api.post("/erp/occurrences", { route_id:Number(form.route_id), category:form.category, severity:form.severity, description:form.description, latitude:position?.coords.latitude, longitude:position?.coords.longitude });
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
  function canChange(row: Occurrence) { return manager || (user?.role === "motorista" && row.status === "aberta"); }
  const filtered=rows.filter(row=>statusFilter==="todos"||(statusFilter==="pendentes"?!["finalizada","cancelada"].includes(row.status):row.status===statusFilter));
  const nextStatuses=(status:string)=>status==="aberta"?["aberta","em_tratamento","cancelada"]:status==="em_tratamento"||status==="em_analise"?["em_tratamento","resolvida","cancelada"]:status==="resolvida"?["resolvida","finalizada","em_tratamento"]:[status];

  return <div className="page-card">
    <div className="page-header"><div><h2>Tarefas de ocorrências</h2><p className="page-subtitle">Registre, atribua, resolva e finalize ocorrências da operação com histórico completo.</p></div>{canReport&&<button className="btn-primary" type="button" onClick={openCreate}>Nova ocorrência</button>}</div>
    <div className="occurrence-summary"><article><span>Abertas</span><strong>{rows.filter(r=>r.status==="aberta").length}</strong></article><article><span>Em tratamento</span><strong>{rows.filter(r=>["em_analise","em_tratamento"].includes(r.status)).length}</strong></article><article><span>Resolvidas</span><strong>{rows.filter(r=>r.status==="resolvida").length}</strong></article><article><span>Finalizadas</span><strong>{rows.filter(r=>r.status==="finalizada").length}</strong></article></div>
    <div className="occurrence-task-filter"><select className="input" value={statusFilter} onChange={event=>setStatusFilter(event.target.value)}><option value="pendentes">Tarefas pendentes</option><option value="todos">Todas as ocorrências</option><option value="aberta">Abertas</option><option value="em_tratamento">Em tratamento</option><option value="resolvida">Resolvidas</option><option value="finalizada">Finalizadas</option><option value="cancelada">Canceladas</option></select></div>
    <div className="table-scroll"><table className="data-table">
      <thead><tr><th>Data</th><th>Rota / veículo</th><th>Motorista</th><th>Categoria</th><th>Gravidade</th><th>Ocorrência / solução</th><th>Responsável</th><th>Status</th><th>Ações</th></tr></thead>
      <tbody>{filtered.map(row=><tr key={row.id}>
        <td>{new Date(row.created_at).toLocaleString("pt-BR")}</td><td><strong>{row.codigo_ut}</strong></td><td>{row.driver||"-"}</td>
        <td>{labels[row.category]||row.category}</td><td><span className={`stock-badge ${row.severity==="critica"||row.severity==="alta"?"low":"warning"}`}>{labels[row.severity]||row.severity}</span></td><td><strong>{row.description}</strong>{row.resolution&&<small>Solução: {row.resolution}</small>}</td><td>{row.assigned_to||"Não atribuída"}</td><td><span className={`stock-badge ${row.status==="finalizada"?"ok":row.status==="cancelada"?"low":"warning"}`}>{labels[row.status]||row.status}</span></td>
        <td>{canChange(row)&&<div className="occurrence-actions">{manager&&row.status==="aberta"&&<button className="btn-primary btn-mini" type="button" onClick={()=>void assume(row)}>Assumir</button>}<button className="btn-ghost btn-mini" type="button" onClick={()=>openEdit(row)}>{manager?"Tratar":"Editar"}</button>{user?.role==="motorista"&&row.status==="aberta"&&<button className="btn-danger btn-mini" type="button" onClick={()=>void remove(row)}>Excluir</button>}</div>}</td>
      </tr>)}
      {!loading&&filtered.length===0&&<tr><td colSpan={9} className="empty-state">Nenhuma tarefa encontrada neste filtro.</td></tr>}
      {loading&&<tr><td colSpan={9} className="empty-state">Carregando ocorrências...</td></tr>}</tbody>
    </table></div>
    {modalOpen&&<div className="modal-backdrop" onClick={()=>!saving&&setModalOpen(false)}><form className="modal-card occurrence-modal" onSubmit={save} onClick={event=>event.stopPropagation()}>
      <h3>{editing?"Editar ocorrência":"Nova ocorrência"}</h3><p>{editing?"Atualize os dados e o andamento da ocorrência.":"Informe os dados encontrados durante a rota."}</p>
      <div className="form-grid">
        <label className="field"><span>ID da rota</span><input className="input" required min="1" type="number" value={form.route_id} onChange={event=>setForm({...form,route_id:event.target.value})}/></label>
        <label className="field"><span>Categoria</span><select className="input" value={form.category} onChange={event=>setForm({...form,category:event.target.value})}><option value="avaria">Avaria</option><option value="acidente">Acidente</option><option value="atraso">Atraso</option><option value="seguranca">Segurança</option><option value="outros">Outros</option></select></label>
        <label className="field"><span>Gravidade</span><select className="input" value={form.severity} onChange={event=>setForm({...form,severity:event.target.value})}><option value="baixa">Baixa</option><option value="media">Média</option><option value="alta">Alta</option><option value="critica">Crítica</option></select></label>
        {editing&&manager&&<label className="field"><span>Próxima etapa</span><select className="input" value={form.status} onChange={event=>setForm({...form,status:event.target.value})}>{nextStatuses(editing.status).map(status=><option value={status} key={status}>{labels[status]}</option>)}</select></label>}
        <label className="field occurrence-wide"><span>Descrição</span><textarea className="input" required minLength={3} rows={4} value={form.description} onChange={event=>setForm({...form,description:event.target.value})}/></label>
        {editing&&manager&&<><label className="field occurrence-wide"><span>O que foi feito para resolver {(["resolvida","finalizada"].includes(form.status))&&"*"}</span><textarea className="input" required={["resolvida","finalizada"].includes(form.status)} minLength={5} rows={3} value={form.resolution} onChange={event=>setForm({...form,resolution:event.target.value})}/></label><label className="field occurrence-wide"><span>Nota desta movimentação</span><textarea className="input" rows={2} placeholder="Contato realizado, orientação dada, providência tomada..." value={form.treatment_note} onChange={event=>setForm({...form,treatment_note:event.target.value})}/></label></>}
      </div>
      {editing&&history.length>0&&<div className="occurrence-history"><h4>Histórico da tarefa</h4>{history.map(item=><div key={item.id}><span>{new Date(item.created_at).toLocaleString("pt-BR")}</span><strong>{labels[item.to_status]||item.to_status}</strong><small>{item.actor||"Sistema"}{item.description?` · ${item.description}`:""}</small></div>)}</div>}
      {error&&<p className="modal-error">{error}</p>}<div className="modal-actions"><button className="btn-primary" disabled={saving}>{saving?"Salvando...":editing?"Salvar alterações":"Registrar ocorrência"}</button><button className="btn-ghost" type="button" disabled={saving} onClick={()=>setModalOpen(false)}>Cancelar</button></div>
    </form></div>}
  </div>;
}

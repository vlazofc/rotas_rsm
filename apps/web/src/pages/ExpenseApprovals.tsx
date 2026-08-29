import { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import {appPrompt} from "../components/AppDialog";

interface Task { id:number; expense_date:string; reason:string; amount?:number|null; notes?:string|null; driver_name?:string|null; submitter_name?:string|null; vehicle_plate?:string|null; route_id?:number|null; proof_url?:string|null; proof_filename?:string|null; approval_status:string; }
const money=(value:number)=>new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(value||0);

export default function ExpenseApprovals(){
  const [tasks,setTasks]=useState<Task[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState("");
  const reload=()=>{setLoading(true);api.get<Task[]>("/expenses/approval-tasks").then(r=>setTasks(r.data)).catch(e=>setError(e?.response?.data?.detail||"Não foi possível carregar a fila.")).finally(()=>setLoading(false))};
  useEffect(reload,[]);
  const total=useMemo(()=>tasks.reduce((sum,row)=>sum+Number(row.amount||0),0),[tasks]);
  async function decide(task:Task,action:string){
    let comment="";
    if(action==="reject"||action==="request_adjustment"){
      comment=(await appPrompt(action==="reject"?"Informe por que esta despesa está sendo recusada.":"Descreva o que precisa ser corrigido antes de uma nova análise.",{title:action==="reject"?"Recusar despesa":"Solicitar ajuste",label:action==="reject"?"Motivo da recusa":"Ajustes necessários",required:true,confirmLabel:action==="reject"?"Recusar":"Enviar para ajuste"}))?.trim()||"";
      if(!comment)return;
    }else if(action==="approve"){const answer=await appPrompt("Registre uma observação para a aprovação, se necessário.",{title:"Aprovar despesa",label:"Observação (opcional)",confirmLabel:"Aprovar"});if(answer===null)return;comment=answer.trim()}
    try{await api.post(`/expenses/${task.id}/decision`,{action,comment:comment||null});reload()}catch(e:any){setError(e?.response?.data?.detail||"Não foi possível registrar a decisão.")}
  }
  return <div className="expense-approval-page">
    <div className="page-header"><div><h2>Tarefas financeiras</h2><p className="page-subtitle">Analise despesas enviadas por motoristas e demais setores antes de contabilizá-las.</p></div><div className="approval-summary"><span>{tasks.length} pendência(s)</span><strong>{money(total)}</strong></div></div>
    {error&&<p className="modal-error">{error}</p>}
    {loading?<p className="empty-state">Carregando solicitações...</p>:<div className="approval-board">
      {tasks.map(task=><article className={`approval-card ${task.approval_status}`} key={task.id}>
        <header><div><small>DESPESA #{task.id}</small><h3>{task.reason.replaceAll("_"," ")}</h3></div><span className="approval-status">{task.approval_status==="in_review"?"Em análise":"Pendente"}</span></header>
        <strong className="approval-amount">{money(Number(task.amount||0))}</strong>
        <dl><div><dt>Lançado por</dt><dd>{task.submitter_name||task.driver_name||"Administrativo"}</dd></div><div><dt>Data</dt><dd>{task.expense_date}</dd></div><div><dt>Placa / rota</dt><dd>{task.vehicle_plate||"—"}{task.route_id?` · Rota ${task.route_id}`:""}</dd></div></dl>
        {task.notes&&<p className="approval-note">{task.notes}</p>}
        {task.proof_url&&<a className="approval-proof" href={task.proof_url} target="_blank" rel="noreferrer">Abrir comprovante · {task.proof_filename||"arquivo"}</a>}
        <footer>{task.approval_status==="pending"&&<button className="btn-ghost" onClick={()=>decide(task,"start_review")}>Iniciar análise</button>}<button className="btn-primary" onClick={()=>decide(task,"approve")}>Aprovar</button><button className="btn-ghost" onClick={()=>decide(task,"request_adjustment")}>Pedir ajuste</button><button className="btn-mini danger" onClick={()=>decide(task,"reject")}>Recusar</button></footer>
      </article>)}
      {!tasks.length&&<div className="approval-empty"><strong>Fila concluída</strong><span>Não existem despesas aguardando decisão financeira.</span></div>}
    </div>}
  </div>
}

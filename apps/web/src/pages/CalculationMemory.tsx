import { useCallback, useEffect, useState } from "react";
import api from "../services/api";

interface Memory { id:number; period_start:string; period_end:string; formula_version:string; created_at:string; created:boolean; inputs:{receitas:unknown[];despesas_aprovadas:unknown[]}; results:{receita_total:string;despesa_total:string;resultado:string;margem_percentual:string;formula:string;despesas_por_categoria:Record<string,string>} }
const iso=(date:Date)=>date.toISOString().slice(0,10);
const money=(value:string)=>Number(value).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});

export default function CalculationMemory(){
  const now=new Date(),first=new Date(now.getFullYear(),now.getMonth(),1);
  const [start,setStart]=useState(iso(first)),[end,setEnd]=useState(iso(now)),[rows,setRows]=useState<Memory[]>([]),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
  const load=useCallback(()=>api.get<Memory[]>("/calculation-memory").then(r=>setRows(r.data)),[]);
  const save=useCallback(async(silent=false)=>{setBusy(true);try{const {data}=await api.post<Memory>("/calculation-memory/snapshot",{period_start:start,period_end:end});if(!silent)setMessage(data.created?"Nova versão registrada.":"Nenhuma alteração: a versão atual já estava guardada.");await load()}catch(e:any){if(!silent)setMessage(e?.response?.data?.detail||"Não foi possível gerar a memória.")}finally{setBusy(false)}},[start,end,load]);
  useEffect(()=>{load();save(true);const timer=window.setInterval(()=>save(true),60000);return()=>window.clearInterval(timer)},[load,save]);
  async function download(row:Memory){const {data}=await api.get(`/calculation-memory/${row.id}/xlsx`,{responseType:"blob"});const url=URL.createObjectURL(data);const a=document.createElement("a");a.href=url;a.download=`memoria-calculo-${row.period_start}-${row.period_end}-v${row.id}.xlsx`;a.click();URL.revokeObjectURL(url)}
  return <div className="page-card calculation-memory"><div className="page-header"><div><h2>Memória de cálculo</h2><p className="page-subtitle">Versões preservadas dos números que formam o resultado financeiro.</p></div><div className="calculation-memory-actions"><label className="field"><span>Início</span><input className="input" type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label className="field"><span>Fim</span><input className="input" type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><button className="btn-primary" disabled={busy} onClick={()=>save(false)}>{busy?"Registrando...":"Registrar agora"}</button></div></div>
    {message&&<p className="calculation-memory-message">{message}</p>}
    <div className="table-scroll"><table className="data-table"><thead><tr><th>Versão</th><th>Período</th><th>Receitas</th><th>Despesas aprovadas</th><th>Resultado</th><th>Margem</th><th>Lançamentos</th><th>Gerada em</th><th></th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>#{row.id}</td><td>{row.period_start} a {row.period_end}</td><td>{money(row.results.receita_total)}</td><td>{money(row.results.despesa_total)}</td><td className={Number(row.results.resultado)>=0?"positive-value":"negative-value"}>{money(row.results.resultado)}</td><td>{Number(row.results.margem_percentual).toLocaleString("pt-BR",{maximumFractionDigits:2})}%</td><td>{row.inputs.receitas.length} receitas · {row.inputs.despesas_aprovadas.length} despesas</td><td>{new Date(row.created_at).toLocaleString("pt-BR")}</td><td><button className="btn-mini" onClick={()=>download(row)}>Baixar Excel</button></td></tr>)}{!rows.length&&<tr><td colSpan={9} className="empty-state">A primeira versão será registrada automaticamente.</td></tr>}</tbody></table></div>
    <p className="calculation-memory-footnote">Registro automático a cada minuto quando houver alteração nos lançamentos. Fórmula v1.0: resultado = receitas - despesas aprovadas; margem = resultado / receitas × 100.</p>
  </div>
}

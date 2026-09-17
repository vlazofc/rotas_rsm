import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";

interface ProofReport {
  route_id: number;
  codigo_ut: string;
  route_date: string;
  stop_id: number;
  sequence: number;
  customer_name: string;
  status: string;
  proof_type: string;
  filename?: string | null;
  url?: string | null;
}

interface AuditReport {
  id: number;
  user_id?: number | null;
  user_name?: string | null;
  user_email?: string | null;
  action: string;
  entity: string;
  entity_id?: string | null;
  detail?: string | null;
  ip?: string | null;
  created_at: string;
}
interface ReportOverview {operation:{routes:number;completed:number;in_transit:number;cancelled:number;completion_rate:number;by_status:{label:string;value:number}[]};control:{occurrences_open:number;tasks_open:number;tasks_in_progress:number;tasks_returned:number};fleet:{maintenance_open:number;maintenance_overdue:number;tires_total:number;tires_attention:number;parts_low:number}}

function currentMonthRange() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  return { start, end };
}

export default function Reports() {
  const { t, i18n } = useTranslation();
  const initial = currentMonthRange();
  const [start, setStart] = useState(initial.start);
  const [end, setEnd] = useState(initial.end);
  const [activeTab, setActiveTab] = useState<"overview" | "operation" | "audit">("overview");
  const [overview,setOverview]=useState<ReportOverview|null>(null);
  const [proofs, setProofs] = useState<ProofReport[]>([]);
  const [auditRows, setAuditRows] = useState<AuditReport[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  function params() {
    return { start, end };
  }

  async function reload(tab = activeTab) {
    setError("");
    setLoading(true);
    setUpdatedAt(null);
    if(tab==="overview"){
      try{const response=await api.get<ReportOverview>("/reports/overview",{params:params()});setOverview(response.data);setUpdatedAt(new Date().toLocaleTimeString(i18n.language))}catch(err:any){setError(formatApiError(err?.response?.data?.detail)??"Não foi possível carregar o resumo gerencial.")}finally{setLoading(false)}
      return;
    }
    if (tab === "operation") {
      try {
        const response = await api.get<ProofReport[]>("/reports/proofs", { params: params() });
        setProofs(response.data);
        setUpdatedAt(new Date().toLocaleTimeString(i18n.language));
      } catch (err: any) {
        setError(formatApiError(err?.response?.data?.detail) ?? t("rep.err_load_operation"));
      } finally {
        setLoading(false);
      }
      return;
    }
    try {
      const response = await api.get<AuditReport[]>("/reports/audit", { params: params() });
      setAuditRows(response.data);
      setUpdatedAt(new Date().toLocaleTimeString(i18n.language));
    } catch (err: any) {
      setError(formatApiError(err?.response?.data?.detail) ?? t("rep.err_load_audit"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload(activeTab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  async function downloadBlob(path: string, filename: string, customParams: Record<string, string> | null = params()) {
    const { data } = await api.get(path, { params: customParams ?? undefined, responseType: "blob" });
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }


  return (
    <div>
      <div className="page-header">
        <div>
          <h2>{t("rep.title")}</h2>
          <p className="page-subtitle">{t("rep.subtitle")}</p>
        </div>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <section className="expense-toolbar card-panel">
        <label className="field">
          <span>{t("rep.start")}</span>
          <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="field">
          <span>{t("rep.end")}</span>
          <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
        <div className="expense-actions">
          <button type="button" className="btn-icon-label" disabled={loading} onClick={() => reload(activeTab)}>
            <IconSearch /> <span>{loading ? t("rep.searching") : t("rep.search")}</span>
          </button>
          {activeTab === "operation" && (
            <>
              <button className="btn-icon-label" onClick={() => downloadBlob("/reports/routes.xlsx", `viagens-${start}-${end}.xlsx`)}>
                <IconRoutes /> <span>{t("rep.trips")}</span>
              </button>
              <button className="btn-icon-label" onClick={() => downloadBlob("/reports/failures.xlsx", `falhas-${start}-${end}.xlsx`)}>
                <IconWarning /> <span>{t("rep.failures")}</span>
              </button>
              <button className="btn-icon-label" onClick={() => downloadBlob("/reports/proofs.zip", `comprovantes-${start}-${end}.zip`)}>
                <IconZip /> <span>{t("rep.images")}</span>
              </button>
            </>
          )}
          {activeTab === "audit" && (
            <button className="btn-icon-label" onClick={() => downloadBlob("/reports/audit.xlsx", `auditoria-${start}-${end}.xlsx`)}>
              <IconAudit /> <span>{t("rep.audit")}</span>
            </button>
          )}
        </div>
      </section>

      {updatedAt && !error && <p className="report-updated">{t("rep.updated_at", { time: updatedAt })}</p>}

      <div className="report-tabs" role="tablist" aria-label={t("rep.tabs_aria")}>
        <button type="button" className={activeTab === "overview" ? "active" : ""} onClick={() => setActiveTab("overview")}><IconDashboard/><span>Visão geral</span></button>
        <button type="button" className={activeTab === "operation" ? "active" : ""} onClick={() => setActiveTab("operation")}>
          <IconRoutes /> <span>{t("rep.tab_operation")}</span>
        </button>
        <button type="button" className={activeTab === "audit" ? "active" : ""} onClick={() => setActiveTab("audit")}>
          <IconAudit /> <span>{t("rep.tab_audit")}</span>
        </button>
      </div>

      {activeTab === "overview" && overview ? <Overview data={overview}/> : activeTab === "audit" ? (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("rep.table_datetime")}</th>
                <th>{t("audit.action")}</th>
                <th>{t("audit.entity")}</th>
                <th>{t("audit.user")}</th>
                <th>{t("audit.detail")}</th>
              </tr>
            </thead>
            <tbody>
              {auditRows.map((row) => (
                <tr key={row.id}>
                  <td>{formatDateTime(row.created_at, i18n.language)}</td>
                  <td><code>{row.action}</code></td>
                  <td>{row.entity}{row.entity_id ? ` #${row.entity_id}` : ""}</td>
                  <td>{row.user_name ?? row.user_email ?? t("audit.system_user")}</td>
                  <td>{row.detail ?? "-"}</td>
                </tr>
              ))}
              {auditRows.length === 0 && (
                <tr>
                  <td colSpan={5} className="empty-state">{t("rep.audit_empty")}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("rep.table_date")}</th>
                <th>{t("rep.table_route")}</th>
                <th>{t("rep.table_stop")}</th>
                <th>{t("rep.table_customer")}</th>
                <th>{t("rep.table_type")}</th>
                <th>{t("rep.table_file")}</th>
              </tr>
            </thead>
            <tbody>
              {proofs.map((proof) => (
                <tr key={`${proof.stop_id}-${proof.proof_type}`}>
                  <td>{proof.route_date}</td>
                  <td>{proof.codigo_ut}</td>
                  <td>{proof.sequence}</td>
                  <td>{proof.customer_name}</td>
                  <td>{proof.proof_type === "entrega" ? t("rep.proof_delivery") : t("rep.proof_return")}</td>
                  <td>
                    {proof.url ? (
                      <a href={proof.url} target="_blank" rel="noreferrer">{proof.filename ?? t("rep.open")}</a>
                    ) : "-"}
                  </td>
                </tr>
              ))}
              {proofs.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty-state">{t("rep.proofs_empty")}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Overview({data}:{data:ReportOverview}){
 return <div className="report-overview">
  <section className="report-kpis">
   <article><span>Rotas no período</span><strong>{data.operation.routes}</strong><small>{data.operation.completion_rate}% concluídas</small></article>
   <article><span>Rotas finalizadas</span><strong>{data.operation.completed}</strong><small>Concluídas no período</small></article>
   <article><span>Rotas em trânsito</span><strong>{data.operation.in_transit}</strong><small>Em acompanhamento</small></article>
   <article><span>Ocorrências abertas</span><strong>{data.control.occurrences_open}</strong><small>Exigem acompanhamento</small></article>
  </section>
  <div className="report-grid-2">
   <ReportPanel title="Situação das rotas" subtitle={`${data.operation.completion_rate}% das rotas finalizadas`}><Bars rows={data.operation.by_status}/></ReportPanel>
   <ReportPanel title="Tarefas e ocorrências" subtitle="Pendências que exigem acompanhamento"><div className="report-mini-kpis"><div><strong>{data.control.tasks_open}</strong><span>Tarefas abertas</span></div><div><strong>{data.control.tasks_in_progress}</strong><span>Em tratamento</span></div><div><strong>{data.control.tasks_returned}</strong><span>Devolvidas</span></div><div><strong>{data.control.occurrences_open}</strong><span>Ocorrências abertas</span></div></div></ReportPanel>
  </div>
  <section className="report-fleet-strip"><div><span>Manutenções abertas</span><strong>{data.fleet.maintenance_open}</strong></div><div className={data.fleet.maintenance_overdue?"warn":""}><span>Manutenções vencidas</span><strong>{data.fleet.maintenance_overdue}</strong></div><div><span>Pneus monitorados</span><strong>{data.fleet.tires_total}</strong></div><div className={data.fleet.tires_attention?"warn":""}><span>Pneus em atenção</span><strong>{data.fleet.tires_attention}</strong></div><div className={data.fleet.parts_low?"warn":""}><span>Itens abaixo do mínimo</span><strong>{data.fleet.parts_low}</strong></div></section>
 </div>
}
function ReportPanel({title,subtitle,children}:{title:string;subtitle:string;children:React.ReactNode}){return <section className="card-panel report-panel"><div className="section-head"><div><h3>{title}</h3><p>{subtitle}</p></div></div>{children}</section>}
function Bars({rows}:{rows:{label:string;value:number}[]}){const max=Math.max(...rows.map(row=>row.value),1);return <div className="report-bars">{rows.slice(0,7).map(row=><div key={row.label}><span>{humanize(row.label)}</span><div><i style={{width:`${Math.max(3,row.value/max*100)}%`}}></i></div><strong>{row.value.toLocaleString("pt-BR")}</strong></div>)}{rows.length===0&&<p className="empty-state">Sem dados no período.</p>}</div>}
function humanize(value:string){return value.replaceAll("_"," ").replace(/(^|\s)\S/g,char=>char.toUpperCase())}

function IconDashboard(){return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>}

function formatDateTime(value: string, locale = "pt-BR") {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(locale);
}

function formatApiError(detail: unknown) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: any) => item?.msg ?? String(item)).join("; ");
  return String(detail);
}

function IconSearch() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function IconExcel() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="16" y2="17" />
      <line x1="10" y1="9" x2="14" y2="9" />
    </svg>
  );
}

function IconRoutes() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function IconZip() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function IconDownload() {
  return <IconZip />;
}

function IconWarning() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function IconAudit() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <path d="M9 15l2 2 4-5" />
    </svg>
  );
}

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import { useAuth } from "../context/AuthContext";

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

interface ExpenseReport {
  id: number;
  expense_date: string;
  driver_name?: string | null;
  vehicle_plate?: string | null;
  reason: string;
  amount?: number | null;
  route_id?: number | null;
  notes?: string | null;
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

const REASON_VALUES = ["combustivel", "manutencao", "limpeza", "outros"];

function currentMonthRange() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  return { start, end };
}

export default function Reports() {
  const { t, i18n } = useTranslation();
  const { hasRole } = useAuth();
  const initial = currentMonthRange();
  const [start, setStart] = useState(initial.start);
  const [end, setEnd] = useState(initial.end);
  const [activeTab, setActiveTab] = useState<"operation" | "expenses" | "audit">("operation");
  const [proofs, setProofs] = useState<ProofReport[]>([]);
  const [expenses, setExpenses] = useState<ExpenseReport[]>([]);
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
    if (tab === "expenses") {
      try {
        const response = await api.get<ExpenseReport[]>("/reports/expenses", { params: params() });
        setExpenses(response.data);
        setUpdatedAt(new Date().toLocaleTimeString(i18n.language));
      } catch (err: any) {
        setError(formatApiError(err?.response?.data?.detail) ?? t("rep.err_load_expenses"));
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

  const expenseTotal = expenses.reduce((sum, expense) => sum + Number(expense.amount ?? 0), 0);
  const expenseMonth = start.slice(0, 7);
  const [year, monthNumber] = expenseMonth.split("-");
  const canDownloadExpenseBatch = hasRole("admin_global");

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
          {activeTab === "expenses" && (
            <>
              <button className="btn-icon-label" title={t("rep.export_expenses")} onClick={() => downloadBlob("/expenses/export.xlsx", `despesas-${expenseMonth}.xlsx`, { month: expenseMonth })}>
                <IconExcel /> <span>{t("rep.btn_expenses")}</span>
              </button>
              <button className="btn-icon-label" title={t("rep.export_routes")} onClick={() => downloadBlob("/reports/routes.xlsx", `relatorio-rotas-${expenseMonth}.xlsx`, { start, end })}>
                <IconRoutes /> <span>{t("rep.btn_routes")}</span>
              </button>
              <button className="btn-icon-label" onClick={() => downloadBlob("/reports/expenses.zip", `comprovantes-despesas-${start}-${end}.zip`)}>
                <IconZip /> <span>{t("rep.proofs")}</span>
              </button>
              {canDownloadExpenseBatch && (
                <button className="btn-icon-label" title={t("rep.download_batch")} onClick={() => downloadBlob(`/expenses/batch/${year}/${monthNumber}.zip`, `despesas-${expenseMonth}.zip`, null)}>
                  <IconDownload /> <span>{t("rep.btn_batch")}</span>
                </button>
              )}
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
        <button type="button" className={activeTab === "operation" ? "active" : ""} onClick={() => setActiveTab("operation")}>
          <IconRoutes /> <span>{t("rep.tab_operation")}</span>
        </button>
        <button type="button" className={activeTab === "expenses" ? "active" : ""} onClick={() => setActiveTab("expenses")}>
          <IconExcel /> <span>{t("rep.tab_expenses")}</span>
        </button>
        <button type="button" className={activeTab === "audit" ? "active" : ""} onClick={() => setActiveTab("audit")}>
          <IconAudit /> <span>{t("rep.tab_audit")}</span>
        </button>
      </div>

      {activeTab === "expenses" ? (
        <section className="card-panel" style={{ marginBottom: 16 }}>
          <div className="section-head">
            <div>
              <h3>{t("rep.expenses_title")}</h3>
              <p>{t("rep.expenses_count", { count: expenses.length })}</p>
            </div>
            <strong>{formatCurrency(expenseTotal, i18n.language)}</strong>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("rep.table_date")}</th>
                  <th>{t("rep.table_driver")}</th>
                  <th>{t("rep.table_plate")}</th>
                  <th>{t("rep.table_reason")}</th>
                  <th>{t("rep.table_amount")}</th>
                  <th>{t("rep.table_route")}</th>
                  <th>{t("rep.table_proof")}</th>
                </tr>
              </thead>
              <tbody>
                {expenses.map((expense) => (
                  <tr key={expense.id}>
                    <td>{expense.expense_date}</td>
                    <td>{expense.driver_name ?? "-"}</td>
                    <td>{expense.vehicle_plate ?? "-"}</td>
                    <td>{REASON_VALUES.includes(expense.reason) ? t(`exp.reasons.${expense.reason}`) : expense.reason}</td>
                    <td>{formatCurrency(Number(expense.amount ?? 0), i18n.language)}</td>
                    <td>{expense.route_id ?? "-"}</td>
                    <td>
                      {expense.url ? (
                        <a href={expense.url} target="_blank" rel="noreferrer">{expense.filename ?? t("rep.open")}</a>
                      ) : "-"}
                    </td>
                  </tr>
                ))}
                {expenses.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty-state">{t("rep.expenses_empty")}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : activeTab === "audit" ? (
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

function formatCurrency(value: number, locale = "pt-BR") {
  return new Intl.NumberFormat(locale, { style: "currency", currency: locale === "pt-BR" ? "BRL" : "EUR" }).format(value);
}

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

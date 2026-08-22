import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import { useAuth } from "../context/AuthContext";

interface Driver {
  id: number;
  name: string;
  active: boolean;
}
interface Vehicle {
  id: number;
  plate: string;
  description?: string | null;
  active: boolean;
}

interface Expense {
  id: number;
  driver_id: number;
  driver_name?: string | null;
  vehicle_id?: number | null;
  vehicle_plate?: string | null;
  route_id?: number | null;
  expense_date: string;
  reason: string;
  amount?: number | string | null;
  notes?: string | null;
  proof_filename?: string | null;
  proof_url?: string | null;
  odometer_km?: number | null;
  odometer_photo_filename?: string | null;
  odometer_photo_url?: string | null;
  created_at: string;
}

const REASON_VALUES = ["combustivel", "manutencao", "limpeza", "outros"];

function currentMonth() {
  return new Date().toISOString().slice(0, 7);
}

export default function Expenses() {
  const { t, i18n } = useTranslation();
  const { hasRole } = useAuth();
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [month, setMonth] = useState(currentMonth());
  const [editing, setEditing] = useState<Expense | "new" | null>(null);
  const [form, setForm] = useState({
    expense_date: new Date().toISOString().slice(0, 10),
    reason: "combustivel",
    amount: "",
    notes: "",
    route_id: "",
    driver_id: "",
    vehicle_id: "",
    odometer_km: "",
    proof: null as File | null,
    odometer_photo: null as File | null,
  });
  const [error, setError] = useState("");
  const isFuel = form.reason === "combustivel";

  const canManageDrivers = hasRole("admin_global", "gestor_brasil", "gestor_financeiro");
  const canDownloadBatch = hasRole("admin_global");
  const canExportRoutes = hasRole("admin_global", "gestor_brasil", "gestor_financeiro", "auditor");

  function reload() {
    api.get<Expense[]>("/expenses", { params: { month } })
      .then((r) => setExpenses(r.data))
      .catch(() => setExpenses([]));
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  useEffect(() => {
    if (canManageDrivers) {
      api.get<Driver[]>("/drivers").then((r) => setDrivers(r.data)).catch(() => setDrivers([]));
    }
  }, [canManageDrivers]);

  useEffect(() => {
    api.get<Vehicle[]>("/vehicles").then((r) => setVehicles(r.data)).catch(() => setVehicles([]));
  }, []);

  const total = useMemo(
    () => expenses.reduce((acc, item) => acc + Number(item.amount ?? 0), 0),
    [expenses],
  );

  function startNew() {
    setError("");
    setForm({
      expense_date: new Date().toISOString().slice(0, 10),
      reason: "combustivel",
      amount: "",
      notes: "",
      route_id: "",
      driver_id: "",
      vehicle_id: "",
      odometer_km: "",
      proof: null,
      odometer_photo: null,
    });
    setEditing("new");
  }

  function startEdit(expense: Expense) {
    setError("");
    setForm({
      expense_date: expense.expense_date,
      reason: expense.reason,
      amount: expense.amount ? String(expense.amount) : "",
      notes: expense.notes ?? "",
      route_id: expense.route_id ? String(expense.route_id) : "",
      driver_id: String(expense.driver_id),
      vehicle_id: expense.vehicle_id ? String(expense.vehicle_id) : "",
      odometer_km: expense.odometer_km ? String(expense.odometer_km) : "",
      proof: null,
      odometer_photo: null,
    });
    setEditing(expense);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (editing === "new" && !form.proof) {
      setError(t("exp.err_no_proof"));
      return;
    }
    if (editing === "new" && !form.vehicle_id) {
      setError(t("exp.err_no_plate"));
      return;
    }
    if (isFuel && editing === "new" && !form.odometer_km) {
      setError(t("exp.err_no_odometer"));
      return;
    }
    if (isFuel && editing === "new" && !form.odometer_photo) {
      setError(t("exp.err_no_odometer_photo"));
      return;
    }
    const payload = new FormData();
    payload.set("expense_date", form.expense_date);
    payload.set("reason", form.reason);
    if (form.amount) payload.set("amount", form.amount);
    if (form.notes.trim()) payload.set("notes", form.notes.trim());
    if (form.route_id) payload.set("route_id", form.route_id);
    if (form.driver_id && canManageDrivers) payload.set("driver_id", form.driver_id);
    if (form.vehicle_id) payload.set("vehicle_id", form.vehicle_id);
    if (form.odometer_km) payload.set("odometer_km", form.odometer_km);
    if (form.proof) payload.set("proof", form.proof);
    if (form.odometer_photo) payload.set("odometer_photo", form.odometer_photo);
    try {
      if (editing === "new") {
        await api.post("/expenses", payload);
      } else if (editing) {
        await api.put(`/expenses/${editing.id}`, payload);
      }
      setEditing(null);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("exp.err_save"));
    }
  }

  async function remove(expense: Expense) {
    if (!confirm(t("exp.delete_confirm", { id: expense.id }) ?? "")) return;
    try {
      await api.delete(`/expenses/${expense.id}`);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("exp.err_delete"));
    }
  }

  async function downloadBlob(path: string, filename: string, params?: Record<string, string>) {
    const { data } = await api.get(path, { params, responseType: "blob" });
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  const [year, monthNumber] = month.split("-");
  const startDate = `${month}-01`;
  const endDate = new Date(Number(year), Number(monthNumber), 0).toISOString().slice(0, 10);

  return (
    <div>
      <div className="page-header">
        <div>
          <h2>{t("exp.title")}</h2>
          <p className="page-subtitle">{t("exp.subtitle")}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 11, color: "#64748b", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("exp.total_month")}</div>
            <strong style={{ fontSize: 22, color: "#059669" }}>{formatCurrency(total, i18n.language)}</strong>
          </div>
          <button className="btn-primary btn-add" onClick={startNew}><span className="btn-add-symbol">+</span><span>{t("exp.new")}</span></button>
        </div>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <section className="expense-toolbar card-panel">
        <label className="field">
          <span>{t("exp.month")}</span>
          <input className="input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        </label>
        <div className="expense-actions">
          <button className="btn-icon-label" title={t("exp.export_expenses")} onClick={() => downloadBlob("/expenses/export.xlsx", `despesas-${month}.xlsx`, { month })}>
            <IconExcel /> <span>{t("exp.btn_expenses")}</span>
          </button>
          {canExportRoutes && (
            <button className="btn-icon-label" title={t("exp.export_routes")} onClick={() => downloadBlob("/reports/routes.xlsx", `relatorio-rotas-${month}.xlsx`, { start: startDate, end: endDate })}>
              <IconRoutes /> <span>{t("exp.btn_routes")}</span>
            </button>
          )}
          {canDownloadBatch && (
            <button className="btn-icon-label" title={t("exp.download_batch")} onClick={() => downloadBlob(`/expenses/batch/${year}/${monthNumber}.zip`, `despesas-${month}.zip`)}>
              <IconZip /> <span>{t("exp.btn_batch")}</span>
            </button>
          )}
        </div>
      </section>

      {editing && (
        <form className="card-panel form-panel" onSubmit={save}>
          <h3 style={{ marginTop: 0 }}>{editing === "new" ? t("exp.new") : t("exp.edit")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("exp.date")}</span>
              <input className="input" type="date" required value={form.expense_date} onChange={(e) => setForm({ ...form, expense_date: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("exp.reason")}</span>
              <select className="input" required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}>
                {REASON_VALUES.map((value) => <option key={value} value={value}>{t(`exp.reasons.${value}`)}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t("exp.amount")}</span>
              <input className="input" type="number" min="0" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("exp.route")}</span>
              <input className="input" type="number" min="1" value={form.route_id} onChange={(e) => setForm({ ...form, route_id: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("exp.vehicle_plate")}</span>
              <select className="input" required={editing === "new"} value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}>
                <option value="">{t("exp.select_plate")}</option>
                {vehicles.filter((vehicle) => vehicle.active).map((vehicle) => (
                  <option key={vehicle.id} value={vehicle.id}>
                    {vehicle.plate}{vehicle.description ? ` · ${vehicle.description}` : ""}
                  </option>
                ))}
              </select>
            </label>
            {canManageDrivers && (
              <label className="field">
                <span>{t("exp.driver")}</span>
                <select className="input" value={form.driver_id} onChange={(e) => setForm({ ...form, driver_id: e.target.value })}>
                  <option value="">{t("exp.use_linked_driver")}</option>
                  {drivers.filter((d) => d.active).map((driver) => <option key={driver.id} value={driver.id}>{driver.name}</option>)}
                </select>
              </label>
            )}
            <div className="field">
              <span>{t("exp.proof")}</span>
              <UploadField
                accept="image/*,application/pdf"
                capture="environment"
                required={editing === "new"}
                file={form.proof}
                label={t("common.attach_proof")}
                selectedLabel={t("common.selected_file")}
                onChange={(file) => setForm({ ...form, proof: file })}
              />
            </div>
            {isFuel && (
              <>
                <label className="field">
                  <span>{t("exp.odometer_km")}</span>
                  <input
                    className="input"
                    type="number"
                    min="0"
                    step="1"
                    required={editing === "new"}
                    value={form.odometer_km}
                    onChange={(e) => setForm({ ...form, odometer_km: e.target.value })}
                  />
                </label>
                <div className="field">
                  <span>{t("exp.odometer_photo")}</span>
                  <UploadField
                    accept="image/*"
                    capture="environment"
                    required={editing === "new"}
                    file={form.odometer_photo}
                    label={t("common.attach_proof")}
                    selectedLabel={t("common.selected_file")}
                    onChange={(file) => setForm({ ...form, odometer_photo: file })}
                  />
                </div>
              </>
            )}
          </div>
          <label className="field" style={{ marginTop: 10 }}>
            <span>{t("exp.notes")}</span>
            <textarea className="input" style={{ minHeight: 74, resize: "vertical" }} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </label>
          <div className="modal-actions">
            <button className="btn-primary" type="submit">{t("common.save")}</button>
            <button className="btn-ghost" type="button" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form>
      )}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("exp.date")}</th>
              <th>{t("exp.driver")}</th>
              <th>{t("exp.table_plate")}</th>
              <th>{t("exp.reason")}</th>
              <th>{t("exp.amount")}</th>
              <th>{t("exp.table_odometer")}</th>
              <th>{t("exp.route")}</th>
              <th>{t("exp.proof")}</th>
              <th>{t("users.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {expenses.map((expense) => (
              <tr key={expense.id}>
                <td>{expense.expense_date}</td>
                <td>{expense.driver_name ?? "-"}</td>
                <td>{expense.vehicle_plate ?? "-"}</td>
                <td>{REASON_VALUES.includes(expense.reason) ? t(`exp.reasons.${expense.reason}`) : expense.reason}</td>
                <td>{expense.amount ? formatCurrency(Number(expense.amount), i18n.language) : "-"}</td>
                <td>
                  {expense.odometer_km != null ? `${expense.odometer_km} km` : "-"}
                  {expense.odometer_photo_url && (
                    <> · <a href={expense.odometer_photo_url} target="_blank" rel="noreferrer">{t("exp.photo_link")}</a></>
                  )}
                </td>
                <td>{expense.route_id ?? "-"}</td>
                <td>
                  {expense.proof_url ? <a href={expense.proof_url} target="_blank" rel="noreferrer">{expense.proof_filename ?? t("exp.open")}</a> : "-"}
                </td>
                <td>
                  <button className="btn-mini" onClick={() => startEdit(expense)}>{t("users.edit")}</button>
                  <button className="btn-mini danger" onClick={() => remove(expense)}>{t("common.delete")}</button>
                </td>
              </tr>
            ))}
            {expenses.length === 0 && (
              <tr>
                <td colSpan={9} className="empty-state">{t("exp.empty")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatCurrency(value: number, locale = "pt-BR") {
  return new Intl.NumberFormat(locale, { style: "currency", currency: locale === "pt-BR" ? "BRL" : "EUR" }).format(value);
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

function UploadField({
  accept,
  capture,
  required,
  file,
  label,
  selectedLabel,
  onChange,
}: {
  accept: string;
  capture?: "environment";
  required?: boolean;
  file: File | null;
  label: string;
  selectedLabel: string;
  onChange: (file: File | null) => void;
}) {
  return (
    <label className="upload-pill">
      <input
        type="file"
        accept={accept}
        capture={capture}
        required={required}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      <span className="upload-pill-icon"><UploadIcon /></span>
      <span>{file ? `${selectedLabel}: ${file.name}` : label}</span>
    </label>
  );
}

function UploadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v12" />
      <path d="m7 8 5-5 5 5" />
      <path d="M5 21h14" />
    </svg>
  );
}

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";

interface RevenueItem {
  id: number;
  branch_id: number;
  route_id?: number | null;
  route_codigo_ut?: string | null;
  revenue_date: string;
  amount: number | string;
  notes?: string | null;
  source: string;
  created_at: string;
}

function currentMonth() {
  return new Date().toISOString().slice(0, 7);
}

export default function Revenues() {
  const { t, i18n } = useTranslation();
  const [revenues, setRevenues] = useState<RevenueItem[]>([]);
  const [month, setMonth] = useState(currentMonth());
  const [editing, setEditing] = useState<RevenueItem | "new" | null>(null);
  const [form, setForm] = useState({
    revenue_date: new Date().toISOString().slice(0, 10),
    amount: "",
    notes: "",
    route_id: "",
  });
  const [error, setError] = useState("");

  function reload() {
    api.get<RevenueItem[]>("/revenues", { params: { month } })
      .then((r) => setRevenues(r.data))
      .catch(() => setRevenues([]));
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  const total = useMemo(
    () => revenues.reduce((acc, item) => acc + Number(item.amount ?? 0), 0),
    [revenues],
  );

  function startNew() {
    setError("");
    setForm({ revenue_date: new Date().toISOString().slice(0, 10), amount: "", notes: "", route_id: "" });
    setEditing("new");
  }

  function startEdit(revenue: RevenueItem) {
    setError("");
    setForm({
      revenue_date: revenue.revenue_date,
      amount: revenue.amount ? String(revenue.amount) : "",
      notes: revenue.notes ?? "",
      route_id: revenue.route_id ? String(revenue.route_id) : "",
    });
    setEditing(revenue);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!form.amount) {
      setError(t("rev.err_no_amount"));
      return;
    }
    const payload = {
      revenue_date: form.revenue_date,
      amount: form.amount,
      notes: form.notes.trim() || null,
      route_id: form.route_id ? Number(form.route_id) : null,
    };
    try {
      if (editing === "new") {
        await api.post("/revenues", payload);
      } else if (editing) {
        await api.put(`/revenues/${editing.id}`, payload);
      }
      setEditing(null);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("rev.err_save"));
    }
  }

  async function remove(revenue: RevenueItem) {
    if (!confirm(t("rev.delete_confirm", { id: revenue.id }) ?? "")) return;
    try {
      await api.delete(`/revenues/${revenue.id}`);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("rev.err_delete"));
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h2>{t("rev.title")}</h2>
          <p className="page-subtitle">{t("rev.subtitle")}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 11, color: "#64748b", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("rev.total_month")}</div>
            <strong style={{ fontSize: 22, color: "#059669" }}>{formatCurrency(total, i18n.language)}</strong>
          </div>
          <button className="btn-primary btn-add" onClick={startNew}><span className="btn-add-symbol">+</span><span>{t("rev.new")}</span></button>
        </div>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <section className="expense-toolbar card-panel">
        <label className="field">
          <span>{t("exp.month")}</span>
          <input className="input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        </label>
      </section>

      {editing !== null && (
        <form onSubmit={save} className="card-panel" style={{ marginBottom: 16 }}>
          <div className="form-grid">
            <label className="field">
              <span>{t("rev.date")}</span>
              <input className="input" type="date" required value={form.revenue_date}
                onChange={(e) => setForm({ ...form, revenue_date: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("rev.amount")}</span>
              <input className="input" type="number" step="0.01" min="0" required value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </label>
            <label className="field">
              <span>{t("rev.route_id")}</span>
              <input className="input" type="number" value={form.route_id}
                placeholder={t("rev.route_id_placeholder")}
                onChange={(e) => setForm({ ...form, route_id: e.target.value })} />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>{t("rev.notes")}</span>
              <input className="input" value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </label>
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button type="submit" className="btn-primary">{t("common.save")}</button>
            <button type="button" className="btn-mini" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form>
      )}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("rev.date")}</th>
              <th>{t("rev.amount")}</th>
              <th>{t("rev.route")}</th>
              <th>{t("rev.notes")}</th>
              <th>{t("users.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {revenues.map((revenue) => (
              <tr key={revenue.id}>
                <td>{revenue.revenue_date}</td>
                <td>{formatCurrency(Number(revenue.amount ?? 0), i18n.language)}</td>
                <td>{revenue.route_codigo_ut ?? revenue.route_id ?? "-"}</td>
                <td>{revenue.notes ?? "-"}</td>
                <td>
                  <button className="btn-mini" onClick={() => startEdit(revenue)}>{t("users.edit")}</button>
                  <button className="btn-mini danger" onClick={() => remove(revenue)}>{t("common.delete")}</button>
                </td>
              </tr>
            ))}
            {revenues.length === 0 && (
              <tr>
                <td colSpan={5} className="empty-state">{t("rev.empty")}</td>
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

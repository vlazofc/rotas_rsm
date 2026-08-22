import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";

interface BalanceteRow {
  route_id: number | null;
  codigo_ut: string | null;
  route_date: string | null;
  revenue: number;
  expense: number;
  balance: number;
}
interface Balancete {
  month: string;
  revenue_total: number;
  expense_total: number;
  balance: number;
  by_route: BalanceteRow[];
}

function currentMonth() {
  return new Date().toISOString().slice(0, 7);
}

export default function Financeiro() {
  const { t, i18n } = useTranslation();
  const [month, setMonth] = useState(currentMonth());
  const [data, setData] = useState<Balancete | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Balancete>("/reports/balancete", { params: { month } })
      .then((r) => { setData(r.data); setError(""); })
      .catch((err) => { setData(null); setError(err?.response?.data?.detail ?? t("fin.err_load")); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  return (
    <div>
      <div className="page-header">
        <div>
          <h2>{t("fin.title")}</h2>
          <p className="page-subtitle">{t("fin.subtitle")}</p>
        </div>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <section className="expense-toolbar card-panel">
        <label className="field">
          <span>{t("exp.month")}</span>
          <input className="input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        </label>
      </section>

      {data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 16 }}>
            <div className="card-panel">
              <div style={{ fontSize: 11, color: "#64748b", fontWeight: 500, textTransform: "uppercase" }}>{t("fin.revenue_total")}</div>
              <strong style={{ fontSize: 26, color: "#059669" }}>{formatCurrency(data.revenue_total, i18n.language)}</strong>
            </div>
            <div className="card-panel">
              <div style={{ fontSize: 11, color: "#64748b", fontWeight: 500, textTransform: "uppercase" }}>{t("fin.expense_total")}</div>
              <strong style={{ fontSize: 26, color: "#dc2626" }}>{formatCurrency(data.expense_total, i18n.language)}</strong>
            </div>
            <div className="card-panel">
              <div style={{ fontSize: 11, color: "#64748b", fontWeight: 500, textTransform: "uppercase" }}>{t("fin.balance")}</div>
              <strong style={{ fontSize: 26, color: data.balance >= 0 ? "#059669" : "#dc2626" }}>{formatCurrency(data.balance, i18n.language)}</strong>
            </div>
          </div>

          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("fin.route")}</th>
                  <th>{t("fin.route_date")}</th>
                  <th>{t("rev.amount")}</th>
                  <th>{t("fin.expense_total")}</th>
                  <th>{t("fin.balance")}</th>
                </tr>
              </thead>
              <tbody>
                {data.by_route.map((row, idx) => (
                  <tr key={row.route_id ?? `no-route-${idx}`}>
                    <td>{row.codigo_ut ?? t("fin.no_route")}</td>
                    <td>{row.route_date ?? "-"}</td>
                    <td>{formatCurrency(row.revenue, i18n.language)}</td>
                    <td>{formatCurrency(row.expense, i18n.language)}</td>
                    <td style={{ color: row.balance >= 0 ? "#059669" : "#dc2626", fontWeight: 700 }}>
                      {formatCurrency(row.balance, i18n.language)}
                    </td>
                  </tr>
                ))}
                {data.by_route.length === 0 && (
                  <tr>
                    <td colSpan={5} className="empty-state">{t("fin.empty")}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function formatCurrency(value: number, locale = "pt-BR") {
  return new Intl.NumberFormat(locale, { style: "currency", currency: locale === "pt-BR" ? "BRL" : "EUR" }).format(value);
}

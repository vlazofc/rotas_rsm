import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";

interface AuditRow {
  id: number;
  user_id: number | null;
  user_name: string | null;
  user_email: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  detail: string | null;
  created_at: string;
}

export default function Audit() {
  const { t, i18n } = useTranslation();
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<AuditRow[]>("/audit")
      .then((r) => setRows(r.data))
      .catch(() => setError(t("audit.load_error")))
      .finally(() => setLoading(false));
  }, [t]);

  function formatDate(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(i18n.language, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(date);
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>{t("audit.title")}</h2>
          <p style={{ marginTop: 0, color: "#64748b" }}>{t("audit.subtitle")}</p>
        </div>
        <span style={{ color: "#64748b", fontSize: 13 }}>{t("audit.total", { count: rows.length })}</span>
      </div>

      {loading && <p>{t("common.loading")}</p>}
      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      {!loading && !error && rows.length === 0 && (
        <div style={emptyBox}>{t("audit.empty")}</div>
      )}
      {!loading && !error && rows.length > 0 && (
        <table style={table}>
          <thead>
            <tr style={{ background: "#f8fafc", textAlign: "left" }}>
              <th style={th}>{t("audit.date")}</th>
              <th style={th}>{t("audit.action")}</th>
              <th style={th}>{t("audit.entity")}</th>
              <th style={th}>{t("audit.user")}</th>
              <th style={th}>{t("audit.detail")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} style={{ borderTop: "1px solid #eef2f7" }}>
                <td style={td}>{formatDate(row.created_at)}</td>
                <td style={td}><code style={code}>{row.action}</code></td>
                <td style={td}>{row.entity}{row.entity_id ? ` #${row.entity_id}` : ""}</td>
                <td style={td}>{row.user_name ?? row.user_email ?? t("audit.system_user")}</td>
                <td style={{ ...td, color: "#475569" }}>{row.detail ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const table: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  background: "#fff",
  borderRadius: 8,
  overflow: "hidden",
  boxShadow: "0 1px 6px rgba(15,23,42,.06)",
};
const th: React.CSSProperties = { padding: 10, fontSize: 13, color: "#475569" };
const td: React.CSSProperties = { padding: 10, fontSize: 14, verticalAlign: "top" };
const code: React.CSSProperties = { background: "#eef2ff", color: "#3730a3", padding: "2px 6px", borderRadius: 6 };
const emptyBox: React.CSSProperties = { background: "#fff", borderRadius: 8, padding: 18, color: "#64748b" };

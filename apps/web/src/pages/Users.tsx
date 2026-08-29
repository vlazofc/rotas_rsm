import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import {appPrompt} from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";

interface UserRow {
  id: number; email: string; name: string; role: string;
  branch_id: number | null; active: boolean;
  blocked: boolean; status_reason?: string | null;
  department?: string | null; subgroup?: string | null; permissions?: string[];
}
interface RoleOption {
  value: string;
  label?: string;
  description: string;
  permissions?: string[];
  order?: number;
}
interface BranchOption {
  id: number;
  name: string;
}

const EMPTY = { email: "", name: "", role: "motorista", password: "", branch_id: "", department: "", subgroup: "", permissions: [] as string[] };
const ACCESS_OPTIONS = [
  ["finance.view", "Visualizar todo o financeiro (despesas, receitas, saldos e dashboard)"],
  ["finance.expense.create", "Lançar despesas administrativas"],
  ["finance.expense.approve", "Analisar e aprovar despesas de outros setores"],
  ["finance.revenue.manage", "Lançar e alterar receitas por rota"],
  ["finance.accounts.manage", "Gerenciar contas a pagar e receber"],
] as const;
const ROLE_ORDER = [
  "admin_global",
  "auditor",
  "gestor_brasil",
  "gestor_financeiro",
  "motorista",
  "operador_logistico",
  "torre_controle",
];

export default function Users() {
  const { t } = useTranslation();
  const { user: me, hasRole } = useAuth();
  const isAdminGlobal = hasRole("admin_global");
  const [users, setUsers] = useState<UserRow[]>([]);
  const [roles, setRoles] = useState<RoleOption[]>([]);
  const [branches, setBranches] = useState<BranchOption[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState("");

  const reload = () => api.get("/users").then((r) => setUsers(r.data)).catch(() => setUsers([]));

  useEffect(() => {
    reload();
    api.get("/users/roles")
      .then((r) => setRoles(orderRoles(r.data)))
      .catch(() => setRoles(orderRoles(ROLE_ORDER.map((value) => ({ value, description: "" })))));
    api.get("/branches").then((r) => setBranches(r.data)).catch(() => setBranches([]));
  }, []);

  const branchName = (branchId: number | null) =>
    branches.find((b) => b.id === branchId)?.name ?? "—";

  function startNew() {
    setError("");
    const defaultBranch = me?.branch_id ?? branches[0]?.id ?? "";
    setForm({ ...EMPTY, branch_id: defaultBranch ? String(defaultBranch) : "" });
    setEditing("new");
  }

  function startEdit(u: UserRow) {
    setError("");
    setForm({ email: u.email, name: u.name, role: u.role, password: "", branch_id: u.branch_id ? String(u.branch_id) : "", department: u.department || "", subgroup: u.subgroup || "", permissions: u.permissions || [] });
    setEditing(u.id);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      if (editing === "new") {
        await api.post("/users", {
          email: form.email, name: form.name, role: form.role,
          password: form.password || null,
          department: form.department || null, subgroup: form.subgroup || null, permissions: form.permissions,
          ...(isAdminGlobal && form.branch_id ? { branch_id: Number(form.branch_id) } : {}),
        });
      } else if (typeof editing === "number") {
        await api.put(`/users/${editing}`, {
          name: form.name, role: form.role, department: form.department || null,
          subgroup: form.subgroup || null, permissions: form.permissions,
          ...(isAdminGlobal && form.branch_id ? { branch_id: Number(form.branch_id) } : {}),
        });
      }
      setEditing(null);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("users.save_error"));
    }
  }

  async function changeStatus(u:UserRow,action:"activate"|"deactivate"|"block"|"unblock") {
    try {
      let reason="";if(["deactivate","block"].includes(action)){const value=await appPrompt(`Informe o motivo para ${action==="block"?"bloquear":"desativar"} ${u.name}.`,{title:action==="block"?"Bloquear usuário":"Desativar usuário",label:"Motivo obrigatório",required:true,confirmLabel:action==="block"?"Bloquear":"Desativar"});if(value===null)return;reason=value}
      await api.post(`/users/${u.id}/status`, { action, reason:reason||null });
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("users.save_error"));
    }
  }

  async function resetPassword(u: UserRow) {
    const pwd = await appPrompt(t("users.reset_prompt", { name: u.name }) ?? "",{title:"Redefinir senha",label:"Nova senha",required:true,confirmLabel:"Redefinir senha"});
    if (!pwd) return;
    if (pwd.length < 8) { setError(t("users.password_short")); return; }
    try {
      await api.post(`/users/${u.id}/reset-password`, { new_password: pwd });
      setError("");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("users.save_error"));
    }
  }

  const roleLabel = (value: string) => {
    const profile = roles.find((r) => r.value === value);
    return profile?.label || t(`roles.${value}`, { defaultValue: value });
  };

  return (
    <div>
      <div style={pageHeader}>
        <div>
          <h2 style={{ margin: 0 }}>{t("users.title")}</h2>
          <p style={subtitle}>{t("users.subtitle")}</p>
        </div>
        <button style={primary} onClick={startNew}>{t("users.new")}</button>
      </div>

      {error && <p style={{ color: "#c00" }}>{error}</p>}

      {editing !== null && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
        <form onSubmit={save} className="modal-card driver-modal" onClick={(event) => event.stopPropagation()}>
          <h3 style={{ marginTop: 0 }}>{editing === "new" ? t("users.new") : t("users.edit")}</h3>
          <div style={grid}>
            <label style={field}>
              <span>{t("users.email")}</span>
              <input style={input} type="email" required value={form.email}
                disabled={editing !== "new"}
                onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </label>
            <label style={field}>
              <span>{t("users.name")}</span>
              <input style={input} required value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label style={field}>
              <span>{t("users.role")}</span>
              <select style={input} value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}>
                {roles.map((r) => (
                  <option key={r.value} value={r.value}>{roleLabel(r.value)}</option>
                ))}
              </select>
            </label>
            <label style={field}>
              <span>Setor</span>
              <input style={input} value={form.department} placeholder="Ex.: Financeiro"
                onChange={(e) => setForm({ ...form, department: e.target.value })} />
            </label>
            <label style={field}>
              <span>Subgrupo</span>
              <input style={input} value={form.subgroup} placeholder="Ex.: Contas a pagar"
                onChange={(e) => setForm({ ...form, subgroup: e.target.value })} />
            </label>
            {editing === "new" && (
              <label style={field}>
                <span>{t("users.password")}</span>
                <input style={input} type="password" minLength={8} value={form.password}
                  placeholder={t("users.password_hint") ?? ""}
                  onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </label>
            )}
            {isAdminGlobal && (
              <label style={field}>
                <span>{t("users.branch")}</span>
                <select style={input} value={form.branch_id}
                  onChange={(e) => setForm({ ...form, branch_id: e.target.value })}>
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <fieldset style={{ ...field, marginTop: 14, padding: 12, border: "1px solid #cbd5e1", borderRadius: 8 }}>
            <legend>Acessos liberados pelo gestor</legend>
            {ACCESS_OPTIONS.map(([code, label]) => <label key={code} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={form.permissions.includes(code)} onChange={(event) => setForm({ ...form, permissions: event.target.checked ? [...form.permissions, code] : form.permissions.filter(item => item !== code) })} />
              <span>{label}</span>
            </label>)}
          </fieldset>
          <div style={{ marginTop: 12 }}>
            <button type="submit" style={primary}>{t("common.save")}</button>
            <button type="button" style={ghost} onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form>
        </div>
      )}

      <table style={table}>
        <thead>
          <tr style={{ background: "#f8fafc", textAlign: "left" }}>
            <th style={th}>{t("users.name")}</th>
            <th style={th}>{t("users.email")}</th>
            <th style={th}>{t("users.role")}</th>
            <th style={th}>Setor / subgrupo</th>
            {isAdminGlobal && <th style={th}>{t("users.branch")}</th>}
            <th style={th}>{t("users.active")}</th>
            <th style={th}>{t("users.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ borderTop: "1px solid #eef2f7", opacity: u.active ? 1 : 0.65 }}>
              <td style={td}>{u.name}</td>
              <td style={td}>{u.email}</td>
              <td style={td}>{roleLabel(u.role)}</td>
              <td style={td}>{[u.department, u.subgroup].filter(Boolean).join(" / ") || "—"}</td>
              {isAdminGlobal && <td style={td}>{branchName(u.branch_id)}</td>}
              <td style={td}><span title={u.status_reason||""}>{u.blocked?"Bloqueado":u.active?"Ativo":"Inativo"}</span></td>
              <td style={td}>
                <button style={mini} onClick={() => startEdit(u)}>{t("users.edit")}</button>
                {u.active?<><button style={mini} onClick={()=>void changeStatus(u,"deactivate")} disabled={u.id===me?.id}>Desativar</button><button style={{...mini,color:"#b42318"}} onClick={()=>void changeStatus(u,"block")} disabled={u.id===me?.id}>Bloquear</button></>:<button style={mini} onClick={()=>void changeStatus(u,u.blocked?"unblock":"activate")}>{u.blocked?"Desbloquear":"Ativar"}</button>}
                <button style={mini} onClick={() => resetPassword(u)}>{t("users.reset_password")}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function orderRoles(values: RoleOption[]) {
  const rank = new Map(ROLE_ORDER.map((value, index) => [value, index]));
  return [...values].sort((a, b) => (rank.get(a.value) ?? 999) - (rank.get(b.value) ?? 999));
}

const pageHeader: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 16 };
const subtitle: React.CSSProperties = { color: "#64748b", margin: "6px 0 0", fontSize: 14 };
const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse", background: "#fff", borderRadius: 12, overflow: "hidden", marginTop: 16, border: "1px solid #e2e8f0", boxShadow: "0 8px 22px rgba(15,23,42,.04)" };
const th: React.CSSProperties = { padding: 10, fontSize: 13, color: "#475569" };
const td: React.CSSProperties = { padding: 10, fontSize: 14 };
const mini: React.CSSProperties = { marginRight: 4, marginBottom: 4, padding: "4px 8px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#fff", cursor: "pointer" };
const primary: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "none", background: "#0a58ca", color: "#fff", cursor: "pointer", marginRight: 8 };
const ghost: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer" };
const panel: React.CSSProperties = { background: "#fff", borderRadius: 12, padding: 18, boxShadow: "0 8px 22px rgba(15,23,42,.04)", border: "1px solid #e2e8f0", marginTop: 12 };
const grid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))", gap: 12 };
const field: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4, fontSize: 13, color: "#475569" };
const input: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 14 };

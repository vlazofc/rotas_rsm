import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import api from "../services/api";
import { useAuth } from "../context/AuthContext";
import { useBranding } from "../context/BrandingContext";
import { LANGUAGES } from "../i18n";

interface Branch { id: number; name: string; locale: string; active: boolean; }
interface TenantItem {
  id: number; name: string; slug: string; country: string; active: boolean;
  feature_ocr: boolean; feature_sharepoint_sync: boolean; feature_financeiro: boolean; feature_rastreamento: boolean;
  feature_route_optimization: boolean; feature_km_calculation: boolean;
  billing_plan?: string | null; billing_amount?: number | string | null; billing_due_day?: number | null;
  billing_last_payment_date?: string | null; billing_status?: string | null; billing_next_due_date?: string | null;
}
interface Driver { id: number; branch_id: number; name: string; document?: string; phone?: string; carrier?: string; active: boolean; }
interface Vehicle { id: number; branch_id: number; plate: string; description?: string; vehicle_type_id?: number | null; temperature_controlled: boolean; active: boolean; }
interface VehicleType { id: number; code: string; label: string; label_pt_br?: string | null; sort_order: number; active: boolean; }

interface Reason { id: number; code: string; label: string; label_pt_br?: string | null; sort_order: number; active: boolean; }
interface RoleProfile {
  value: string;
  label: string;
  description?: string;
  permissions: string[];
  sort_order: number;
  active: boolean;
  system: boolean;
}

type Tab = "profiles" | "branches" | "drivers" | "vehicles" | "vehicle_types" | "reasons" | "branding" | "tenants" | "carriers" | "customers";
interface CarrierItem { id: number; tenant_id: number | null; name: string; document: string | null; active: boolean; }
interface CustomerItem { id: number; tenant_id: number; name: string; document: string | null; email: string | null; phone: string | null; address: string | null; active: boolean; }

export default function Config() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams();
  const { hasRole } = useAuth();
  const routeTab = params.tab as Tab | undefined;

  const tabs: { key: Tab; label: string }[] = [
    { key: "profiles", label: t("config.tabs.profiles") },
    { key: "branches", label: t("config.tabs.branches") },
    { key: "drivers", label: t("config.tabs.drivers") },
    { key: "vehicles", label: t("config.tabs.vehicles") },
    { key: "vehicle_types", label: t("config.tabs.vehicle_types") },
    { key: "reasons", label: t("config.tabs.reasons") },
    { key: "carriers", label: t("config.tabs.carriers") },
    { key: "customers", label: t("config.tabs.customers") },
    ...(hasRole("admin_global") ? [{ key: "branding" as Tab, label: t("config.tabs.branding") }] : []),
    ...(hasRole("admin_global") ? [{ key: "tenants" as Tab, label: t("config.tabs.tenants") }] : []),
  ];
  const tab = tabs.some((tb) => tb.key === routeTab) ? routeTab! : "drivers";

  return (
    <div>
      <div style={pageHeader}>
        <div>
          <h2 style={{ margin: 0 }}>{t("config.title")}</h2>
          <p style={subtitle}>{t("config.subtitle")}</p>
        </div>
      </div>
      <div style={tabsWrap}>
        {tabs.map((tb) => (
          <button key={tb.key} onClick={() => navigate(`/config/${tb.key}`)}
            style={{ ...tabBtn, ...(tab === tb.key ? tabActive : {}) }}>
            {tb.label}
          </button>
        ))}
      </div>
      {tab === "profiles" && <ProfilesTab />}
      {tab === "branches" && <BranchesTab />}
      {tab === "drivers" && <DriversTab />}
      {tab === "vehicles" && <VehiclesTab />}
      {tab === "vehicle_types" && <VehicleTypesTab />}
      {tab === "reasons" && <ReasonsTab />}
      {tab === "carriers" && <CarriersTab />}
      {tab === "customers" && <CustomersTab />}
      {tab === "branding" && <BrandingTab />}
      {tab === "tenants" && <TenantsTab />}
    </div>
  );
}

// ---------------------------------------------------------------- Perfis
function ProfilesTab() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin_global");
  const empty = { value: "", label: "", description: "", permissions: "", sort_order: "100", active: true };
  const [rows, setRows] = useState<RoleProfile[]>([]);
  const [editing, setEditing] = useState<"new" | string | null>(null);
  const [form, setForm] = useState({ ...empty });
  const [error, setError] = useState("");

  const reload = () => api.get("/users/role-profiles").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);

  function startNew() {
    setError("");
    setForm({ ...empty });
    setEditing("new");
  }
  function startEdit(role: RoleProfile) {
    setError("");
    setForm({
      value: role.value,
      label: role.label,
      description: role.description ?? "",
      permissions: role.permissions.join("\n"),
      sort_order: String(role.sort_order),
      active: role.active,
    });
    setEditing(role.value);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const payload = {
      value: form.value.trim(),
      label: form.label.trim(),
      description: form.description.trim() || null,
      permissions: form.permissions.split("\n").map((p) => p.trim()).filter(Boolean),
      sort_order: Number(form.sort_order),
      active: form.active,
    };
    try {
      if (editing === "new") await api.post("/users/role-profiles", payload);
      else if (typeof editing === "string") await api.put(`/users/role-profiles/${editing}`, payload);
      setEditing(null);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("config.save_error"));
    }
  }
  async function toggle(role: RoleProfile) {
    try {
      await api.put(`/users/role-profiles/${role.value}`, { active: !role.active });
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("config.save_error"));
    }
  }
  async function remove(role: RoleProfile) {
    if (!window.confirm(t("config.delete_confirm", { name: role.label }) ?? "")) return;
    try {
      await api.delete(`/users/role-profiles/${role.value}`);
      reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("config.save_error"));
    }
  }

  return (
    <Section title={t("config.tabs.profiles")} onNew={canEdit ? startNew : undefined} newLabel={t("config.new_profile")} error={error}>
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.profile_code")}>
              <input style={input} required value={form.value} disabled={editing !== "new"}
                onChange={(e) => setForm({ ...form, value: e.target.value })} />
            </Field>
            <Field label={t("config.profile_label")}>
              <input style={input} required value={form.label}
                onChange={(e) => setForm({ ...form, label: e.target.value })} />
            </Field>
            <Field label={t("config.sort_order")}>
              <input style={input} type="number" value={form.sort_order}
                onChange={(e) => setForm({ ...form, sort_order: e.target.value })} />
            </Field>
            <Field label={t("users.active")}>
              <input type="checkbox" checked={form.active}
                onChange={(e) => setForm({ ...form, active: e.target.checked })} />
            </Field>
          </div>
          <div style={{ ...grid, marginTop: 12 }}>
            <Field label={t("config.description")}>
              <textarea style={textarea} value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <Field label={t("config.permissions")}>
              <textarea style={textarea} value={form.permissions}
                placeholder={t("config.permissions_hint") ?? ""}
                onChange={(e) => setForm({ ...form, permissions: e.target.value })} />
            </Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.profile_label"), t("config.profile_code"), t("config.description"), t("config.permissions"), t("users.active"), t("users.actions")]}>
        {rows.map((role) => (
          <tr key={role.value} style={{ ...rowStyle, opacity: role.active ? 1 : 0.5 }}>
            <td style={td}><strong>{role.label}</strong>{role.system && <div style={muted}>{t("config.system_profile")}</div>}</td>
            <td style={td}>{role.value}</td>
            <td style={td}>{role.description ?? "—"}</td>
            <td style={td}>{role.permissions.length ? role.permissions.join("; ") : "—"}</td>
            <td style={td}>{role.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}>
              {canEdit && <button style={mini} onClick={() => startEdit(role)}>{t("users.edit")}</button>}
              {canEdit && <button style={mini} onClick={() => toggle(role)}>{role.active ? t("users.deactivate") : t("users.activate")}</button>}
              {canEdit && !role.system && <button style={mini} onClick={() => remove(role)}>{t("common.delete")}</button>}
            </td>
          </tr>
        ))}
      </Table>
    </Section>
  );
}

// ---------------------------------------------------------------- Motivos de falha
function ReasonsTab() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canDelete = hasRole("admin_global");
  const [rows, setRows] = useState<Reason[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [form, setForm] = useState({ label: "", label_pt_br: "", sort_order: "100" });
  const [error, setError] = useState("");

  const reload = () => api.get("/failure-reasons").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm({ label: "", label_pt_br: "", sort_order: "100" }); setEditing("new"); }
  function startEdit(r: Reason) { setError(""); setForm({ label: r.label, label_pt_br: r.label_pt_br ?? "", sort_order: String(r.sort_order) }); setEditing(r.id); }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const body = { label: form.label, label_pt_br: form.label_pt_br || null, sort_order: Number(form.sort_order) || 100 };
    try {
      if (editing === "new") await api.post("/failure-reasons", body);
      else if (typeof editing === "number") await api.put(`/failure-reasons/${editing}`, body);
      setEditing(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function toggle(r: Reason) {
    try { await api.put(`/failure-reasons/${r.id}`, { active: !r.active }); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function remove(r: Reason) {
    if (!window.confirm(t("config.delete_confirm", { name: r.label }) ?? "")) return;
    try { await api.delete(`/failure-reasons/${r.id}`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  return (
    <Section title={t("config.tabs.reasons")} onNew={startNew} newLabel={t("config.new_reason")} error={error}>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>{t("config.reasons_help")}</p>
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.reason_label_pt")}><input style={input} required value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })} /></Field>
            <Field label={t("config.reason_label_br")}><input style={input} value={form.label_pt_br}
              placeholder={form.label}
              onChange={(e) => setForm({ ...form, label_pt_br: e.target.value })} /></Field>
            <Field label={t("config.sort_order")}><input type="number" style={input} value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: e.target.value })} /></Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.reason_label_pt"), t("config.reason_label_br"), t("config.sort_order"), t("users.active"), t("users.actions")]}>
        {rows.map((r) => (
          <tr key={r.id} style={{ ...rowStyle, opacity: r.active ? 1 : 0.5 }}>
            <td style={td}>{r.label}</td>
            <td style={td}>{r.label_pt_br || r.label}</td>
            <td style={td}>{r.sort_order}</td>
            <td style={td}>{r.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}>
              <button style={mini} onClick={() => startEdit(r)}>{t("users.edit")}</button>
              <button style={mini} onClick={() => toggle(r)}>{r.active ? t("users.deactivate") : t("users.activate")}</button>
              {canDelete && <button style={mini} onClick={() => remove(r)}>{t("common.delete")}</button>}
            </td>
          </tr>
        ))}
      </Table>
    </Section>
  );
}

// ---------------------------------------------------------------- Filiais
function BranchesTab() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin_global"); // só admin global administra filiais
  const [rows, setRows] = useState<Branch[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [form, setForm] = useState({ name: "", locale: "pt-BR" });
  const [error, setError] = useState("");

  const reload = () => api.get("/branches").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm({ name: "", locale: "pt-BR" }); setEditing("new"); }
  function startEdit(b: Branch) { setError(""); setForm({ name: b.name, locale: b.locale }); setEditing(b.id); }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    try {
      if (editing === "new") await api.post("/branches", { name: form.name, locale: form.locale });
      else if (typeof editing === "number") await api.put(`/branches/${editing}`, form);
      setEditing(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function toggle(b: Branch) {
    try { await api.put(`/branches/${b.id}`, { active: !b.active }); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function remove(b: Branch) {
    if (!window.confirm(t("config.delete_confirm", { name: b.name }) ?? "")) return;
    try { await api.delete(`/branches/${b.id}`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  return (
    <Section title={t("config.tabs.branches")} onNew={canEdit ? startNew : undefined} newLabel={t("config.new_branch")} error={error}>
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.name")}><input style={input} required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label={t("config.locale")}>
              <select style={input} value={form.locale} onChange={(e) => setForm({ ...form, locale: e.target.value })}>
                <option value="pt-BR">pt-BR</option>
              </select>
            </Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.name"), t("config.locale"), t("users.active"), t("users.actions")]}>
        {rows.map((b) => (
          <tr key={b.id} style={{ ...rowStyle, opacity: b.active ? 1 : 0.5 }}>
            <td style={td}>{b.name}</td>
            <td style={td}>{b.locale}</td>
            <td style={td}>{b.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}>
              {canEdit && <button style={mini} onClick={() => startEdit(b)}>{t("users.edit")}</button>}
              {canEdit && <button style={mini} onClick={() => toggle(b)}>{b.active ? t("users.deactivate") : t("users.activate")}</button>}
              {canEdit && <button style={mini} onClick={() => remove(b)}>{t("common.delete")}</button>}
            </td>
          </tr>
        ))}
      </Table>
    </Section>
  );
}

// ---------------------------------------------------------------- Motoristas
function DriversTab() {
  const { t } = useTranslation();
  const { user, hasRole } = useAuth();
  const canDelete = hasRole("admin_global");
  const [rows, setRows] = useState<Driver[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const empty = { name: "", document: "", phone: "", carrier: "" };
  const [form, setForm] = useState({ ...empty });
  const [error, setError] = useState("");

  const reload = () => api.get("/drivers").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm({ ...empty }); setEditing("new"); }
  function startEdit(d: Driver) {
    setError("");
    setForm({ name: d.name, document: d.document ?? "", phone: d.phone ?? "", carrier: d.carrier ?? "" });
    setEditing(d.id);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    try {
      if (editing === "new") await api.post("/drivers", { branch_id: user?.branch_id ?? 1, ...form });
      else if (typeof editing === "number") await api.put(`/drivers/${editing}`, form);
      setEditing(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function toggle(d: Driver) {
    try { await api.put(`/drivers/${d.id}`, { active: !d.active }); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function remove(d: Driver) {
    if (!window.confirm(t("config.delete_confirm", { name: d.name }) ?? "")) return;
    try { await api.delete(`/drivers/${d.id}`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  return (
    <Section title={t("config.tabs.drivers")} onNew={startNew} newLabel={t("config.new_driver")} error={error}>
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.name")}><input style={input} required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label={t("config.document")}><input style={input} value={form.document}
              onChange={(e) => setForm({ ...form, document: e.target.value })} /></Field>
            <Field label={t("config.phone")}><input style={input} value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
            <Field label={t("config.carrier")}><input style={input} value={form.carrier}
              onChange={(e) => setForm({ ...form, carrier: e.target.value })} /></Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.name"), t("config.document"), t("config.phone"), t("config.carrier"), t("users.active"), t("users.actions")]}>
        {rows.map((d) => (
          <tr key={d.id} style={{ ...rowStyle, opacity: d.active ? 1 : 0.5 }}>
            <td style={td}>{d.name}</td>
            <td style={td}>{d.document ?? "—"}</td>
            <td style={td}>{d.phone ?? "—"}</td>
            <td style={td}>{d.carrier ?? "—"}</td>
            <td style={td}>{d.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}>
              <button style={mini} onClick={() => startEdit(d)}>{t("users.edit")}</button>
              <button style={mini} onClick={() => toggle(d)}>{d.active ? t("users.deactivate") : t("users.activate")}</button>
              {canDelete && <button style={mini} onClick={() => remove(d)}>{t("common.delete")}</button>}
            </td>
          </tr>
        ))}
      </Table>
    </Section>
  );
}

// ---------------------------------------------------------------- Veículos
function VehiclesTab() {
  const { t, i18n } = useTranslation();
  const { user, hasRole } = useAuth();
  const canDelete = hasRole("admin_global");
  const [rows, setRows] = useState<Vehicle[]>([]);
  const [types, setTypes] = useState<VehicleType[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const empty = { plate: "", description: "", vehicle_type_id: "", temperature_controlled: false };
  const [form, setForm] = useState({ ...empty });
  const [error, setError] = useState("");

  const localizedTypeLabel = (vt: VehicleType) => (i18n.language === "pt-BR" && vt.label_pt_br) ? vt.label_pt_br : vt.label;
  const typeLabelById = (id?: number | null) => {
    const vt = types.find((t2) => t2.id === id);
    return vt ? localizedTypeLabel(vt) : "—";
  };

  const reload = () => {
    api.get("/vehicles").then((r) => setRows(r.data)).catch(() => setRows([]));
    api.get("/vehicle-types", { params: { only_active: true } }).then((r) => setTypes(r.data)).catch(() => setTypes([]));
  };
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm({ ...empty }); setEditing("new"); }
  function startEdit(v: Vehicle) {
    setError("");
    setForm({ plate: v.plate, description: v.description ?? "", vehicle_type_id: v.vehicle_type_id ? String(v.vehicle_type_id) : "", temperature_controlled: v.temperature_controlled });
    setEditing(v.id);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const payload = { ...form, vehicle_type_id: form.vehicle_type_id ? Number(form.vehicle_type_id) : null };
    try {
      if (editing === "new") await api.post("/vehicles", { branch_id: user?.branch_id ?? 1, ...payload });
      else if (typeof editing === "number") await api.put(`/vehicles/${editing}`, payload);
      setEditing(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function toggle(v: Vehicle) {
    try { await api.put(`/vehicles/${v.id}`, { active: !v.active }); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function remove(v: Vehicle) {
    if (!window.confirm(t("config.delete_confirm", { name: v.plate }) ?? "")) return;
    try { await api.delete(`/vehicles/${v.id}`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  return (
    <Section title={t("config.tabs.vehicles")} onNew={startNew} newLabel={t("config.new_vehicle")} error={error}>
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.plate")}><input style={input} required value={form.plate}
              onChange={(e) => setForm({ ...form, plate: e.target.value })} /></Field>
            <Field label={t("config.description")}><input style={input} value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
            <Field label={t("config.vehicle_type")}>
              <select style={input} value={form.vehicle_type_id}
                onChange={(e) => setForm({ ...form, vehicle_type_id: e.target.value })}>
                <option value="">—</option>
                {types.map((vt) => (
                  <option key={vt.id} value={vt.id}>{localizedTypeLabel(vt)}</option>
                ))}
              </select>
            </Field>
            <Field label={t("config.temperature")}>
              <input type="checkbox" checked={form.temperature_controlled}
                onChange={(e) => setForm({ ...form, temperature_controlled: e.target.checked })} />
            </Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.plate"), t("config.description"), t("config.vehicle_type"), t("config.temperature"), t("users.active"), t("users.actions")]}>
        {rows.map((v) => (
          <tr key={v.id} style={{ ...rowStyle, opacity: v.active ? 1 : 0.5 }}>
            <td style={td}>{v.plate}</td>
            <td style={td}>{v.description ?? "—"}</td>
            <td style={td}>{typeLabelById(v.vehicle_type_id)}</td>
            <td style={td}>{v.temperature_controlled ? t("common.yes") : t("common.no")}</td>
            <td style={td}>{v.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}>
              <button style={mini} onClick={() => startEdit(v)}>{t("users.edit")}</button>
              <button style={mini} onClick={() => toggle(v)}>{v.active ? t("users.deactivate") : t("users.activate")}</button>
              {canDelete && <button style={mini} onClick={() => remove(v)}>{t("common.delete")}</button>}
            </td>
          </tr>
        ))}
      </Table>
    </Section>
  );
}

// ---------------------------------------------------------- Tipologias de veículo
function VehicleTypesTab() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canDelete = hasRole("admin_global");
  const [rows, setRows] = useState<VehicleType[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [form, setForm] = useState({ label: "", label_pt_br: "", sort_order: "100" });
  const [error, setError] = useState("");

  const reload = () => api.get("/vehicle-types").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm({ label: "", label_pt_br: "", sort_order: "100" }); setEditing("new"); }
  function startEdit(vt: VehicleType) { setError(""); setForm({ label: vt.label, label_pt_br: vt.label_pt_br ?? "", sort_order: String(vt.sort_order) }); setEditing(vt.id); }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const body = { label: form.label, label_pt_br: form.label_pt_br || null, sort_order: Number(form.sort_order) || 100 };
    try {
      if (editing === "new") await api.post("/vehicle-types", body);
      else if (typeof editing === "number") await api.put(`/vehicle-types/${editing}`, body);
      setEditing(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function toggle(vt: VehicleType) {
    try { await api.put(`/vehicle-types/${vt.id}`, { active: !vt.active }); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function remove(vt: VehicleType) {
    if (!window.confirm(t("config.delete_confirm", { name: vt.label }) ?? "")) return;
    try { await api.delete(`/vehicle-types/${vt.id}`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  return (
    <Section title={t("config.tabs.vehicle_types")} onNew={startNew} newLabel={t("config.new_vehicle_type")} error={error}>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>{t("config.vehicle_types_help")}</p>
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.vehicle_type_label_pt")}><input style={input} required value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })} /></Field>
            <Field label={t("config.vehicle_type_label_br")}><input style={input} value={form.label_pt_br}
              placeholder={form.label}
              onChange={(e) => setForm({ ...form, label_pt_br: e.target.value })} /></Field>
            <Field label={t("config.sort_order")}><input type="number" style={input} value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: e.target.value })} /></Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.vehicle_type_label_pt"), t("config.vehicle_type_label_br"), t("config.sort_order"), t("users.active"), t("users.actions")]}>
        {rows.map((vt) => (
          <tr key={vt.id} style={{ ...rowStyle, opacity: vt.active ? 1 : 0.5 }}>
            <td style={td}>{vt.label}</td>
            <td style={td}>{vt.label_pt_br || vt.label}</td>
            <td style={td}>{vt.sort_order}</td>
            <td style={td}>{vt.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}>
              <button style={mini} onClick={() => startEdit(vt)}>{t("users.edit")}</button>
              <button style={mini} onClick={() => toggle(vt)}>{vt.active ? t("users.deactivate") : t("users.activate")}</button>
              {canDelete && <button style={mini} onClick={() => remove(vt)}>{t("common.delete")}</button>}
            </td>
          </tr>
        ))}
      </Table>
    </Section>
  );
}

// ---------------------------------------------------------- Transportadoras
function CarriersTab() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canDelete = hasRole("admin_global");
  const [rows, setRows] = useState<CarrierItem[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [form, setForm] = useState({ name: "", document: "" });
  const [error, setError] = useState("");

  const reload = () => api.get("/carriers").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm({ name: "", document: "" }); setEditing("new"); }
  function startEdit(c: CarrierItem) { setError(""); setForm({ name: c.name, document: c.document ?? "" }); setEditing(c.id); }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const body = { name: form.name, document: form.document || null };
    try {
      if (editing === "new") await api.post("/carriers", body);
      else if (typeof editing === "number") await api.put(`/carriers/${editing}`, body);
      setEditing(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function toggle(c: CarrierItem) {
    try { await api.put(`/carriers/${c.id}`, { active: !c.active }); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function remove(c: CarrierItem) {
    if (!window.confirm(t("config.delete_confirm", { name: c.name }) ?? "")) return;
    try { await api.delete(`/carriers/${c.id}`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  return (
    <Section title={t("config.tabs.carriers")} onNew={startNew} newLabel={t("config.new_carrier")} error={error}>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>{t("config.carriers_help")}</p>
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.name")}><input style={input} required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label={t("config.carrier_document")}><input style={input} value={form.document}
              onChange={(e) => setForm({ ...form, document: e.target.value })} /></Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.name"), t("config.carrier_document"), t("users.active"), t("users.actions")]}>
        {rows.map((c) => (
          <tr key={c.id} style={{ ...rowStyle, opacity: c.active ? 1 : 0.5 }}>
            <td style={td}>{c.name}</td>
            <td style={td}>{c.document || "—"}</td>
            <td style={td}>{c.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}>
              <button style={mini} onClick={() => startEdit(c)}>{t("users.edit")}</button>
              <button style={mini} onClick={() => toggle(c)}>{c.active ? t("users.deactivate") : t("users.activate")}</button>
              {canDelete && <button style={mini} onClick={() => remove(c)}>{t("common.delete")}</button>}
            </td>
          </tr>
        ))}
      </Table>
    </Section>
  );
}

// ---------------------------------------------------------- Clientes finais
function CustomersTab() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<CustomerItem[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const empty = { name: "", document: "", email: "", phone: "", address: "" };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState("");

  const reload = () => api.get("/customers").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);
  function startNew() { setError(""); setForm(empty); setEditing("new"); }
  function startEdit(c: CustomerItem) {
    setError("");
    setForm({ name: c.name, document: c.document ?? "", email: c.email ?? "", phone: c.phone ?? "", address: c.address ?? "" });
    setEditing(c.id);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const body = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value.trim() || null]));
    try {
      if (editing === "new") await api.post("/customers", body);
      else if (typeof editing === "number") await api.put(`/customers/${editing}`, body);
      setEditing(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function toggle(c: CustomerItem) {
    try { await api.put(`/customers/${c.id}`, { active: !c.active }); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  return (
    <Section title={t("config.tabs.customers")} onNew={startNew} newLabel={t("config.new_customer")} error={error}>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>{t("config.customers_help")}</p>
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.name")}><input style={input} required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label={t("config.document")}><input style={input} value={form.document} onChange={(e) => setForm({ ...form, document: e.target.value })} /></Field>
            <Field label={t("users.email")}><input type="email" style={input} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label={t("config.phone")}><input style={input} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
            <Field label={t("config.address")}><input style={input} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.name"), t("config.document"), t("users.email"), t("config.phone"), t("users.active"), t("users.actions")]}>
        {rows.map((c) => (
          <tr key={c.id} style={{ ...rowStyle, opacity: c.active ? 1 : 0.5 }}>
            <td style={td}>{c.name}</td><td style={td}>{c.document || "—"}</td><td style={td}>{c.email || "—"}</td><td style={td}>{c.phone || "—"}</td>
            <td style={td}>{c.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}><button style={mini} onClick={() => startEdit(c)}>{t("users.edit")}</button><button style={mini} onClick={() => toggle(c)}>{c.active ? t("users.deactivate") : t("users.activate")}</button></td>
          </tr>
        ))}
      </Table>
    </Section>
  );
}

// ---------------------------------------------------------- Personalização
function BrandingTab() {
  const { t } = useTranslation();
  const { branding, reload } = useBranding();
  const [form, setForm] = useState({ app_name: "", app_subtitle: "", primary_color: "#12a386" });
  const [enabledLocales, setEnabledLocales] = useState<string[]>(LANGUAGES.map((l) => l.code));
  const [topbarExtendsSidebar, setTopbarExtendsSidebar] = useState(true);
  const [logo, setLogo] = useState<File | null>(null);
  const [logoRail, setLogoRail] = useState<File | null>(null);
  const [background, setBackground] = useState<File | null>(null);
  const [favicon, setFavicon] = useState<File | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (loaded) return;
    setForm({
      app_name: branding.app_name ?? "",
      app_subtitle: branding.app_subtitle ?? "",
      primary_color: branding.primary_color ?? "#12a386",
    });
    setEnabledLocales(branding.enabled_locales ?? LANGUAGES.map((l) => l.code));
    setTopbarExtendsSidebar(branding.topbar_extends_sidebar);
    setLoaded(true);
  }, [branding, loaded]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setSuccess("");
    const payload = new FormData();
    payload.set("app_name", form.app_name.trim());
    payload.set("app_subtitle", form.app_subtitle.trim());
    payload.set("primary_color", form.primary_color);
    payload.set("enabled_locales", enabledLocales.join(","));
    payload.set("topbar_extends_sidebar", String(topbarExtendsSidebar));
    if (logo) payload.set("logo", logo);
    if (logoRail) payload.set("logo_rail", logoRail);
    if (background) payload.set("background", background);
    if (favicon) payload.set("favicon", favicon);
    try {
      await api.put("/branding", payload);
      setLogo(null); setLogoRail(null); setBackground(null); setFavicon(null);
      await reload();
      setSuccess(t("config.branding_saved"));
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("config.save_error"));
    }
  }

  async function removeImage(kind: "logo" | "logo_rail" | "background" | "favicon") {
    setError(""); setSuccess("");
    const payload = new FormData();
    payload.set("app_name", form.app_name.trim());
    payload.set("app_subtitle", form.app_subtitle.trim());
    payload.set("primary_color", form.primary_color);
    const removeField = { logo: "remove_logo", logo_rail: "remove_logo_rail", background: "remove_background", favicon: "remove_favicon" }[kind];
    payload.set(removeField, "true");
    try {
      await api.put("/branding", payload);
      await reload();
      setSuccess(t("config.branding_saved"));
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("config.save_error"));
    }
  }

  return (
    <Section title={t("config.tabs.branding")} newLabel="" error={error}>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>{t("config.branding_help")}</p>
      {success && <p style={{ color: "#087461" }}>{success}</p>}
      <form onSubmit={save} style={panel}>
        <div style={grid}>
          <Field label={t("config.branding_app_name")}>
            <input style={input} value={form.app_name} placeholder="Rotas Brasil RSM"
              onChange={(e) => setForm({ ...form, app_name: e.target.value })} />
          </Field>
          <Field label={t("config.branding_app_subtitle")}>
            <input style={input} value={form.app_subtitle} placeholder={t("app.subtitle")}
              onChange={(e) => setForm({ ...form, app_subtitle: e.target.value })} />
          </Field>
          <Field label={t("config.branding_color")}>
            <input style={{ ...input, height: 40, padding: 4 }} type="color" value={form.primary_color}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })} />
          </Field>
          <Field label={t("config.branding_languages")}>
            <div style={{ display: "flex", gap: 14, alignItems: "center", height: 40 }}>
              {LANGUAGES.map((l) => (
                <label key={l.code} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--ink)", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={enabledLocales.includes(l.code)}
                    onChange={(e) => {
                      if (!e.target.checked && enabledLocales.length === 1) return;
                      setEnabledLocales((prev) =>
                        e.target.checked ? [...prev, l.code] : prev.filter((code) => code !== l.code));
                    }}
                  />
                  <img src={l.flagSrc} alt="" style={{ width: 20, height: 14, objectFit: "cover" }} />
                </label>
              ))}
            </div>
          </Field>
          <Field label={t("config.branding_topbar_extends")}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--ink)", cursor: "pointer", height: 40 }}>
              <input
                type="checkbox"
                checked={topbarExtendsSidebar}
                onChange={(e) => setTopbarExtendsSidebar(e.target.checked)}
              />
              {t("config.branding_topbar_extends_label")}
            </label>
          </Field>
        </div>
        <div style={{ ...grid, marginTop: 12 }}>
          <Field label={t("config.branding_logo")}>
            <BrandingImageUpload
              id="branding-logo"
              accept="image/*"
              file={logo}
              currentUrl={branding.logo_url}
              previewStyle={{ height: 36, maxWidth: 150, objectFit: "contain" }}
              attachLabel={t("config.branding_attach_image")}
              selectedLabel={t("common.selected_file")}
              clearLabel={t("common.clear")}
              deleteLabel={t("common.delete")}
              onChange={setLogo}
              onRemove={() => removeImage("logo")}
            />
          </Field>
          <Field label={t("config.branding_logo_rail")}>
            <BrandingImageUpload
              id="branding-logo-rail"
              accept="image/*"
              file={logoRail}
              currentUrl={branding.logo_rail_url}
              previewStyle={{ height: 36, width: 36, objectFit: "contain" }}
              attachLabel={t("config.branding_attach_image")}
              selectedLabel={t("common.selected_file")}
              clearLabel={t("common.clear")}
              deleteLabel={t("common.delete")}
              onChange={setLogoRail}
              onRemove={() => removeImage("logo_rail")}
            />
          </Field>
          <Field label={t("config.branding_background")}>
            <BrandingImageUpload
              id="branding-background"
              accept="image/*"
              file={background}
              currentUrl={branding.background_url}
              previewStyle={{ height: 42, width: 72, objectFit: "cover", borderRadius: 6 }}
              attachLabel={t("config.branding_attach_image")}
              selectedLabel={t("common.selected_file")}
              clearLabel={t("common.clear")}
              deleteLabel={t("common.delete")}
              onChange={setBackground}
              onRemove={() => removeImage("background")}
            />
          </Field>
          <Field label={t("config.branding_favicon")}>
            <BrandingImageUpload
              id="branding-favicon"
              accept="image/*,.ico"
              file={favicon}
              currentUrl={branding.favicon_url}
              previewStyle={{ height: 28, width: 28, objectFit: "contain" }}
              attachLabel={t("config.branding_attach_image")}
              selectedLabel={t("common.selected_file")}
              clearLabel={t("common.clear")}
              deleteLabel={t("common.delete")}
              onChange={setFavicon}
              onRemove={() => removeImage("favicon")}
            />
          </Field>
        </div>
        <div style={{ marginTop: 12 }}>
          <button type="submit" style={primary}>{t("common.save")}</button>
        </div>
      </form>
    </Section>
  );
}

// ---------------------------------------------------------------- Clientes (tenants)
function TorreControleSyncPanel() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<{
    configured: boolean; last_run_at: string | null; last_run_detail: string | null;
    default_branch_id: number | null; default_branch_name: string | null;
  } | null>(null);
  const [branches, setBranches] = useState<{ id: number; name: string; tenant_id: number | null }[]>([]);
  const [branchId, setBranchId] = useState("");
  const [message, setMessage] = useState("");

  const reload = () => api.get("/sync/torre-controle/status").then((r) => {
    setStatus(r.data);
    setBranchId((current) => current || (r.data.default_branch_id ? String(r.data.default_branch_id) : ""));
  }).catch(() => setStatus(null));
  useEffect(() => {
    reload();
    api.get("/branches").then((r) => setBranches(r.data)).catch(() => setBranches([]));
  }, []);

  async function syncNow() {
    setMessage("");
    try {
      const { data } = await api.post("/sync/torre-controle", branchId ? { branch_id: Number(branchId) } : {});
      setMessage(data.queued ? t("config.sync_queued") : data.detail);
      reload();
    } catch (err: any) { setMessage(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  if (!status) return null;

  return (
    <div style={{ ...panel, marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
      <div>
        <strong>{t("config.sync_title")}</strong>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--muted)" }}>
          {status.configured ? t("config.sync_configured") : t("config.sync_not_configured")}
          {status.last_run_at && ` · ${t("config.sync_last_run")}: ${new Date(status.last_run_at).toLocaleString()}`}
        </p>
        {message && <p style={{ margin: "4px 0 0", fontSize: 13, color: "#087461" }}>{message}</p>}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <select style={{ ...input, minWidth: 220 }} value={branchId} onChange={(e) => setBranchId(e.target.value)}>
          <option value="">{t("config.sync_branch_default", { name: status.default_branch_name ?? "—" })}</option>
          {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        <button type="button" style={mini} onClick={syncNow} disabled={!status.configured}>
          {t("config.sync_now")}
        </button>
      </div>
    </div>
  );
}

function TenantsTab() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<TenantItem[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const emptyForm = {
    name: "", slug: "", country: "BR",
    feature_ocr: true, feature_sharepoint_sync: false, feature_financeiro: true, feature_rastreamento: true, feature_route_optimization: true, feature_km_calculation: true,
    billing_plan: "", billing_amount: "", billing_due_day: "",
  };
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [brandingTenantId, setBrandingTenantId] = useState<number | null>(null);
  const [userTenantId, setUserTenantId] = useState<number | null>(null);

  const reload = () => api.get("/tenants").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm(emptyForm); setEditing("new"); }
  function startEdit(item: TenantItem) {
    setError("");
    setForm({
      name: item.name, slug: item.slug, country: item.country,
      feature_ocr: item.feature_ocr, feature_sharepoint_sync: item.feature_sharepoint_sync,
      feature_financeiro: item.feature_financeiro, feature_rastreamento: item.feature_rastreamento,
      feature_route_optimization: item.feature_route_optimization ?? true, feature_km_calculation: item.feature_km_calculation ?? true,
      billing_plan: item.billing_plan ?? "",
      billing_amount: item.billing_amount != null ? String(item.billing_amount) : "",
      billing_due_day: item.billing_due_day != null ? String(item.billing_due_day) : "",
    });
    setEditing(item.id);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const payload = {
      ...form,
      billing_amount: form.billing_amount ? Number(form.billing_amount) : null,
      billing_due_day: form.billing_due_day ? Number(form.billing_due_day) : null,
    };
    try {
      if (editing === "new") await api.post("/tenants", payload);
      else if (typeof editing === "number") await api.put(`/tenants/${editing}`, payload);
      setEditing(null); reload();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function toggle(item: TenantItem) {
    try { await api.put(`/tenants/${item.id}`, { active: !item.active }); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }
  async function markPaid(item: TenantItem) {
    try { await api.post(`/tenants/${item.id}/mark-paid`); reload(); }
    catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  async function simulateTenant(tenantId: number) {
    setError("");
    try {
      const { data } = await api.post(`/tenants/${tenantId}/preview-session`);
      const hash = `access_token=${encodeURIComponent(data.access_token)}&refresh_token=${encodeURIComponent(data.refresh_token)}`;
      window.open(`/preview-session#${hash}`, "_blank");
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  const [copiedSlug, setCopiedSlug] = useState<string | null>(null);
  function accessLink(slug: string) {
    return `${window.location.origin}/?empresa=${slug}`;
  }
  async function copyAccessLink(slug: string) {
    try {
      await navigator.clipboard.writeText(accessLink(slug));
      setCopiedSlug(slug);
      setTimeout(() => setCopiedSlug((current) => (current === slug ? null : current)), 2000);
    } catch { setError(t("config.save_error")); }
  }

  return (
    <Section title={t("config.tabs.tenants")} onNew={startNew} newLabel={t("config.new_tenant")} error={error}>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>{t("config.tenants_help")}</p>
      <TorreControleSyncPanel />
      {editing !== null && (
        <form onSubmit={save} style={panel}>
          <div style={grid}>
            <Field label={t("config.name")}><input style={input} required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label={t("config.tenant_slug")}>
              <input style={input} required disabled={editing !== "new"} placeholder="adeste" value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} />
            </Field>
            <Field label={t("config.tenant_country")}>
              <input style={input} maxLength={2} value={form.country}
                onChange={(e) => setForm({ ...form, country: e.target.value.toUpperCase() })} />
            </Field>
          </div>
          <Field label={t("config.tenant_features")}>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 4 }}>
              {([
                ["feature_ocr", t("config.feature_ocr")],
                ["feature_sharepoint_sync", t("config.feature_sharepoint_sync")],
                ["feature_financeiro", t("config.feature_financeiro")],
                ["feature_rastreamento", t("config.feature_rastreamento")],
                ["feature_route_optimization", t("config.feature_route_optimization")],
                ["feature_km_calculation", t("config.feature_km_calculation")],
              ] as const).map(([key, label]) => (
                <label key={key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--ink)", cursor: "pointer" }}>
                  <input type="checkbox" checked={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.checked })} />
                  {label}
                </label>
              ))}
            </div>
          </Field>
          <Field label={t("config.tenant_billing")}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
              <input style={{ ...input, maxWidth: 160 }} placeholder={t("config.billing_plan")} value={form.billing_plan}
                onChange={(e) => setForm({ ...form, billing_plan: e.target.value })} />
              <input style={{ ...input, maxWidth: 140 }} type="number" step="0.01" min="0" placeholder={t("config.billing_amount")} value={form.billing_amount}
                onChange={(e) => setForm({ ...form, billing_amount: e.target.value })} />
              <input style={{ ...input, maxWidth: 140 }} type="number" min="1" max="28" placeholder={t("config.billing_due_day")} value={form.billing_due_day}
                onChange={(e) => setForm({ ...form, billing_due_day: e.target.value })} />
            </div>
          </Field>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.name"), t("config.tenant_slug"), t("config.tenant_country"), t("config.tenant_billing"), t("users.active"), t("users.actions")]}>
        {rows.map((item) => (
          <tr key={item.id} style={{ ...rowStyle, opacity: item.active ? 1 : 0.5 }}>
            <td style={td}>{item.name}</td>
            <td style={td}>{item.slug}</td>
            <td style={td}>{item.country}</td>
            <td style={td}>
              {item.billing_status && item.billing_status !== "sem_plano" ? (
                <>
                  <span style={{
                    display: "inline-block", padding: "2px 8px", borderRadius: 10, fontSize: 11, fontWeight: 700,
                    background: BILLING_STATUS_COLOR[item.billing_status]?.bg ?? "#e2e8f0",
                    color: BILLING_STATUS_COLOR[item.billing_status]?.fg ?? "#475569",
                  }}>
                    {t(`config.billing_status_${item.billing_status}`)}
                  </span>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                    {item.billing_plan} · {item.billing_amount ? formatCurrency(Number(item.billing_amount)) : ""} · {t("config.billing_due_day_short")} {item.billing_due_day}
                  </div>
                </>
              ) : <span style={{ color: "var(--muted)", fontSize: 12 }}>{t("config.billing_status_sem_plano")}</span>}
            </td>
            <td style={td}>{item.active ? t("common.yes") : t("common.no")}</td>
            <td style={td}>
              <button style={mini} onClick={() => startEdit(item)}>{t("users.edit")}</button>
              <button style={mini} onClick={() => toggle(item)}>{item.active ? t("users.deactivate") : t("users.activate")}</button>
              {item.billing_due_day != null && (
                <button style={mini} onClick={() => markPaid(item)}>{t("config.mark_paid")}</button>
              )}
              <button style={mini} onClick={() => setBrandingTenantId(brandingTenantId === item.id ? null : item.id)}>
                {t("config.tabs.branding")}
              </button>
              <button style={mini} onClick={() => simulateTenant(item.id)}>{t("config.simulate")}</button>
              <button style={mini} onClick={() => setUserTenantId(userTenantId === item.id ? null : item.id)}>
                {t("config.create_first_user")}
              </button>
              <button style={mini} onClick={() => copyAccessLink(item.slug)}>
                {copiedSlug === item.slug ? t("config.link_copied") : t("config.copy_link")}
              </button>
            </td>
          </tr>
        ))}
        {brandingTenantId !== null && (
          <tr>
            <td colSpan={6} style={{ padding: 0, border: "none" }}>
              <TenantBrandingPanel tenantId={brandingTenantId} tenantName={rows.find((r) => r.id === brandingTenantId)?.name ?? ""} />
            </td>
          </tr>
        )}
        {userTenantId !== null && (
          <tr>
            <td colSpan={6} style={{ padding: 0, border: "none" }}>
              <TenantUserPanel tenantId={userTenantId} tenantName={rows.find((r) => r.id === userTenantId)?.name ?? ""}
                onCreated={() => setUserTenantId(null)} />
            </td>
          </tr>
        )}
      </Table>
    </Section>
  );
}

function TenantUserPanel({ tenantId, tenantName, onCreated }: { tenantId: number; tenantName: string; onCreated: () => void }) {
  const { t } = useTranslation();
  const [branchId, setBranchId] = useState<number | null>(null);
  const [form, setForm] = useState({ email: "", name: "", role: "gestor_brasil", password: "" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setError(""); setSuccess(""); setBranchId(null);
    api.get("/branches").then((r) => {
      const branch = (r.data as { id: number; tenant_id: number | null }[]).find((b) => b.tenant_id === tenantId);
      setBranchId(branch?.id ?? null);
      if (!branch) setError(t("config.tenant_no_branch"));
    }).catch(() => setError(t("config.save_error")));
  }, [tenantId]);

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError(""); setSuccess("");
    if (!branchId) { setError(t("config.tenant_no_branch")); return; }
    setSaving(true);
    try {
      await api.post("/users", { ...form, branch_id: branchId });
      setSuccess(t("config.first_user_created"));
      setForm({ email: "", name: "", role: "gestor_brasil", password: "" });
      onCreated();
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
    finally { setSaving(false); }
  }

  return (
    <div style={panel}>
      <h4 style={{ marginTop: 0 }}>{t("config.create_first_user")} — {tenantName}</h4>
      {error && <p style={{ color: "#b91c1c", fontSize: 13 }}>{error}</p>}
      {success && <p style={{ color: "#15803d", fontSize: 13 }}>{success}</p>}
      <form onSubmit={save}>
        <div style={grid}>
          <Field label={t("users.email")}><input type="email" style={input} required value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label={t("users.name")}><input style={input} required value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label={t("users.role")}>
            <select style={input} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="gestor_brasil">{t("config.role_gestor_brasil", { defaultValue: "Gestor" })}</option>
              <option value="admin_global">{t("config.role_admin_global", { defaultValue: "Administrador global" })}</option>
            </select>
          </Field>
          <Field label={t("users.password")}><input type="password" style={input} required minLength={8} value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
        </div>
        <div style={{ marginTop: 12 }}>
          <button type="submit" style={primary} disabled={saving || !branchId}>{t("common.save")}</button>
        </div>
      </form>
    </div>
  );
}

function TenantBrandingPanel({ tenantId, tenantName }: { tenantId: number; tenantName: string }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({ app_name: "", primary_color: "#12a386" });
  const [logo, setLogo] = useState<File | null>(null);
  const [currentLogoUrl, setCurrentLogoUrl] = useState<string | null>(null);
  const [background, setBackground] = useState<File | null>(null);
  const [currentBackgroundUrl, setCurrentBackgroundUrl] = useState<string | null>(null);
  const [favicon, setFavicon] = useState<File | null>(null);
  const [currentFaviconUrl, setCurrentFaviconUrl] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    setLoaded(false);
    api.get("/branding", { params: { edit_tenant_id: tenantId } }).then((r) => {
      setForm({ app_name: r.data.app_name ?? "", primary_color: r.data.primary_color ?? "#12a386" });
      setCurrentLogoUrl(r.data.logo_url ?? null);
      setCurrentBackgroundUrl(r.data.background_url ?? null);
      setCurrentFaviconUrl(r.data.favicon_url ?? null);
      setLoaded(true);
    });
  }, [tenantId]);

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError(""); setSuccess("");
    const payload = new FormData();
    payload.set("app_name", form.app_name.trim());
    payload.set("primary_color", form.primary_color);
    if (logo) payload.set("logo", logo);
    if (background) payload.set("background", background);
    if (favicon) payload.set("favicon", favicon);
    try {
      await api.put("/branding", payload, { params: { tenant_id: tenantId } });
      setLogo(null); setBackground(null); setFavicon(null);
      setSuccess(t("config.branding_saved"));
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  async function removeImage(kind: "logo" | "background" | "favicon") {
    setError(""); setSuccess("");
    const payload = new FormData();
    payload.set("app_name", form.app_name.trim());
    payload.set("primary_color", form.primary_color);
    const removeField = { logo: "remove_logo", background: "remove_background", favicon: "remove_favicon" }[kind];
    payload.set(removeField, "true");
    try {
      await api.put("/branding", payload, { params: { tenant_id: tenantId } });
      if (kind === "logo") setCurrentLogoUrl(null);
      else if (kind === "background") setCurrentBackgroundUrl(null);
      else setCurrentFaviconUrl(null);
      setSuccess(t("config.branding_saved"));
    } catch (err: any) { setError(err?.response?.data?.detail ?? t("config.save_error")); }
  }

  if (!loaded) return null;

  return (
    <div style={{ ...panel, marginTop: 16, border: "2px solid var(--brand)" }}>
      <h4 style={{ marginTop: 0 }}>{t("config.tabs.branding")} — {tenantName}</h4>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>{t("config.tenant_branding_help")}</p>
      {success && <p style={{ color: "#087461" }}>{success}</p>}
      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      <form onSubmit={save}>
        <div style={grid}>
          <Field label={t("config.branding_app_name")}>
            <input style={input} value={form.app_name} onChange={(e) => setForm({ ...form, app_name: e.target.value })} />
          </Field>
          <Field label={t("config.branding_color")}>
            <input style={{ ...input, height: 40, padding: 4 }} type="color" value={form.primary_color}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })} />
          </Field>
          <Field label={t("config.branding_logo")}>
            <BrandingImageUpload
              id={`tenant-logo-${tenantId}`}
              accept="image/*"
              file={logo}
              currentUrl={currentLogoUrl}
              previewStyle={{ height: 36, maxWidth: 150, objectFit: "contain" }}
              attachLabel={t("config.branding_attach_image")}
              selectedLabel={t("common.selected_file")}
              clearLabel={t("common.clear")}
              deleteLabel={t("common.delete")}
              onChange={setLogo}
              onRemove={() => removeImage("logo")}
            />
          </Field>
          <Field label={t("config.branding_background")}>
            <BrandingImageUpload
              id={`tenant-background-${tenantId}`}
              accept="image/*"
              file={background}
              currentUrl={currentBackgroundUrl}
              previewStyle={{ height: 42, width: 72, objectFit: "cover", borderRadius: 6 }}
              attachLabel={t("config.branding_attach_image")}
              selectedLabel={t("common.selected_file")}
              clearLabel={t("common.clear")}
              deleteLabel={t("common.delete")}
              onChange={setBackground}
              onRemove={() => removeImage("background")}
            />
          </Field>
          <Field label={t("config.branding_favicon")}>
            <BrandingImageUpload
              id={`tenant-favicon-${tenantId}`}
              accept="image/*"
              file={favicon}
              currentUrl={currentFaviconUrl}
              previewStyle={{ height: 28, width: 28, objectFit: "contain" }}
              attachLabel={t("config.branding_attach_image")}
              selectedLabel={t("common.selected_file")}
              clearLabel={t("common.clear")}
              deleteLabel={t("common.delete")}
              onChange={setFavicon}
              onRemove={() => removeImage("favicon")}
            />
          </Field>
        </div>
        <div style={{ marginTop: 12 }}>
          <button type="submit" style={primary}>{t("common.save")}</button>
        </div>
      </form>
    </div>
  );
}

function BrandingImageUpload({
  id,
  accept,
  file,
  currentUrl,
  previewStyle,
  attachLabel,
  selectedLabel,
  clearLabel,
  deleteLabel,
  onChange,
  onRemove,
}: {
  id: string;
  accept: string;
  file: File | null;
  currentUrl: string | null;
  previewStyle: React.CSSProperties;
  attachLabel: string;
  selectedLabel: string;
  clearLabel: string;
  deleteLabel: string;
  onChange: (file: File | null) => void;
  onRemove: () => void;
}) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [imageOk, setImageOk] = useState(true);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      setImageOk(true);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setImageOk(true);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    setImageOk(true);
  }, [currentUrl]);

  const imageUrl = previewUrl || currentUrl;

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <label className="upload-pill" htmlFor={id}>
        <input
          id={id}
          type="file"
          accept={accept}
          onChange={(e) => onChange(e.target.files?.[0] ?? null)}
        />
        <span className="upload-pill-icon"><UploadIcon /></span>
        <span>{file ? `${selectedLabel}: ${file.name}` : attachLabel}</span>
      </label>
      {imageUrl && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 42 }}>
          {imageOk ? (
            <img
              src={imageUrl}
              alt=""
              style={previewStyle}
              onError={() => setImageOk(false)}
              onLoad={() => setImageOk(true)}
            />
          ) : (
            <span style={{ color: "#b91c1c", fontSize: 12 }}>Preview indisponível</span>
          )}
          {file ? (
            <button type="button" style={mini} onClick={() => onChange(null)}>{clearLabel}</button>
          ) : currentUrl ? (
            <button type="button" style={mini} onClick={onRemove}>{deleteLabel}</button>
          ) : null}
        </div>
      )}
    </div>
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

// ---------------------------------------------------------------- helpers UI
function Section({ title, onNew, newLabel, error, children }:
  { title: string; onNew?: () => void; newLabel: string; error: string; children: React.ReactNode }) {
  return (
    <div style={sectionShell}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: "8px 0" }}>{title}</h3>
        {onNew && <button style={primary} onClick={onNew}>{newLabel}</button>}
      </div>
      {error && <p style={{ color: "#c00" }}>{error}</p>}
      {children}
    </div>
  );
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label style={field}><span>{label}</span>{children}</label>;
}
function FormButtons({ onCancel }: { onCancel: () => void }) {
  const { t } = useTranslation();
  return (
    <div style={{ marginTop: 12 }}>
      <button type="submit" style={primary}>{t("common.save")}</button>
      <button type="button" style={ghost} onClick={onCancel}>{t("common.cancel")}</button>
    </div>
  );
}
function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <table style={table}>
      <thead><tr style={{ background: "#f8fafc", textAlign: "left" }}>
        {head.map((h) => <th key={h} style={th}>{h}</th>)}
      </tr></thead>
      <tbody>{children}</tbody>
    </table>
  );
}

const BILLING_STATUS_COLOR: Record<string, { bg: string; fg: string }> = {
  em_dia: { bg: "#dcfce7", fg: "#15803d" },
  a_vencer: { bg: "#fef9c3", fg: "#a16207" },
  atrasado: { bg: "#fee2e2", fg: "#b91c1c" },
};
function formatCurrency(value: number, locale = "pt-BR") {
  return new Intl.NumberFormat(locale, { style: "currency", currency: locale === "pt-BR" ? "BRL" : "EUR" }).format(value);
}
const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse", background: "var(--panel)", borderRadius: 12, overflow: "hidden", marginTop: 12 };
const th: React.CSSProperties = { padding: 10, fontSize: 13, color: "var(--muted)" };
const td: React.CSSProperties = { padding: 10, fontSize: 14, color: "var(--ink)" };
const rowStyle: React.CSSProperties = { borderTop: "1px solid var(--line)" };
const mini: React.CSSProperties = { marginRight: 4, marginBottom: 4, padding: "4px 8px", fontSize: 12, border: "1px solid var(--line)", borderRadius: 6, background: "var(--panel)", color: "var(--ink)", cursor: "pointer" };
const primary: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "none", background: "#0a58ca", color: "#fff", cursor: "pointer", marginRight: 8 };
const ghost: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", cursor: "pointer" };
const panel: React.CSSProperties = { background: "var(--panel)", borderRadius: 12, padding: 18, boxShadow: "0 2px 10px rgba(0,0,0,.05)", marginTop: 12 };
const grid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))", gap: 12 };
const field: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4, fontSize: 13, color: "var(--muted)" };
const input: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--line)", fontSize: 14, background: "var(--panel)", color: "var(--ink)" };
const textarea: React.CSSProperties = { ...input, minHeight: 86, resize: "vertical" };
const muted: React.CSSProperties = { color: "var(--muted)", fontSize: 12, marginTop: 2 };
const pageHeader: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 };
const subtitle: React.CSSProperties = { color: "var(--muted)", margin: "6px 0 0", fontSize: 14 };
const tabsWrap: React.CSSProperties = { display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", background: "var(--panel)", padding: 6, borderRadius: 10, border: "1px solid var(--line)" };
const sectionShell: React.CSSProperties = { background: "var(--panel)", borderRadius: 12, padding: 18, border: "1px solid var(--line)", boxShadow: "0 8px 22px rgba(15,23,42,.04)" };
const tabBtn: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "1px solid transparent", background: "transparent", cursor: "pointer", color: "var(--muted)", fontWeight: 600 };
const tabActive: React.CSSProperties = { background: "#0f172a", color: "#fff", border: "1px solid #0f172a" };

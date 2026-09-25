import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import {appPrompt, appConfirm} from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";

interface UserRow {
  id: number; email: string; login?: string | null; name: string; role: string;
  branch_id: number | null; tenant_id?: number | null; active: boolean;
  must_change_password: boolean;
  blocked: boolean; status_reason?: string | null;
  department?: string | null; subgroup?: string | null; permissions?: string[];
  carrier_id?: number | null; carrier_name?: string | null;
}
interface RoleOption {
  value: string;
  label?: string;
  description: string;
  permissions?: string[];
  order?: number;
}
interface BranchOption { id:number; name:string; tenant_id:number|null }
interface DriverOption { id:number; name:string; user_id?:number|null; tenant_id?:number|null; branch_id:number; active:boolean; blocked:boolean }
interface CarrierOption { id:number; name:string; tenant_id:number|null; active:boolean }
interface CarrierMaster { carrier_id:number; carrier_name:string; user_id:number; user_name:string; user_email:string; is_first_master:boolean }
interface OperationalSettings {
  require_manual_justification: boolean;
  require_checkin_before_delivery: boolean;
  require_delivery_proof: boolean;
  require_failure_proof: boolean;
  require_warehouse_return_proof: boolean;
  require_failure_reason: boolean;
  require_returned_quantity: boolean;
  routing_enabled: boolean;
}
const EMPTY = { email: "", login: "", name: "", role: "motorista", department: "", subgroup: "", branch_id: "", tenant_id: "", driver_id: "", carrier_id: "", permissions: [] as string[] };
const DEPARTMENTS = ["Operação", "Torre de controle", "Frota", "Cadastros", "Diretoria"];
const ROLE_ORDER = [
  "admin_global",
  "auditor",
  "gerente",
  "motorista",
  "operador_logistico",
  "monitoramento",
];

export default function Users() {
  const { t } = useTranslation();
  const { user: me } = useAuth();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersLoadError, setUsersLoadError] = useState("");
  const [roles, setRoles] = useState<RoleOption[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [credentials, setCredentials] = useState<{ email: string; login?: string | null; initial_password: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [operationalSettings, setOperationalSettings] = useState<OperationalSettings | null>(null);
  const [routingSaving, setRoutingSaving] = useState(false);
  const [branches,setBranches]=useState<BranchOption[]>([]);
  const [drivers,setDrivers]=useState<DriverOption[]>([]);
  const [carriers,setCarriers]=useState<CarrierOption[]>([]);
  const [carrierMasters,setCarrierMasters]=useState<CarrierMaster[]>([]);
  const [section,setSection]=useState<"internal"|"carrier_users"|"drivers"|"masters">("internal");

  const reload = async () => {
    setUsersLoading(true);
    setUsersLoadError("");
    try {
      const { data } = await api.get<UserRow[]>("/users");
      if (!Array.isArray(data)) throw new Error("Resposta inválida ao consultar usuários.");
      setUsers(data);
    } catch (err: any) {
      setUsersLoadError(err?.response?.data?.detail ?? "Não foi possível carregar os usuários. Tente novamente.");
    } finally {
      setUsersLoading(false);
    }
  };
  const reloadDrivers = () => api.get<DriverOption[]>("/drivers").then((r) => setDrivers(r.data)).catch(() => setDrivers([]));
  const reloadMasters = () => api.get<CarrierMaster[]>("/access-model/carrier-masters").then((r) => setCarrierMasters(r.data)).catch(() => setCarrierMasters([]));

  useEffect(() => {
    reload();
    reloadDrivers();
    reloadMasters();
    api.get<CarrierOption[]>("/carriers?only_active=true").then(r=>setCarriers(r.data)).catch(()=>setCarriers([]));
    api.get("/users/roles")
      .then((r) => setRoles(orderRoles(r.data)))
      .catch(() => setRoles(orderRoles(ROLE_ORDER.map((value) => ({ value, description: "" })))));
    api.get("/branches").then(r=>setBranches(r.data)).catch(()=>setBranches([]));
  }, []);

  useEffect(() => {
    if (me?.role !== "admin_global") return;
    api.get("/operational-settings")
      .then((response) => setOperationalSettings(response.data))
      .catch(() => setError("Não foi possível consultar a configuração do roteirizador."));
  }, [me?.role]);

  async function toggleRouting() {
    if (!operationalSettings || routingSaving) return;
    setRoutingSaving(true);
    setError("");
    try {
      const { data } = await api.put("/operational-settings", {
        ...operationalSettings,
        routing_enabled: !operationalSettings.routing_enabled,
      });
      setOperationalSettings(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Não foi possível alterar o roteirizador.");
    } finally {
      setRoutingSaving(false);
    }
  }

  const departments = [...new Set([...DEPARTMENTS, ...users.map(user => user.department).filter((value): value is string => Boolean(value)), ...(form.department ? [form.department] : [])])];

  function startNew() {
    setError("");
    setForm({ ...EMPTY, role: section === "drivers" ? "motorista" : section === "masters" ? "gestor_brasil" : "planejamento", department:section === "masters" ? "Transportadora" : "" });
    setEditing("new");
  }

  function startEdit(u: UserRow) {
    setError("");
    const branch=branches.find(item=>item.id===u.branch_id);
    setForm({ email: u.email, login: u.login || (u.role === "motorista" ? u.email.split("@")[0] : ""), name: u.name, role: u.role, department: u.department || "", subgroup: u.subgroup || "", branch_id:u.branch_id?String(u.branch_id):"", tenant_id:String(branch?.tenant_id??u.tenant_id??""), driver_id:String(drivers.find(driver=>driver.user_id===u.id)?.id||""), carrier_id:String(carrierMasters.find(master=>master.user_id===u.id)?.carrier_id||""), permissions: [] });
    setEditing(u.id);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (saving) return;
    if(section==="masters"&&!form.carrier_id){setError("Selecione a transportadora do usuário master.");return}
    setSaving(true);
    setError("");
    try {
      let savedUserId: number;
      if (editing === "new") {
        const { data } = await api.post("/users", {
          email: section === "drivers" ? null : form.email, login: section === "drivers" ? form.login : null, name: form.name, role: section === "masters" ? "operador_logistico" : form.role,
          department: form.department || null, subgroup: form.subgroup || null, permissions: [],
          branch_id: form.branch_id ? Number(form.branch_id) : null,
        });
        setCredentials({ email: data.email, login: data.login, initial_password: data.initial_password });
        savedUserId=data.id;
        setCopied(false);
      } else if (typeof editing === "number") {
        await api.put(`/users/${editing}`, {
          ...(section === "drivers" ? { login: form.login } : { email: form.email }), name: form.name, ...(section === "masters" ? {} : {role: form.role}), department: form.department || null,
          subgroup: form.subgroup || null, permissions: [],
          branch_id: form.branch_id ? Number(form.branch_id) : null,
        });
        savedUserId=editing;
      } else {
        return;
      }
      if(section==="drivers"){
        const current=drivers.find(driver=>driver.user_id===savedUserId);
        const selected=form.driver_id?Number(form.driver_id):null;
        if(current&&current.id!==selected)await api.put(`/drivers/${current.id}`,{user_id:null});
        if(selected&&current?.id!==selected)await api.put(`/drivers/${selected}`,{user_id:savedUserId});
        await reloadDrivers();
      }
      if(section==="masters"){
        if(!form.carrier_id) throw new Error("Selecione a transportadora do usuário master.");
        await api.post(`/access-model/carriers/${Number(form.carrier_id)}/masters/${savedUserId}`);
        await reloadMasters();
      }
      setEditing(null);
      reload();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : err?.message || t("users.save_error"));
    } finally { setSaving(false); }
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
    if (!await appConfirm(`Gerar uma senha temporária para ${u.name}? A senha atual deixará de funcionar e a troca será obrigatória no próximo acesso.`, { title: "Redefinir senha", confirmLabel: "Gerar senha" })) return;
    try {
      const { data } = await api.post(`/users/${u.id}/reset-password`);
      setCredentials({ email: data.email, login: data.login, initial_password: data.initial_password });
      setCopied(false);
      setError("");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("users.save_error"));
    }
  }

  const roleLabel = (value: string) => {
    const profile = roles.find((r) => r.value === value);
    return profile?.label || t(`roles.${value}`, { defaultValue: value });
  };

  const masterUserIds=new Set(carrierMasters.map(master=>master.user_id));
  const isCarrierContext=Boolean(me?.is_carrier_master);
  const internalUsers=users.filter((user) => user.role!=="motorista"&&!masterUserIds.has(user.id)&&(isCarrierContext?Boolean(user.carrier_id):!user.carrier_id));
  const visibleUsers = users.filter((user) => section === "drivers" ? user.role === "motorista" : section === "masters" ? masterUserIds.has(user.id) : section === "carrier_users" ? Boolean(user.carrier_id)&&!masterUserIds.has(user.id)&&user.role!=="motorista" : internalUsers.some(internal=>internal.id===user.id));

  return (
    <div>
      <div style={pageHeader}>
        <div>
          <h2 style={{ margin: 0 }}>{t("users.title")}</h2>
          <p style={subtitle}>{t("users.subtitle")}</p>
        </div>
        {section!=="carrier_users"&&<button style={primary} onClick={startNew}>{section === "drivers" ? "Novo acesso de motorista" : section === "masters" ? "Novo master" : t("users.new")}</button>}
      </div>

      {error && <p style={{ color: "#c00" }}>{error}</p>}
      {usersLoadError && <p role="alert" style={{ color: "#c00" }}>{usersLoadError} <button type="button" className="btn-mini" style={mini} onClick={() => void reload()}>Tentar novamente</button></p>}

      {me?.role === "admin_global" && operationalSettings && (
        <section style={{ ...panel, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
          <div>
            <strong>Roteirizador</strong>
            <p style={subtitle}>Controle global do cálculo e da otimização de rotas.</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={operationalSettings.routing_enabled}
            disabled={routingSaving}
            onClick={toggleRouting}
            style={{
              ...primary,
              minWidth: 110,
              marginRight: 0,
              background: operationalSettings.routing_enabled ? "#15803d" : "#64748b",
              opacity: routingSaving ? 0.65 : 1,
            }}
          >
            {routingSaving ? "Salvando…" : operationalSettings.routing_enabled ? "Ligado" : "Desligado"}
          </button>
        </section>
      )}

      <nav aria-label="Seções de usuários" style={sectionNav}>
        <button type="button" onClick={() => setSection("internal")} style={{...sectionButton,...(section === "internal" ? sectionButtonActive : {})}}>
          {isCarrierContext?"Usuários da transportadora":"Usuários internos"} <span style={sectionCount}>{usersLoading ? "…" : internalUsers.length}</span>
        </button>
        {!me?.is_carrier_master&&<button type="button" onClick={() => setSection("carrier_users")} style={{...sectionButton,...(section === "carrier_users" ? sectionButtonActive : {})}}>
          Usuários de transportadoras <span style={sectionCount}>{usersLoading ? "…" : users.filter(user=>Boolean(user.carrier_id)&&!masterUserIds.has(user.id)&&user.role!=="motorista").length}</span>
        </button>}
        <button type="button" onClick={() => setSection("drivers")} style={{...sectionButton,...(section === "drivers" ? sectionButtonActive : {})}}>
          Acesso de motoristas <span style={sectionCount}>{usersLoading ? "…" : users.filter(user => user.role === "motorista").length}</span>
        </button>
        <button type="button" onClick={() => setSection("masters")} style={{...sectionButton,...(section === "masters" ? sectionButtonActive : {})}}>
          Masters de transportadoras <span style={sectionCount}>{carrierMasters.length}</span>
        </button>
      </nav>

      <div style={{marginTop:12,marginBottom:4}}>
        <strong>{section === "drivers" ? "Cadastro de acesso de motorista" : section === "masters" ? "Cadastro de masters de transportadoras" : section === "carrier_users" ? "Usuários criados pelas transportadoras" : isCarrierContext ? "Cadastro de usuários da transportadora" : "Cadastro de usuários internos"}</strong>
        <p style={subtitle}>{section === "drivers" ? "Gerencie login, situação e senha dos motoristas que acessam o Adimax Log." : section === "masters" ? "Crie o usuário e vincule-o à transportadora no mesmo cadastro. Cada transportadora aceita até três masters ativos." : section === "carrier_users" ? "Consulte e gerencie os acessos criados pelos masters de cada transportadora." : isCarrierContext ? "Gerencie os acessos vinculados exclusivamente à sua transportadora." : "Gerencie os acessos da equipe administrativa e operacional."}</p>
      </div>

      {editing !== null && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
        <form onSubmit={save} className="modal-card driver-modal" onClick={(event) => event.stopPropagation()}>
          <h3 style={{ marginTop: 0 }}>{section === "drivers" ? (editing === "new" ? "Novo acesso de motorista" : "Editar acesso de motorista") : section === "masters" ? (editing === "new" ? "Novo master de transportadora" : "Editar master") : (editing === "new" ? t("users.new") : t("users.edit"))}</h3>
          <div style={grid}>
            {section === "drivers" ? <label style={field}>
              <span>Usuário</span>
              <input style={input} required value={form.login} placeholder="nome.sobrenome" autoComplete="username"
                pattern="[a-z0-9]+([._-][a-z0-9]+)+" title="Use o padrão nome.sobrenome, sem espaços ou acentos"
                onChange={(e) => setForm({ ...form, login: e.target.value.toLowerCase().replace(/\s+/g, ".") })} />
            </label> : <label style={field}>
              <span>{t("users.email")}</span>
              <input style={input} type="email" required value={form.email}
                disabled={editing !== "new" && me?.role !== "admin_global"}
                onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </label>}
            <label style={field}>
              <span>{t("users.name")}</span>
              <input style={input} required value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            {section === "masters" && <label style={field}>
              <span>Transportadora *</span>
              <select style={input} required disabled={editing !== "new"} value={form.carrier_id} onChange={e=>{
                const carrier=carriers.find(item=>String(item.id)===e.target.value);
                const branch=branches.find(item=>item.tenant_id===carrier?.tenant_id);
                setForm({...form,carrier_id:e.target.value,tenant_id:String(carrier?.tenant_id||""),branch_id:branch?String(branch.id):""});
              }}><option value="">Selecione a transportadora</option>{carriers.map(carrier=><option key={carrier.id} value={carrier.id}>{carrier.name}</option>)}</select>
              <small>O usuário visualizará somente a operação da transportadora selecionada.</small>
            </label>}
            {section === "drivers" && <label style={field}>
              <span>Cadastro do motorista</span>
              <select style={input} required value={form.driver_id} onChange={e=>{
                const driver=drivers.find(item=>String(item.id)===e.target.value);
                setForm({...form,driver_id:e.target.value,tenant_id:driver?.tenant_id?String(driver.tenant_id):form.tenant_id,branch_id:driver?String(driver.branch_id):form.branch_id});
              }}>
                <option value="">Selecione o motorista</option>
                {drivers.filter(driver=>!driver.user_id||driver.user_id===editing).map(driver=><option key={driver.id} value={driver.id} disabled={!driver.active||driver.blocked}>{driver.name}{!driver.active||driver.blocked?" — indisponível":""}</option>)}
              </select>
              <small>Empresa e filial serão ajustadas ao cadastro escolhido. As rotas atribuídas aparecerão neste login.</small>
            </label>}
            {section === "internal" && <label style={field}>
              <span>{t("users.role")}</span>
              <select style={input} value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}>
                {roles.map((r) => (
                  <option key={r.value} value={r.value}>{roleLabel(r.value)}</option>
                ))}
              </select>
            </label>}
            {section === "internal" && <label style={field}>
              <span>Setor</span>
              <select style={input} value={form.department}
                onChange={(e) => setForm({ ...form, department: e.target.value })}>
                <option value="">Selecione o setor</option>
                {departments.map(department => <option key={department} value={department}>{department}</option>)}
              </select>
            </label>}
            {section === "internal" && <label style={field}>
              <span>Subgrupo</span>
              <input style={input} value={form.subgroup} placeholder="Ex.: Supervisão de entregas"
                onChange={(e) => setForm({ ...form, subgroup: e.target.value })} />
            </label>}
            <label style={field}><span>Filial principal</span><select style={input} disabled={(section==="drivers"&&Boolean(form.driver_id))||section==="masters"} value={form.branch_id} onChange={e=>setForm({...form,branch_id:e.target.value,tenant_id:String(branches.find(item=>item.id===Number(e.target.value))?.tenant_id??"")})}><option value="">Selecione a filial</option>{branches.filter(item=>section!=="masters"||item.tenant_id===Number(form.tenant_id)).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            {editing === "new" && <p style={{ ...subtitle, gridColumn: "1 / -1" }}>A senha inicial será gerada automaticamente ao salvar. O usuário deverá trocá-la no primeiro acesso.</p>}
          </div>
          {error && <p role="alert" style={{ color: "#c00" }}>{error}</p>}
          <div style={{ marginTop: 12 }}>
            <button type="submit" style={primary} disabled={saving}>{saving ? "Salvando…" : t("common.save")}</button>
            <button type="button" style={ghost} onClick={() => setEditing(null)}>{t("common.cancel")}</button>
          </div>
        </form>
        </div>
      )}

      {credentials && <div className="modal-backdrop">
        <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="credentials-title" style={{ maxWidth: 520 }}>
          <h3 id="credentials-title">Senha temporária gerada</h3>
          <p>Copie e entregue estes dados ao usuário. A senha será exibida somente agora e deverá ser trocada no primeiro acesso.</p>
          <label style={field}>{credentials.login ? "Usuário" : "E-mail"}<input style={input} readOnly value={credentials.login || credentials.email} /></label>
          <label style={{ ...field, marginTop: 12 }}>Senha temporária<input style={input} readOnly value={credentials.initial_password} autoComplete="off" onFocus={event => event.target.select()} /></label>
          <div style={{ marginTop: 16 }}>
            <button style={primary} onClick={async () => {
              try { await navigator.clipboard.writeText(`${credentials.login ? "Usuário" : "E-mail"}: ${credentials.login || credentials.email}\nSenha temporária: ${credentials.initial_password}`); setCopied(true); }
              catch { setCopied(false); }
            }}>{copied ? "Copiado!" : "Copiar acesso"}</button>
            <button style={ghost} onClick={() => setCredentials(null)}>Concluir</button>
          </div>
        </section>
      </div>}

      <div className="table-scroll"><table className="data-table" style={table}>
        <thead>
          <tr style={{ background: "var(--soft)", textAlign: "left" }}>
            <th style={th}>{t("users.name")}</th>
            <th style={th}>{section === "drivers" ? "Usuário" : t("users.email")}</th>
            <th style={th}>{t("users.role")}</th>
            <th style={th}>Setor / subgrupo</th>
            {section === "drivers"&&<th style={th}>Motorista vinculado</th>}
            {section === "masters"&&<th style={th}>Transportadora</th>}
            {section === "carrier_users"&&<th style={th}>Transportadora</th>}
            <th style={th}>{t("users.active")}</th>
            <th style={th}>{t("users.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {visibleUsers.map((u) => (
            <tr key={u.id} style={{ borderTop: "1px solid var(--line)" }}>
              <td style={td}>{u.name}</td>
              <td style={td}>{section === "drivers" ? (u.login || u.email.split("@")[0]) : u.email}</td>
              <td style={td}>{section === "masters" ? "Master" : roleLabel(u.role)}</td>
              <td style={td}>{[u.department, u.subgroup].filter(Boolean).join(" / ") || "—"}</td>
              {section === "drivers"&&<td style={td}>{drivers.find(driver=>driver.user_id===u.id)?.name||<span className="stock-badge warning">Sem vínculo</span>}</td>}
              {section === "masters"&&<td style={td}>{carrierMasters.find(master=>master.user_id===u.id)?.carrier_name||"—"}</td>}
              {section === "carrier_users"&&<td style={td}>{u.carrier_name||"—"}</td>}
              <td style={td}><span className={`stock-badge ${u.blocked ? "expired" : u.active ? "ok" : ""}`} title={u.status_reason||""}>{u.blocked?"Bloqueado":u.active?"Ativo":"Inativo"}</span></td>
              <td style={td}>
                <button className="btn-mini" style={mini} onClick={() => startEdit(u)}>{t("users.edit")}</button>
                {u.active?<><button className="btn-mini" style={mini} onClick={()=>void changeStatus(u,"deactivate")} disabled={u.id===me?.id}>Desativar</button><button className="btn-mini danger" style={mini} onClick={()=>void changeStatus(u,"block")} disabled={u.id===me?.id}>Bloquear</button></>:<button className="btn-mini" style={mini} onClick={()=>void changeStatus(u,u.blocked?"unblock":"activate")}>{u.blocked?"Desbloquear":"Ativar"}</button>}
                <button className="btn-mini" style={mini} onClick={() => resetPassword(u)}>{t("users.reset_password")}</button>
              </td>
            </tr>
          ))}
          {usersLoading && section !== "masters" && <tr><td style={{...td,textAlign:"center",color:"var(--muted)"}} colSpan={section==="internal"?6:7}>Carregando usuários…</td></tr>}
          {!usersLoading && visibleUsers.length === 0 && <tr><td style={{...td,textAlign:"center",color:"var(--muted)"}} colSpan={section==="internal"?6:7}>{section === "drivers" ? "Nenhum acesso de motorista cadastrado." : section === "masters" ? "Nenhum master de transportadora cadastrado." : section === "carrier_users" ? "Nenhum usuário criado por transportadora." : isCarrierContext ? "Nenhum usuário cadastrado para esta transportadora." : "Nenhum usuário interno cadastrado."}</td></tr>}
        </tbody>
      </table></div>
    </div>
  );
}

function orderRoles(values: RoleOption[]) {
  const rank = new Map(ROLE_ORDER.map((value, index) => [value, index]));
  return [...values].sort((a, b) => (rank.get(a.value) ?? 999) - (rank.get(b.value) ?? 999));
}

const pageHeader: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 16 };
const subtitle: React.CSSProperties = { color: "var(--muted)", margin: "6px 0 0", fontSize: 14 };
const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse", background: "var(--panel)", color: "var(--ink)", borderRadius: 12, overflow: "hidden", marginTop: 16, border: "1px solid var(--line)", boxShadow: "0 8px 22px rgba(15,23,42,.04)" };
const th: React.CSSProperties = { padding: 10, fontSize: 13, color: "var(--ink)" };
const td: React.CSSProperties = { padding: 10, fontSize: 14 };
const mini: React.CSSProperties = { marginRight: 4, marginBottom: 4 };
const primary: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "none", background: "#0a58ca", color: "#fff", cursor: "pointer", marginRight: 8 };
const ghost: React.CSSProperties = { padding: "8px 14px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", cursor: "pointer" };
const panel: React.CSSProperties = { background: "var(--panel)", color: "var(--ink)", borderRadius: 12, padding: 18, boxShadow: "0 8px 22px rgba(15,23,42,.04)", border: "1px solid var(--line)", marginTop: 12 };
const sectionNav: React.CSSProperties = { display:"flex", gap:6, marginTop:16, padding:5, width:"fit-content", maxWidth:"100%", overflowX:"auto", border:"1px solid var(--line)", borderRadius:10, background:"var(--soft)" };
const sectionButton: React.CSSProperties = { display:"flex", alignItems:"center", gap:8, padding:"9px 14px", border:0, borderRadius:7, background:"transparent", color:"var(--muted)", fontWeight:700, cursor:"pointer", whiteSpace:"nowrap" };
const sectionButtonActive: React.CSSProperties = { background:"var(--panel)", color:"var(--ink)", boxShadow:"0 1px 4px rgba(15,23,42,.12)" };
const sectionCount: React.CSSProperties = { minWidth:22, padding:"2px 6px", borderRadius:999, background:"rgba(148,163,184,.18)", fontSize:12, textAlign:"center" };
const grid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))", gap: 12 };
const field: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4, fontSize: 13, color: "var(--ink)" };
const input: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--line)", fontSize: 14 };

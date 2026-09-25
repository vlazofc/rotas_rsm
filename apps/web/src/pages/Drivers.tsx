import { FormEvent, useEffect, useMemo, useState } from "react";
import api from "../services/api";
import {appConfirm,appPrompt} from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";

type Driver = {
  id: number;
  branch_id: number;
  branch_ids: number[];
  name: string;
  user_id?: number | null;
  employment_type: "proprio" | "agregado";
  daily_rate?: number | null;
  document?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  birth_date?: string | null;
  cnh_number?: string | null;
  cnh_category?: string | null;
  cnh_expiry_date?: string | null;
  antt_number?: string | null;
  antt_expiry_date?: string | null;
  registration_updated_at?: string | null;
  registration_due_date?: string | null;
  document_url?: string | null;
  cnh_url?: string | null;
  cnh_status: string;
  antt_status: string;
  registration_status: string;
  active: boolean;
  blocked: boolean;
  status_reason?: string | null;
};
type Settings = {
  cnh_alert_days: number;
  antt_alert_days: number;
  registration_renewal_months: number;
  registration_alert_days: number;
  statement_release_day: number;
};
type Branch = { id:number; name:string; tenant_id:number|null };
type DriverAccess = { id:number; name:string; login?:string|null; tenant_id?:number|null; branch_id?:number|null; active:boolean; blocked:boolean; linked_driver_id?:number|null };
const empty = {
  name: "",
  user_id: "",
  employment_type: "proprio",
  daily_rate: "",
  document: "",
  phone: "",
  email: "",
  address: "",
  city: "",
  state: "",
  postal_code: "",
  birth_date: "",
  cnh_number: "",
  cnh_category: "",
  cnh_expiry_date: "",
  antt_number: "",
  antt_expiry_date: "",
  registration_updated_at: new Date().toISOString().slice(0, 10),
  branch_ids: [] as number[],
};
const labels: Record<string, string> = {
  ok: "Em dia",
  warning: "Próximo do vencimento",
  expired: "Vencido",
  missing: "Não informado",
  not_applicable: "Não se aplica",
};

export default function Drivers() {
  const { user, hasRole } = useAuth(),
    [rows, setRows] = useState<Driver[]>([]),
    [settings, setSettings] = useState<Settings>({
      cnh_alert_days: 30,
      antt_alert_days: 30,
      registration_renewal_months: 12,
      registration_alert_days: 30,
      statement_release_day: 1,
    }),
    [editing, setEditing] = useState<Driver | "new" | null>(null),
    [settingsOpen, setSettingsOpen] = useState(false),
    [form, setForm] = useState({ ...empty }),
    [files, setFiles] = useState<{
      document_photo: File | null;
      cnh_document: File | null;
    }>({ document_photo: null, cnh_document: null }),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [error, setError] = useState("");
  const [branches,setBranches]=useState<Branch[]>([]);
  const [driverAccesses,setDriverAccesses]=useState<DriverAccess[]>([]);
  const canDelete = hasRole("admin_global");
  const load = () =>
    Promise.all([
      api.get<Driver[]>("/drivers"),
      api.get<Settings>("/drivers/settings/alerts"),
    ]).then(([d, s]) => {
      setRows(d.data);
      setSettings(s.data);
    });
  useEffect(() => {
    load().catch(() => {});
    api.get<Branch[]>("/branches").then(response=>setBranches(response.data.filter(branch=>user?.tenant_id==null||branch.tenant_id===user.tenant_id))).catch(()=>setBranches([]));
    api.get<DriverAccess[]>("/drivers/access-options").then(response=>setDriverAccesses(response.data)).catch(()=>setDriverAccesses([]));
  }, []);
  const filtered = useMemo(
    () =>
      rows.filter((row) => {
        const text =
          `${row.name} ${row.document || ""} ${row.cnh_number || ""} ${row.antt_number || ""} ${row.phone || ""}`.toLowerCase();
        const alert =
          [row.cnh_status, row.antt_status, row.registration_status].includes(
            "expired",
          ) ||
          [row.cnh_status, row.antt_status, row.registration_status].includes(
            "warning",
          );
        return (
          (!query || text.includes(query.toLowerCase())) &&
          (!status ||
            (status === "alert" && alert) ||
            (status === "active" && row.active) ||
            (status === "inactive" && !row.active))
        );
      }),
    [rows, query, status],
  );
  const alerts = rows.filter((row) =>
    [row.cnh_status, row.antt_status, row.registration_status].some(
      (value) => value === "expired" || value === "warning",
    ),
  ).length;
  function edit(row?: Driver) {
    setError("");
    setFiles({ document_photo: null, cnh_document: null });
    if (!row) {
      setForm({ ...empty });
      setEditing("new");
      return;
    }
    setForm({...empty,...Object.fromEntries(Object.keys(empty).filter(key=>key!=="branch_ids").map((key) => [key, String((row as any)[key] || "")])) as Partial<typeof empty>,branch_ids:row.branch_ids?.length?row.branch_ids:[row.branch_id]});
    setEditing(row);
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const payload = {
        branch_id: form.branch_ids[0] || user?.branch_id || 1,
        branch_ids: form.branch_ids,
        ...Object.fromEntries(
          Object.entries(form).filter(([key])=>key!=="branch_ids").map(([key, value]) => [key, value || null]),
        ),
        daily_rate: null,
        user_id: form.user_id ? Number(form.user_id) : null,
      };
      const response =
        editing === "new"
          ? await api.post<Driver>("/drivers", payload)
          : await api.put<Driver>(
              `/drivers/${(editing as Driver).id}`,
              payload,
            );
      if (files.document_photo || files.cnh_document) {
        const data = new FormData();
        if (files.document_photo)
          data.set("document_photo", files.document_photo);
        if (files.cnh_document) data.set("cnh_document", files.cnh_document);
        await api.post(`/drivers/${response.data.id}/documents`, data);
      }
      setEditing(null);
      await load();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Não foi possível salvar o motorista.",
      );
    }
  }
  async function changeStatus(row:Driver,action:"activate"|"deactivate"|"block"|"unblock") {
    let reason="";if(["deactivate","block"].includes(action)){const value=await appPrompt(`Informe o motivo para ${action==="block"?"bloquear":"desativar"} ${row.name}.`,{title:action==="block"?"Bloquear motorista":"Desativar motorista",label:"Motivo obrigatório",required:true,confirmLabel:action==="block"?"Bloquear":"Desativar"});if(value===null)return;reason=value}
    try{await api.post(`/drivers/${row.id}/status`,{action,reason:reason||null});await load()}catch(e:any){setError(e?.response?.data?.detail||"Não foi possível alterar a situação.")}
  }
  async function remove(row: Driver) {
    if (await appConfirm(`Excluir ${row.name}? Esta ação não poderá ser desfeita.`,{title:"Excluir motorista",confirmLabel:"Sim, excluir",danger:true})) {
      try {
        await api.delete(`/drivers/${row.id}`);
        load();
      } catch (e: any) {
        setError(e?.response?.data?.detail || "Não foi possível excluir.");
      }
    }
  }
  async function saveSettings(e: FormEvent) {
    e.preventDefault();
    try {
      await api.put("/drivers/settings/alerts", settings);
      setSettingsOpen(false);
      load();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Não foi possível salvar os parâmetros.",
      );
    }
  }
  return (
    <div className="drivers-page">
      <div className="page-header">
        <div>
          <h2>Motoristas</h2>
          <p className="page-subtitle">
            Cadastro documental, habilitação, RNTRC/ANTT e alertas de renovação.
          </p>
        </div>
        <div className="driver-header-actions">
          <button className="btn-ghost" onClick={() => setSettingsOpen(true)}>
            Parâmetros de alertas
          </button>
          <button className="btn-primary btn-add" onClick={() => edit()}>
            <span className="btn-add-symbol">+</span>Novo motorista
          </button>
        </div>
      </div>
      {error && <p className="modal-error">{error}</p>}
      <div className="driver-kpis">
        <article>
          <span>Ativos</span>
          <strong>{rows.filter((r) => r.active).length}</strong>
        </article>
        <article className={alerts ? "driver-alert" : ""}>
          <span>Exigem atenção</span>
          <strong>{alerts}</strong>
        </article>
        <article>
          <span>CNH vencida</span>
          <strong>
            {rows.filter((r) => r.cnh_status === "expired").length}
          </strong>
        </article>
        <article>
          <span>Cadastro a renovar</span>
          <strong>
            {
              rows.filter((r) =>
                ["expired", "warning"].includes(r.registration_status),
              ).length
            }
          </strong>
        </article>
      </div>
      <section className="card-panel driver-filters">
        <input
          className="input"
          placeholder="Buscar nome, CPF, CNH, RNTRC ou telefone"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="input"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">Todos</option>
          <option value="alert">Com alertas</option>
          <option value="active">Ativos</option>
          <option value="inactive">Inativos</option>
        </select>
      </section>
      <div className="driver-grid">
        {filtered.map((row) => (
          <article className="driver-card" key={row.id}>
            <header>
              <div className="driver-avatar">
                {row.name
                  .split(" ")
                  .map((v) => v[0])
                  .slice(0, 2)
                  .join("")}
              </div>
              <div>
                <h3>{row.name}</h3>
                <span>Motorista cadastrado</span>
              </div>
              <span className={`stock-badge ${row.active ? "ok" : row.blocked ? "expired" : ""}`} title={row.status_reason||""}>
                {row.blocked ? "Bloqueado" : row.active ? "Ativo" : "Inativo"}
              </span>
            </header>
            <dl>
              <div>
                <dt>Contato</dt>
                <dd>
                  {row.phone || "—"}
                  <br />
                  {row.email || "—"}
                </dd>
              </div>
              <div>
                <dt>CNH</dt>
                <dd>
                  {row.cnh_number || "—"}{" "}
                  {row.cnh_category && `· ${row.cnh_category}`}
                  <br />
                  <Status value={row.cnh_status} />
                </dd>
              </div>
              <div>
                <dt>RNTRC / ANTT</dt>
                <dd>
                  {row.antt_number || "Opcional"}
                  <br />
                  <Status value={row.antt_status} />
                </dd>
              </div>
              <div>
                <dt>Renovação cadastral</dt>
                <dd>
                  {row.registration_due_date || "Sem data-base"}
                  <br />
                  <Status value={row.registration_status} />
                </dd>
              </div>
            </dl>
            <div className="driver-docs">
              {row.document_url ? (
                <a href={row.document_url} target="_blank" rel="noreferrer">
                  Documento
                </a>
              ) : (
                <span>Documento pendente</span>
              )}
              {row.cnh_url ? (
                <a href={row.cnh_url} target="_blank" rel="noreferrer">
                  CNH digitalizada
                </a>
              ) : (
                <span>CNH pendente</span>
              )}
            </div>
            <footer>
              <button className="btn-mini" onClick={() => edit(row)}>
                Editar
              </button>
              {row.active?<><button className="btn-mini" onClick={()=>void changeStatus(row,"deactivate")}>Desativar</button><button className="btn-mini danger" onClick={()=>void changeStatus(row,"block")}>Bloquear</button></>:<button className="btn-mini" onClick={()=>void changeStatus(row,row.blocked?"unblock":"activate")}>{row.blocked?"Desbloquear":"Ativar"}</button>}
              {canDelete && (
                <button className="btn-mini danger" onClick={() => remove(row)}>
                  Excluir
                </button>
              )}
            </footer>
          </article>
        ))}
      </div>
      {editing && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
          <form
            className="modal-card driver-modal"
            onSubmit={save}
            onClick={(e) => e.stopPropagation()}
          >
            <h3>{editing === "new" ? "Novo motorista" : "Editar motorista"}</h3>
            <h4>Filiais onde pode atuar</h4>
            <p className="page-subtitle">Selecione explicitamente as unidades autorizadas. Novas filiais não serão incluídas automaticamente.</p>
            <div className="checkbox-grid">
              {branches.filter(branch => user?.tenant_id == null || branch.tenant_id === user.tenant_id).map(branch => (
                <label key={branch.id} className="check-row">
                  <input type="checkbox" checked={form.branch_ids.includes(branch.id)} onChange={(event) => setForm({
                    ...form,
                    branch_ids: event.target.checked
                      ? [...form.branch_ids, branch.id]
                      : form.branch_ids.filter(id => id !== branch.id),
                  })} />
                  <span>{branch.name}</span>
                </label>
              ))}
            </div>
            <h4>Dados pessoais e contato</h4>
            <div className="form-grid">
              <Field label="Acesso no app do motorista">
                <select
                  className="input"
                  value={form.user_id}
                  onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                >
                  <option value="">Sem acesso vinculado</option>
                  {driverAccesses
                    .filter(access => {
                      const selectedTenant = user?.tenant_id;
                      return selectedTenant == null || access.tenant_id === selectedTenant;
                    })
                    .filter(access => !access.linked_driver_id || access.linked_driver_id === (editing === "new" ? undefined : editing.id))
                    .map(access => (
                      <option key={access.id} value={access.id} disabled={!access.active || access.blocked}>
                        {access.name}{access.login ? ` (${access.login})` : ""}{!access.active || access.blocked ? " — indisponível" : ""}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="Nome completo">
                <input
                  className="input"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="CPF / documento">
                <input
                  className="input"
                  value={form.document}
                  onChange={(e) =>
                    setForm({ ...form, document: e.target.value })
                  }
                />
              </Field>
              <Field label="Nascimento">
                <input
                  className="input"
                  type="date"
                  value={form.birth_date}
                  onChange={(e) =>
                    setForm({ ...form, birth_date: e.target.value })
                  }
                />
              </Field>
              <Field label="Telefone">
                <input
                  className="input"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              </Field>
              <Field label="E-mail">
                <input
                  className="input"
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </Field>
              <Field label="Endereço">
                <input
                  className="input"
                  value={form.address}
                  onChange={(e) =>
                    setForm({ ...form, address: e.target.value })
                  }
                />
              </Field>
              <Field label="Cidade">
                <input
                  className="input"
                  value={form.city}
                  onChange={(e) => setForm({ ...form, city: e.target.value })}
                />
              </Field>
              <Field label="UF">
                <input
                  className="input"
                  maxLength={2}
                  value={form.state}
                  onChange={(e) =>
                    setForm({ ...form, state: e.target.value.toUpperCase() })
                  }
                />
              </Field>
              <Field label="CEP">
                <input
                  className="input"
                  value={form.postal_code}
                  onChange={(e) =>
                    setForm({ ...form, postal_code: e.target.value })
                  }
                />
              </Field>
            </div>
            <h4>Habilitação e registros</h4>
            <div className="form-grid">
              <Field label="Número da CNH">
                <input
                  className="input"
                  value={form.cnh_number}
                  onChange={(e) =>
                    setForm({ ...form, cnh_number: e.target.value })
                  }
                />
              </Field>
              <Field label="Categoria">
                <input
                  className="input"
                  placeholder="B, C, D, E..."
                  value={form.cnh_category}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      cnh_category: e.target.value.toUpperCase(),
                    })
                  }
                />
              </Field>
              <Field label="Vencimento da CNH">
                <input
                  className="input"
                  type="date"
                  value={form.cnh_expiry_date}
                  onChange={(e) =>
                    setForm({ ...form, cnh_expiry_date: e.target.value })
                  }
                />
              </Field>
              <Field label="RNTRC / ANTT (opcional)">
                <input
                  className="input"
                  value={form.antt_number}
                  onChange={(e) =>
                    setForm({ ...form, antt_number: e.target.value })
                  }
                />
              </Field>
              <Field label="Vencimento RNTRC / ANTT">
                <input
                  className="input"
                  type="date"
                  value={form.antt_expiry_date}
                  onChange={(e) =>
                    setForm({ ...form, antt_expiry_date: e.target.value })
                  }
                />
              </Field>
              <Field label="Última atualização cadastral">
                <input
                  className="input"
                  type="date"
                  value={form.registration_updated_at}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      registration_updated_at: e.target.value,
                    })
                  }
                />
              </Field>
            </div>
            <h4>Documentos digitalizados</h4>
            <div className="form-grid">
              <Field label="Foto do documento">
                <input
                  className="input"
                  type="file"
                  accept="image/*,application/pdf"
                  onChange={(e) =>
                    setFiles({
                      ...files,
                      document_photo: e.target.files?.[0] || null,
                    })
                  }
                />
              </Field>
              <Field label="Foto / PDF da CNH">
                <input
                  className="input"
                  type="file"
                  accept="image/*,application/pdf"
                  onChange={(e) =>
                    setFiles({
                      ...files,
                      cnh_document: e.target.files?.[0] || null,
                    })
                  }
                />
              </Field>
            </div>
            {error && <p className="modal-error">{error}</p>}
            <div className="modal-actions">
              <button className="btn-primary">Salvar motorista</button>
              <button
                className="btn-ghost"
                type="button"
                onClick={() => setEditing(null)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}
      {settingsOpen && (
        <div className="modal-backdrop" onClick={() => setSettingsOpen(false)}>
          <form
            className="modal-card"
            onSubmit={saveSettings}
            onClick={(e) => e.stopPropagation()}
          >
            <h3>Parâmetros de validade</h3>
            <p>
              Defina quando o sistema deve sinalizar documentos e renovação
              cadastral.
            </p>
            <div className="form-grid">
              <NumberField
                label="Alertar CNH com antecedência (dias)"
                value={settings.cnh_alert_days}
                onChange={(value) =>
                  setSettings({ ...settings, cnh_alert_days: value })
                }
              />
              <NumberField
                label="Alertar RNTRC/ANTT (dias)"
                value={settings.antt_alert_days}
                onChange={(value) =>
                  setSettings({ ...settings, antt_alert_days: value })
                }
              />
              <NumberField
                label="Renovar cadastro a cada (meses)"
                value={settings.registration_renewal_months}
                onChange={(value) =>
                  setSettings({
                    ...settings,
                    registration_renewal_months: value,
                  })
                }
              />
              <NumberField
                label="Alertar renovação cadastral (dias)"
                value={settings.registration_alert_days}
                onChange={(value) =>
                  setSettings({ ...settings, registration_alert_days: value })
                }
              />
              <NumberField label="Dia mensal para liberar o aceite do extrato" value={settings.statement_release_day} onChange={(value)=>setSettings({...settings,statement_release_day:Math.max(1,Math.min(28,value))})}/>
            </div>
            <div className="modal-actions">
              <button className="btn-primary">Salvar parâmetros</button>
              <button
                className="btn-ghost"
                type="button"
                onClick={() => setSettingsOpen(false)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
function Status({ value }: { value: string }) {
  return (
    <span className={`driver-status ${value}`}>{labels[value] || value}</span>
  );
}
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        className="input"
        type="number"
        min="1"
        required
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </Field>
  );
}

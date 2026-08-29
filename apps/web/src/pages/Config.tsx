import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import api from "../services/api";
import {appConfirm} from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";
import { useBranding } from "../context/BrandingContext";
import { LANGUAGES } from "../i18n";

interface Branch { id: number; name: string; locale: string; active: boolean; }
interface TenantItem {
  id: number; name: string; slug: string; country: string; active: boolean;
  feature_sharepoint_sync: boolean; feature_financeiro: boolean; feature_rastreamento: boolean;
  feature_route_optimization: boolean; feature_km_calculation: boolean;
  billing_plan?: string | null; billing_amount?: number | string | null; billing_due_day?: number | null;
  billing_last_payment_date?: string | null; billing_status?: string | null; billing_next_due_date?: string | null;
}
interface Driver { id: number; branch_id: number; name: string; document?: string; phone?: string; carrier?: string; active: boolean; }
interface Vehicle { id: number; branch_id: number; plate: string; description?: string; vehicle_type_id?: number | null; carrier_id?: number | null; carrier_name?: string | null; axles?: number | null; rear_dual_wheels?: boolean; temperature_controlled: boolean; active: boolean; }
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

type Tab = "company" | "branding" | "parameters" | "integrations";
interface CarrierItem { id: number; tenant_id: number | null; name: string; document: string | null; kind: "arrendatario" | "beneficiario"; active: boolean; }
interface CustomerItem { id: number; tenant_id: number; name: string; document: string | null; email: string | null; phone: string | null; address: string | null; active: boolean; }

export default function Config() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams();
  const routeTab = params.tab as Tab | undefined;
  const { user } = useAuth();

  const tabs: { key: Tab; label: string }[] = [
    { key: "company", label: "Dados da empresa" },
    { key: "branding", label: "Personalização" },
    { key: "parameters", label: "Parâmetros" },
    ...(user?.role === "admin_global" ? [{ key: "integrations" as Tab, label: "Integrações" }] : []),
  ];
  const tab = tabs.some((tb) => tb.key === routeTab) ? routeTab! : "company";

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
      {tab === "company" && <CompanyTab />}
      {tab === "branding" && <BrandingTab />}
      {tab === "parameters" && <SettingsCenter />}
      {tab === "integrations" && user?.role === "admin_global" && <TruckControlIntegration />}
    </div>
  );
}

type TruckControlStatus={configured:boolean;base_url:string;enabled:boolean;poll_interval_seconds:number;last_message_id:number;last_sync_at?:string|null;last_success_at?:string|null;last_vehicle_sync_at?:string|null;last_error?:string|null};
function TruckControlIntegration(){
  const[status,setStatus]=useState<TruckControlStatus|null>(null),[form,setForm]=useState({base_url:"",login:"",password:"",current_password:"",enabled:false}),[error,setError]=useState(""),[saved,setSaved]=useState(""),[busy,setBusy]=useState(false);
  const load=()=>api.get<TruckControlStatus>("/integrations/truckcontrol").then(r=>{setStatus(r.data);setForm(f=>({...f,base_url:r.data.base_url,enabled:r.data.enabled}))}).catch(e=>setError(e?.response?.data?.detail||"Não foi possível carregar a integração."));
  useEffect(()=>{void load()},[]);
  async function save(){setBusy(true);setError("");setSaved("");try{await api.put("/integrations/truckcontrol",{...form,login:form.login||null,password:form.password||null});setForm(f=>({...f,login:"",password:"",current_password:""}));setSaved("Configuração salva com credenciais criptografadas.");await load()}catch(e:any){setError(e?.response?.data?.detail||"Não foi possível salvar a integração.")}finally{setBusy(false)}}
  async function test(){setBusy(true);setError("");setSaved("");try{const r=await api.post("/integrations/truckcontrol/test",null,{params:{current_password:form.current_password}});setSaved(`Conexão validada: ${r.data.vehicles??0} veículos, ${r.data.linked??0} vinculados e ${r.data.received??0} posições recebidas.`);setForm(f=>({...f,current_password:""}));await load()}catch(e:any){setError(e?.response?.data?.detail||"Falha ao validar a conexão.")}finally{setBusy(false)}}
  const date=(value?:string|null)=>value?new Date(value).toLocaleString("pt-BR"):"Ainda não executado";
  return <section className="card-panel">
    <div className="section-heading"><div><h3>TruckControl</h3><p>Monitoramento exclusivo dos veículos próprios ativos, no menor intervalo permitido pelo fornecedor: 30 segundos. O vínculo das placas é atualizado a cada 5 minutos.</p></div><span className={`stock-badge ${status?.enabled?"ok":""}`}>{status?.enabled?"Ativa":"Inativa"}</span></div>
    {error&&<p className="modal-error">{error}</p>}{saved&&<p className="workflow-resolution">{saved}</p>}
    <div className="settings-info-grid"><article><strong>Última sincronização</strong><p>{date(status?.last_sync_at)}</p></article><article><strong>Último sucesso</strong><p>{date(status?.last_success_at)}</p></article><article><strong>Cursor de mensagens</strong><p>{status?.last_message_id??1}</p></article></div>
    {status?.last_error&&<p className="modal-error">Última falha: {status.last_error}</p>}
    <div className="form-grid">
      <Field label="URL HTTPS do webservice"><input className="input" value={form.base_url} onChange={e=>setForm({...form,base_url:e.target.value})}/></Field>
      <Field label="Login TruckControl"><input className="input" autoComplete="off" placeholder={status?.configured?"Deixe vazio para manter":"Informe o login"} value={form.login} onChange={e=>setForm({...form,login:e.target.value})}/></Field>
      <Field label="Senha TruckControl"><input className="input" type="password" autoComplete="new-password" placeholder={status?.configured?"Deixe vazio para manter":"Informe a senha"} value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/></Field>
      <Field label="Sua senha atual (confirmação)"><input className="input" type="password" autoComplete="current-password" value={form.current_password} onChange={e=>setForm({...form,current_password:e.target.value})}/></Field>
    </div>
    <label className="settings-rule-card" style={{marginTop:16}}><input type="checkbox" checked={form.enabled} onChange={e=>setForm({...form,enabled:e.target.checked})}/><span><strong>Ativar sincronização automática</strong><small>Somente ative após validar a conexão e o vínculo das placas.</small></span></label>
    <div style={{marginTop:16}}><button className="btn-primary" disabled={busy||!form.current_password} onClick={()=>void save()}>{busy?"Processando...":"Salvar configuração"}</button><button className="btn-secondary" disabled={busy||!status?.configured||!form.current_password} onClick={()=>void test()}>Testar agora</button></div>
    <p style={muted}>As credenciais nunca são devolvidas ao navegador. Alterações e testes exigem perfil de administrador global e confirmação da sua senha.</p>
  </section>
}

type CompanyData = {legal_name:string;document:string;state_registration:string;address:string;city:string;state:string;postal_code:string;phone:string;email:string;antt_number:string;antt_expiry_date:string;partners:string};
const emptyCompany:CompanyData={legal_name:"",document:"",state_registration:"",address:"",city:"",state:"",postal_code:"",phone:"",email:"",antt_number:"",antt_expiry_date:"",partners:""};
function CompanyTab(){
  const [form,setForm]=useState<CompanyData>(emptyCompany),[loading,setLoading]=useState(true),[error,setError]=useState(""),[saved,setSaved]=useState("");
  useEffect(()=>{api.get("/tenants/me").then(response=>setForm(Object.fromEntries(Object.keys(emptyCompany).map(key=>[key,response.data[key]??""])) as CompanyData)).catch((e)=>setError(e?.response?.data?.detail||"Não foi possível carregar os dados da empresa.")).finally(()=>setLoading(false))},[]);
  async function save(){setError("");setSaved("");try{const response=await api.put<CompanyData>("/tenants/me/company",{...form,antt_expiry_date:form.antt_expiry_date||null} as any);setForm(Object.fromEntries(Object.keys(emptyCompany).map(key=>[key,(response.data as any)[key]??""])) as CompanyData);setSaved("Dados da empresa salvos. A frota própria usará este cadastro automaticamente.")}catch(e:any){setError(e?.response?.data?.detail||"Não foi possível salvar os dados da empresa.")}}
  if(loading)return <div className="card-panel empty-state">Carregando dados da empresa...</div>;
  return <section className="card-panel company-registration">
    <div className="section-heading"><div><h3>Empresa contratante</h3><p>Cadastro institucional usado automaticamente como proprietário dos veículos de frota própria.</p></div><button className="btn-primary" onClick={()=>void save()}>Salvar dados</button></div>
    {error&&<p className="modal-error">{error}</p>}{saved&&<p className="workflow-resolution">{saved}</p>}
    <h4>Identificação</h4><div className="form-grid">
      <Field label="Razão social *"><input className="input" required value={form.legal_name} onChange={e=>setForm({...form,legal_name:e.target.value})}/></Field>
      <Field label="CNPJ *"><input className="input" required inputMode="numeric" value={form.document} onChange={e=>setForm({...form,document:e.target.value})}/></Field>
      <Field label="Inscrição estadual"><input className="input" value={form.state_registration} onChange={e=>setForm({...form,state_registration:e.target.value})}/></Field>
      <Field label="Telefone"><input className="input" value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})}/></Field>
      <Field label="E-mail"><input className="input" type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/></Field>
    </div>
    <h4>Endereço</h4><div className="form-grid">
      <Field label="Endereço completo *"><input className="input" required value={form.address} onChange={e=>setForm({...form,address:e.target.value})}/></Field>
      <Field label="Cidade *"><input className="input" required value={form.city} onChange={e=>setForm({...form,city:e.target.value})}/></Field>
      <Field label="UF *"><input className="input" required maxLength={2} value={form.state} onChange={e=>setForm({...form,state:e.target.value.toUpperCase()})}/></Field>
      <Field label="CEP"><input className="input" value={form.postal_code} onChange={e=>setForm({...form,postal_code:e.target.value})}/></Field>
    </div>
    <h4>ANTT e quadro societário</h4><div className="form-grid">
      <Field label="ANTT / RNTRC *"><input className="input" required value={form.antt_number} onChange={e=>setForm({...form,antt_number:e.target.value.toUpperCase()})}/></Field>
      <Field label="Validade da ANTT"><input className="input" type="date" value={form.antt_expiry_date} onChange={e=>setForm({...form,antt_expiry_date:e.target.value})}/></Field>
      <label className="field company-partners"><span>Sócios / responsáveis legais</span><textarea className="input" rows={4} placeholder="Informe nome, CPF e função de cada sócio ou responsável." value={form.partners} onChange={e=>setForm({...form,partners:e.target.value})}/></label>
    </div>
    <div className="company-auto-note"><strong>Preenchimento automático da frota própria</strong><span>Ao cadastrar ou editar um veículo próprio, o sistema vinculará esta empresa como proprietária e copiará a ANTT vigente para o veículo.</span></div>
  </section>
}

type OperationalRules = {
  require_manual_justification:boolean;require_checkin_before_delivery:boolean;require_delivery_proof:boolean;
  require_failure_proof:boolean;require_warehouse_return_proof:boolean;require_failure_reason:boolean;require_returned_quantity:boolean;
};
type DriverParameters = {cnh_alert_days:number;antt_alert_days:number;registration_renewal_months:number;registration_alert_days:number;statement_release_day:number};
type AlertParameters = {alert_due_days:number;alert_document_days:number;tire_warning_mm:number;tire_critical_mm:number};
const ruleLabels:Record<keyof OperationalRules,{title:string;description:string}>={
  require_manual_justification:{title:"Justificativa para alteração manual",description:"Exige motivo quando a operação altera dados calculados ou importados."},
  require_checkin_before_delivery:{title:"Check-in antes da entrega",description:"Impede concluir a entrega sem registrar a chegada ao destino."},
  require_delivery_proof:{title:"Comprovante de entrega",description:"Exige foto ou documento para finalizar uma entrega."},
  require_failure_proof:{title:"Comprovante de insucesso",description:"Exige evidência quando uma entrega não for concluída."},
  require_warehouse_return_proof:{title:"Comprovante de devolução ao armazém",description:"Exige evidência da entrega física dos itens devolvidos."},
  require_failure_reason:{title:"Motivo de insucesso",description:"Obriga a seleção de um motivo cadastrado para a ocorrência."},
  require_returned_quantity:{title:"Quantidade devolvida",description:"Exige informar a quantidade quando houver devolução."},
};

function SettingsCenter(){
  const [section,setSection]=useState<"rules"|"alerts"|"parameters">("rules"),[rules,setRules]=useState<OperationalRules|null>(null),[drivers,setDrivers]=useState<DriverParameters|null>(null),[alerts,setAlerts]=useState<AlertParameters|null>(null),[error,setError]=useState(""),[saved,setSaved]=useState("");
  useEffect(()=>{Promise.all([api.get<OperationalRules>("/operational-settings"),api.get<DriverParameters>("/drivers/settings/alerts"),api.get<AlertParameters>("/operational-settings/alerts")]).then(([r,d,a])=>{setRules(r.data);setDrivers(d.data);setAlerts(a.data)}).catch((e)=>setError(e?.response?.data?.detail||"Não foi possível carregar as configurações."))},[]);
  async function saveRules(){if(!rules)return;setError("");try{setRules((await api.put<OperationalRules>("/operational-settings",rules)).data);setSaved("Regras operacionais salvas.")}catch(e:any){setError(e?.response?.data?.detail||"Não foi possível salvar as regras.")}}
  async function saveDriverSettings(){if(!drivers)return;setError("");try{setDrivers((await api.put<DriverParameters>("/drivers/settings/alerts",drivers)).data);setSaved("Alertas e parâmetros salvos.")}catch(e:any){setError(e?.response?.data?.detail||"Não foi possível salvar os parâmetros.")}}
  async function saveAlerts(){if(!alerts||!drivers)return;setError("");try{const[a,d]=await Promise.all([api.put<AlertParameters>("/operational-settings/alerts",alerts),api.put<DriverParameters>("/drivers/settings/alerts",drivers)]);setAlerts(a.data);setDrivers(d.data);setSaved("Parâmetros de alertas salvos.")}catch(e:any){setError(e?.response?.data?.detail||"Não foi possível salvar os alertas.")}}
  return <section className="settings-center">
    <div className="card-panel"><div className="workflow-filter"><button className={section==="rules"?"active":""} onClick={()=>setSection("rules")}>Regras</button><button className={section==="alerts"?"active":""} onClick={()=>setSection("alerts")}>Alertas</button><button className={section==="parameters"?"active":""} onClick={()=>setSection("parameters")}>Parâmetros</button></div></div>
    {error&&<p className="modal-error">{error}</p>}{saved&&<p className="workflow-resolution">{saved}</p>}
    {section==="rules"&&<div className="card-panel"><div className="section-heading"><div><h3>Regras operacionais</h3><p>Obrigatoriedades aplicadas às rotas, entregas, ocorrências e devoluções.</p></div><button className="btn-primary" disabled={!rules} onClick={()=>void saveRules()}>Salvar regras</button></div>{rules&&<div className="settings-rule-grid">{(Object.keys(ruleLabels) as Array<keyof OperationalRules>).map(key=><label className="settings-rule-card" key={key}><input type="checkbox" checked={rules[key]} onChange={e=>{setSaved("");setRules({...rules,[key]:e.target.checked})}}/><span><strong>{ruleLabels[key].title}</strong><small>{ruleLabels[key].description}</small></span></label>)}</div>}</div>}
    {section==="alerts"&&<div className="card-panel"><div className="section-heading"><div><h3>Alertas</h3><p>Limites usados pela central para classificar riscos e antecipar vencimentos.</p></div><button className="btn-primary" disabled={!drivers||!alerts} onClick={()=>void saveAlerts()}>Salvar alertas</button></div>{drivers&&alerts&&<div className="form-grid"><ConfigNumber label="Financeiro, compras e manutenção — antecedência" suffix="dias" value={alerts.alert_due_days} min={1} max={90} onChange={value=>{setSaved("");setAlerts({...alerts,alert_due_days:value})}}/><ConfigNumber label="CRLV — alertar com antecedência" suffix="dias" value={alerts.alert_document_days} min={1} max={365} onChange={value=>{setSaved("");setAlerts({...alerts,alert_document_days:value})}}/><ConfigNumber label="Sulco do pneu — atenção" suffix="mm" value={alerts.tire_warning_mm} min={0} max={30} step={0.1} onChange={value=>{setSaved("");setAlerts({...alerts,tire_warning_mm:value})}}/><ConfigNumber label="Sulco do pneu — crítico" suffix="mm" value={alerts.tire_critical_mm} min={0} max={30} step={0.1} onChange={value=>{setSaved("");setAlerts({...alerts,tire_critical_mm:value})}}/><ConfigNumber label="CNH — alertar com antecedência" suffix="dias" value={drivers.cnh_alert_days} min={1} max={365} onChange={value=>{setSaved("");setDrivers({...drivers,cnh_alert_days:value})}}/><ConfigNumber label="RNTRC/ANTT — alertar com antecedência" suffix="dias" value={drivers.antt_alert_days} min={1} max={365} onChange={value=>{setSaved("");setDrivers({...drivers,antt_alert_days:value})}}/><ConfigNumber label="Renovação cadastral — alertar antes" suffix="dias" value={drivers.registration_alert_days} min={1} max={365} onChange={value=>{setSaved("");setDrivers({...drivers,registration_alert_days:value})}}/></div>}<div className="settings-info-grid"><article><strong>Críticos</strong><p>Vencidos, atrasados, sem estoque, ocorrências críticas, tarefas prioridade zero e pneus no limite.</p></article><article><strong>Atenção</strong><p>Itens próximos do prazo, estoque mínimo, tarefas prioritárias e documentos a vencer.</p></article><article><strong>Informativos</strong><p>Dados que precisam ser completados, como pneus ainda sem medição de sulco.</p></article></div></div>}
    {section==="parameters"&&<div className="card-panel"><div className="section-heading"><div><h3>Parâmetros gerais</h3><p>Valores que controlam periodicidade e liberação dos processos.</p></div><button className="btn-primary" disabled={!drivers} onClick={()=>void saveDriverSettings()}>Salvar parâmetros</button></div>{drivers&&<div className="form-grid"><ConfigNumber label="Renovar cadastro do motorista a cada" suffix="meses" value={drivers.registration_renewal_months} min={1} max={60} onChange={value=>{setSaved("");setDrivers({...drivers,registration_renewal_months:value})}}/><ConfigNumber label="Dia mensal para liberar aceite do extrato" suffix="dia do mês" value={drivers.statement_release_day} min={1} max={28} onChange={value=>{setSaved("");setDrivers({...drivers,statement_release_day:value})}}/></div>}<div className="settings-info-grid"><article><strong>Compras</strong><p>O prazo de entrega e o SLA são definidos individualmente ao executar cada compra.</p></article><article><strong>Manutenção</strong><p>A previsão de conclusão é definida em cada ordem de serviço e alimenta os alertas de SLA.</p></article><article><strong>Financeiro</strong><p>Vencimentos, recorrências e períodos são definidos em cada lançamento para preservar a rastreabilidade.</p></article></div></div>}
  </section>;
}

function ConfigNumber({label,suffix,value,min,max,step=1,onChange}:{label:string;suffix:string;value:number;min:number;max:number;step?:number;onChange:(value:number)=>void}){return <label className="field"><span>{label}</span><div className="settings-number"><input className="input" type="number" required min={min} max={max} step={step} value={value} onChange={e=>onChange(Number(e.target.value))}/><small>{suffix}</small></div></label>}

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
    if (!await appConfirm(t("config.delete_confirm", { name: role.label }) ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
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
    if (!await appConfirm(t("config.delete_confirm", { name: r.label }) ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
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
    if (!await appConfirm(t("config.delete_confirm", { name: b.name }) ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
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
    if (!await appConfirm(t("config.delete_confirm", { name: d.name }) ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
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
  const [owners, setOwners] = useState<CarrierItem[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const empty = { plate: "", description: "", vehicle_type_id: "", carrier_id: "", axles: "2", rear_dual_wheels: true, temperature_controlled: false };
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
    api.get("/carriers", { params: { only_active: true } }).then((r) => setOwners(r.data)).catch(() => setOwners([]));
  };
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm({ ...empty }); setEditing("new"); }
  function startEdit(v: Vehicle) {
    setError("");
    setForm({ plate: v.plate, description: v.description ?? "", vehicle_type_id: v.vehicle_type_id ? String(v.vehicle_type_id) : "", carrier_id: v.carrier_id ? String(v.carrier_id) : "", axles: String(v.axles ?? 2), rear_dual_wheels: v.rear_dual_wheels ?? true, temperature_controlled: v.temperature_controlled });
    setEditing(v.id);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const payload = { ...form, vehicle_type_id: form.vehicle_type_id ? Number(form.vehicle_type_id) : null, carrier_id: form.carrier_id ? Number(form.carrier_id) : null, axles: Number(form.axles) };
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
    if (!await appConfirm(t("config.delete_confirm", { name: v.plate }) ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
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
            <Field label={t("config.carrier")}><select style={input} value={form.carrier_id} onChange={(e) => setForm({ ...form, carrier_id: e.target.value })}><option value="">—</option>{owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.name}</option>)}</select></Field>
            <Field label="Quantidade de eixos"><input style={input} type="number" min={2} max={5} required value={form.axles} onChange={(e) => setForm({ ...form, axles: e.target.value })} /></Field>
            <Field label="Rodagem traseira"><select style={input} value={form.rear_dual_wheels ? "dupla" : "simples"} onChange={(e) => setForm({ ...form, rear_dual_wheels: e.target.value === "dupla" })}><option value="dupla">Dupla — 4 pneus por eixo</option><option value="simples">Simples — 2 pneus por eixo</option></select></Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table
        head={[t("config.plate"), t("config.description"), t("config.vehicle_type"), "Configuração", t("config.carrier"), t("config.temperature"), t("users.active"), t("users.actions")]}
      >
        {rows.map((v) => (
          <tr key={v.id} style={{ ...rowStyle, opacity: v.active ? 1 : 0.5 }}>
            <td style={td}>{v.plate}</td>
            <td style={td}>{v.description ?? "—"}</td>
            <td style={td}>{typeLabelById(v.vehicle_type_id)}</td>
            <td style={td}>{v.axles ?? 2} eixos · rodagem {v.rear_dual_wheels === false ? "simples" : "dupla"}</td>
            <td style={td}>{v.carrier_name ?? "—"}</td>
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
    if (!await appConfirm(t("config.delete_confirm", { name: vt.label }) ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
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

// --------------------------------------------- Arrendatários / Beneficiários
function CarriersTab() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canDelete = hasRole("admin_global");
  const [rows, setRows] = useState<CarrierItem[]>([]);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [form, setForm] = useState({ name: "", document: "", kind: "arrendatario" as "arrendatario" | "beneficiario" });
  const [error, setError] = useState("");

  const reload = () => api.get("/carriers").then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { reload(); }, []);

  function startNew() { setError(""); setForm({ name: "", document: "", kind: "arrendatario" }); setEditing("new"); }
  function startEdit(c: CarrierItem) { setError(""); setForm({ name: c.name, document: c.document ?? "", kind: c.kind }); setEditing(c.id); }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setError("");
    const body = { name: form.name, document: form.document || null, kind: form.kind };
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
    if (!await appConfirm(t("config.delete_confirm", { name: c.name }) ?? "",{title:"Confirmar exclusão",confirmLabel:"Sim, excluir",danger:true})) return;
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
            <Field label="Tipo"><select style={input} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as "arrendatario" | "beneficiario" })}><option value="arrendatario">Arrendatário</option><option value="beneficiario">Beneficiário</option></select></Field>
          </div>
          <FormButtons onCancel={() => setEditing(null)} />
        </form>
      )}
      <Table head={[t("config.name"), "Tipo", t("config.carrier_document"), t("users.active"), t("users.actions")]}>
        {rows.map((c) => (
          <tr key={c.id} style={{ ...rowStyle, opacity: c.active ? 1 : 0.5 }}>
            <td style={td}>{c.name}</td>
            <td style={td}>{c.kind === "beneficiario" ? "Beneficiário" : "Arrendatário"}</td>
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
  const [form, setForm] = useState({ app_name: "", app_subtitle: "", login_intro_text: "", login_layout: "centered" as "centered"|"institutional"|"side_form", primary_color: "#12a386", sidebar_background_color:"#ffffff", sidebar_text_color:"#334155", sidebar_active_color:"#12a386" });
  const [enabledLocales, setEnabledLocales] = useState<string[]>(LANGUAGES.map((l) => l.code));
  const [topbarExtendsSidebar, setTopbarExtendsSidebar] = useState(true);
  const [logo, setLogo] = useState<File | null>(null);
  const [logoRail, setLogoRail] = useState<File | null>(null);
  const [background, setBackground] = useState<File | null>(null);
  const [favicon, setFavicon] = useState<File | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (loaded) return;
    setForm({
      app_name: branding.app_name ?? "",
      app_subtitle: branding.app_subtitle ?? "",
      login_intro_text: branding.login_intro_text ?? "",
      login_layout: branding.login_layout ?? "centered",
      primary_color: branding.primary_color ?? "#12a386",
      sidebar_background_color: branding.sidebar_background_color ?? "#ffffff",
      sidebar_text_color: branding.sidebar_text_color ?? "#334155",
      sidebar_active_color: branding.sidebar_active_color ?? branding.primary_color ?? "#12a386",
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
    payload.set("login_intro_text", form.login_intro_text.trim());
    payload.set("login_layout", form.login_layout);
    payload.set("primary_color", form.primary_color);
    payload.set("sidebar_background_color",form.sidebar_background_color);payload.set("sidebar_text_color",form.sidebar_text_color);payload.set("sidebar_active_color",form.sidebar_active_color);
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
      setOpen(false);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("config.save_error"));
    }
  }

  async function removeImage(kind: "logo" | "logo_rail" | "background" | "favicon") {
    setError(""); setSuccess("");
    const payload = new FormData();
    payload.set("app_name", form.app_name.trim());
    payload.set("app_subtitle", form.app_subtitle.trim());
    payload.set("login_intro_text", form.login_intro_text.trim());
    payload.set("login_layout", form.login_layout);
    payload.set("primary_color", form.primary_color);
    payload.set("sidebar_background_color",form.sidebar_background_color);payload.set("sidebar_text_color",form.sidebar_text_color);payload.set("sidebar_active_color",form.sidebar_active_color);
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
      <div className="card-panel" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div><strong>{branding.app_name || "Rotas Brasil RSM"}</strong><p style={{ ...subtitle, marginBottom: 0 }}>Cor principal: {branding.primary_color || "#12a386"}</p></div>
        <button type="button" className="btn-primary" onClick={() => { setError(""); setSuccess(""); setOpen(true); }}>Editar personalização</button>
      </div>
      {open && <div className="modal-backdrop" onClick={() => setOpen(false)}>
      <form onSubmit={save} className="modal-card driver-modal" onClick={(event) => event.stopPropagation()}>
        <h3>{t("config.tabs.branding")}</h3>
        <div style={grid}>
          <Field label={t("config.branding_app_name")}>
            <input style={input} value={form.app_name} placeholder="Rotas Brasil RSM"
              onChange={(e) => setForm({ ...form, app_name: e.target.value })} />
          </Field>
          <Field label={t("config.branding_app_subtitle")}>
            <input style={input} value={form.app_subtitle} placeholder={t("app.subtitle")}
              onChange={(e) => setForm({ ...form, app_subtitle: e.target.value })} />
          </Field>
          <Field label="Texto introdutório do login">
            <textarea style={textarea} maxLength={1000} rows={4} value={form.login_intro_text} placeholder="Apresente sua empresa, operação ou uma orientação de acesso."
              onChange={(e) => setForm({ ...form, login_intro_text: e.target.value })} />
          </Field>
          <Field label="Layout da tela de login">
            <div className="login-layout-picker">
              {([['centered','Cartão central'],['institutional','Identidade + acesso'],['side_form','Acesso + apresentação']] as const).map(([value,label])=><button type="button" key={value} className={form.login_layout===value?'active':''} onClick={()=>setForm({...form,login_layout:value})}><span className={`layout-mini layout-mini-${value}`}><i/><b/></span><small>{label}</small></button>)}
            </div>
          </Field>
          <Field label={t("config.branding_color")}>
            <input style={{ ...input, height: 40, padding: 4 }} type="color" value={form.primary_color}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })} />
          </Field>
          <Field label="Fundo da barra de navegação"><input style={{...input,height:40,padding:4}} type="color" value={form.sidebar_background_color} onChange={e=>setForm({...form,sidebar_background_color:e.target.value})}/></Field>
          <Field label="Texto da barra de navegação"><input style={{...input,height:40,padding:4}} type="color" value={form.sidebar_text_color} onChange={e=>setForm({...form,sidebar_text_color:e.target.value})}/></Field>
          <Field label="Item ativo da navegação"><input style={{...input,height:40,padding:4}} type="color" value={form.sidebar_active_color} onChange={e=>setForm({...form,sidebar_active_color:e.target.value})}/></Field>
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
          <button type="button" className="btn-ghost" style={{ marginLeft: 8 }} onClick={() => setOpen(false)}>{t("common.cancel")}</button>
        </div>
      </form>
      </div>}
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
    feature_sharepoint_sync: false, feature_financeiro: true, feature_rastreamento: true, feature_route_optimization: true, feature_km_calculation: true,
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
      feature_sharepoint_sync: item.feature_sharepoint_sync,
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

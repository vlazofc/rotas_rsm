import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../services/api";
import {appAlert,appConfirm} from "../components/AppDialog";
import { useAuth } from "../context/AuthContext";

type Part = {
  id: number;
  sku: string;
  name: string;
  unit: string;
  quantity: number;
  minimum_quantity: number;
  average_cost?: number | null;
};
type Content = { id: number; title: string; body?: string; kind: string };
type Occurrence = {
  stop_id: number;
  codigo_ut: string;
  date: string;
  plate?: string;
  customer: string;
  status: string;
};
type Statement = {
  id: string;
  date: string;
  kind: string;
  description: string;
  route?: string;
  amount: number;
};
type PartForm = {
  sku: string;
  name: string;
  unit: string;
  minimum_quantity: string;
  average_cost: string;
};
const blankPart: PartForm = {
  sku: "",
  name: "",
  unit: "un",
  minimum_quantity: "0",
  average_cost: "",
};

export default function ERP() {
  const { user, hasRole } = useAuth();
  const [params, setParams] = useSearchParams();
  const valid = ["occurrences", "finance", "stock", "content"];
  const requestedTab = params.get("tab") || "occurrences";
  const tab = valid.includes(requestedTab) ? requestedTab : "occurrences";
  const [parts, setParts] = useState<Part[]>([]),
    [content, setContent] = useState<Content[]>([]),
    [occurrences, setOccurrences] = useState<Occurrence[]>([]);
  const [dre, setDre] = useState({
    revenue: 0,
    expense: 0,
    result: 0,
    margin_percent: 0,
  });
  const [post, setPost] = useState({
    title: "",
    body: "",
    kind: "comunicado",
    published: true,
  });
  const [contentOpen, setContentOpen] = useState(false);
  const [partForm, setPartForm] = useState<PartForm>(blankPart),
    [editingPart, setEditingPart] = useState<Part | "new" | null>(null);
  const [movingPart, setMovingPart] = useState<Part | null>(null),
    [movement, setMovement] = useState({
      kind: "entrada",
      quantity: "",
      unit_cost: "",
      reference: "",
    });
  const [query, setQuery] = useState(""),
    [stockFilter, setStockFilter] = useState("all"),
    [error, setError] = useState("");
  const manager = hasRole("admin_global", "gestor_brasil");
  const financeAccess = hasRole(
    "admin_global",
    "gestor_brasil",
    "gestor_financeiro",
  );
  const setTab = (next: string) => {
    setParams({ tab: next }, { replace: true });
  };

  const load = useCallback(async () => {
    const [o, c] = await Promise.all([
      api.get("/erp/occurrences"),
      api.get("/erp/content"),
    ]);
    setOccurrences(o.data);
    setContent(c.data);
    if (manager) setParts((await api.get("/erp/parts")).data);
    if (financeAccess) setDre((await api.get("/erp/dre")).data);
  }, [financeAccess, manager]);
  useEffect(() => {
    void load().catch(() => {});
  }, [load]);

  function openNew() {
    setPartForm(blankPart);
    setEditingPart("new");
    setError("");
  }
  function openEdit(part: Part) {
    setPartForm({
      sku: part.sku,
      name: part.name,
      unit: part.unit,
      minimum_quantity: String(part.minimum_quantity),
      average_cost: part.average_cost != null ? String(part.average_cost) : "",
    });
    setEditingPart(part);
    setError("");
  }
  async function savePart(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const payload = {
        sku: partForm.sku.trim(),
        name: partForm.name.trim(),
        unit: partForm.unit,
        minimum_quantity: Number(partForm.minimum_quantity || 0),
        average_cost: partForm.average_cost
          ? Number(partForm.average_cost)
          : null,
      };
      if (editingPart === "new")
        await api.post("/erp/parts", {
          ...payload,
          branch_id: user!.branch_id,
        });
      else if (editingPart)
        await api.put(`/erp/parts/${editingPart.id}`, payload);
      setEditingPart(null);
      await load();
    } catch (requestError: any) {
      setError(
        requestError?.response?.data?.detail ||
          "Não foi possível salvar o item.",
      );
    }
  }
  function openMovement(part: Part, kind = "entrada") {
    setMovingPart(part);
    setMovement({
      kind,
      quantity: "",
      unit_cost: part.average_cost != null ? String(part.average_cost) : "",
      reference: "",
    });
    setError("");
  }
  async function saveMovement(event: FormEvent) {
    event.preventDefault();
    if (!movingPart) return;
    setError("");
    try {
      await api.post(`/erp/parts/${movingPart.id}/movements`, {
        kind: movement.kind,
        quantity: Number(movement.quantity),
        unit_cost: movement.unit_cost ? Number(movement.unit_cost) : null,
        reference: movement.reference || null,
      });
      setMovingPart(null);
      await load();
    } catch (requestError: any) {
      setError(
        requestError?.response?.data?.detail ||
          "Não foi possível registrar a movimentação.",
      );
    }
  }
  async function removePart(part: Part) {
    if (
      !await appConfirm(
        `Desativar ${part.name} do estoque? O histórico será preservado.`,
        {title:"Desativar item",confirmLabel:"Sim, desativar",danger:true},
      )
    )
      return;
    try {
      await api.delete(`/erp/parts/${part.id}`);
      await load();
    } catch (requestError: any) {
      await appAlert(
        requestError?.response?.data?.detail ||
          "Não foi possível excluir o item.",
        {title:"Falha ao desativar item"},
      );
    }
  }
  async function addPost(event: FormEvent) {
    event.preventDefault();
    await api.post("/erp/content", { ...post, branch_id: user!.branch_id });
    setPost({ title: "", body: "", kind: "comunicado", published: true });
    setContentOpen(false);
    await load();
  }
  const money = (value: number) =>
    value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const filteredParts = useMemo(
    () =>
      parts.filter((part) => {
        const matchText =
          !query ||
          `${part.sku} ${part.name}`
            .toLowerCase()
            .includes(query.toLowerCase());
        const low = part.quantity <= part.minimum_quantity;
        return (
          matchText &&
          (stockFilter === "all" ||
            (stockFilter === "low" && low) ||
            (stockFilter === "available" && !low))
        );
      }),
    [parts, query, stockFilter],
  );
  const stockStats = useMemo(
    () => ({
      items: parts.length,
      units: parts.reduce((sum, part) => sum + Number(part.quantity), 0),
      low: parts.filter((part) => part.quantity <= part.minimum_quantity)
        .length,
      value: parts.reduce(
        (sum, part) =>
          sum + Number(part.quantity) * Number(part.average_cost || 0),
        0,
      ),
    }),
    [parts],
  );

  return (
    <div className="page-card">
      <div className="page-header">
        <div>
          <h1>{tab === "stock" ? "Estoque de peças" : "ERP administrativo"}</h1>
          {tab === "stock" && (
            <p className="page-subtitle">
              Controle de saldos, níveis mínimos e movimentações da frota.
            </p>
          )}
        </div>
        {tab === "stock" && manager && (
          <button className="btn-primary btn-add" onClick={openNew}>
            <span className="btn-add-symbol">+</span>
            <span>Novo item</span>
          </button>
        )}
      </div>
      {tab !== "stock" && (
        <div className="tabs">
          {[
            ["occurrences", "Ocorrências"],
            ["finance", "Dashboard financeiro"],
            ["content", "Conteúdo"],
          ].map((item) => (
            <button
              key={item[0]}
              className={tab === item[0] ? "tab active" : "tab"}
              onClick={() => setTab(item[0])}
            >
              {item[1]}
            </button>
          ))}
        </div>
      )}
      {tab === "occurrences" && (
        <table>
          <thead>
            <tr>
              <th>Data</th>
              <th>Rota</th>
              <th>Placa</th>
              <th>Cliente</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {occurrences.map((item) => (
              <tr key={item.stop_id}>
                <td>{item.date}</td>
                <td>{item.codigo_ut}</td>
                <td>{item.plate || "-"}</td>
                <td>{item.customer}</td>
                <td>{item.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {tab === "finance" && (
        <div className="summary-grid">
          {[
            ["Receitas", dre.revenue],
            ["Despesas", dre.expense],
            ["Resultado", dre.result],
          ].map((item) => (
            <div className="summary-card" key={String(item[0])}>
              <span>{item[0]}</span>
              <strong>{money(Number(item[1]))}</strong>
            </div>
          ))}
          <div className="summary-card">
            <span>Margem</span>
            <strong>{dre.margin_percent}%</strong>
          </div>
        </div>
      )}
      {tab === "stock" && (
        <StockView
          parts={filteredParts}
          stats={stockStats}
          query={query}
          setQuery={setQuery}
          stockFilter={stockFilter}
          setStockFilter={setStockFilter}
          onEdit={openEdit}
          onMove={openMovement}
          onRemove={removePart}
        />
      )}
      {tab === "content" && (
        <>
          {manager && (
            <div className="section-heading">
              <div>
                <h2>Conteúdo</h2>
                <p>Comunicados e materiais publicados para a operação.</p>
              </div>
              <button
                className="btn-primary"
                onClick={() => setContentOpen(true)}
              >
                + Novo conteúdo
              </button>
            </div>
          )}
          <div className="card-grid">
            {content.map((item) => (
              <article className="summary-card" key={item.id}>
                <small>{item.kind}</small>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </>
      )}
      {contentOpen && (
        <div className="modal-backdrop" onClick={() => setContentOpen(false)}>
          <form
            className="modal-card"
            onSubmit={addPost}
            onClick={(event) => event.stopPropagation()}
          >
            <h3>Novo conteúdo</h3>
            <div className="form-grid">
              <label className="field">
                <span>Título</span>
                <input
                  className="input"
                  required
                  value={post.title}
                  onChange={(event) =>
                    setPost({ ...post, title: event.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Tipo</span>
                <select
                  className="input"
                  value={post.kind}
                  onChange={(event) =>
                    setPost({ ...post, kind: event.target.value })
                  }
                >
                  <option>comunicado</option>
                  <option>treinamento</option>
                  <option>video</option>
                </select>
              </label>
            </div>
            <label className="field">
              <span>Conteúdo</span>
              <textarea
                className="input"
                rows={5}
                value={post.body}
                onChange={(event) =>
                  setPost({ ...post, body: event.target.value })
                }
              />
            </label>
            <div className="modal-actions">
              <button className="btn-primary">Publicar</button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setContentOpen(false)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}
      {editingPart && (
        <div className="modal-backdrop" onClick={() => setEditingPart(null)}>
          <form
            className="modal-card modal-card-compact"
            onSubmit={savePart}
            onClick={(event) => event.stopPropagation()}
          >
            <h3>
              {editingPart === "new" ? "Novo item de estoque" : "Editar item"}
            </h3>
            <p>Identifique a peça e defina o nível mínimo para reposição.</p>
            <div className="form-grid">
              <label className="field">
                <span>SKU</span>
                <input
                  className="input"
                  required
                  value={partForm.sku}
                  onChange={(event) =>
                    setPartForm({ ...partForm, sku: event.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Peça</span>
                <input
                  className="input"
                  required
                  value={partForm.name}
                  onChange={(event) =>
                    setPartForm({ ...partForm, name: event.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Unidade</span>
                <input
                  className="input"
                  required
                  value={partForm.unit}
                  onChange={(event) =>
                    setPartForm({ ...partForm, unit: event.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Estoque mínimo</span>
                <input
                  className="input"
                  min="0"
                  step="0.01"
                  type="number"
                  required
                  value={partForm.minimum_quantity}
                  onChange={(event) =>
                    setPartForm({
                      ...partForm,
                      minimum_quantity: event.target.value,
                    })
                  }
                />
              </label>
              <label className="field occurrence-wide">
                <span>Custo médio</span>
                <input
                  className="input"
                  min="0"
                  step="0.01"
                  type="number"
                  value={partForm.average_cost}
                  onChange={(event) =>
                    setPartForm({
                      ...partForm,
                      average_cost: event.target.value,
                    })
                  }
                />
              </label>
            </div>
            {error && <p className="modal-error">{error}</p>}
            <div className="modal-actions">
              <button className="btn-primary">Salvar</button>
              <button
                className="btn-ghost"
                type="button"
                onClick={() => setEditingPart(null)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}
      {movingPart && (
        <div className="modal-backdrop" onClick={() => setMovingPart(null)}>
          <form
            className="modal-card modal-card-compact"
            onSubmit={saveMovement}
            onClick={(event) => event.stopPropagation()}
          >
            <h3>Movimentar estoque</h3>
            <p>
              <strong>{movingPart.sku}</strong> · {movingPart.name} — saldo
              atual: {movingPart.quantity} {movingPart.unit}
            </p>
            <div className="form-grid">
              <label className="field">
                <span>Operação</span>
                <select
                  className="input"
                  value={movement.kind}
                  onChange={(event) =>
                    setMovement({ ...movement, kind: event.target.value })
                  }
                >
                  <option value="entrada">Entrada</option>
                  <option value="saida">Saída</option>
                  <option value="ajuste">Ajuste positivo</option>
                </select>
              </label>
              <label className="field">
                <span>Quantidade</span>
                <input
                  autoFocus
                  required
                  min="0.01"
                  step="0.01"
                  type="number"
                  className="input"
                  value={movement.quantity}
                  onChange={(event) =>
                    setMovement({ ...movement, quantity: event.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Custo unitário</span>
                <input
                  min="0"
                  step="0.01"
                  type="number"
                  className="input"
                  value={movement.unit_cost}
                  onChange={(event) =>
                    setMovement({ ...movement, unit_cost: event.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Referência</span>
                <input
                  className="input"
                  placeholder="NF, OS ou motivo"
                  value={movement.reference}
                  onChange={(event) =>
                    setMovement({ ...movement, reference: event.target.value })
                  }
                />
              </label>
            </div>
            {error && <p className="modal-error">{error}</p>}
            <div className="modal-actions">
              <button className="btn-primary">Confirmar movimentação</button>
              <button
                className="btn-ghost"
                type="button"
                onClick={() => setMovingPart(null)}
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

function StockView({
  parts,
  stats,
  query,
  setQuery,
  stockFilter,
  setStockFilter,
  onEdit,
  onMove,
  onRemove,
}: {
  parts: Part[];
  stats: { items: number; units: number; low: number; value: number };
  query: string;
  setQuery: (value: string) => void;
  stockFilter: string;
  setStockFilter: (value: string) => void;
  onEdit: (part: Part) => void;
  onMove: (part: Part, kind?: string) => void;
  onRemove: (part: Part) => void;
}) {
  return (
    <>
      <div className="stock-summary">
        <article>
          <span>Itens cadastrados</span>
          <strong>{stats.items}</strong>
        </article>
        <article>
          <span>Unidades em estoque</span>
          <strong>{stats.units.toLocaleString("pt-BR")}</strong>
        </article>
        <article className={stats.low ? "stock-alert" : ""}>
          <span>Abaixo do mínimo</span>
          <strong>{stats.low}</strong>
        </article>
        <article>
          <span>Valor estimado</span>
          <strong>
            {stats.value.toLocaleString("pt-BR", {
              style: "currency",
              currency: "BRL",
            })}
          </strong>
        </article>
      </div>
      <div className="stock-toolbar">
        <input
          className="input"
          placeholder="Buscar por SKU ou peça..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select
          className="input"
          value={stockFilter}
          onChange={(event) => setStockFilter(event.target.value)}
        >
          <option value="all">Todos os níveis</option>
          <option value="low">Abaixo do mínimo</option>
          <option value="available">Estoque disponível</option>
        </select>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Peça</th>
              <th>Saldo</th>
              <th>Mínimo</th>
              <th>Custo médio</th>
              <th>Situação</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {parts.map((part) => {
              const low = part.quantity <= part.minimum_quantity;
              return (
                <tr key={part.id}>
                  <td>
                    <strong>{part.sku}</strong>
                  </td>
                  <td>{part.name}</td>
                  <td>
                    <strong>
                      {part.quantity.toLocaleString("pt-BR")} {part.unit}
                    </strong>
                  </td>
                  <td>
                    {part.minimum_quantity.toLocaleString("pt-BR")} {part.unit}
                  </td>
                  <td>
                    {part.average_cost != null
                      ? Number(part.average_cost).toLocaleString("pt-BR", {
                          style: "currency",
                          currency: "BRL",
                        })
                      : "-"}
                  </td>
                  <td>
                    <span className={`stock-badge ${low ? "low" : "ok"}`}>
                      {low ? "Repor estoque" : "Disponível"}
                    </span>
                  </td>
                  <td>
                    <div className="occurrence-actions">
                      <button
                        className="btn-primary btn-mini"
                        onClick={() => onMove(part, "entrada")}
                      >
                        Movimentar
                      </button>
                      <button className="btn-mini" onClick={() => onEdit(part)}>
                        Editar
                      </button>
                      <button
                        className="btn-mini danger"
                        onClick={() => onRemove(part)}
                      >
                        Excluir
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {parts.length === 0 && (
              <tr>
                <td className="empty-state" colSpan={7}>
                  Nenhum item encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function StatementPanel() {
  const { hasPermission } = useAuth(),
    canManage = hasPermission("finance.accounts.manage", "gestor_financeiro");
  const today = new Date(),
    first = new Date(today.getFullYear(), today.getMonth(), 1)
      .toISOString()
      .slice(0, 10),
    last = new Date(today.getFullYear(), today.getMonth() + 1, 0)
      .toISOString()
      .slice(0, 10);
  const [rows, setRows] = useState<Statement[]>([]),
    [drivers, setDrivers] = useState<Array<{ id: number; name: string; employment_type?: "proprio" | "agregado"; daily_rate?: number | null }>>([]),
    [filters, setFilters] = useState({
      start: first,
      end: last,
      driver_id: "",
    }),
    [summary, setSummary] = useState<any>(null),
    [open, setOpen] = useState(false),
    [error, setError] = useState(""),
    [form, setForm] = useState({
      driver_id: "",
      route_id: "",
      entry_date: new Date().toISOString().slice(0, 10),
      kind: "earning",
      reason: "",
      amount: "",
      notes: "",
    });
  const load = useCallback(async () => {
    const params = {
      start: filters.start,
      end: filters.end,
      driver_id: filters.driver_id || undefined,
    };
    setRows((await api.get("/erp/statement", { params })).data);
    if (filters.driver_id)
      setSummary(
        (
          await api.get("/erp/driver-statement", {
            params: {
              driver_id: filters.driver_id,
              start: filters.start,
              end: filters.end,
            },
          })
        ).data,
      );
    else setSummary(null);
  }, [filters]);
  useEffect(() => {
    Promise.all([api.get("/drivers")]).then(([d]) => {
      setDrivers(d.data);
    });
    void load().catch(() => {});
  }, [load]);
  const money = (value: number) =>
    value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await api.post("/erp/driver-adjustments", {
        ...form,
        driver_id: Number(form.driver_id),
        route_id: form.route_id ? Number(form.route_id) : null,
        amount: Number(form.amount),
      });
      setOpen(false);
      await load();
    } catch (e: any) {
      setError(
        e?.response?.data?.detail || "Não foi possível lançar no extrato.",
      );
    }
  }
  async function pdf() {
    if (!filters.driver_id) return;
    const { data } = await api.get("/erp/driver-statement.pdf", {
      params: {
        driver_id: filters.driver_id,
        start: filters.start,
        end: filters.end,
      },
      responseType: "blob",
    });
    const url = URL.createObjectURL(data),
      a = document.createElement("a");
    a.href = url;
    a.download = `extrato-motorista-${filters.driver_id}-${filters.start}-${filters.end}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }
  async function releaseForAcceptance() {
    if (!filters.driver_id || !summary) return;
    try {
      const {data} = await api.post("/erp/driver-statement-periods/release", {driver_id:Number(filters.driver_id),start:filters.start,end:filters.end});
      await appAlert(`Extrato versão ${data.version} liberado para o motorista a partir de ${new Date(`${data.release_date}T12:00:00`).toLocaleDateString("pt-BR")}.`, {title:"Extrato liberado"});
    } catch (e:any) {
      await appAlert(e?.response?.data?.detail || "Não foi possível liberar o extrato.", {title:"Falha na liberação"});
    }
  }
  return (
    <section className="statement-page">
      <div className="section-heading">
        <div>
          <h2>Extrato para pagamento de motorista</h2>
          <p>Diárias de motoristas próprios e valores negociados por rota para agregados.</p>
        </div>
        {canManage && (
          <button
            className="btn-primary"
            onClick={() => {
              setForm({ ...form, driver_id: filters.driver_id });
              setOpen(true);
            }}
          >
            Novo ganho ou desconto
          </button>
        )}
      </div>
      <div className="card-panel statement-filters">
        <label className="field">
          <span>Início</span>
          <input
            className="input"
            type="date"
            value={filters.start}
            onChange={(e) => setFilters({ ...filters, start: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Fim</span>
          <input
            className="input"
            type="date"
            value={filters.end}
            onChange={(e) => setFilters({ ...filters, end: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Motorista</span>
          <select
            className="input"
            value={filters.driver_id}
            onChange={(e) =>
              setFilters({ ...filters, driver_id: e.target.value })
            }
          >
            <option value="">Todos</option>
            {drivers.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} · {d.employment_type === "agregado" ? "agregado" : "próprio"}
              </option>
            ))}
          </select>
        </label>
        {filters.driver_id && <div className="occurrence-actions"><button className="btn-ghost" onClick={pdf}>Gerar PDF do motorista</button>{canManage&&summary&&summary.net>0&&<button className="btn-primary" onClick={()=>void releaseForAcceptance()}>Liberar para aceite</button>}</div>}
      </div>
      {summary && (
        <><div className="statement-summary">
          <article>
            <span>{summary.driver.employment_type === "agregado" ? "Rotas negociadas" : `Diárias · ${money(summary.driver.daily_rate || 0)}/dia`}</span>
            <strong className="positive">{money(summary.earnings)}</strong>
          </article>
          <article>
            <span>Descontos autorizados</span>
            <strong className="negative">{money(summary.deductions)}</strong>
          </article>
          <article>
            <span>Líquido do motorista</span>
            <strong>{money(summary.net)}</strong>
          </article>
        </div>{summary.pending_routes > 0 && <p className="modal-error">{summary.pending_routes} rota(s) finalizada(s) ainda estão sem valor negociado.</p>}{summary.daily_rate_missing && <p className="modal-error">Configure o valor da diária no cadastro deste motorista para calcular o pagamento.</p>}</>
      )}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Data</th>
              <th>Tipo</th>
              <th>Descrição</th>
              <th>Rota</th>
              <th>Valor</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.date}</td>
                <td>{row.kind.replaceAll("_", " ")}</td>
                <td>{row.description}</td>
                <td>{row.route || "-"}</td>
                <td className={row.amount >= 0 ? "positive" : "negative"}>
                  {money(row.amount)}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={5} className="empty-state">
                  {filters.driver_id ? "Nenhum pagamento encontrado no período." : "Selecione um motorista para gerar o extrato de pagamento."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <form
            className="modal-card"
            onSubmit={save}
            onClick={(e) => e.stopPropagation()}
          >
            <h3>Lançamento no extrato do motorista</h3>
            <p>
              Este lançamento é independente das despesas de viagem e será
              auditado.
            </p>
            <div className="form-grid">
              <label className="field">
                <span>Motorista</span>
                <select
                  className="input"
                  required
                  value={form.driver_id}
                  onChange={(e) =>
                    setForm({ ...form, driver_id: e.target.value })
                  }
                >
                  <option value="">Selecione</option>
                  {drivers.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Tipo</span>
                <select
                  className="input"
                  value={form.kind}
                  onChange={(e) => setForm({ ...form, kind: e.target.value })}
                >
                  <option value="earning">Ganho</option>
                  <option value="deduction">Desconto</option>
                </select>
              </label>
              <label className="field">
                <span>Data</span>
                <input
                  className="input"
                  required
                  type="date"
                  value={form.entry_date}
                  onChange={(e) =>
                    setForm({ ...form, entry_date: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Valor</span>
                <input
                  className="input"
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Rota (opcional)</span>
                <input
                  className="input"
                  type="number"
                  value={form.route_id}
                  onChange={(e) =>
                    setForm({ ...form, route_id: e.target.value })
                  }
                />
              </label>
              <label className="field">
                <span>Motivo obrigatório</span>
                <input
                  className="input"
                  required
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                />
              </label>
            </div>
            <label className="field">
              <span>Observações</span>
              <textarea
                className="input"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </label>
            {error && <p className="modal-error">{error}</p>}
            <div className="modal-actions">
              <button className="btn-primary">Confirmar lançamento</button>
              <button
                className="btn-ghost"
                type="button"
                onClick={() => setOpen(false)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

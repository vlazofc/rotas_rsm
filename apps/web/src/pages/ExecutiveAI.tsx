import { FormEvent, useEffect, useRef, useState } from "react";
import api from "../services/api";
import "./ExecutiveAI.css";
import ReactMarkdown from "react-markdown";

type Message = { id?: number; role: "user" | "assistant"; content: string; created_at?: string };
type Conversation = { id: number; title: string; updated_at: string };
type Status = { configured: boolean; suggestions: string[] };
const AGENT_AVATARS = ["🧔‍♂️", "🕵️‍♂️", "🤵", "👩‍💼", "👩‍💻"] as const;
type AgentAvatar = typeof AGENT_AVATARS[number];

function normalizeMessages(value: unknown): Message[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => ({
      id: typeof item.id === "number" ? item.id : undefined,
      role: item.role === "assistant" ? "assistant" : "user",
      content: typeof item.content === "string" ? item.content : String(item.content ?? ""),
      created_at: typeof item.created_at === "string" ? item.created_at : undefined,
    }));
}

function ExecutiveAvatar({ avatar, small = false }: { avatar: AgentAvatar; small?: boolean }) {
  return <span className={`executive-avatar ${small ? "small" : ""}`} aria-hidden="true"><span>{avatar}</span></span>;
}

export default function ExecutiveAI() {
  const [status, setStatus] = useState<Status | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [avatar, setAvatar] = useState<AgentAvatar>(() => {
    const saved = localStorage.getItem("executive-agent-avatar") as AgentAvatar | null;
    return saved && AGENT_AVATARS.includes(saved) ? saved : "👩‍💻";
  });
  const [avatarPickerOpen, setAvatarPickerOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const loadConversations = () => api.get<Conversation[]>("/executive-ai/conversations").then(({ data }) => setConversations(data));

  useEffect(() => {
    Promise.all([api.get<Status>("/executive-ai/status"), loadConversations()])
      .then(([response]) => setStatus(response.data))
      .catch(() => setError("Não foi possível carregar o agente executivo."));
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function openConversation(id: number) {
    setConversationId(id); setError("");
    try {
      const { data } = await api.get(`/executive-ai/conversations/${id}`);
      setMessages(normalizeMessages(data?.messages));
    } catch (requestError: any) {
      setError(requestError?.response?.data?.detail || "Não foi possível abrir esta conversa.");
    }
  }
  function newConversation() { setConversationId(null); setMessages([]); setInput(""); setError(""); }
  function chooseAvatar(nextAvatar: AgentAvatar) {
    setAvatar(nextAvatar); localStorage.setItem("executive-agent-avatar", nextAvatar); setAvatarPickerOpen(false);
  }
  async function send(event?: FormEvent, messageOverride?: string) {
    event?.preventDefault();
    const message = (messageOverride ?? input).trim();
    if (!message || loading) return;
    setInput(""); setError(""); setMessages((items) => [...items, { role: "user", content: message }]); setLoading(true);
    try {
      const { data } = await api.post("/executive-ai/chat", { message, conversation_id: conversationId });
      setConversationId(data.conversation_id);
      setMessages((items) => [...items, { role: "assistant", content: typeof data?.answer === "string" ? data.answer : String(data?.answer ?? "") }]);
      await loadConversations();
    } catch (requestError: any) {
      setError(requestError?.response?.data?.detail || "O agente não conseguiu gerar a análise.");
    } finally { setLoading(false); }
  }

  return <div className="executive-ai-page">
    <aside className="executive-ai-sidebar">
      <div className="executive-ai-brand">
        <div className="executive-avatar-picker">
          <button className="executive-avatar-trigger" onClick={() => setAvatarPickerOpen((open) => !open)} aria-label="Escolher avatar do assistente" title="Escolher avatar"><ExecutiveAvatar avatar={avatar} small/><span className="avatar-edit">✦</span></button>
          {avatarPickerOpen && <div className="executive-avatar-options" role="menu" aria-label="Avatares disponíveis">{AGENT_AVATARS.map((option) => <button key={option} className={avatar === option ? "selected" : ""} onClick={() => chooseAvatar(option)} aria-label={`Selecionar ${option}`}>{option}</button>)}</div>}
        </div>
        <div><h3>Diretoria em foco</h3><small>Personalize seu assistente</small></div>
      </div>
      <button className="btn-primary" onClick={newConversation}>＋ Nova análise</button>
      <div className="executive-ai-history-label">Histórico de conversas</div>
      <nav>{conversations.map((item) => <button key={item.id} className={conversationId === item.id ? "active" : ""} onClick={() => void openConversation(item.id)}><strong>{item.title}</strong><small>{new Date(item.updated_at).toLocaleString("pt-BR")}</small></button>)}
        {!conversations.length && <p className="executive-ai-empty-history">Suas análises ficarão organizadas aqui.</p>}
      </nav>
      <div className="executive-ai-privacy">🔒 Ambiente interno e dados restritos ao seu acesso.</div>
    </aside>
    <section className="executive-ai-main">
      <header><div><h2>Assistente executivo</h2><p>Informações da operação transformadas em decisões claras para a diretoria.</p></div><span className={`executive-status ${status?.configured ? "ok" : "warning"}`}><i/>{status?.configured ? "Disponível" : "Configuração pendente"}</span></header>
      {!messages.length && <div className="executive-ai-welcome"><ExecutiveAvatar avatar={avatar}/><span className="executive-ai-eyebrow">ANÁLISE CORPORATIVA</span><h3>Olá! O que precisamos entender hoje?</h3><p>Escolha um relatório pronto ou faça uma pergunta sobre finanças, operação e frota.</p><div className="executive-ai-suggestions">{status?.suggestions.map((suggestion, index) => <button key={suggestion} onClick={() => void send(undefined, suggestion)}><span>{["↗", "◎", "⚑", "▦", "◇", "✓"][index % 6]}</span>{suggestion}</button>)}</div></div>}
      {!!messages.length && <div className="executive-ai-messages">{messages.map((message, index) => <article key={message.id || index} className={message.role}>{message.role === "assistant" ? <ExecutiveAvatar avatar={avatar} small/> : <div className="user-avatar">Você</div>}<div className="executive-message"><span className="message-author">{message.role === "assistant" ? "Assistente executivo" : "Você"}</span>{message.role === "assistant" ? <ReactMarkdown>{message.content}</ReactMarkdown> : <p>{message.content}</p>}</div></article>)}{loading && <article className="assistant"><ExecutiveAvatar avatar={avatar} small/><div className="executive-message"><span className="message-author">Assistente executivo</span><p className="executive-thinking">Consultando os indicadores internos e preparando o relatório…</p></div></article>}<div ref={endRef} /></div>}
      {error && <p className="modal-error">{error}</p>}
      <form className="executive-ai-composer" onSubmit={(event) => void send(event)}><textarea className="input" rows={3} maxLength={4000} placeholder="Pergunte sobre resultados, rotas, ocorrências, frota ou prioridades..." value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} /><button className="btn-primary executive-ai-send" disabled={loading || !input.trim()} aria-label="Enviar mensagem">➤</button><small>Somente dados internos autorizados · Enter para enviar · Shift + Enter para nova linha</small></form>
    </section>
  </div>;
}

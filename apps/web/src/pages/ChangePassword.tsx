import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import api, { storeTokens } from "../services/api";
import { useAuth } from "../context/AuthContext";

export default function ChangePassword() {
  const { user, loading, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  if (loading) return <div className="login-page">Carregando…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.must_change_password) return <Navigate to="/" replace />;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (newPassword !== confirmation) { setError("As senhas não coincidem."); return; }
    if (newPassword === currentPassword) { setError("Escolha uma senha diferente da temporária."); return; }
    if (new TextEncoder().encode(newPassword).length > 72) { setError("A nova senha é muito longa. Use até 72 bytes."); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/auth/change-password", { current_password: currentPassword, new_password: newPassword });
      storeTokens(data.access_token, data.refresh_token);
      setCurrentPassword(""); setNewPassword(""); setConfirmation("");
      await refresh();
      navigate("/", { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Não foi possível alterar a senha. Tente novamente.");
    } finally { setSaving(false); }
  }

  return <div className="login-page">
    <form className="login-card" onSubmit={submit}>
      <div className="login-copy">
        <h2>Defina sua senha</h2>
        <p>Para acessar o sistema, substitua a senha temporária por uma senha pessoal com pelo menos 8 caracteres.</p>
      </div>
      <input type="email" autoComplete="username" value={user.email} readOnly aria-label="E-mail" className="login-input" />
      <label className="login-label" htmlFor="temporary-password">Senha temporária</label>
      <input id="temporary-password" className="login-input" type="password" autoComplete="current-password" required value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} />
      <label className="login-label" htmlFor="new-password">Nova senha</label>
      <input id="new-password" className="login-input" type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={newPassword} onChange={e => setNewPassword(e.target.value)} />
      <label className="login-label" htmlFor="confirm-password">Confirme a nova senha</label>
      <input id="confirm-password" className="login-input" type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={confirmation} onChange={e => setConfirmation(e.target.value)} />
      {error && <p className="login-error" role="alert">{error}</p>}
      <button className="login-submit" type="submit" disabled={saving}>{saving ? "Salvando…" : "Salvar senha e entrar"}</button>
      <button type="button" onClick={logout} disabled={saving} style={{ marginTop: 12 }}>Sair</button>
    </form>
  </div>;
}

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { login } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { useBranding } from "../context/BrandingContext";
import LanguageSwitcher from "../components/LanguageSwitcher";
import ThemeToggle from "../components/ThemeToggle";

export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const { branding, reload: reloadBranding } = useBranding();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      await refresh();
      navigate("/");
      reloadBranding();
    } catch {
      setError(t("login.error"));
    } finally {
      setLoading(false);
    }
  }

  const accent = branding.primary_color || "#0a58ca";
  const accentText = readableTextColor(accent);
  const pageStyle: React.CSSProperties = branding.background_url
    ? { backgroundImage: `url(${branding.background_url})` }
    : {};

  return (
    <div className={`login-page${branding.background_url ? " has-background" : ""}`} style={pageStyle}>
      <form onSubmit={onSubmit} className="login-card">
        <div className="login-brand">
          {branding.logo_url ? (
            <span className="login-logo-frame">
              <img src={branding.logo_url} alt={branding.app_name ?? t("app.title")} />
            </span>
          ) : (
            <h1>{branding.app_name || t("app.title")}</h1>
          )}
        </div>
        <div className="login-tools">
          <ThemeToggle />
          <LanguageSwitcher />
        </div>
        <label className="login-label">{t("login.email")}</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required
          className="login-input" />
        <label className="login-label">{t("login.password")}</label>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required
          className="login-input" />
        {error && <p className="login-error">{error}</p>}
        <button type="submit" disabled={loading} className="login-submit" style={{ background: accent, color: accentText }}>
          {loading ? t("common.loading") : t("login.submit")}
        </button>
      </form>
    </div>
  );
}

function readableTextColor(hex: string): string {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) return "#fff";
  const value = match[1];
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? "#0f172a" : "#fff";
}

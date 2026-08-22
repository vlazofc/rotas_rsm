import { ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useBranding } from "../context/BrandingContext";
import api, { exitPreviewSession, isPreviewMode } from "../services/api";
import LanguageSwitcher from "./LanguageSwitcher";
import ThemeToggle from "./ThemeToggle";

interface NavItem {
  to: string;
  label: string;
  roles?: string[]; // ausente = visível para todos os perfis autenticados
  group?: string;
  feature?: "feature_financeiro" | "feature_ocr" | "feature_rastreamento"; // exige o serviço ativo no cliente
}

function IconSvg({ children }: { children: ReactNode }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

function DashboardIcon() {
  return (
    <IconSvg>
      <rect x="3" y="3" width="8" height="8" rx="1" />
      <rect x="13" y="3" width="8" height="8" rx="1" />
      <rect x="13" y="13" width="8" height="8" rx="1" />
      <rect x="3" y="13" width="8" height="8" rx="1" />
    </IconSvg>
  );
}

function TruckIcon() {
  return (
    <IconSvg>
      <rect x="1" y="3" width="15" height="13" rx="1" />
      <path d="M16 8h4l3 3v5h-7V8z" />
      <circle cx="5.5" cy="18.5" r="2.5" />
      <circle cx="18.5" cy="18.5" r="2.5" />
    </IconSvg>
  );
}

function GearIcon() {
  return (
    <IconSvg>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </IconSvg>
  );
}

function HelpIcon() {
  return (
    <IconSvg>
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <line x1="12" y1="17" x2="12" y2="17" />
    </IconSvg>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const loc = useLocation();
  const navigate = useNavigate();
  const { user, logout, hasRole } = useAuth();
  const { branding } = useBranding();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar_collapsed") === "1");
  const [helpOpen, setHelpOpen] = useState(false);
  const [features, setFeatures] = useState({ feature_financeiro: true, feature_ocr: true, feature_rastreamento: true, feature_route_optimization: true, feature_km_calculation: true });

  useEffect(() => {
    api.get("/tenants/me")
      .then((r) => setFeatures({
        feature_financeiro: r.data.feature_financeiro,
        feature_ocr: r.data.feature_ocr,
        feature_rastreamento: r.data.feature_rastreamento,
        feature_route_optimization: r.data.feature_route_optimization ?? true,
        feature_km_calculation: r.data.feature_km_calculation ?? true,
      }))
      .catch(() => {});
  }, []);

  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar_collapsed", next ? "1" : "0");
      return next;
    });
  }

  const canCreateRoute = hasRole("admin_global", "gestor_brasil", "operador_logistico");
  const canConfig = hasRole("admin_global", "gestor_brasil");
  const helpFaq = [
    { question: t("rail.help_faq.navigation_q"), answer: t("rail.help_faq.navigation_a") },
    { question: t("rail.help_faq.dashboard_q"), answer: t("rail.help_faq.dashboard_a") },
    { question: t("rail.help_faq.routes_q"), answer: t("rail.help_faq.routes_a") },
    { question: t("rail.help_faq.manifests_q"), answer: t("rail.help_faq.manifests_a") },
    { question: t("rail.help_faq.config_q"), answer: t("rail.help_faq.config_a") },
    { question: t("rail.help_faq.buttons_q"), answer: t("rail.help_faq.buttons_a") },
  ];

  const allItems: NavItem[] = [
    { to: "/", label: t("nav.dashboard"), group: t("nav.group_operation") },
    { to: "/routes", label: t("nav.routes"), group: t("nav.group_operation") },
    { to: "/expenses", label: t("nav.expenses", { defaultValue: "Despesas" }), group: t("nav.group_operation") },
    { to: "/reports", label: t("nav.reports", { defaultValue: "Relatórios" }), roles: ["admin_global", "gestor_brasil", "auditor"], group: t("nav.group_operation") },
    { to: "/manifests", label: t("nav.manifests"), roles: ["gestor_brasil", "operador_logistico"], group: t("nav.group_operation"), feature: "feature_ocr" },
    { to: "/financeiro", label: t("nav.financeiro", { defaultValue: "Financeiro" }), roles: ["admin_global", "gestor_brasil", "gestor_financeiro"], group: t("nav.group_financeiro", { defaultValue: "Financeiro" }), feature: "feature_financeiro" },
    { to: "/revenues", label: t("nav.revenues", { defaultValue: "Receitas" }), roles: ["admin_global", "gestor_brasil", "gestor_financeiro"], group: t("nav.group_financeiro", { defaultValue: "Financeiro" }), feature: "feature_financeiro" },
    { to: "/config/drivers", label: t("config.tabs.drivers"), roles: ["admin_global", "gestor_brasil"], group: t("nav.group_registers") },
    { to: "/config/vehicles", label: t("config.tabs.vehicles"), roles: ["admin_global", "gestor_brasil"], group: t("nav.group_registers") },
    { to: "/config/branches", label: t("config.tabs.branches"), roles: ["admin_global", "gestor_brasil"], group: t("nav.group_registers") },
    { to: "/config/carriers", label: t("config.tabs.carriers"), roles: ["admin_global", "gestor_brasil"], group: t("nav.group_registers") },
    { to: "/config/customers", label: t("config.tabs.customers"), roles: ["admin_global", "gestor_brasil"], group: t("nav.group_registers") },
    { to: "/config/reasons", label: t("config.tabs.reasons"), roles: ["admin_global", "gestor_brasil"], group: t("nav.group_registers") },
    { to: "/config/profiles", label: t("config.tabs.profiles"), roles: ["admin_global", "gestor_brasil"], group: t("nav.group_admin") },
    { to: "/config/tenants", label: t("config.tabs.tenants"), roles: ["admin_global"], group: t("nav.group_admin") },
    { to: "/users", label: t("nav.users"), roles: ["admin_global", "gestor_brasil"], group: t("nav.group_admin") },
    { to: "/audit", label: t("nav.audit"), roles: ["admin_global", "gestor_brasil", "auditor"], group: t("nav.group_admin") },
  ];

  const items = allItems.filter((i) => (!i.roles || hasRole(...i.roles)) && (!i.feature || features[i.feature]));
  const groups = Array.from(new Set(items.map((i) => i.group ?? "")));

  return (
    <div className={`app-shell${collapsed ? " is-collapsed" : ""}${branding.topbar_extends_sidebar ? " strip-extended" : ""}`}>
      <div className="icon-rail">
        <button
          type="button"
          className="brand-mark"
          onClick={toggleSidebar}
          title={t("rail.toggle_sidebar")}
          style={branding.primary_color ? { background: branding.primary_color } : undefined}
        >
          {branding.logo_rail_url || branding.logo_url ? (
            <img src={branding.logo_rail_url || branding.logo_url || undefined} alt="" style={{ width: 22, height: 22, objectFit: "contain" }} />
          ) : (branding.app_name || "Admmendes").slice(0, 2).toUpperCase()}
        </button>
        <button type="button" className="rail-dot" onClick={() => navigate("/")} title={t("rail.dashboard")}>
          <DashboardIcon />
        </button>
        {canCreateRoute && (
          <button type="button" className="rail-dot" onClick={() => navigate("/routes")} title={t("nav.routes")}>
            <TruckIcon />
          </button>
        )}
        {canConfig && (
          <button type="button" className="rail-dot" onClick={() => navigate("/config")} title={t("rail.config")}>
            <GearIcon />
          </button>
        )}
        <button type="button" className="rail-dot" onClick={() => setHelpOpen(true)} title={t("rail.help")}>
          <HelpIcon />
        </button>
      </div>

      <aside className="sidebar">
        <div className="sidebar-head">
          {branding.logo_url && <img className="sidebar-logo" src={branding.logo_url} alt="" />}
          <h3 className="app-title">{branding.app_name || t("app.title")}</h3>
          <div className="app-subtitle">{branding.app_subtitle || t("app.subtitle")}</div>
        </div>
        <nav className="nav-groups">
          {groups.map((group) => (
            <div key={group}>
              <div className="nav-group-title">{group}</div>
              <div className="nav-links">
                {items.filter((i) => (i.group ?? "") === group).map((i) => {
                  const active = i.to === "/" ? loc.pathname === "/" : loc.pathname === i.to || loc.pathname.startsWith(`${i.to}/`);
                  return (
                    <Link key={i.to} to={i.to} className={`nav-link${active ? " is-active" : ""}`}>{i.label}</Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="sidebar-user">
          {user && (
            <div>
              <div className="user-name">{user.name}</div>
              <div className="user-role">
                {t(`roles.${user.role}`, { defaultValue: user.role })}
              </div>
            </div>
          )}
          <button onClick={logout} className="logout-btn">
            {t("nav.logout")}
          </button>
        </div>
      </aside>

      <div className="content-shell">
        <div>
          {isPreviewMode() && (
            <div style={{ background: "#7c3aed", color: "#fff", padding: "8px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 13, fontWeight: 600 }}>
              <span>{t("nav.preview_mode_banner", { defaultValue: "Modo de simulação — você está vendo o ambiente do cliente." })}</span>
              <button type="button" onClick={exitPreviewSession} style={{ background: "#fff", color: "#7c3aed", border: "none", borderRadius: 6, padding: "4px 10px", fontWeight: 700, cursor: "pointer" }}>
                {t("nav.exit_preview", { defaultValue: "Sair da simulação" })}
              </button>
            </div>
          )}
          <header className="topbar">
            <div className="mobile-top-title">{t("app.title")}</div>
            <ThemeToggle />
            <LanguageSwitcher />
          </header>
        </div>
        <main className="page-main">{children}</main>
      </div>

      {helpOpen && (
        <div className="modal-backdrop" onClick={() => setHelpOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>{t("rail.help_title")}</h3>
            <p>{t("rail.help_intro")}</p>
            <div className="help-faq">
              {helpFaq.map((item) => (
                <section key={item.question} className="help-faq-item">
                  <h4>{item.question}</h4>
                  <p>{item.answer}</p>
                </section>
              ))}
            </div>
            <p className="help-contact">{t("rail.help_contact")}</p>
            <div className="modal-actions">
              <button type="button" className="btn-ghost" onClick={() => setHelpOpen(false)}>
                {t("common.close")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

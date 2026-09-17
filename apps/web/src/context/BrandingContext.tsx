import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import api from "../services/api";

export interface Branding {
  app_name: string | null;
  app_subtitle: string | null;
  login_intro_text: string | null;
  login_layout: "centered" | "institutional" | "side_form";
  primary_color: string | null;
  sidebar_background_color: string | null;
  sidebar_text_color: string | null;
  sidebar_active_color: string | null;
  enabled_locales: string[] | null;
  topbar_extends_sidebar: boolean;
  logo_url: string | null;
  logo_rail_url: string | null;
  background_url: string | null;
  favicon_url: string | null;
}

const DEFAULTS: Branding = {
  app_name: "Adimax",
  app_subtitle: "Gestão de rotas e entregas",
  login_intro_text: "Operação logística com rotas, entregas e ocorrências em um só lugar.",
  login_layout: "institutional",
  primary_color: "#F9A61A",
  sidebar_background_color: "#F2F2F2",
  sidebar_text_color: "#242424",
  sidebar_active_color: "#F9A61A",
  enabled_locales: ["pt-BR"],
  topbar_extends_sidebar: true,
  logo_url: "/brand/adimax-logo.png",
  logo_rail_url: "/brand/adimax-logo.png",
  background_url: null,
  favicon_url: "/brand/adimax-favicon.png",
};

interface BrandingState {
  branding: Branding;
  loading: boolean;
  reload: () => Promise<void>;
}

const BrandingContext = createContext<BrandingState | undefined>(undefined);

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBranding] = useState<Branding>(DEFAULTS);
  const [loading, setLoading] = useState(true);

  async function reload() {
    try {
      const tenantSlug = new URLSearchParams(window.location.search).get("empresa") || undefined;
      const { data } = await api.get<Branding>("/branding", { params: { tenant_slug: tenantSlug } });
      const definedBranding = Object.fromEntries(Object.entries(data).filter(([, value]) => value != null));
      setBranding({ ...DEFAULTS, ...definedBranding } as Branding);
    } catch {
      setBranding(DEFAULTS);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    // Aplica a cor personalizada apenas na barra superior (--blue), preservando
    // a cor de marca do restante do sistema (--brand: botões, menu, gráficos).
    document.documentElement.style.setProperty("--blue", branding.primary_color || "#F9A61A");
    document.documentElement.style.setProperty("--brand", branding.primary_color || "#F9A61A");
  }, [branding.primary_color]);

  useEffect(() => {
    const existing = document.querySelectorAll<HTMLLinkElement>("link[rel~='icon']");
    if (branding.favicon_url) {
      existing.forEach((link) => link.remove());
      const link = document.createElement("link");
      link.rel = "icon";
      link.href = branding.favicon_url;
      document.head.appendChild(link);
    } else if (existing.length === 0) {
      // Restaura o favicon padrão do build se nenhum customizado estiver definido.
      const link = document.createElement("link");
      link.rel = "icon";
      link.type = "image/svg+xml";
      link.href = "/favicon.svg";
      document.head.appendChild(link);
    }
  }, [branding.favicon_url]);

  return (
    <BrandingContext.Provider value={{ branding, loading, reload }}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding(): BrandingState {
  const ctx = useContext(BrandingContext);
  if (!ctx) throw new Error("useBranding precisa estar dentro de <BrandingProvider>");
  return ctx;
}

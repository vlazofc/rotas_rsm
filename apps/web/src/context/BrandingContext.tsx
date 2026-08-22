import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import api from "../services/api";

export interface Branding {
  app_name: string | null;
  app_subtitle: string | null;
  primary_color: string | null;
  enabled_locales: string[] | null;
  topbar_extends_sidebar: boolean;
  logo_url: string | null;
  logo_rail_url: string | null;
  background_url: string | null;
  favicon_url: string | null;
}

const DEFAULTS: Branding = {
  app_name: null,
  app_subtitle: null,
  primary_color: null,
  enabled_locales: null,
  topbar_extends_sidebar: true,
  logo_url: null,
  logo_rail_url: null,
  background_url: null,
  favicon_url: null,
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
      setBranding({ ...DEFAULTS, ...data });
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
    document.documentElement.style.setProperty("--blue", branding.primary_color || "#2f9bd8");
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

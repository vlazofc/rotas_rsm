import axios from "axios";

// Por padrão a API fica no mesmo domínio (/api). Se VITE_API_URL estiver
// definida (build de produção com subdomínio dedicado), usa essa URL completa.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
});

// Modo de simulação ("Simular ambiente" no painel Clientes): a sessão de
// preview vive em sessionStorage (isolada por aba), sem tocar a sessão do
// admin em localStorage — assim o admin pode abrir o ambiente do cliente
// numa aba nova sem perder o próprio login.
export function isPreviewMode(): boolean {
  return sessionStorage.getItem("preview_mode") === "1";
}

function getToken(): string | null {
  return isPreviewMode() ? sessionStorage.getItem("access_token") : localStorage.getItem("access_token");
}

function getRefreshToken(): string | null {
  return isPreviewMode() ? sessionStorage.getItem("refresh_token") : localStorage.getItem("refresh_token");
}

function storeTokens(accessToken: string, refreshToken: string) {
  const storage = isPreviewMode() ? sessionStorage : localStorage;
  storage.setItem("access_token", accessToken);
  storage.setItem("refresh_token", refreshToken);
}

export function startPreviewSession(accessToken: string, refreshToken: string) {
  sessionStorage.setItem("preview_mode", "1");
  sessionStorage.setItem("access_token", accessToken);
  sessionStorage.setItem("refresh_token", refreshToken);
}

export function exitPreviewSession() {
  sessionStorage.removeItem("preview_mode");
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
  location.href = "/";
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshPromise: Promise<string> | null = null;

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config as (typeof error.config & { _retried?: boolean }) | undefined;
    const canRefresh = error.response?.status === 401
      && original
      && !original._retried
      && !String(original.url || "").includes("/auth/login")
      && !String(original.url || "").includes("/auth/refresh")
      && Boolean(getRefreshToken());
    if (canRefresh) {
      original._retried = true;
      refreshPromise ??= api.post("/auth/refresh", { refresh_token: getRefreshToken() })
        .then(({ data }) => {
          storeTokens(data.access_token, data.refresh_token);
          return data.access_token as string;
        })
        .finally(() => { refreshPromise = null; });
      try {
        const accessToken = await refreshPromise;
        original.headers.Authorization = `Bearer ${accessToken}`;
        return api(original);
      } catch {
        // A limpeza abaixo encerra a sessão quando o refresh expirou ou foi invalidado.
      }
    }
    if (error.response?.status === 401) {
      if (isPreviewMode()) {
        sessionStorage.removeItem("preview_mode");
        sessionStorage.removeItem("access_token");
        sessionStorage.removeItem("refresh_token");
      } else {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      }
      if (location.pathname !== "/login") location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export async function login(email: string, password: string) {
  // /auth/login usa form OAuth2 (username = email)
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);
  const { data } = await api.post("/auth/login", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  storeTokens(data.access_token, data.refresh_token);
  return data;
}

export function logout() {
  if (isPreviewMode()) {
    exitPreviewSession();
    return;
  }
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  location.href = "/login";
}

export default api;

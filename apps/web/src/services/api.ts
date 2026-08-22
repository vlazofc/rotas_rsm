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

api.interceptors.response.use(
  (r) => r,
  (error) => {
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
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
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

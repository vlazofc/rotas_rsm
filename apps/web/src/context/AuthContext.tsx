import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import api, { isPreviewMode, logout as apiLogout } from "../services/api";

export interface CurrentUser {
  id: number;
  email: string;
  name: string;
  role: string;
  branch_id: number | null;
  tenant_id: number | null;
  department?: string | null;
  subgroup?: string | null;
  permissions?: string[];
  navigation_layout?: "sidebar" | "top";
}

interface AuthState {
  user: CurrentUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => void;
  hasRole: (...roles: string[]) => boolean;
  hasPermission: (permission: string, ...fallbackRoles: string[]) => boolean;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    const token = isPreviewMode() ? sessionStorage.getItem("access_token") : localStorage.getItem("access_token");
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get<CurrentUser>("/auth/me");
      setUser(data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function hasRole(...roles: string[]) {
    if (!user) return false;
    // admin_global passa em tudo (espelha a regra do backend)
    if (user.role === "admin_global") return true;
    return roles.includes(user.role);
  }

  function hasPermission(permission: string, ...fallbackRoles: string[]) {
    if (!user) return false;
    if (user.role === "admin_global") return true;
    return Boolean(user.permissions?.includes(permission)) || fallbackRoles.includes(user.role);
  }

  function logout() {
    setUser(null);
    apiLogout();
  }

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout, hasRole, hasPermission }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth precisa estar dentro de <AuthProvider>");
  return ctx;
}

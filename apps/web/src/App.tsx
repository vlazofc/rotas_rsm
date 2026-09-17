import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import AppDialogHost from "./components/AppDialog";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrandingProvider } from "./context/BrandingContext";
import { ThemeProvider } from "./context/ThemeContext";

const Login = lazy(() => import("./pages/Login"));
const ChangePassword = lazy(() => import("./pages/ChangePassword"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const RoutesPage = lazy(() => import("./pages/Routes"));
const Routing = lazy(() => import("./pages/Routing"));
const ManualRouting = lazy(() => import("./pages/ManualRouting"));
const RouteDetail = lazy(() => import("./pages/RouteDetail"));
const Occurrences = lazy(() => import("./pages/Occurrences"));
const Gallery = lazy(() => import("./pages/Gallery"));
const Tracking = lazy(() => import("./pages/Tracking"));
const Drivers = lazy(() => import("./pages/Drivers"));
const Vehicles = lazy(() => import("./pages/Vehicles"));
const Reports = lazy(() => import("./pages/Reports"));
const Users = lazy(() => import("./pages/Users"));
const Profiles = lazy(() => import("./pages/Profiles"));

function Loading() {
  return <div className="app-loading"><div className="loading-route" aria-hidden="true"><span>1</span><i /><span>2</span><i /><span>3</span></div><strong>Preparando sua rota…</strong><small>Organizando os melhores caminhos</small></div>;
}

function VersionRefresh() {
  useEffect(() => {
    // O APK atualiza os dados por polling e possui seu próprio atualizador.
    // Recarregar o bundle dentro do WebView fecha a parada/modal em uso pelo motorista.
    if (/\bAdimaxMotorista\//i.test(navigator.userAgent)) return;
    let checking = false;
    async function check() {
      if (checking || document.hidden) return;
      checking = true;
      try {
        const html = await fetch(`/?version_check=${Date.now()}`, { cache: "no-store" }).then(response => response.text());
        const latest = html.match(/\/assets\/index-[^"']+\.js/)?.[0];
        const current = [...document.scripts].map(script => script.getAttribute("src") || "").find(src => /\/assets\/index-[^/]+\.js/.test(src));
        if (latest && current && !current.includes(latest) && !document.querySelector('.modal-backdrop, [role="dialog"]')) location.reload();
      } catch { /* sem rede: tenta novamente no próximo ciclo */ }
      finally { checking = false; }
    }
    const timer = window.setInterval(() => void check(), 60000);
    const onVisible = () => { if (!document.hidden) void check(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    void check();
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); window.removeEventListener("focus", onVisible); };
  }, []);
  return null;
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (user?.must_change_password) return <Navigate to="/change-password" replace />;
  return user ? children : <Navigate to="/login" replace />;
}

function RequireRole({ roles, children }: { roles: string[]; children: JSX.Element }) {
  const { hasRole, loading } = useAuth();
  if (loading) return <Loading />;
  return hasRole(...roles) ? children : <Navigate to="/" replace />;
}

function HomePage() {
  const { user } = useAuth();
  return user?.role === "motorista" ? <Navigate to="/routes" replace /> : <Dashboard />;
}

export default function App() {
  return (
    <ThemeProvider><BrandingProvider><AuthProvider>
      <VersionRefresh />
      <AppDialogHost />
      <BrowserRouter><Suspense fallback={<Loading />}><Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/change-password" element={<ChangePassword />} />
        <Route element={<RequireAuth><Layout><Outlet /></Layout></RequireAuth>}>
          <Route path="/" element={<HomePage />} />
          <Route path="/routes" element={<RoutesPage />} />
          <Route path="/routing" element={<RequireRole roles={["admin_global", "gestor_brasil", "operador_logistico", "torre_controle"]}><Routing /></RequireRole>} />
          <Route path="/routing/manual" element={<RequireRole roles={["admin_global", "gestor_brasil", "operador_logistico", "torre_controle"]}><ManualRouting /></RequireRole>} />
          <Route path="/routes/:id" element={<RouteDetail />} />
          <Route path="/occurrences" element={<Occurrences />} />
          <Route path="/tracking" element={<Tracking />} />
          <Route path="/gallery" element={<RequireRole roles={["admin_global", "gestor_brasil", "auditor", "operador_logistico", "torre_controle"]}><Gallery /></RequireRole>} />
          <Route path="/config/drivers" element={<RequireRole roles={["admin_global", "gestor_brasil", "operador_logistico"]}><Drivers /></RequireRole>} />
          <Route path="/config/vehicles" element={<RequireRole roles={["admin_global", "gestor_brasil", "operador_logistico"]}><Vehicles /></RequireRole>} />
          <Route path="/reports" element={<RequireRole roles={["admin_global", "gestor_brasil", "auditor"]}><Reports /></RequireRole>} />
          <Route path="/users" element={<RequireRole roles={["admin_global", "gestor_brasil"]}><Users /></RequireRole>} />
          <Route path="/profiles" element={<RequireRole roles={["admin_global"]}><Profiles /></RequireRole>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes></Suspense></BrowserRouter>
    </AuthProvider></BrandingProvider></ThemeProvider>
  );
}

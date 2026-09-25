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
const Carriers = lazy(() => import("./pages/Carriers"));
const Branches = lazy(() => import("./pages/Branches"));
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

function RequirePermission({ permission, roles, children, internalOnly=false }: { permission:string; roles:string[]; children:JSX.Element; internalOnly?:boolean }) {
  const { user, hasPermission, loading } = useAuth();
  if (loading) return <Loading />;
  if (internalOnly && user?.is_carrier_master) return <Navigate to="/" replace />;
  return hasPermission(permission, ...roles) ? children : <Navigate to="/" replace />;
}

function HomePage() {
  const { user } = useAuth();
  if (user?.role === "motorista") return <Navigate to="/routes" replace />;
  if (user?.role === "gestor_financeiro" || user?.role === "diretoria") return <Navigate to="/reports" replace />;
  return <Dashboard />;
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
          <Route path="/routing" element={<RequirePermission internalOnly permission="module.monitoring" roles={["gestor_brasil", "operador_logistico", "torre_controle"]}><Routing /></RequirePermission>} />
          <Route path="/routing/manual" element={<RequirePermission internalOnly permission="module.routing" roles={["gestor_brasil", "operador_logistico", "torre_controle"]}><ManualRouting /></RequirePermission>} />
          <Route path="/routes/:id" element={<RouteDetail />} />
          <Route path="/occurrences" element={<Occurrences />} />
          <Route path="/tracking" element={<Tracking />} />
          <Route path="/gallery" element={<RequirePermission permission="module.gallery" roles={["gestor_brasil", "auditor", "operador_logistico", "torre_controle"]}><Gallery /></RequirePermission>} />
          <Route path="/config/drivers" element={<RequirePermission permission="module.drivers" roles={["gestor_brasil", "operador_logistico"]}><Drivers /></RequirePermission>} />
          <Route path="/config/vehicles" element={<RequirePermission permission="module.vehicles" roles={["gestor_brasil", "operador_logistico"]}><Vehicles /></RequirePermission>} />
          <Route path="/carriers" element={<RequirePermission internalOnly permission="module.carriers" roles={["gestor_brasil"]}><Carriers /></RequirePermission>} />
          <Route path="/config/branches" element={<RequirePermission internalOnly permission="module.branches" roles={["gestor_brasil"]}><Branches /></RequirePermission>} />
          <Route path="/reports" element={<RequirePermission internalOnly permission="module.reports" roles={["gestor_brasil", "gestor_financeiro", "auditor", "diretoria"]}><Reports /></RequirePermission>} />
          <Route path="/users" element={<RequirePermission permission="module.users" roles={["gestor_brasil"]}><Users /></RequirePermission>} />
          <Route path="/profiles" element={<RequireRole roles={["admin_global"]}><Profiles /></RequireRole>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes></Suspense></BrowserRouter>
    </AuthProvider></BrandingProvider></ThemeProvider>
  );
}

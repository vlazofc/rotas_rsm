import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrandingProvider } from "./context/BrandingContext";
import { ThemeProvider } from "./context/ThemeContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import RoutesPage from "./pages/Routes";
import RouteDetail from "./pages/RouteDetail";
import ManifestsPage from "./pages/Manifests";
import Expenses from "./pages/Expenses";
import Reports from "./pages/Reports";
import Audit from "./pages/Audit";
import Users from "./pages/Users";
import Config from "./pages/Config";
import PreviewSession from "./pages/PreviewSession";
import Revenues from "./pages/Revenues";
import Financeiro from "./pages/Financeiro";

function Loading() {
  return <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>…</div>;
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return user ? children : <Navigate to="/login" replace />;
}

function RequireRole({ roles, children }: { roles: string[]; children: JSX.Element }) {
  const { hasRole, loading } = useAuth();
  if (loading) return <Loading />;
  return hasRole(...roles) ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <ThemeProvider>
    <BrandingProvider>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/preview-session" element={<PreviewSession />} />
          <Route path="/" element={<RequireAuth><Layout><Dashboard /></Layout></RequireAuth>} />
          <Route path="/routes" element={<RequireAuth><Layout><RoutesPage /></Layout></RequireAuth>} />
          <Route path="/routes/:id" element={<RequireAuth><Layout><RouteDetail /></Layout></RequireAuth>} />
          <Route path="/manifests" element={<RequireAuth><Layout><ManifestsPage /></Layout></RequireAuth>} />
          <Route path="/expenses" element={<RequireAuth><Layout><Expenses /></Layout></RequireAuth>} />
          <Route
            path="/revenues"
            element={
              <RequireAuth>
                <RequireRole roles={["admin_global", "gestor_brasil", "gestor_financeiro"]}>
                  <Layout><Revenues /></Layout>
                </RequireRole>
              </RequireAuth>
            }
          />
          <Route
            path="/financeiro"
            element={
              <RequireAuth>
                <RequireRole roles={["admin_global", "gestor_brasil", "gestor_financeiro"]}>
                  <Layout><Financeiro /></Layout>
                </RequireRole>
              </RequireAuth>
            }
          />
          <Route
            path="/reports"
            element={
              <RequireAuth>
                <RequireRole roles={["admin_global", "gestor_brasil", "auditor"]}>
                  <Layout><Reports /></Layout>
                </RequireRole>
              </RequireAuth>
            }
          />
          <Route
            path="/audit"
            element={
              <RequireAuth>
                <RequireRole roles={["admin_global", "gestor_brasil", "auditor"]}>
                  <Layout><Audit /></Layout>
                </RequireRole>
              </RequireAuth>
            }
          />
          <Route
            path="/config/:tab?"
            element={
              <RequireAuth>
                <RequireRole roles={["admin_global", "gestor_brasil"]}>
                  <Layout><Config /></Layout>
                </RequireRole>
              </RequireAuth>
            }
          />
          <Route
            path="/users"
            element={
              <RequireAuth>
                <RequireRole roles={["admin_global", "gestor_brasil"]}>
                  <Layout><Users /></Layout>
                </RequireRole>
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
    </BrandingProvider>
    </ThemeProvider>
  );
}

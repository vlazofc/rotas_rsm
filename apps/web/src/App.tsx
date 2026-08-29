import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrandingProvider } from "./context/BrandingContext";
import { ThemeProvider } from "./context/ThemeContext";
import Layout from "./components/Layout";
import AppDialogHost from "./components/AppDialog";

const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const RoutesPage = lazy(() => import("./pages/Routes"));
const RouteDetail = lazy(() => import("./pages/RouteDetail"));
const Expenses = lazy(() => import("./pages/Expenses"));
const Reports = lazy(() => import("./pages/Reports"));
const Audit = lazy(() => import("./pages/Audit"));
const Users = lazy(() => import("./pages/Users"));
const Config = lazy(() => import("./pages/Config"));
const PreviewSession = lazy(() => import("./pages/PreviewSession"));
const Revenues = lazy(() => import("./pages/Revenues"));
const Financeiro = lazy(() => import("./pages/Financeiro"));
const FleetMaintenance = lazy(() => import("./pages/FleetMaintenance"));
const Gallery = lazy(() => import("./pages/Gallery"));
const ERP = lazy(() => import("./pages/ERP"));
const Tracking = lazy(() => import("./pages/Tracking"));
const FinancialDashboard = lazy(() => import("./pages/FinancialDashboard"));
const Occurrences = lazy(() => import("./pages/Occurrences"));
const Purchases = lazy(() => import("./pages/Purchases"));
const FinancialAccounts = lazy(() => import("./pages/FinancialAccounts"));
const Drivers = lazy(() => import("./pages/Drivers"));
const Vehicles = lazy(() => import("./pages/Vehicles"));
const Suppliers = lazy(() => import("./pages/Suppliers"));
const Customers = lazy(() => import("./pages/Customers"));
const ExpenseApprovals = lazy(() => import("./pages/ExpenseApprovals"));
const WorkflowTasks = lazy(() => import("./pages/WorkflowTasks"));
const CalculationMemory = lazy(() => import("./pages/CalculationMemory"));
const Statement = lazy(() => import("./pages/Statement"));
const DriverStatementPortal = lazy(() => import("./pages/DriverStatementPortal"));
const ExecutiveAI = lazy(() => import("./pages/ExecutiveAI"));
const Carriers = lazy(() => import("./pages/RegistryPages").then((module) => ({ default: module.Carriers })));
const FailureReasons = lazy(() => import("./pages/RegistryPages").then((module) => ({ default: module.FailureReasons })));
const Profiles = lazy(() => import("./pages/RegistryPages").then((module) => ({ default: module.Profiles })));
const VehicleTypes = lazy(() => import("./pages/RegistryPages").then((module) => ({ default: module.VehicleTypes })));

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

function RequirePermission({ permission, roles = [], children }: { permission: string; roles?: string[]; children: JSX.Element }) {
  const { hasPermission, loading } = useAuth();
  if (loading) return <Loading />;
  return hasPermission(permission, ...roles) ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <ThemeProvider>
    <BrandingProvider>
    <AuthProvider>
      <AppDialogHost />
      <BrowserRouter>
        <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/preview-session" element={<PreviewSession />} />
          <Route path="/" element={<RequireAuth><Layout><Dashboard /></Layout></RequireAuth>} />
          <Route path="/routes" element={<RequireAuth><Layout><RoutesPage /></Layout></RequireAuth>} />
          <Route path="/routes/:id" element={<RequireAuth><Layout><RouteDetail /></Layout></RequireAuth>} />
          <Route path="/expenses" element={<RequireAuth><Layout><Expenses /></Layout></RequireAuth>} />
          <Route
            path="/revenues"
            element={
              <RequireAuth>
                <RequirePermission permission="finance.view" roles={["gestor_brasil", "gestor_financeiro"]}>
                  <Layout><Revenues /></Layout>
                </RequirePermission>
              </RequireAuth>
            }
          />
          <Route
            path="/financeiro"
            element={
              <RequireAuth>
                <RequirePermission permission="finance.view" roles={["gestor_brasil", "gestor_financeiro"]}>
                  <Layout><Financeiro /></Layout>
                </RequirePermission>
              </RequireAuth>
            }
          />
          <Route
            path="/fleet-maintenance"
            element={
              <RequireAuth>
                <RequireRole roles={["admin_global", "gestor_brasil"]}>
                  <Layout><FleetMaintenance /></Layout>
                </RequireRole>
              </RequireAuth>
            }
          />
          <Route
            path="/gallery"
            element={
              <RequireAuth>
                <RequireRole roles={["admin_global", "gestor_brasil", "auditor", "operador_logistico"]}>
                  <Layout><Gallery /></Layout>
                </RequireRole>
              </RequireAuth>
            }
          />
          <Route path="/erp" element={<RequireAuth><Layout><ERP /></Layout></RequireAuth>} />
          <Route path="/tracking" element={<RequireAuth><Layout><Tracking /></Layout></RequireAuth>} />
          <Route path="/occurrences" element={<RequireAuth><Layout><Occurrences /></Layout></RequireAuth>} />
          <Route path="/tasks" element={<RequireAuth><Layout><WorkflowTasks /></Layout></RequireAuth>} />
          <Route path="/purchases" element={<RequireAuth><Layout><Purchases /></Layout></RequireAuth>} />
          <Route path="/financial-dashboard" element={<RequireAuth><RequirePermission permission="finance.view" roles={["gestor_brasil","gestor_financeiro"]}><Layout><FinancialDashboard /></Layout></RequirePermission></RequireAuth>} />
          <Route path="/financial-accounts" element={<RequireAuth><RequirePermission permission="finance.view" roles={["gestor_brasil","gestor_financeiro"]}><Layout><FinancialAccounts /></Layout></RequirePermission></RequireAuth>} />
          <Route path="/calculation-memory" element={<RequireAuth><RequirePermission permission="finance.view" roles={["gestor_brasil","gestor_financeiro","auditor"]}><Layout><CalculationMemory /></Layout></RequirePermission></RequireAuth>} />
          <Route path="/statement" element={<RequireAuth><RequirePermission permission="finance.view" roles={["gestor_brasil","gestor_financeiro"]}><Layout><Statement /></Layout></RequirePermission></RequireAuth>} />
          <Route path="/my-statement" element={<RequireAuth><RequireRole roles={["motorista"]}><Layout><DriverStatementPortal /></Layout></RequireRole></RequireAuth>} />
          <Route path="/executive-ai" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil","gestor_financeiro","auditor","diretoria"]}><Layout><ExecutiveAI /></Layout></RequireRole></RequireAuth>} />
          <Route path="/expense-approvals" element={<RequireAuth><RequirePermission permission="finance.expense.approve" roles={["gestor_brasil","gestor_financeiro"]}><Layout><ExpenseApprovals /></Layout></RequirePermission></RequireAuth>} />
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
          <Route path="/config/drivers" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil"]}><Layout><Drivers /></Layout></RequireRole></RequireAuth>} />
          <Route path="/config/vehicles" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil","operador_logistico","torre_controle"]}><Layout><Vehicles /></Layout></RequireRole></RequireAuth>} />
          <Route path="/suppliers" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil","gestor_financeiro","operador_logistico"]}><Layout><Suppliers /></Layout></RequireRole></RequireAuth>} />
          <Route path="/customers" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil"]}><Layout><Customers /></Layout></RequireRole></RequireAuth>} />
          <Route path="/profiles" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil"]}><Layout><Profiles /></Layout></RequireRole></RequireAuth>} />
          <Route path="/vehicle-types" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil"]}><Layout><VehicleTypes /></Layout></RequireRole></RequireAuth>} />
          <Route path="/failure-reasons" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil"]}><Layout><FailureReasons /></Layout></RequireRole></RequireAuth>} />
          <Route path="/carriers" element={<RequireAuth><RequireRole roles={["admin_global","gestor_brasil"]}><Layout><Carriers /></Layout></RequireRole></RequireAuth>} />
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
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
    </BrandingProvider>
    </ThemeProvider>
  );
}

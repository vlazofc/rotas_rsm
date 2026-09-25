import { ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useBranding } from "../context/BrandingContext";
import api, { exitPreviewSession, isPreviewMode } from "../services/api";
import LanguageSwitcher from "./LanguageSwitcher";
import ThemeToggle from "./ThemeToggle";
import { usePolling } from "../hooks/usePolling";
import { OfflineQueueState, subscribeOfflineQueue, syncOfflineQueue } from "../services/offlineQueue";

interface NavItem {
  to: string;
  label: string;
  icon?: string;
  roles?: string[]; // ausente = visível para todos os perfis autenticados
  group?: string;
  feature?: "feature_rastreamento" | "feature_route_optimization"; // exige o serviço ativo no cliente
  permission?: string;
  fallbackRoles?: string[];
}
interface AppNotification { id: number; title: string; body?: string; read: boolean; created_at: string }
interface LiveAlert { id:string;event_type:string;severity:"critical"|"warning"|"info";category:string;title:string;body:string;href:string;due_date?:string|null }
interface ActingOption { id:number; name:string }

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

function NavIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    tracking: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a8 8 0 1 0-2.8 3.2"/><path d="m16 16 5 5m0-5v5h-5"/></>,
    route: <><circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h3a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7"/></>,
    alert: <><path d="M10.3 2.9 1.8 17a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 2.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4m0 4h.01"/></>,
    tasks: <><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 3V1h6v2M8 9l2 2 4-4m-6 9h8"/></>,
    gallery: <><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></>,
    money: <><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M16 9a4 4 0 0 0-8 0c0 4 8 2 8 6a4 4 0 0 1-8 0M12 7v10"/></>,
    expense: <><path d="M12 3v14m-4-4 4 4 4-4"/><path d="M5 21h14"/></>,
    revenue: <><path d="M12 21V7m-4 4 4-4 4 4"/><path d="M5 3h14"/></>,
    account: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 14h2"/></>,
    ledger: <><path d="M4 3h14a2 2 0 0 1 2 2v16H6a2 2 0 0 1-2-2V3Z"/><path d="M8 3v18m4-13h5m-5 4h5"/></>,
    person: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
    vehicle: <><path d="m5 17-2-1V9l3-5h12l3 5v7l-2 1"/><path d="M5 17h14M5 9h14"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/></>,
    box: <><path d="m3 6 9-4 9 4-9 4-9-4Z"/><path d="m3 6 9 4 9-4v12l-9 4-9-4V6Z"/></>,
    building: <><path d="M3 21h18M6 21V3h12v18M9 7h2m2 0h2M9 11h2m2 0h2M9 15h2m2 0h2"/></>,
    wrench: <><path d="M14.7 6.3a4 4 0 0 0-5-5L12 3.6 9.6 6 7.3 3.7a4 4 0 0 0 5 5L4 17l3 3 8.3-8.3a4 4 0 0 0 5-5L18 9l-3-3 2.3-2.3"/></>,
    tire: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M7 4.5 9 8m8-3.5L15 8M7 19.5 9 16m8 3.5L15 16"/></>,
    document: <><path d="M6 2h9l4 4v16H6V2Z"/><path d="M14 2v5h5M9 12h6m-6 4h6"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1A7 7 0 0 0 15 6l-.3-2.6h-4L10.4 6A7 7 0 0 0 9 7L6.6 6 4.6 9.5 6.7 11a7 7 0 0 0 0 2l-2.1 1.5 2 3.4 2.4-1A7 7 0 0 0 10.4 18l.3 2.6h4L15 18a7 7 0 0 0 1.5-1l2.4 1 2-3.4-2-1.5a7 7 0 0 0 .1-1Z"/></>,
    calculator: <><rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8v4H8zM8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h4"/></>,
    receipt: <><path d="M5 2h14v20l-3-2-4 2-4-2-3 2V2Z"/><path d="M8 7h8M8 11h8M8 15h5"/></>,
    chart: <><path d="M4 20V10m6 10V4m6 16v-7m5 7H2"/></>,
    report: <><path d="M6 2h9l4 4v16H6V2Z"/><path d="M14 2v5h5M9 17v-3m3 3v-6m3 6V9"/></>,
    audit: <><path d="M6 3h12v18H6zM9 7h6M9 11h3"/><path d="m13 16 2 2 4-5"/></>,
    robot: <><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/></>,
    users: <><circle cx="9" cy="8" r="3"/><circle cx="17" cy="10" r="2"/><path d="M3 20a6 6 0 0 1 12 0M14 16a5 5 0 0 1 7 4"/></>,
    badge: <><rect x="4" y="3" width="16" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M7 15h4m3-7h3m-3 4h3"/></>,
    store: <><path d="M3 9 5 3h14l2 6"/><path d="M5 13v8h14v-8M3 9a3 3 0 0 0 5 2 3 3 0 0 0 4 0 3 3 0 0 0 4 0 3 3 0 0 0 5-2"/></>,
    supplier: <><path d="M3 7h11v12H3zM14 11h4l3 4v4h-7z"/><circle cx="7" cy="20" r="2"/><circle cx="18" cy="20" r="2"/></>,
    link: <><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/></>,
    clipboard: <><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 10l2 2 4-4M9 16h6"/></>,
    inventory: <><path d="M4 7h16v14H4zM2 3h20v4H2zM9 11h6"/></>,
    tag: <><path d="M20 13 11 22 2 13V2h11l7 7v4Z"/><circle cx="7" cy="7" r="1"/></>,
  };
  return <span className="nav-link-icon" aria-hidden="true"><IconSvg>{paths[name] || paths.document}</IconSvg></span>;
}

function navIconFor(item: NavItem) {
  const path = item.to;
  if (path === "/") return "dashboard";
  if (path === "/reports") return "report";
  if (path === "/audit") return "audit";
  if (path === "/executive-ai") return "robot";
  if (path === "/profiles") return "badge";
  if (path === "/users") return "users";
  if (path === "/customers") return "store";
  if (path === "/suppliers") return "supplier";
  if (path === "/carriers") return "link";
  if (path === "/failure-reasons") return "tag";
  if (path.includes("tab=checklist")) return "clipboard";
  if (path.includes("tab=stock")) return "inventory";
  if (path.includes("tab=tires")) return "tire";
  if (path.includes("tab=plans")) return "settings";
  if (path.includes("tracking")) return "tracking";
  if (path.includes("occurrence")) return "alert";
  if (path.includes("task") || path.includes("approval")) return "tasks";
  if (path.includes("gallery")) return "gallery";
  if (path.includes("route")) return "route";
  if (path.includes("drivers") || path.includes("users") || path.includes("profiles")) return "person";
  if (path.includes("vehicles") || path.includes("vehicle-types")) return "vehicle";
  if (path.includes("carriers") || path.includes("suppliers") || path.includes("customers")) return "building";
  if (path.includes("stock") || path.includes("purchases")) return "box";
  if (path.includes("tires")) return "tire";
  if (path.includes("fleet-maintenance")) return "wrench";
  if (path.includes("config") || path.includes("failure-reasons")) return "settings";
  return item.icon || "document";
}

export default function Layout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const loc = useLocation();
  const { user, logout, refresh, hasRole, hasPermission } = useAuth();
  const { branding } = useBranding();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar_collapsed") === "1");
  const [navigationLayout,setNavigationLayout]=useState<"sidebar"|"top">("sidebar");
  const [openTopGroup, setOpenTopGroup] = useState<string | null>(null);
  const topNavRef = useRef<HTMLElement>(null);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [liveAlerts,setLiveAlerts]=useState<LiveAlert[]>([]);
  const [alertFilter,setAlertFilter]=useState<"all"|"critical"|"warning"|"info">("all");
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const notificationsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!notificationsOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !notificationsRef.current?.contains(event.target)) {
        setNotificationsOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeOutside, true);
    return () => document.removeEventListener("pointerdown", closeOutside, true);
  }, [notificationsOpen]);
  const [clearingNotifications, setClearingNotifications] = useState(false);
  const [notificationToasts, setNotificationToasts] = useState<AppNotification[]>([]);
  const seenNotificationIds = useRef(new Set<number>());
  const toastTimers = useRef(new Map<number, number>());
  const [features, setFeatures] = useState({ feature_rastreamento: true, feature_route_optimization: true, feature_km_calculation: true });
  const [appConsentRequired, setAppConsentRequired] = useState(false);
  const [appConsentReady, setAppConsentReady] = useState(false);
  const [savingAppConsent, setSavingAppConsent] = useState(false);
  const driverTrackingRoute = useRef<number | null>(null);
  const driverBrowserWatch = useRef<number | null>(null);
  const [offlineQueue, setOfflineQueue] = useState<OfflineQueueState>({ online: navigator.onLine, pending: 0, syncing: false, failed: 0 });
  const [actingBranches,setActingBranches]=useState<ActingOption[]>([]);
  const [actingCarriers,setActingCarriers]=useState<ActingOption[]>([]);
  const [adminCount,setAdminCount]=useState<number|null>(null);

  useEffect(() => { const unsubscribe = subscribeOfflineQueue(setOfflineQueue); return unsubscribe; }, []);

  useEffect(()=>{
    if(user?.role!=="admin_global")return;
    Promise.all([api.get("/branches"),api.get("/carriers"),api.get("/auth/admin-security-status")]).then(([branches,carriers,security])=>{
      setActingBranches(branches.data);setActingCarriers(carriers.data);setAdminCount(security.data.active_admin_count);
    }).catch(()=>{});
  },[user?.role]);

  async function setActingContext(branchId:number|null,carrierId:number|null){
    await api.put("/auth/acting-context",{branch_id:branchId,carrier_id:carrierId});
    await refresh();
    window.location.assign("/");
  }

  useEffect(() => {
    api.get("/tenants/me")
      .then((r) => setFeatures({
        feature_rastreamento: r.data.feature_rastreamento,
        feature_route_optimization: r.data.feature_route_optimization ?? true,
        feature_km_calculation: r.data.feature_km_calculation ?? true,
      }))
      .catch(() => {});
  }, []);
  useEffect(()=>{if(user?.navigation_layout)setNavigationLayout(user.navigation_layout)},[user?.navigation_layout]);
  useEffect(() => {
    if (user?.role !== "motorista") { setAppConsentRequired(false); return; }
    setAppConsentReady(false);
    api.get<{accepted:boolean}>("/tracking/app-permission-consent")
      .then(({data}) => { setAppConsentRequired(!data.accepted); setAppConsentReady(data.accepted); })
      .catch(() => { setAppConsentRequired(true); setAppConsentReady(false); });
  }, [user?.id, user?.role]);

  async function acceptAppPermissions() {
    setSavingAppConsent(true);
    try {
      await api.put("/tracking/app-permission-consent", { accepted: true, terms_version: "1.0" });
      setAppConsentRequired(false);
      setAppConsentReady(true);
      const android = window.AndroidLocation as (typeof window.AndroidLocation & { requestAllPermissions?: () => void }) | undefined;
      android?.requestAllPermissions?.();
    } finally {
      setSavingAppConsent(false);
    }
  }

  useEffect(() => {
    if (user?.role !== "motorista" || !appConsentReady) return;
    let disposed = false;
    let routeTimer: number | undefined;
    let refreshingRoute = false;
    const stop = (revoke: boolean) => {
      window.AndroidLocation?.stopLocationUpdates?.();
      if (driverBrowserWatch.current !== null) navigator.geolocation.clearWatch(driverBrowserWatch.current);
      driverBrowserWatch.current = null;
      delete window.onAndroidLocation;
      const wasActive = driverTrackingRoute.current !== null;
      driverTrackingRoute.current = null;
      if (revoke && wasActive) void api.put("/tracking/consent", { accepted: false, terms_version: "1.0" }).catch(() => {});
    };
    const start = async (routeId: number) => {
      if (driverTrackingRoute.current === routeId || disposed) return;
      stop(false);
      await api.put("/tracking/consent", { accepted: true, terms_version: "1.0" });
      if (disposed) return;
      driverTrackingRoute.current = routeId;
      const send = (latitude:number,longitude:number,accuracy?:number,speedMps?:number,recordedAt?:string) => void api.post("/tracking/positions", { route_id: routeId, latitude, longitude, accuracy_m: accuracy, speed_kmh: speedMps == null ? null : speedMps * 3.6, recorded_at: recordedAt || undefined }).catch(() => {});
      window.onAndroidLocation = send;
      if (window.AndroidLocation) { window.AndroidLocation.startLocationUpdates?.(120000); return; }
      driverBrowserWatch.current = navigator.geolocation.watchPosition(p => send(p.coords.latitude,p.coords.longitude,p.coords.accuracy,p.coords.speed??undefined),() => {},{enableHighAccuracy:true,maximumAge:15000});
    };
    const refresh = async () => {
      if (disposed || refreshingRoute || document.hidden) return;
      refreshingRoute = true;
      try {
        const {data} = await api.get<Array<{id:number;status:string;route_date?:string}>>("/routes");
        const today = new Date().toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
        const active = data.find(route => route.status === "em_rota")
          ?? data.find(route => route.route_date === today && !["finalizada", "cancelada"].includes(route.status));
        if (active) await start(active.id); else stop(true);
      } finally {
        refreshingRoute = false;
        if (!disposed) routeTimer = window.setTimeout(() => void refresh(), 27000 + Math.random() * 6000);
      }
    };
    void refresh();
    const onVisible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      disposed = true;
      if (routeTimer) window.clearTimeout(routeTimer);
      document.removeEventListener("visibilitychange", onVisible);
      stop(false);
    };
  }, [user?.id, user?.role, appConsentReady]);
  useEffect(() => {
    setOpenTopGroup(null);
    setNotificationsOpen(false);
    setNotificationToasts([]);
    toastTimers.current.forEach((toastTimer) => window.clearTimeout(toastTimer));
    toastTimers.current.clear();
  }, [loc.pathname, loc.search]);
  useEffect(() => {
    if (!openTopGroup) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !topNavRef.current?.contains(event.target)) setOpenTopGroup(null);
    };
    document.addEventListener("pointerdown", closeOutside, true);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNotificationsOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside, true);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [openTopGroup]);
  async function toggleNavigationLayout(){const next=navigationLayout==="sidebar"?"top":"sidebar";setNavigationLayout(next);try{await api.put("/auth/preferences",{navigation_layout:next});await refresh()}catch{setNavigationLayout(navigationLayout)}}

  const loadNotifications = () => {
      const notificationsRequest = api.get<AppNotification[]>("/notifications", { params: { unread_only: true } }).then((r) => {
        const unread = r.data;
        const incoming = unread.filter((item) => !seenNotificationIds.current.has(item.id)).slice(0, 3);
        r.data.forEach((item) => seenNotificationIds.current.add(item.id));
        setNotifications(r.data);
        if (incoming.length) {
          const nativeAlerts = window.AndroidLocation as (typeof window.AndroidLocation & { showNotification?: (title:string, message:string, notificationId:number) => void }) | undefined;
          const newest = incoming[0];
          nativeAlerts?.showNotification?.(newest.title || "Aviso operacional", newest.body || "Há uma nova atualização na sua rota.", newest.id);
          setNotificationToasts((current) => [...incoming, ...current.filter((item) => !incoming.some((next) => next.id === item.id))].slice(0, 3));
          incoming.forEach((item) => {
            const existing = toastTimers.current.get(item.id);
            if (existing) window.clearTimeout(existing);
            toastTimers.current.set(item.id, window.setTimeout(() => {
              setNotificationToasts((current) => current.filter((toast) => toast.id !== item.id));
              toastTimers.current.delete(item.id);
            }, 9000));
          });
        }
      }).catch(() => {});
      const alertsRequest = api.get<LiveAlert[]>("/notifications/live").then(r=>setLiveAlerts(r.data)).catch(()=>{});
      return Promise.allSettled([notificationsRequest, alertsRequest]).then(() => undefined);
  };

  useEffect(() => {
    loadNotifications();
    return () => {
      toastTimers.current.forEach((toastTimer) => window.clearTimeout(toastTimer));
      toastTimers.current.clear();
    };
  }, []);
  usePolling(loadNotifications, 60000);

  async function readNotification(id: number) {
    const previous = notifications;
    setNotifications((items) => items.filter((item) => item.id !== id));
    dismissNotificationToast(id);
    try {
      await api.post(`/notifications/${id}/read`);
    } catch {
      setNotifications(previous);
    }
  }
  async function clearNotifications() {
    if ((!notifications.length && !liveAlerts.length) || clearingNotifications) return;
    const previous = notifications;
    const previousAlerts = liveAlerts;
    setClearingNotifications(true);
    setNotifications([]);
    setLiveAlerts([]);
    setNotificationToasts([]);
    toastTimers.current.forEach((toastTimer) => window.clearTimeout(toastTimer));
    toastTimers.current.clear();
    try {
      await Promise.all([
        api.post("/notifications/actions/read-all"),
        api.post("/notifications/actions/dismiss-live", { alert_ids: previousAlerts.map((item) => item.id) }),
      ]);
    } catch {
      setNotifications(previous);
      setLiveAlerts(previousAlerts);
    } finally {
      setClearingNotifications(false);
    }
  }
  async function viewLiveAlert(alert: LiveAlert) {
    setLiveAlerts((items) => items.filter((item) => item.id !== alert.id));
    try {
      await api.post("/notifications/actions/dismiss-live", { alert_ids: [alert.id] });
    } catch {
      setLiveAlerts((items) => items.some((item) => item.id === alert.id) ? items : [...items, alert]);
    }
    setNotificationsOpen(false);
  }
  function dismissNotificationToast(id: number) {
    const timer = toastTimers.current.get(id);
    if (timer) window.clearTimeout(timer);
    toastTimers.current.delete(id);
    setNotificationToasts((items) => items.filter((item) => item.id !== id));
  }
  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar_collapsed", next ? "1" : "0");
      return next;
    });
  }

  const allItems: NavItem[] = [
    // Navegação enxuta da operação JMD.
    { to: "/", label: t("nav.dashboard"), permission:"module.dashboard", fallbackRoles: ["gestor_brasil", "auditor", "operador_logistico", "torre_controle"], group: t("nav.group_operation") },
    { to: "/routes", label: t("nav.routes"), permission:"module.routes", fallbackRoles:["gestor_brasil","operador_logistico","torre_controle","motorista","cliente"], group: t("nav.group_operation") },
    { to: "/routing", label: "Monitoramento de rotas", permission:"module.monitoring", fallbackRoles: ["gestor_brasil","operador_logistico","torre_controle"], group: t("nav.group_operation"), feature: "feature_route_optimization" },
    { to: "/routing/manual", label: "Roteirização manual", permission:"module.routing", fallbackRoles: ["gestor_brasil","operador_logistico","torre_controle"], group: t("nav.group_operation"), feature: "feature_route_optimization" },
    { to: "/occurrences", label: "Ocorrências", permission:"module.occurrences", fallbackRoles:["gestor_brasil","operador_logistico","torre_controle","motorista"], group: t("nav.group_operation") },
    { to: "/gallery", label: "Galeria", permission:"module.gallery", fallbackRoles: ["gestor_brasil","auditor","operador_logistico","torre_controle"], group: t("nav.group_operation") },
    { to: "/tracking", label: "Monitoramento GPS", permission:"module.tracking", fallbackRoles:["gestor_brasil","operador_logistico","torre_controle","motorista","cliente"], group: t("nav.group_operation"), feature: "feature_rastreamento" },

    // --- Cadastros ---
    { to: "/config/drivers", label: t("config.tabs.drivers"), permission:"module.drivers", fallbackRoles: ["gestor_brasil", "operador_logistico"], group: t("nav.group_registers") },
    { to: "/config/vehicles", label: t("config.tabs.vehicles"), permission:"module.vehicles", fallbackRoles: ["gestor_brasil", "operador_logistico"], group: t("nav.group_registers") },
    { to: "/carriers", label: "Transportadoras", permission:"module.carriers", fallbackRoles: ["gestor_brasil"], group: t("nav.group_registers") },
    { to: "/config/branches", label: "Filiais Adimax", permission:"module.branches", fallbackRoles: ["gestor_brasil"], group: t("nav.group_registers") },

    // --- Administração ---
    { to: "/reports", label: t("nav.reports", { defaultValue: "Relatórios" }), permission:"module.reports", fallbackRoles:["gestor_brasil","gestor_financeiro","auditor","diretoria"], group: t("nav.group_admin") },
    { to: "/users", label: t("nav.users"), permission:"module.users", fallbackRoles:["gestor_brasil"], group: t("nav.group_admin") },
    { to: "/profiles", label: "Perfis de acesso", roles: ["admin_global"], group: t("nav.group_admin") },
  ];

  const items = allItems.filter((i) =>
    (!user?.is_carrier_master || ["/", "/routes", "/occurrences", "/gallery", "/tracking", "/config/drivers", "/config/vehicles", "/users"].includes(i.to)) &&
    (!i.roles || hasRole(...i.roles)) &&
    (!i.permission || hasPermission(i.permission, ...(i.fallbackRoles || []))) &&
    (!i.feature || features[i.feature])
  );
  const desiredGroupOrder = [
    t("nav.group_operation"),
    t("nav.group_fleet", { defaultValue: "Frota" }),
    t("nav.group_registers"),
    t("nav.group_admin"),
  ];
  const groups = desiredGroupOrder.filter((group) => items.some((i) => i.group === group));

  return (
    <div className={`app-shell navigation-${navigationLayout}${collapsed ? " is-collapsed" : ""}${branding.topbar_extends_sidebar ? " strip-extended" : ""}${user?.role==="admin_global"?" has-admin-context-bar":""}`} style={{"--nav-bg":branding.sidebar_background_color||"var(--panel)","--nav-text":branding.sidebar_text_color||"#334155","--nav-active":branding.sidebar_active_color||branding.primary_color||"var(--brand)"} as React.CSSProperties}>
      {user?.role==="admin_global"&&<div style={{position:"fixed",zIndex:1200,left:0,right:0,top:0,display:"flex",justifyContent:"center",alignItems:"center",gap:8,padding:"6px 12px",background:user.acting_read_only?"#7c2d12":"#172554",color:"white",fontSize:12}}>
        <strong>{user.acting_read_only?"VER COMO · SOMENTE LEITURA":"Administrador global"}</strong>
        <select aria-label="Ver como filial" value={user.acting_branch_id||""} onChange={e=>void setActingContext(e.target.value?Number(e.target.value):null,user.acting_carrier_id||null)}><option value="">Todas as filiais</option>{actingBranches.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <select aria-label="Ver como transportadora" value={user.acting_carrier_id||""} onChange={e=>void setActingContext(user.acting_branch_id||null,e.target.value?Number(e.target.value):null)}><option value="">Todas as transportadoras</option>{actingCarriers.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        {user.acting_read_only&&<button type="button" onClick={()=>void setActingContext(null,null)}>Sair do modo</button>}
        {adminCount!==null&&adminCount>1&&<span title="Revise periodicamente as contas com acesso irrestrito.">⚠ {adminCount} administradores globais ativos</span>}
      </div>}
      {(!offlineQueue.online || offlineQueue.pending > 0) && (
        <button className={`offline-queue-banner${offlineQueue.failed ? " has-error" : ""}`} type="button" onClick={() => void syncOfflineQueue()}>
          <strong>{offlineQueue.online ? (offlineQueue.syncing ? "Sincronizando operação…" : `${offlineQueue.pending} ação(ões) aguardando envio`) : "Trabalhando sem internet"}</strong>
          <span>{offlineQueue.online ? (offlineQueue.failed ? "Toque para tentar novamente" : "Os registros serão enviados em ordem") : "Pode continuar: suas ações estão salvas neste aparelho"}</span>
        </button>
      )}
      {appConsentRequired && <div className="app-consent-backdrop" role="presentation">
        <section className="app-consent-card" role="dialog" aria-modal="true" aria-labelledby="app-consent-title">
          <div className="app-consent-brand">ADIMAX · MOTORISTA</div>
          <h2 id="app-consent-title">Permissões e compartilhamento</h2>
          <p>Para registrar e comprovar as operações da rota, o aplicativo precisa utilizar os recursos abaixo.</p>
          <div className="app-consent-items">
            <article><span>⌖</span><div><strong>Localização e GPS</strong><small>Usados durante a operação para acompanhar a rota, registrar posição, data e hora das evidências.</small></div></article>
            <article><span>▣</span><div><strong>Câmera e arquivos</strong><small>Usados para fotografar e anexar comprovantes de entrega, falhas e ocorrências.</small></div></article>
            <article><span>✓</span><div><strong>Registro do aceite</strong><small>Seu aceite, usuário, versão do termo e data/hora ficam armazenados para auditoria.</small></div></article>
          </div>
          <p className="app-consent-note">Os dados são utilizados exclusivamente para execução, rastreabilidade e evidência das entregas. As permissões do Android podem ser alteradas nas configurações do aparelho.</p>
          <button className="btn-primary app-consent-accept" type="button" disabled={savingAppConsent} onClick={() => void acceptAppPermissions()}>{savingAppConsent ? "Registrando aceite…" : "Li e aceito · Continuar"}</button>
        </section>
      </div>}
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
          ) : (branding.app_name || "Adimax").slice(0, 2).toUpperCase()}
        </button>
        <nav className="rail-nav" aria-label="Navegação recolhida">
          {items.map((item) => {
            const [itemPath,itemQuery]=item.to.split("?");
            const currentParams=new URLSearchParams(loc.search),itemParams=new URLSearchParams(itemQuery||"");
            const active=itemQuery?loc.pathname===itemPath&&[...itemParams.entries()].every(([key,value])=>currentParams.get(key)===value):(["/","/routing"].includes(item.to)?loc.pathname===item.to:loc.pathname===item.to||loc.pathname.startsWith(`${item.to}/`));
            return <Link key={item.to} to={item.to} className={`rail-nav-link${active?" is-active":""}`} title={item.label} aria-label={item.label}><NavIcon name={navIconFor(item)}/></Link>;
          })}
        </nav>
      </div>

      <aside className="sidebar">
        <div className="sidebar-head">
          <div className="sidebar-head-row">
            <div className="sidebar-brand-copy">
              {branding.logo_url && <img className="sidebar-logo" src={branding.logo_url} alt="" />}
              <h3 className="app-title">{branding.app_name || t("app.title")}</h3>
              <div className="app-subtitle">{branding.app_subtitle || t("app.subtitle")}</div>
            </div>
            <button type="button" className="sidebar-collapse-btn" onClick={toggleSidebar} title="Recolher menu" aria-label="Recolher menu">
              <IconSvg><path d="m15 18-6-6 6-6" /></IconSvg>
            </button>
          </div>
        </div>
        <nav className="nav-groups">
          {groups.map((group) => (
            <div key={group}>
              <div className="nav-group-title">{group}</div>
              <div className="nav-links">
                {items.filter((i) => (i.group ?? "") === group).map((i) => {
                  const [itemPath, itemQuery] = i.to.split("?");
                  const currentParams = new URLSearchParams(loc.search);
                  const itemParams = new URLSearchParams(itemQuery || "");
                  const active = itemQuery
                    ? loc.pathname === itemPath && [...itemParams.entries()].every(([key, value]) => currentParams.get(key) === value)
                    : (["/", "/routing"].includes(i.to) ? loc.pathname === i.to : loc.pathname === i.to || loc.pathname.startsWith(`${i.to}/`));
                  return (
                    <Link key={i.to} to={i.to} className={`nav-link${active ? " is-active" : ""}`}>
                      <NavIcon name={navIconFor(i)} />
                      <span>{i.label}</span>
                    </Link>
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

      {navigationLayout==="top"&&<header className="horizontal-nav" ref={topNavRef}>
        <Link to="/" className="horizontal-brand">{branding.logo_url&&<img src={branding.logo_url} alt=""/>}<span><strong>{branding.app_name||t("app.title")}</strong><small>{branding.app_subtitle||t("app.subtitle")}</small></span></Link>
        <nav>{groups.map(group=><div className={`horizontal-group${openTopGroup===group?" is-open":""}`} key={group}>
          <button type="button" aria-expanded={openTopGroup===group} onClick={()=>setOpenTopGroup(current=>current===group?null:group)}>{group}<span>⌄</span></button>
          <div className="horizontal-dropdown">{items.filter(i=>(i.group??"")===group).map(i=><Link key={i.to} to={i.to} onClick={()=>setOpenTopGroup(null)}><NavIcon name={navIconFor(i)}/><span>{i.label}</span></Link>)}</div>
        </div>)}</nav>
        <div className="horizontal-user"><strong>{user?.name}</strong><button onClick={logout}>Sair</button></div>
      </header>}

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
            <button type="button" className="navigation-position-toggle" onClick={()=>void toggleNavigationLayout()} title={navigationLayout==="sidebar"?"Mover navegação para o topo":"Mover navegação para a lateral"} aria-label={navigationLayout==="sidebar"?"Mover navegação para o topo":"Mover navegação para a lateral"}>
              {navigationLayout==="sidebar"?<IconSvg><path d="M4 5h16M4 12h16M4 19h16"/><path d="m16 9 4 3-4 3"/></IconSvg>:<IconSvg><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 3v18M12 8h6m-6 4h6m-6 4h6"/></IconSvg>}
            </button>
            <div ref={notificationsRef} style={{ position: "relative" }}>
              <button type="button" className={`rail-dot notification-bell ${liveAlerts.some(item=>item.severity==="critical")?"has-critical":""}`} title="Central de alertas" aria-label="Central de alertas" aria-expanded={notificationsOpen} onClick={() => { setNotificationsOpen(open => !open); setNotificationToasts([]); }}>
                <span aria-hidden="true">🔔</span>
                {(liveAlerts.length + notifications.filter((n) => !n.read).length) > 0 && <b>{Math.min(liveAlerts.length + notifications.filter((n) => !n.read).length, 99)}</b>}
              </button>
              {notificationsOpen && <div className="alert-center">
                <header><div><span>MONITORAMENTO</span><h3>Central de alertas</h3></div><div className="alert-center-actions">{(!!notifications.length || !!liveAlerts.length) && <button type="button" onClick={() => void clearNotifications()} disabled={clearingNotifications}>{clearingNotifications ? "Limpando…" : "Limpar notificações"}</button>}<b>{liveAlerts.length + notifications.length}</b><button className="alert-center-close" type="button" aria-label="Fechar central de alertas" onClick={() => setNotificationsOpen(false)}>×</button></div></header>
                <div className="alert-center-filters">{(["all","critical","warning","info"] as const).map(level=><button key={level} className={alertFilter===level?"active":""} onClick={()=>setAlertFilter(level)}>{level==="all"?"Todos":level==="critical"?"Críticos":level==="warning"?"Atenção":"Informativos"}</button>)}</div>
                <div className="alert-center-list">{liveAlerts.filter(item=>alertFilter==="all"||item.severity===alertFilter).map(item=><Link className={`alert-center-item ${item.severity}`} to={item.href} key={item.id} onClick={()=>void viewLiveAlert(item)}><i></i><span><small>{item.category}{item.due_date?` · ${new Date(`${item.due_date}T12:00`).toLocaleDateString("pt-BR")}`:""}</small><strong>{item.title}</strong><em>{item.body}</em></span><b>›</b></Link>)}
                  {liveAlerts.filter(item=>alertFilter==="all"||item.severity===alertFilter).length===0&&<div className="alert-center-empty"><span>✓</span><strong>Nenhum alerta nesta categoria</strong><small>Os indicadores estão dentro dos parâmetros atuais.</small></div>}
                  {notifications.map(item=><button className="alert-center-event" key={item.id} onClick={()=>void readNotification(item.id)}><strong>{item.title}</strong><small>{item.body}</small></button>)}
                </div>
                <footer><span>Atualização automática a cada 60 segundos</span><span>Somente alertas operacionais</span></footer>
              </div>}
            </div>
            <ThemeToggle />
            <LanguageSwitcher />
          </header>
        </div>
        <main className="page-main">{children}</main>
      </div>

      <div className="notification-toast-stack" aria-live="polite" aria-atomic="false">
        {notificationToasts.map((notification) => (
          <article className="notification-toast" key={notification.id}>
            <button className="notification-toast-main" type="button" onClick={() => void readNotification(notification.id)}>
              <span className="notification-toast-icon">🔔</span>
              <span className="notification-toast-copy">
                <small>ADIMAX · AGORA</small>
                <strong>{notification.title}</strong>
                {notification.body && <span>{notification.body}</span>}
              </span>
            </button>
            <button className="notification-toast-close" type="button" aria-label="Fechar e marcar notificação como lida" onClick={() => void readNotification(notification.id)}>×</button>
            <i className="notification-toast-progress" />
          </article>
        ))}
      </div>

    </div>
  );
}

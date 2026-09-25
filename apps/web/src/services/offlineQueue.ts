import type { AxiosRequestConfig, AxiosResponse } from "axios";

export interface OfflineQueueState {
  online: boolean;
  pending: number;
  syncing: boolean;
  failed: number;
}

interface StoredFormEntry { key: string; value: string | Blob; filename?: string }
interface OfflineAction {
  id: string;
  createdAt: number;
  method: string;
  url: string;
  params?: unknown;
  bodyKind: "empty" | "json" | "form" | "raw";
  body?: unknown;
  headers?: Record<string, string>;
  attempts: number;
  error?: string;
}

type Sender = (config: AxiosRequestConfig & { _offlineReplay?: boolean }) => Promise<AxiosResponse>;

const DB_NAME = "adimax-driver-offline";
const STORE = "actions";
const ELIGIBLE = [
  /^\/routes\/\d+\/(arrive-cd|enter-dock|loading-start|loading-finish|release|depart|close|empty-truck-photo|loaded-return-photo)$/,
  /^\/routes\/\d+\/stops\/\d+\/(checkin|deliver|deliver-with-proof|replacement-proof|warehouse-return-proof)$/,
  /^\/tracking\/positions$/,
];

let sender: Sender | null = null;
let syncing = false;
export function isNetworkAvailable(): boolean { return (window as any).__adimaxNativeOnline ?? navigator.onLine; }
let state: OfflineQueueState = { online: isNetworkAvailable(), pending: 0, syncing: false, failed: 0 };
const listeners = new Set<(next: OfflineQueueState) => void>();

function openDb(): Promise<IDBDatabase> {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function allActions(): Promise<OfflineAction[]> {
  const db = await openDb();
  return new Promise<OfflineAction[]>((resolve, reject) => {
    const request = db.transaction(STORE, "readonly").objectStore(STORE).getAll();
    request.onsuccess = () => resolve((request.result as OfflineAction[]).sort((a, b) => a.createdAt - b.createdAt));
    request.onerror = () => reject(request.error);
  }).finally(() => db.close());
}

async function putAction(action: OfflineAction): Promise<void> {
  const db = await openDb();
  return new Promise<void>((resolve, reject) => {
    const request = db.transaction(STORE, "readwrite").objectStore(STORE).put(action);
    request.onsuccess = () => resolve(); request.onerror = () => reject(request.error);
  }).finally(() => db.close());
}

async function deleteAction(id: string): Promise<void> {
  const db = await openDb();
  return new Promise<void>((resolve, reject) => {
    const request = db.transaction(STORE, "readwrite").objectStore(STORE).delete(id);
    request.onsuccess = () => resolve(); request.onerror = () => reject(request.error);
  }).finally(() => db.close());
}

function publish(actions?: OfflineAction[]) {
  const apply = (items: OfflineAction[]) => {
    state = { online: isNetworkAvailable(), pending: items.length, syncing, failed: items.filter(item => item.error).length };
    listeners.forEach(listener => listener(state));
  };
  if (actions) apply(actions); else void allActions().then(apply).catch(() => {});
}

function cleanHeaders(headers: unknown): Record<string, string> {
  const source = (headers && typeof headers === "object" ? headers : {}) as Record<string, unknown>;
  return Object.fromEntries(Object.entries(source)
    .filter(([key, value]) => value != null && !["authorization", "content-length", "content-type"].includes(key.toLowerCase()))
    .map(([key, value]) => [key, String(value)]));
}

async function serialize(config: AxiosRequestConfig): Promise<OfflineAction> {
  let bodyKind: OfflineAction["bodyKind"] = "empty", body: unknown;
  if (config.data instanceof FormData) {
    bodyKind = "form";
    const entries: StoredFormEntry[] = [];
    config.data.forEach((value, key) => entries.push({ key, value, filename: value instanceof File ? value.name : undefined }));
    body = entries;
  } else if (config.data != null) {
    bodyKind = typeof config.data === "string" ? "raw" : "json";
    body = config.data;
  }
  return {
    id: crypto.randomUUID(), createdAt: Date.now(), method: String(config.method || "post").toLowerCase(),
    url: String(config.url), params: config.params, bodyKind, body, headers: cleanHeaders(config.headers), attempts: 0,
  };
}

function restoreBody(action: OfflineAction): unknown {
  if (action.bodyKind !== "form") return action.body;
  const form = new FormData();
  for (const entry of action.body as StoredFormEntry[]) {
    if (entry.value instanceof Blob) form.append(entry.key, entry.value, entry.filename); else form.append(entry.key, entry.value);
  }
  return form;
}

export function isOfflineEligible(config?: AxiosRequestConfig): boolean {
  if (!config?.url || config._offlineReplay) return false;
  const method = String(config.method || "get").toLowerCase();
  return ["post", "put", "patch"].includes(method) && ELIGIBLE.some(pattern => pattern.test(String(config.url)));
}

export async function queueOfflineRequest(config: AxiosRequestConfig): Promise<AxiosResponse> {
  const action = await serialize(config);
  const existing = action.url === "/tracking/positions" ? undefined : (await allActions()).find(
    item => item.method === action.method && item.url === action.url,
  );
  if (existing) {
    return {
      data: { offline_queued: true, client_action_id: existing.id, duplicate_ignored: true },
      status: 202, statusText: "Already saved offline", headers: {}, config: config as never,
    };
  }
  await putAction(action);
  publish();
  return {
    data: { offline_queued: true, client_action_id: action.id }, status: 202, statusText: "Saved offline",
    headers: {}, config: config as never,
  };
}

export async function syncOfflineQueue(): Promise<void> {
  if (syncing || !isNetworkAvailable() || !sender) return;
  syncing = true; publish();
  try {
    const actions = await allActions();
    for (const action of actions) {
      try {
        await sender({
          method: action.method, url: action.url, params: action.params, data: restoreBody(action),
          headers: { ...action.headers, "X-Client-Action-ID": action.id }, _offlineReplay: true,
        });
        await deleteAction(action.id);
      } catch (error: any) {
        action.attempts += 1;
        action.error = error?.response
          ? `HTTP ${error.response.status}: ${JSON.stringify(error.response.data?.detail ?? error.response.data).slice(0, 180)}`
          : "Sem conexão";
        await putAction(action);
        // Preserva a ordem operacional. Uma entrega não pode ultrapassar seu check-in.
        break;
      }
    }
  } finally {
    syncing = false;
    const remaining = await allActions();
    publish(remaining);
    if (remaining.length === 0) window.dispatchEvent(new CustomEvent("adimax-offline-synced"));
  }
}

export function configureOfflineQueue(nextSender: Sender) {
  sender = nextSender;
  window.addEventListener("online", () => { publish(); void syncOfflineQueue(); });
  window.addEventListener("offline", () => publish());
  publish();
  if (isNetworkAvailable()) void syncOfflineQueue();
}

export function subscribeOfflineQueue(listener: (next: OfflineQueueState) => void) {
  listeners.add(listener); listener(state);
  return () => { listeners.delete(listener); };
}

declare module "axios" {
  export interface AxiosRequestConfig { _offlineReplay?: boolean }
}

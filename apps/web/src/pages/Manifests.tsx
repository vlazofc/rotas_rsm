import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import api from "../services/api";

interface ManifestItem {
  id: number;
  branch_id: number;
  route_id: number | null;
  original_filename: string;
  status: string;
  ocr_confidence: number | null;
  error_message: string | null;
}

interface ManifestDetail {
  manifest: ManifestItem;
  file_url: string;
  ocr: null | {
    engine: string | null;
    confidence: number | null;
    needs_review: boolean | null;
    extracted: Record<string, unknown> | null;
  };
}

const emptyJson = {
  codigo_ut: "",
  data_carga: "",
  hora_carga: "",
  origem: "",
  destinos: [],
  portagem_ida: null,
  portagem_volta: null,
  km_total: null,
};

export default function ManifestsPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState<ManifestItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ManifestDetail | null>(null);
  const [jsonText, setJsonText] = useState(JSON.stringify(emptyJson, null, 2));
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(
    () => items.find((i) => i.id === selectedId) ?? null,
    [items, selectedId],
  );

  async function loadList(selectFirst = false) {
    const { data } = await api.get<ManifestItem[]>("/manifests");
    const manifestId = Number(searchParams.get("manifest_id"));
    setItems(data);
    if (manifestId && data.some((item) => item.id === manifestId)) {
      setSelectedId(manifestId);
      return;
    }
    if (selectFirst && data.length > 0) setSelectedId(data[0].id);
  }

  async function loadDetail(id: number) {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get<ManifestDetail>(`/manifests/${id}`);
      setDetail(data);
      setJsonText(JSON.stringify(data.ocr?.extracted ?? emptyJson, null, 2));
    } catch {
      setError(t("manifest.load_error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadList(true).catch(() => setError(t("manifest.load_error")));
  }, []);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
  }, [selectedId]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post<ManifestItem>("/manifests/upload", form);
      setFile(null);
      setMessage(t("manifest.uploaded"));
      await loadList();
      setSelectedId(data.id);
    } catch {
      setError(t("manifest.upload_error"));
    } finally {
      setLoading(false);
    }
  }

  async function confirm() {
    if (!selectedId) return;
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const extracted_json = JSON.parse(jsonText);
      await api.post(`/manifests/${selectedId}/confirm`, { extracted_json });
      setMessage(t("manifest.confirmed"));
      await loadList();
      await loadDetail(selectedId);
    } catch (err) {
      setError(apiError(err, t("manifest.invalid_json")));
    } finally {
      setLoading(false);
    }
  }

  async function generateRoute() {
    if (!selectedId) return;
    const validation = validateRouteJson(jsonText, t);
    if (validation) {
      setError(validation);
      return;
    }
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const { data } = await api.post(`/manifests/${selectedId}/generate-route`);
      setMessage(t("manifest.route_generated", { id: data.route_id, stops: data.stops }));
      await loadList();
      await loadDetail(selectedId);
    } catch (err) {
      setError(apiError(err, t("manifest.generate_error")));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2>{t("manifest.title")}</h2>

      <form onSubmit={upload} style={panel}>
        <label style={label}>{t("manifest.file")}</label>
        <input
          type="file"
          accept="application/pdf,image/png,image/jpeg,image/tiff"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button type="submit" disabled={loading || !file} className="btn-primary">
          {t("manifest.upload")}
        </button>
      </form>

      {message && <p style={{ color: "#166534" }}>{message}</p>}
      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <div className="manifest-layout">
        <aside className="manifest-history-panel" style={panel}>
          <h3 style={{ marginTop: 0 }}>{t("manifest.history")}</h3>
          {items.length === 0 ? (
            <p>{t("manifest.empty")}</p>
          ) : (
            <div className="manifest-history-list">
              {items.map((m) => (
                <button
                  key={m.id}
                  className="manifest-history-item"
                  onClick={() => setSelectedId(m.id)}
                  style={{
                    ...listBtn,
                    borderColor: selectedId === m.id ? "#bfdbfe" : "#cbd5e1",
                    background: selectedId === m.id ? "#eff6ff" : "#fff",
                    boxShadow: selectedId === m.id ? "inset 3px 0 0 #0a58ca" : "none",
                  }}
                >
                  <strong>#{m.id}</strong>
                  <span title={m.original_filename}>{m.original_filename}</span>
                  <span style={{ color: "#64748b" }}>{t(`manifest_status.${m.status}`, { defaultValue: m.status })}</span>
                </button>
              ))}
            </div>
          )}
        </aside>

        <section className="manifest-main-panel">
          {!selected ? (
            <div style={panel}>{t("manifest.select")}</div>
          ) : (
            <>
              <div style={panel}>
                <h3 style={{ marginTop: 0 }}>{selected.original_filename}</h3>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 12, color: "#475569" }}>
                  <span>{t("manifest.status")}: <strong>{t(`manifest_status.${detail?.manifest.status ?? selected.status}`, { defaultValue: detail?.manifest.status ?? selected.status })}</strong></span>
                  <span>{t("manifest.confidence")}: <strong>{formatConfidence(detail?.ocr?.confidence ?? selected.ocr_confidence)}</strong></span>
                  <span>{t("manifest.engine")}: <strong>{detail?.ocr?.engine ?? "-"}</strong></span>
                  {detail?.manifest.route_id && <span>{t("manifest.route")}: <strong>#{detail.manifest.route_id}</strong></span>}
                </div>
                {detail?.manifest.status === "ERRO_OCR" && detail.manifest.error_message && (
                  <p style={{ color: "#b91c1c" }}>{detail.manifest.error_message}</p>
                )}
              </div>

              <div className="manifest-detail-grid">
                <div style={panel}>
                  <h3 style={{ marginTop: 0 }}>{t("manifest.original")}</h3>
                  {detail?.file_url ? (
                    <iframe title="manifest-file" src={detail.file_url} className="manifest-file-frame" />
                  ) : (
                    <p>{loading ? t("common.loading") : t("manifest.no_file")}</p>
                  )}
                </div>

                <div style={panel}>
                  <h3 style={{ marginTop: 0 }}>{t("manifest.extracted")}</h3>
                  <textarea
                    value={jsonText}
                    onChange={(e) => setJsonText(e.target.value)}
                    spellCheck={false}
                    style={textarea}
                  />
                  <div className="manifest-actions">
                    <button onClick={confirm} disabled={loading} className="btn-primary">{t("manifest.confirm")}</button>
                    <button onClick={generateRoute} disabled={loading || detail?.manifest.status !== "CONFERIDO" || Boolean(validateRouteJson(jsonText, t))} className="btn-ghost">
                      {t("manifest.generate")}
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function formatConfidence(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(value * 100)}%`;
}

function apiError(err: unknown, fallback: string) {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

function validateRouteJson(text: string, t: (key: string) => string) {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(text);
  } catch {
    return t("manifest.validation.invalid_json");
  }
  if (!String(payload.codigo_ut ?? "").trim()) return t("manifest.validation.code_required");
  if (!String(payload.data_carga ?? "").trim()) return t("manifest.validation.date_required");
  if (!Array.isArray(payload.destinos)) return t("manifest.validation.destinations_list");
  return "";
}

const panel: React.CSSProperties = {
  background: "#fff",
  borderRadius: 8,
  padding: 16,
  boxShadow: "0 2px 10px rgba(0,0,0,.05)",
  marginBottom: 16,
};
const label: React.CSSProperties = { fontSize: 13, color: "#475569", marginRight: 6 };
const listBtn: React.CSSProperties = {
  display: "grid",
  gap: 4,
  textAlign: "left",
  border: "1px solid #cbd5e1",
  borderRadius: 8,
  padding: 10,
  cursor: "pointer",
};
const textarea: React.CSSProperties = {
  width: "100%",
  minHeight: 620,
  boxSizing: "border-box",
  border: "1px solid #cbd5e1",
  borderRadius: 8,
  padding: 12,
  fontFamily: "Consolas, Monaco, monospace",
  fontSize: 13,
};

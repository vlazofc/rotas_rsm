import { useEffect } from "react";
import { startPreviewSession } from "../services/api";

/** Recebe os tokens de simulação pela URL (hash, não fica no histórico/servidor)
 * e inicia a sessão de preview isolada nesta aba. Aberta pelo botão
 * "Simular ambiente" do painel Clientes. */
export default function PreviewSession() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");
    if (accessToken && refreshToken) {
      startPreviewSession(accessToken, refreshToken);
    }
    window.location.replace("/");
  }, []);

  return <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>…</div>;
}

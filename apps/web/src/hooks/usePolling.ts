import { useEffect, useRef } from "react";

/**
 * Executa `callback` periodicamente (a cada `intervalMs`) enquanto a aba
 * estiver visível, para manter os dados atualizados sem exigir F5.
 * Pausa automaticamente quando a aba fica em background e re-executa
 * imediatamente ao voltar o foco.
 */
export function usePolling(callback: () => void | Promise<void>, intervalMs: number) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;
    let running = false;
    const schedule = () => {
      if (disposed) return;
      if (timer) window.clearTimeout(timer);
      const jitter = intervalMs * (0.85 + Math.random() * 0.3);
      timer = window.setTimeout(tick, jitter);
    };
    const tick = async () => {
      if (disposed || running) return;
      if (timer) window.clearTimeout(timer);
      if (!running && document.visibilityState === "visible") {
        running = true;
        try { await callbackRef.current(); } catch { /* A próxima consulta tenta novamente após falhas transitórias. */ } finally { running = false; schedule(); }
        return;
      }
      schedule();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible" && !running) void tick();
    };
    schedule();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [intervalMs]);
}

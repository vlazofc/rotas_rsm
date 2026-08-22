import { useEffect, useRef } from "react";

/**
 * Executa `callback` periodicamente (a cada `intervalMs`) enquanto a aba
 * estiver visível, para manter os dados atualizados sem exigir F5.
 * Pausa automaticamente quando a aba fica em background e re-executa
 * imediatamente ao voltar o foco.
 */
export function usePolling(callback: () => void, intervalMs: number) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") callbackRef.current();
    };
    const id = setInterval(tick, intervalMs);
    const onVisible = () => { if (document.visibilityState === "visible") callbackRef.current(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [intervalMs]);
}

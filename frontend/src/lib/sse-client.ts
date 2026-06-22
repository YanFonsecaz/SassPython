import { getAccessToken } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

type SSECallback = (data: Record<string, unknown>) => void;

interface SSEOptions {
  onError?: (error: Event) => void;
  onComplete?: () => void;
}

const EVENTOS_TERMINAIS = ["concluida", "falhou", "cancelada"];

/**
 * Conexão SSE resiliente.
 *
 * O stream pode encerrar sem um evento terminal — por idle/timeout de proxy
 * (ex.: Render), queda de rede, ou o teto de duração do backend. Quando isso
 * acontece e a execução ainda não terminou, RECONECTAMOS automaticamente (com
 * backoff), em vez de congelar a UI no último estado recebido. Receber dados
 * zera o contador de falhas; só desistimos (onError) após várias falhas
 * seguidas SEM dados (ex.: token inválido / backend fora).
 */
export function createSSEConnection(
  path: string,
  onMessage: SSECallback,
  options: SSEOptions = {}
): { close: () => void } {
  const controller = new AbortController();
  let finalizado = false;
  let falhasSeguidas = 0;
  const maxFalhas = 5;

  function agendarReconexao() {
    if (controller.signal.aborted || finalizado) return;
    falhasSeguidas++;
    if (falhasSeguidas > maxFalhas) {
      options.onError?.(new Event("error"));
      return;
    }
    const delay = Math.min(1000 * falhasSeguidas, 5000);
    setTimeout(() => {
      if (!controller.signal.aborted && !finalizado) connect();
    }, delay);
  }

  async function connect() {
    if (controller.signal.aborted || finalizado) return;

    const token = getAccessToken();
    if (!token) {
      // token ainda não disponível (ou expirou) — tenta de novo com backoff
      agendarReconexao();
      return;
    }

    const url = new URL(`${API_BASE}${path}`, window.location.origin);

    try {
      const response = await fetch(url.toString(), {
        headers: {
          Accept: "text/event-stream",
          Authorization: `Bearer ${token}`,
        },
        credentials: "include",
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        agendarReconexao();
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        falhasSeguidas = 0; // conexão saudável recebendo dados

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6);
          if (!jsonStr.trim()) continue;
          try {
            const data = JSON.parse(jsonStr) as Record<string, unknown>;
            onMessage(data);
            if (EVENTOS_TERMINAIS.includes(data.type as string)) {
              finalizado = true;
              options.onComplete?.();
              return;
            }
          } catch {
            // ignore parse errors
          }
        }
      }

      // Stream encerrou sem evento terminal (idle/timeout de proxy) → reconecta.
      agendarReconexao();
    } catch {
      if (!controller.signal.aborted) {
        agendarReconexao();
      }
    }
  }

  connect();

  return {
    close: () => controller.abort(),
  };
}

import { getAccessToken } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

type SSECallback = (data: Record<string, unknown>) => void;

interface SSEOptions {
  onError?: (error: Event) => void;
  onComplete?: () => void;
}

export function createSSEConnection(
  path: string,
  onMessage: SSECallback,
  options: SSEOptions = {}
): { close: () => void } {
  const controller = new AbortController();
  let retries = 0;
  const maxRetries = 3;

  async function connect() {
    const token = getAccessToken();
    if (!token && retries < maxRetries) {
      retries++;
      await new Promise((r) => setTimeout(r, 1000 * retries));
      if (!controller.signal.aborted) connect();
      return;
    }

    const url = new URL(`${API_BASE}${path}`, window.location.origin);

    try {
      const response = await fetch(url.toString(), {
        headers: {
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: "include",
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        options.onError?.(new Event("error"));
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6);
            if (jsonStr.trim()) {
              try {
                const data = JSON.parse(jsonStr) as Record<string, unknown>;
                onMessage(data);

                const type = data.type as string;
                if (["concluida", "falhou", "cancelada"].includes(type)) {
                  options.onComplete?.();
                  return;
                }
              } catch {
                // ignore parse errors
              }
            }
          }
        }
      }

      options.onComplete?.();
    } catch {
      if (!controller.signal.aborted) {
        options.onError?.(new Event("error"));
      }
    }
  }

  connect();

  return {
    close: () => controller.abort(),
  };
}

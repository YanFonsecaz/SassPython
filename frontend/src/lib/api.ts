import type { ApiError } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

let accessToken: string | null = null;
let refreshToken: string | null = null;
let csrfToken: string | null = null;

function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function readRefreshCookie(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)refresh_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (!token) { csrfToken = null; refreshToken = null; }
}

export function setRefreshToken(token: string | null) {
  refreshToken = token;
}

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

type RefreshCallback = () => Promise<void>;
let onAuthExpired: RefreshCallback | null = null;

export function setOnAuthExpired(cb: RefreshCallback) {
  onAuthExpired = cb;
}

let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  try {
    const rt = refreshToken || readRefreshCookie();
    const body = rt ? JSON.stringify({ refresh_token: rt }) : undefined;
    const csrf = csrfToken || readCsrfCookie();
    const headers: Record<string, string> = {};
    if (body) headers["Content-Type"] = "application/json";
    if (csrf) headers["X-CSRF-Token"] = csrf;
    const resposta = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers,
      body,
    });
    if (!resposta.ok) return null;
    const dados = await resposta.json();
    const novoToken = dados.access_token as string;
    accessToken = novoToken;
    if (dados.refresh_token) refreshToken = dados.refresh_token as string;
    if (dados.csrf_token) csrfToken = dados.csrf_token as string;
    return novoToken;
  } catch {
    return null;
  }
}

async function getValidToken(): Promise<string | null> {
  if (accessToken) return accessToken;
  if (isRefreshing) return refreshPromise;
  isRefreshing = true;
  refreshPromise = refreshAccessToken().finally(() => {
    isRefreshing = false;
    refreshPromise = null;
  });
  return refreshPromise;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  noAuth?: boolean;
  noRefresh?: boolean;
}

async function request<T>(
  caminho: string,
  opcoes: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {}, noAuth = false, noRefresh = false } = opcoes;

  let token: string | null = null;
  if (!noAuth) {
    token = noRefresh ? accessToken : await getValidToken();
  }

  const reqHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...headers,
  };

  if (token) {
    reqHeaders["Authorization"] = `Bearer ${token}`;
  }

  const csrf = csrfToken || readCsrfCookie();
  if (csrf && method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    reqHeaders["X-CSRF-Token"] = csrf;
  }

  const resposta = await fetch(`${API_BASE}${caminho}`, {
    method,
    headers: reqHeaders,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });

  if (resposta.status === 401 && !noRefresh && !noAuth) {
    if (!isRefreshing) {
      isRefreshing = true;
      refreshPromise = refreshAccessToken().finally(() => {
        isRefreshing = false;
        refreshPromise = null;
      });
    }
    const novoToken = await refreshPromise;
    if (novoToken) {
      reqHeaders["Authorization"] = `Bearer ${novoToken}`;
      const retry = await fetch(`${API_BASE}${caminho}`, {
        method,
        headers: reqHeaders,
        body: body ? JSON.stringify(body) : undefined,
        credentials: "include",
      });
      if (!retry.ok) {
        const err = await parseError(retry);
        throw err;
      }
      return retry.json() as Promise<T>;
    }
    accessToken = null;
    if (onAuthExpired) onAuthExpired();
    throw { detalhe: "Sessao expirada" } as ApiError;
  }

  if (!resposta.ok) {
    const err = await parseError(resposta);
    throw err;
  }

  if (resposta.status === 204) return undefined as T;
  return resposta.json() as Promise<T>;
}

async function parseError(resposta: Response): Promise<ApiError> {
  let data: Record<string, unknown> = {};
  try {
    data = await resposta.json();
    if (data.detail && !data.detalhe) data.detalhe = data.detail;
    // FastAPI/Pydantic devolve { detail: [{ loc, msg, type }] } em 422.
    // Normaliza pra um campo unico esperado por mensagemErroAmigavel.
    if (Array.isArray(data.detail)) {
      data.errors = data.detail as ApiError["errors"];
      data.detail = undefined;
      delete data.detail;
    }
  } catch {
    data = { detalhe: `Erro ${resposta.status}` };
  }
  return { ...(data as ApiError), status: resposta.status };
}

// Baixa binarios (ex.: .docx) reaproveitando a mesma logica de auth de
// request(): renova o token via getValidToken() e, em 401, refaz o refresh e
// repete a requisicao. Retorna Blob em vez de JSON.
async function requestBlob(
  caminho: string,
  opcoes: RequestOptions = {}
): Promise<Blob> {
  const { method = "GET", body, headers = {}, noAuth = false, noRefresh = false } = opcoes;

  let token: string | null = null;
  if (!noAuth) {
    token = noRefresh ? accessToken : await getValidToken();
  }

  const reqHeaders: Record<string, string> = { ...headers };
  if (body !== undefined) reqHeaders["Content-Type"] = "application/json";
  if (token) reqHeaders["Authorization"] = `Bearer ${token}`;

  const csrf = csrfToken || readCsrfCookie();
  if (csrf && method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    reqHeaders["X-CSRF-Token"] = csrf;
  }

  const enviar = (headersReq: Record<string, string>) =>
    fetch(`${API_BASE}${caminho}`, {
      method,
      headers: headersReq,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "include",
    });

  const resposta = await enviar(reqHeaders);

  if (resposta.status === 401 && !noRefresh && !noAuth) {
    if (!isRefreshing) {
      isRefreshing = true;
      refreshPromise = refreshAccessToken().finally(() => {
        isRefreshing = false;
        refreshPromise = null;
      });
    }
    const novoToken = await refreshPromise;
    if (novoToken) {
      reqHeaders["Authorization"] = `Bearer ${novoToken}`;
      const retry = await enviar(reqHeaders);
      if (!retry.ok) {
        const err = await parseError(retry);
        throw err;
      }
      return retry.blob();
    }
    accessToken = null;
    if (onAuthExpired) onAuthExpired();
    throw { detalhe: "Sessao expirada", status: 401 } as ApiError;
  }

  if (!resposta.ok) {
    const err = await parseError(resposta);
    throw err;
  }

  return resposta.blob();
}

export const api = {
  get: <T>(caminho: string, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "GET" }),

  blob: (caminho: string, opcoes?: RequestOptions) =>
    requestBlob(caminho, opcoes),

  post: <T>(caminho: string, body?: unknown, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "POST", body }),

  put: <T>(caminho: string, body?: unknown, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "PUT", body }),

  patch: <T>(caminho: string, body?: unknown, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "PATCH", body }),

  delete: <T>(caminho: string, body?: unknown, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "DELETE", body }),
};

export function mensagemErroAmigavel(err: unknown): string {
  if (!err || typeof err !== "object") return "Algo deu errado. Tente novamente.";
  const e = err as {
    status?: number;
    detalhe?: string;
    detail?: string;
    errors?: Array<{ loc?: string[]; msg?: string; message?: string }>;
    errors_map?: Record<string, string>;
  };

  const MAPA_STATUS: Record<number, string> = {
    400: "Requisição inválida. Verifique os dados e tente novamente.",
    401: "Sessão expirada. Faça login novamente.",
    402: "Saldo insuficiente de créditos.",
    403: "Você não tem permissão para isso.",
    404: "Recurso não encontrado.",
    409: "Conflito: o recurso já existe.",
    422: "Dados inválidos. Verifique os campos destacados.",
    429: "Muitas requisições. Aguarde alguns minutos e tente novamente.",
    500: "Erro interno do servidor. Tente novamente mais tarde.",
    502: "Servidor indisponível. Tente novamente em instantes.",
    503: "Serviço temporariamente indisponível. Tente novamente.",
  };

  // Prioridade 1: detalhe explicito do backend (HTTPException.detail)
  const detalhe = e.detalhe || e.detail;
  if (detalhe && /^[A-ZÀ-ÿ]/.test(detalhe) && detalhe.length < 200) return detalhe;

  // Prioridade 2: erros de validacao do Pydantic (422) ou erros estruturados
  const erros = e.errors || [];
  if (erros.length > 0) {
    const partes = erros.map((errItem) => {
      const campo = errItem.loc && errItem.loc.length > 0
        ? errItem.loc[errItem.loc.length - 1]
        : null;
      const msg = errItem.msg || errItem.message || "invalido";
      return campo ? `${campo}: ${msg}` : msg;
    });
    // Limita o tamanho pra nao estourar a UI
    const texto = partes.slice(0, 3).join("; ");
    const sufixo = partes.length > 3 ? ` (e mais ${partes.length - 3})` : "";
    return `${texto}${sufixo}`.replace(/^./, (c) => c.toUpperCase());
  }

  if (e.errors_map && Object.keys(e.errors_map).length > 0) {
    return Object.entries(e.errors_map)
      .map(([campo, msg]) => `${campo}: ${msg}`)
      .join("; ")
      .replace(/^./, (c) => c.toUpperCase());
  }

  // Prioridade 3: mapa de status (fallback generico por HTTP code)
  if (e.status && MAPA_STATUS[e.status]) return MAPA_STATUS[e.status];

  return "Algo deu errado. Tente novamente.";
}


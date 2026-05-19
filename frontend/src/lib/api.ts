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
  try {
    return (await resposta.json()) as ApiError;
  } catch {
    return { detalhe: `Erro ${resposta.status}` };
  }
}

export const api = {
  get: <T>(caminho: string, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "GET" }),

  post: <T>(caminho: string, body?: unknown, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "POST", body }),

  put: <T>(caminho: string, body?: unknown, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "PUT", body }),

  delete: <T>(caminho: string, body?: unknown, opcoes?: RequestOptions) =>
    request<T>(caminho, { ...opcoes, method: "DELETE", body }),
};


import { api, getAccessToken, mensagemErroAmigavel } from "@/lib/api";

export interface BlocoEntrada {
  texto: string;
  imagens: string[];
}

export interface GerarParecerReq {
  cliente_id: string;
  titulo_sugerido?: string;
  blocos: BlocoEntrada[];
}

export interface ParecerExecucao {
  id: string;
  status: string;
  etapa_atual?: string | null;
  parecer_id?: string | null;
  erro_msg?: string | null;
}

export interface ParecerResumo {
  id: string;
  titulo: string;
  cliente_nome: string;
  site?: string;
  plataforma?: string;
  n_imagens: number;
  status: string;
  criado_em: string;
}

export interface ParecerDoc {
  id: string;
  titulo: string;
  parecer_html: string;
  estrutura: unknown;
  meta: Record<string, string>;
  cliente_nome: string;
  criado_em: string;
}

export async function custoParecer(b: GerarParecerReq) {
  return api.post<{ custo: number; n_imagens: number }>("/ferramentas/parecer/custo", b);
}

export async function gerarParecer(b: GerarParecerReq) {
  return api.post<{ id: string; status: string }>("/ferramentas/parecer/gerar", b);
}

export async function buscarExecucaoParecer(id: string) {
  return api.get<ParecerExecucao>(`/ferramentas/parecer/execucao/${id}`);
}

export async function listarPareceres(clienteId?: string) {
  const qs = clienteId ? `?cliente_id=${encodeURIComponent(clienteId)}` : "";
  return api.get<{ pareceres: ParecerResumo[] }>(`/ferramentas/parecer/historico${qs}`);
}

export async function buscarParecerDoc(id: string) {
  return api.get<ParecerDoc>(`/ferramentas/parecer/${id}`);
}

function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export async function exportarParecer(id: string, html: string, nome?: string): Promise<Blob> {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";
  const token = getAccessToken();
  const csrf = readCsrfCookie();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const resp = await fetch(`${API_BASE}/ferramentas/parecer/${id}/exportar`, {
    method: "POST",
    headers,
    body: JSON.stringify({ html, nome_arquivo: nome }),
    credentials: "include",
  });

  if (!resp.ok) {
    try {
      const err = await resp.json();
      throw new Error(err.detalhe || `Erro ${resp.status}`);
    } catch {
      if (!resp.headers.get("content-type")?.includes("json")) {
        throw new Error(await resp.text() || `Erro ${resp.status}`);
      }
      throw new Error(`Erro ${resp.status}`);
    }
  }

  return resp.blob();
}

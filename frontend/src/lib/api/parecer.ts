import { api } from "@/lib/api";

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

export async function exportarParecer(id: string, html: string, nome?: string): Promise<Blob> {
  return api.blob(`/ferramentas/parecer/${id}/exportar`, {
    method: "POST",
    body: { html, nome_arquivo: nome },
  });
}

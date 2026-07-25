import { api, getAccessToken } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export type StatusItem = "aprovado" | "atencao" | "reprovado" | "na" | "sem_dados";

export interface AuditoriaResumoSeotec {
  id: string;
  cliente_id: string;
  dominio: string;
  fase: string;
  score_antes: number | null;
  score_depois: number | null;
  criado_em: string;
}

export interface CrawlResumoSeotec {
  id: string;
  fase_destino: string;
  origem: string;
  status: string;
  erro_msg: string | null;
  contadores_json: Record<string, unknown>;
  criado_em: string;
}

export interface ItemRespostaSeotec {
  item_slug: string;
  nome: string;
  categoria: string;
  peso: number;
  prioridade: string;
  fonte: string;
  modo: string;
  status_antes: StatusItem | null;
  status_depois: StatusItem | null;
  diagnostico: string | null;
  recomendacao: string | null;
  evidencias_json: Record<string, unknown>;
  status_cliente: string | null;
  validacao_seo: string | null;
  observacao_cliente: string | null;
  observacao_seo: string | null;
}

export interface AuditoriaDetalheSeotec extends AuditoriaResumoSeotec {
  ultimo_crawl: CrawlResumoSeotec | null;
  itens: ItemRespostaSeotec[];
}

export interface ItemPatchSeotec {
  status_antes?: StatusItem | null;
  status_depois?: StatusItem | null;
  diagnostico?: string | null;
  recomendacao?: string | null;
  status_cliente?: string | null;
  validacao_seo?: string | null;
  observacao_cliente?: string | null;
  observacao_seo?: string | null;
}

export interface UploadResponseSeotec {
  crawl_id: string;
  execucao_id: string;
  custo: number;
  fase_destino: string;
  status: string;
}

export async function criarAuditoriaSeotec(
  clienteId: string,
  dominio: string,
): Promise<AuditoriaResumoSeotec> {
  return api.post<AuditoriaResumoSeotec>(
    "/ferramentas/auditoria-seo-tecnico/auditorias",
    { cliente_id: clienteId, dominio },
  );
}

export async function listarAuditoriasSeotec(
  clienteId?: string,
): Promise<AuditoriaResumoSeotec[]> {
  const qs = clienteId ? `?cliente_id=${clienteId}` : "";
  return api.get<AuditoriaResumoSeotec[]>(
    `/ferramentas/auditoria-seo-tecnico/auditorias${qs}`,
  );
}

export async function buscarAuditoriaSeotec(
  auditoriaId: string,
): Promise<AuditoriaDetalheSeotec> {
  return api.get<AuditoriaDetalheSeotec>(
    `/ferramentas/auditoria-seo-tecnico/auditorias/${auditoriaId}`,
  );
}

export async function editarItemSeotec(
  auditoriaId: string,
  itemSlug: string,
  dados: ItemPatchSeotec,
): Promise<ItemRespostaSeotec> {
  return api.patch<ItemRespostaSeotec>(
    `/ferramentas/auditoria-seo-tecnico/auditorias/${auditoriaId}/itens/${itemSlug}`,
    dados,
  );
}

export async function uploadPacoteSeotec(
  auditoriaId: string,
  arquivo: File,
): Promise<UploadResponseSeotec> {
  const formData = new FormData();
  formData.append("arquivo", arquivo);

  const token = getAccessToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const csrf = typeof document !== "undefined"
    ? (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)?.[1] ?? null)
    : null;
  if (csrf) headers["X-CSRF-Token"] = decodeURIComponent(csrf);

  const resposta = await fetch(
    `${API_BASE}/ferramentas/auditoria-seo-tecnico/auditorias/${auditoriaId}/upload`,
    {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    },
  );

  if (!resposta.ok) {
    let data: Record<string, unknown> = {};
    try { data = await resposta.json(); } catch { /* noop */ }
    const err = { ...(data as Record<string, unknown>), status: resposta.status };
    if (data.detail && !data.detalhe) (err as Record<string, unknown>).detalhe = data.detail;
    throw err;
  }

  return resposta.json() as Promise<UploadResponseSeotec>;
}

export async function atualizarAuditoriaSeotec(
  auditoriaId: string,
  dados: { fase?: string },
): Promise<AuditoriaResumoSeotec> {
  return api.patch<AuditoriaResumoSeotec>(
    `/ferramentas/auditoria-seo-tecnico/auditorias/${auditoriaId}`,
    dados,
  );
}

export async function exportarAuditoriaDocxSeotec(auditoriaId: string): Promise<Blob> {
  return api.blob(`/ferramentas/auditoria-seo-tecnico/auditorias/${auditoriaId}/docx`);
}

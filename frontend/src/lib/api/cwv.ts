import { api } from "@/lib/api";

function fetchBlobAuth(path: string): Promise<Blob> {
  return api.blob(`/ferramentas${path}`);
}

export type CwvEsforco = "baixo" | "medio" | "alto";

export interface CwvProblemaResposta {
  id: string;
  kb_codigo: string | null;
  audit_id: string | null;
  titulo: string;
  severidade: number;
  prioridade_ordem: number;
  metricas_afetadas: string[];
  contexto_especifico: Record<string, unknown>;
  documentacao_md: string;
  pesquisado?: boolean;
  esforco?: CwvEsforco | null;
  threshold?: string | null;
}

export interface CwvAnaliseResposta {
  id: string;
  cliente_id: string;
  url: string;
  url_canonica: string;
  template_tipo: string;
  plataforma_detectada: string;
  estrategia: string;
  score_performance: number | null;
  lcp_ms: number | null;
  cls: number | null;
  inp_ms: number | null;
  fcp_ms: number | null;
  ttfb_ms: number | null;
  tbt_ms: number | null;
  status: string;
  erro_msg: string | null;
  criado_em: string;
  problemas: CwvProblemaResposta[];
  audits_totais: number;
  n_network_requests: number;
  main_document_size_bytes: number;
  llm_usado?: boolean;
  llm_audits_processados?: number;
  llm_audits_descartados?: number;
  // Field data CrUX (SPEC_CWV_Field_Data_Retencao_Payload).
  crux_lcp_p75_ms?: number | null;
  crux_inp_p75_ms?: number | null;
  crux_cls_p75?: number | null;
  crux_lcp_categoria?: string | null;
  crux_inp_categoria?: string | null;
  crux_cls_categoria?: string | null;
  crux_overall_categoria?: string | null;
  crux_origem_fallback?: boolean;
  field_data_disponivel?: boolean;
}

export interface CwvAnaliseResumo {
  id: string;
  url_canonica: string;
  template_tipo: string;
  estrategia: string;
  score_performance: number | null;
  lcp_ms: number | null;
  cls: number | null;
  inp_ms: number | null;
  n_problemas: number;
  n_problemas_alta_severidade: number;
  criado_em: string;
}

export interface CwvHistoricoUrlResposta {
  url_canonica: string;
  template_tipo: string;
  plataforma_detectada: string;
  analises: CwvAnaliseResumo[];
}

export interface CwvCustoResponse {
  custo: number;
  custo_por_url: number;
  n_urls: number;
  n_urls_reais: number;
}

export interface CwvExecucaoCriada {
  id: string;
  ferramenta: string;
  status: string;
  etapa_atual: string | null;
  creditos_cobrados: number;
  criado_em: string;
  n_urls: number;
  custo_estimado: number;
}

export type TemplateTipo = "home" | "categoria" | "produto" | "blog" | "blogpost" | "outros";

export interface CwvAnalisarRequest {
  cliente_id: string;
  urls_por_template: Record<TemplateTipo, string[]>;
}

export async function buscarCustoCwv(nUrls: number): Promise<CwvCustoResponse> {
  return api.get<CwvCustoResponse>(`/ferramentas/core-web-vitals/custo?n_urls=${nUrls}`);
}

export async function analisarCwv(dados: CwvAnalisarRequest): Promise<CwvExecucaoCriada> {
  return api.post<CwvExecucaoCriada>("/ferramentas/core-web-vitals/analisar", dados);
}

export async function buscarExecucaoCwv(execucaoId: string) {
  return api.get<CwvExecucaoCriada & { resultado_json: Record<string, unknown> | null; erro_msg: string | null; concluida_em: string | null }>(
    `/ferramentas/core-web-vitals/execucao/${execucaoId}`
  );
}

export async function buscarAnaliseCwv(analiseId: string): Promise<CwvAnaliseResposta> {
  return api.get<CwvAnaliseResposta>(`/ferramentas/core-web-vitals/analise/${analiseId}`);
}

export async function buscarHistoricoCwv(clienteId: string, template?: string): Promise<{ urls: CwvHistoricoUrlResposta[] }> {
  const qs = new URLSearchParams({ cliente_id: clienteId });
  if (template) qs.set("template", template);
  return api.get(`/ferramentas/core-web-vitals/historico?${qs}`);
}

export async function buscarHistoricoUrlCwv(clienteId: string, urlCanonica: string, estrategia?: string): Promise<CwvHistoricoUrlResposta> {
  const qs = new URLSearchParams({ cliente_id: clienteId, url: urlCanonica });
  if (estrategia) qs.set("estrategia", estrategia);
  return api.get(`/ferramentas/core-web-vitals/historico-url?${qs}`);
}

export async function reanalisarCwv(analiseId: string): Promise<CwvExecucaoCriada> {
  return api.post<CwvExecucaoCriada>(`/ferramentas/core-web-vitals/reanalisar/${analiseId}`);
}

export async function overridePlataformaCwv(
  analiseId: string,
  plataforma: string,
): Promise<{ plataforma: string; n_problemas_atualizados: number }> {
  return api.patch<{ plataforma: string; n_problemas_atualizados: number }>(
    `/ferramentas/core-web-vitals/analise/${analiseId}/plataforma`,
    { plataforma },
  );
}

// Types for comparison
export interface MetricaComparada {
  antes: number;
  depois: number;
  delta: number;
  melhorou: boolean | null;
}

export interface ProblemaComparado {
  kb_codigo: string | null;
  titulo: string;
}

export interface ComparacaoResposta {
  analise_atual_id: string;
  analise_anterior_id: string | null;
  dias_decorridos: number | null;
  metricas: Record<string, MetricaComparada>;
  problemas_resolvidos: ProblemaComparado[];
  problemas_novos: ProblemaComparado[];
  problemas_persistentes: ProblemaComparado[];
}

export async function buscarComparacao(analiseId: string): Promise<ComparacaoResposta> {
  return api.get<ComparacaoResposta>(`/ferramentas/core-web-vitals/comparacao/${analiseId}`);
}

export interface IrmaResponse {
  existe: boolean;
  analise: CwvAnaliseResposta | null;
}

export async function buscarIrmaCwv(analiseId: string): Promise<IrmaResponse> {
  return api.get<IrmaResponse>(`/ferramentas/core-web-vitals/analise/${analiseId}/irma`);
}

export async function exportarProblemaCwvDocx(problemaId: string): Promise<Blob> {
  return fetchBlobAuth(`/core-web-vitals/problema/${problemaId}/docx`);
}

export async function exportarRelatorioCwvDocx(analiseId: string): Promise<Blob> {
  return fetchBlobAuth(`/core-web-vitals/analise/${analiseId}/docx`);
}

export async function exportarExecucaoCwvDocx(execucaoId: string): Promise<Blob> {
  return fetchBlobAuth(`/core-web-vitals/execucao/${execucaoId}/docx`);
}

export interface HealthScorePorEstrategia {
  mobile: number | null;
  desktop: number | null;
}

export interface HealthScoreResposta {
  health_score: number | null;
  n_pass: number;
  n_total: number;
  por_estrategia: HealthScorePorEstrategia;
}

export async function buscarHealthScoreCwv(execucaoId: string): Promise<HealthScoreResposta> {
  return api.get<HealthScoreResposta>(`/ferramentas/core-web-vitals/execucao/${execucaoId}/health-score`);
}

export type VereditoPageExperience = "pass" | "fail" | "erro" | "na";

export interface PageExperienceResposta {
  origem: string;
  https: VereditoPageExperience;
  ssl: VereditoPageExperience;
  redirect_301: VereditoPageExperience;
  security_headers: VereditoPageExperience;
  safe_browsing: VereditoPageExperience;
  mixed_content: VereditoPageExperience;
  mobile_friendly: VereditoPageExperience;
  detalhes_json: Record<string, unknown>;
}

export interface PageExperienceListResponse {
  origens: PageExperienceResposta[];
}

export async function buscarPageExperienceCwv(execucaoId: string): Promise<PageExperienceListResponse> {
  return api.get<PageExperienceListResponse>(`/ferramentas/core-web-vitals/execucao/${execucaoId}/page-experience`);
}

// --- SPEC_CWV_Auditoria_Ciclo_De_Vida ---------------------------------------

export type FaseAuditoria = "before" | "aguardando_implementacao" | "after" | "concluida";
export type OrigemItem = "psi_audit" | "page_experience" | "field_data";
export type StatusCheck = "pass" | "fail" | "na";
export type StatusImplementacao = "nao_executado" | "em_andamento" | "implementado";

export interface ChecklistItemResposta {
  id: string;
  origem: OrigemItem;
  item_codigo: string;
  titulo: string;
  status_before: StatusCheck;
  status_after: StatusCheck | null;
  status_implementacao: StatusImplementacao;
  nota_cliente: string | null;
  nota_seo: string | null;
  prioridade: number;
  esforco: string | null;
  escopo_json: Record<string, unknown>;
}

export interface AuditoriaResposta {
  id: string;
  cliente_id: string;
  titulo: string;
  fase: FaseAuditoria;
  execucao_before_id: string | null;
  execucao_after_id: string | null;
  health_score_before: number | null;
  health_score_after: number | null;
  consolidacao_status: string;
  relatorio_json: Record<string, unknown> | null;
  checklist: ChecklistItemResposta[];
  n_pass_before: number;
  n_fail_before: number;
  n_implementados: number;
  criado_em: string;
  atualizado_em: string;
}

export interface AuditoriaResumo {
  id: string;
  titulo: string;
  fase: FaseAuditoria;
  health_score_before: number | null;
  health_score_after: number | null;
  n_itens: number;
  criado_em: string;
}

export async function criarAuditoriaCwv(clienteId: string, execucaoId: string, titulo?: string): Promise<AuditoriaResposta> {
  return api.post<AuditoriaResposta>("/ferramentas/core-web-vitals/auditorias", {
    cliente_id: clienteId,
    execucao_id: execucaoId,
    titulo,
  });
}

export async function listarAuditoriasCwv(clienteId: string): Promise<{ auditorias: AuditoriaResumo[] }> {
  return api.get(`/ferramentas/core-web-vitals/auditorias?cliente_id=${clienteId}`);
}

export async function buscarAuditoriaCwv(auditoriaId: string): Promise<AuditoriaResposta> {
  return api.get<AuditoriaResposta>(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}`);
}

export async function atualizarAuditoriaCwv(auditoriaId: string, dados: { fase?: FaseAuditoria; titulo?: string }): Promise<AuditoriaResposta> {
  return api.patch<AuditoriaResposta>(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}`, dados);
}

export async function atualizarItemChecklistCwv(
  auditoriaId: string,
  itemId: string,
  dados: { status_implementacao?: StatusImplementacao; nota_cliente?: string; nota_seo?: string },
): Promise<ChecklistItemResposta> {
  return api.patch<ChecklistItemResposta>(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}/itens/${itemId}`, dados);
}

export async function reauditarCwv(auditoriaId: string): Promise<{ id: string; status: string; custo_estimado: number; auditoria_id: string }> {
  return api.post(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}/reauditar`);
}

export interface ProblemaConsolidadoResposta {
  id: string;
  titulo: string;
  causa_raiz: string;
  kb_codigo: string | null;
  severidade: number;
  prioridade_ordem: number;
  esforco: string | null;
  metricas_afetadas: string[];
  escopo_json: { urls?: string[]; estrategias?: string[]; descricao?: string };
  evidencias_json: Record<string, unknown>;
  recomendacao_md: string;
  problemas_origem_ids: string[];
}

export async function consolidarAuditoriaCwv(auditoriaId: string): Promise<{ status: string; auditoria_id: string }> {
  return api.post(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}/consolidar`);
}

export async function buscarConsolidadosCwv(auditoriaId: string): Promise<{ consolidados: ProblemaConsolidadoResposta[]; status: string }> {
  return api.get(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}/consolidados`);
}

export async function gerarRelatorioCwv(auditoriaId: string): Promise<{ status: string; auditoria_id: string }> {
  return api.post(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}/relatorio`);
}

export async function exportarAuditoriaDocxCwv(auditoriaId: string): Promise<Blob> {
  return fetchBlobAuth(`/core-web-vitals/auditorias/${auditoriaId}/docx`);
}

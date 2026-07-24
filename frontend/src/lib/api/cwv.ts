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

// SPEC_CWV_Contratos_JSONB_Tipados: espelha backend ResultadoJsonResposta.
export interface ResultadoJsonResposta {
  n_urls_analisadas?: number | null;
  n_urls_falharam?: number | null;
  analise_ids?: string[];
  analises?: Array<Record<string, unknown>>;
  health_score?: Record<string, unknown> | null;
  motivo_falha?: string | null;
  // SPEC_CWV_Auditoria_Automatica_Pos_Execucao (A2):
  auditoria_id?: string | null;
  auditoria_existente_id?: string | null;
  [k: string]: unknown;
}

export interface ExecucaoResposta {
  id: string;
  ferramenta: string;
  status: string;
  etapa_atual: string | null;
  creditos_cobrados: number;
  resultado_json: ResultadoJsonResposta | null;
  entrada_json: Record<string, unknown>;
  erro_msg: string | null;
  criado_em: string;
  concluida_em: string | null;
  cliente_id: string | null;
}

export async function buscarExecucaoCwv(execucaoId: string): Promise<ExecucaoResposta> {
  return api.get<ExecucaoResposta>(
    `/ferramentas/core-web-vitals/execucao/${execucaoId}`
  );
}

export async function buscarAnaliseCwv(analiseId: string): Promise<CwvAnaliseResposta> {
  return api.get<CwvAnaliseResposta>(`/ferramentas/core-web-vitals/analise/${analiseId}`);
}

// SPEC_CWV_Paginacao_Listagens: params opcionais, default backend = 20.
export interface PaginacaoParams {
  limit?: number;
  offset?: number;
}

export async function buscarHistoricoCwv(
  clienteId: string,
  template?: string,
  pag?: PaginacaoParams,
): Promise<{ urls: CwvHistoricoUrlResposta[]; total: number }> {
  const qs = new URLSearchParams({ cliente_id: clienteId });
  if (template) qs.set("template", template);
  if (pag?.limit !== undefined) qs.set("limit", String(pag.limit));
  if (pag?.offset !== undefined) qs.set("offset", String(pag.offset));
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
export type OrigemItem = "psi_audit" | "page_experience" | "field_data" | "agentic";
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
  metricas_afetadas: string[];
}

// SPEC_CWV_Contratos_JSONB_Tipados: relatorio_json tipado (espelha backend).
export interface PlanoFaseRelatorio {
  titulo: string;
  justificativa: string;
  itens_codigos: string[];
}

export interface RelatorioJsonResposta {
  status?: string | null;
  sumario_executivo_md?: string | null;
  diagnostico_tecnico_md?: string | null;
  plano_fases?: PlanoFaseRelatorio[];
  gerado_em?: string | null;
  modelo?: string | null;
  [k: string]: unknown; // extra="allow" no backend
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
  relatorio_json: RelatorioJsonResposta | null;
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
  cliente_id: string | null;
  cliente_nome: string | null;
  health_score_before: number | null;
  health_score_after: number | null;
  n_itens: number;
  criado_em: string;
}

// --- SPEC_CWV_Auditoria_Comparativo_API ------------------------------------

export interface ComparativoMetricas {
  analise_id: string;
  score_performance: number | null;
  lcp_ms: number | null;
  cls: number | null;
  inp_ms: number | null;
  tbt_ms: number | null;
  n_problemas: number;
}

export interface ComparativoProblemas {
  resolvidos: number;
  persistentes: number;
  novos: number;
  titulos_resolvidos: string[];
  titulos_novos: string[];
}

export interface ComparativoPar {
  url_canonica: string;
  estrategia: string;
  template_tipo: string;
  before: ComparativoMetricas;
  after: ComparativoMetricas | null;
  problemas: ComparativoProblemas | null;
}

export interface ComparativoResposta {
  fase: FaseAuditoria;
  pares: ComparativoPar[];
}

export async function criarAuditoriaCwv(clienteId: string, execucaoId: string, titulo?: string): Promise<AuditoriaResposta> {
  return api.post<AuditoriaResposta>("/ferramentas/core-web-vitals/auditorias", {
    cliente_id: clienteId,
    execucao_id: execucaoId,
    titulo,
  });
}

export async function listarAuditoriasCwv(
  clienteId?: string,
  pag?: PaginacaoParams,
): Promise<{ auditorias: AuditoriaResumo[]; total: number }> {
  const params = new URLSearchParams();
  if (clienteId) params.set("cliente_id", clienteId);
  if (pag?.limit !== undefined) params.set("limit", String(pag.limit));
  if (pag?.offset !== undefined) params.set("offset", String(pag.offset));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return api.get(`/ferramentas/core-web-vitals/auditorias${qs}`);
}

export async function buscarAuditoriaCwv(auditoriaId: string): Promise<AuditoriaResposta> {
  return api.get<AuditoriaResposta>(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}`);
}

export async function buscarComparativoAuditoria(auditoriaId: string): Promise<ComparativoResposta> {
  return api.get<ComparativoResposta>(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}/comparativo`);
}

// --- SPEC_CWV_Auditoria_UI_V2: ficha do item (KB) --------------------------

export interface LinkReferencia {
  titulo: string;
  url: string;
}

export interface EvidenciaItem {
  url_canonica: string;
  estrategia: string;
  elementos: string[];
  total: number;
}

export interface ItemDetalheResposta {
  item_codigo: string;
  titulo: string;
  tem_kb: boolean;
  descricao: string | null;
  severidade: number | null;
  metricas_afetadas: string[];
  solucao_geral: string | null;
  solucao_plataforma: string | null;
  plataforma: string | null;
  links_referencia: LinkReferencia[];
  esforco: string | null;
  urls_escopo: string[];
  evidencias: EvidenciaItem[];
}

// SPEC_CWV_Navegacao_Agentica_Geracao_IA: artefato gerado por IA (llms.txt/WebMCP).
export type TipoArtefatoAgentico = "llms_txt" | "webmcp";

export interface ArtefatoAgenticoResposta {
  tipo: string;
  diagnostico: string | null;
  conteudo_md: string;
  explicacao_md: string | null;
  meta_json: Record<string, unknown>;
  modelo: string | null;
  gerado_em: string;
}

export async function gerarArtefatoAgentico(
  auditoriaId: string,
  tipo: TipoArtefatoAgentico,
): Promise<ArtefatoAgenticoResposta> {
  return api.post<ArtefatoAgenticoResposta>(
    `/ferramentas/core-web-vitals/auditorias/${auditoriaId}/artefatos/${tipo}`,
  );
}

export async function buscarArtefatoAgentico(
  auditoriaId: string,
  tipo: TipoArtefatoAgentico,
): Promise<ArtefatoAgenticoResposta> {
  return api.get<ArtefatoAgenticoResposta>(
    `/ferramentas/core-web-vitals/auditorias/${auditoriaId}/artefatos/${tipo}`,
  );
}

export async function buscarDetalheItemChecklist(
  auditoriaId: string,
  itemId: string,
): Promise<ItemDetalheResposta> {
  return api.get<ItemDetalheResposta>(
    `/ferramentas/core-web-vitals/auditorias/${auditoriaId}/itens/${itemId}/detalhe`,
  );
}

export async function atualizarAuditoriaCwv(auditoriaId: string, dados: { fase?: FaseAuditoria; titulo?: string }): Promise<AuditoriaResposta> {
  return api.patch<AuditoriaResposta>(`/ferramentas/core-web-vitals/auditorias/${auditoriaId}`, dados);
}

export async function atualizarItemChecklistCwv(
  auditoriaId: string,
  itemId: string,
  dados: { status_implementacao?: StatusImplementacao; nota_cliente?: string; nota_seo?: string; prioridade?: number; status_before?: StatusCheck; status_after?: StatusCheck },
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

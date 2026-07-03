export interface Execucao {
  id: string;
  ferramenta: string;
  status: string;
  etapa_atual: string | null;
  creditos_cobrados: number;
  erro_msg: string | null;
  tentativas_revisao: number;
  tentativas_feedback: number;
  criado_em: string;
  concluida_em: string | null;
}

export interface ExecucaoDetalhe extends Execucao {
  entrada_json: Record<string, unknown>;
  resultado_json: Record<string, unknown> | null;
  cliente_id: string | null;
}

export interface ExecucaoCriada {
  id: string;
  ferramenta: string;
  status: string;
  etapa_atual: string | null;
  creditos_cobrados: number;
  criado_em: string;
}

export interface VersaoArtigo {
  versao: number;
  origem: string;
  titulo: string;
  contagem_palavras: number;
  score_revisao: number | null;
  feedback_recebido: string | null;
  criado_em: string;
  conteudo_markdown?: string;
}

export interface GerarArtigoRequest {
  cliente_id: string;
  persona_id: string;
  topico: string;
  palavra_chave_principal: string;
  palavras_chave_secundarias: string[];
  tipo_conteudo: string;
  meta_palavras: number;
  objetivo: string;
  artigo_introdutorio: string;
  perguntas_clientes: string;
  instrucoes_adicionais: string;
}

export interface CustoItem {
  acao: string;
  custo_creditos: number;
  chamadas_llm_estimadas: number;
}

export interface CancelarResultado {
  id: string;
  status: string;
  creditos_cobrados: number;
  mensagem: string;
}

export interface InlinksRequest {
  cliente_id?: string;
  pilar_url?: string;
  pilar_markdown?: string;
  candidatas_urls: string[];
  threshold_score?: number;
  max_inlinks?: number;
  rel_attr?: string;
  ancoras_preferidas?: string[];
  objetivo_linkagem?: string;
  permitir_cta_fallback?: boolean;
}

export interface CustoInlinksResponse {
  custo_base: number;
  custo_por_url: number;
  custo_maximo: number;
  custo_estimado: number;
  n_urls: number;
}

export type CategoriaMatchInlink =
  | "alta_similaridade"
  | "boa_similaridade"
  | "complemento_contextual"
  | "similaridade_media";

export interface InlinkAplicado {
  id?: string;
  url_destino: string;
  anchor_text: string;
  paragrafo_idx: number;
  offset_chars: number;
  score_total: number;
  score_semantico: number;
  score_contexto: number;
  status: string;
  motivo_rejeicao?: string | null;
  trecho_contexto?: string | null;
  titulo_destino?: string | null;
  motivo_contexto?: string | null;
  categoria_match?: CategoriaMatchInlink | string | null;
  motivo_sugestao?: string | null;
  trecho_original?: string | null;
  conector_antes?: string | null;
  conector_depois?: string | null;
  confianca?: number | null;
  sinal_cos_contexto?: number | null;
  sinal_cos_ancora?: number | null;
}

export interface ResultadoInlinks {
  n_candidatas_validas: number;
  n_aplicadas: number;
  n_rejeitadas: number;
  funil?: FunilInlinks;
  artigo_titulo: string;
  artigo: string;
  conteudo_markdown: string;
  pilar_original: string;
  imagem_url: string | null;
  inlinks: InlinkAplicado[];
}

export interface DistribuirInlinksRequest {
  cliente_id?: string;
  url_alvo: string;
  candidatas_urls: string[];
  threshold_score?: number;
  max_inlinks_por_candidata?: number;
  rel_attr?: string;
  ancoras_preferidas?: string[];
  objetivo_linkagem?: string;
  permitir_cta_fallback?: boolean;
}

export interface CustoDistribuirInlinksResponse {
  custo_base: number;
  custo_por_candidata: number;
  custo_maximo: number;
  custo_estimado: number;
  n_candidatas: number;
}

export interface CandidataResultado {
  url: string;
  url_canonica: string;
  titulo: string;
  status: "aplicado" | "sugestao_manual" | "sem_match" | "falhou_extracao";
  markdown_modificado?: string | null;
  anchor_text?: string | null;
  trecho_original?: string | null;
  paragrafo_idx?: number | null;
  justificativa?: string | null;
  score_total?: number | null;
  score_semantico?: number | null;
  motivo?: string | null;
  trecho_contexto?: string | null;
  categoria_match?: string | null;
  ancora_preferida_usada?: boolean | null;
}

export interface FunilInlinks {
  n_solicitadas?: number;
  n_scrape_ok?: number;
  n_scrape_falhas?: number;
  urls_falhas?: string[];
  n_pos_cosine_top15?: number;
  n_pos_piso_ruido?: number;
  n_descartadas_piso_ruido?: number;
  n_viaveis?: number;
  n_descartadas_similaridade?: number;
  n_falhas_extracao?: number;
  threshold_informativo?: number;
  n_enviadas_juiz?: number;
  n_decisao_aplicar?: number;
  n_decisao_sugerir?: number;
  n_decisao_descartar?: number;
  n_sem_match?: number;
  n_rejeitados_revisor?: number;
  n_aplicadas?: number;
  motivos?: Record<string, number>;
}

export interface ResultadoDistribuirInlinks {
  url_alvo: string;
  titulo_alvo: string;
  alvo_modo?: "pleno" | "slug_only";
  n_candidatas_validas: number;
  n_aplicadas: number;
  n_sugestoes: number;
  n_sem_match: number;
  n_falhas: number;
  candidatas: CandidataResultado[];
  alvo_invalido?: boolean;
  motivo_alvo?: string | null;
  funil?: FunilInlinks;
}

// ── SPEC_Inlinks_Descoberta_Automatica_Candidatas ─────────────────────────────

export type StatusIndiceSite =
  | "nao_indexado"
  | "indexando"
  | "pronto"
  | "falhou";

export interface IndiceSiteStatus {
  status: StatusIndiceSite;
  n_paginas: number;
  n_falhas: number;
  dominio: string | null;
  atualizado_em: string | null;
  erro_msg: string | null;
}

export interface CandidataSugerida {
  url: string;
  titulo: string;
  resumo: string;
  score: number;
}

export interface RespostaCandidatas {
  candidatas: CandidataSugerida[];
  modo: string;
  total: number;
}

export interface IndexarSiteResponse {
  id: string;
  ferramenta: "indexar_site";
  status: string;
  dominio: string;
  custo_maximo_estimado: number;
}

export interface ClienteResumido {
  id: string;
  nome: string;
  site_url: string | null;
}

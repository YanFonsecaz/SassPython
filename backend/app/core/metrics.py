from prometheus_client import Counter, Gauge, Histogram

llm_calls_total = Counter(
    "llm_calls_total",
    "Total LLM calls",
    ["model", "usuario_id"],
)
llm_call_duration = Histogram(
    "llm_call_duration_seconds",
    "LLM call duration",
    ["model"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
)
workflow_duration = Histogram(
    "workflow_duration_seconds",
    "Workflow duration",
    ["ferramenta", "status"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1200),
)
credits_reserved = Gauge(
    "credits_reserved_total",
    "Total credits currently reserved",
)
rate_limit_blocks = Counter(
    "rate_limit_blocks_total",
    "Rate limit blocks",
    ["endpoint", "scope"],
)

cwv_psi_request_total = Counter(
    "cwv_psi_request_total",
    "Total PSI API requests",
    ["key_index", "status"],
)
cwv_psi_quota_exhausted = Counter(
    "cwv_psi_quota_exhausted_total",
    "PSI quota exhausted (all keys failed)",
    ["key_index"],
)
cwv_analise_duracao_seconds = Histogram(
    "cwv_analise_duracao_seconds",
    "CWV analysis duration per URL",
    buckets=(10, 30, 60, 120, 300, 600),
)
cwv_llm_tokens_total = Counter(
    "cwv_llm_tokens_total",
    "CWV LLM token usage",
    ["agente", "modelo", "tipo"],
)
cwv_llm_custo_usd = Counter(
    "cwv_llm_custo_usd_total",
    "CWV LLM cost in USD",
    ["agente", "modelo"],
)
cwv_problemas_por_analise = Histogram(
    "cwv_problemas_por_analise",
    "Number of problems found per CWV analysis",
    buckets=(0, 5, 10, 15, 20, 30, 50),
)
cwv_pesquisador_invocacoes = Counter(
    "cwv_pesquisador_invocacoes_total",
    "CWV Pesquisador agent invocations",
)
cwv_kb_miss_total = Counter(
    "cwv_kb_miss_total",
    "CWV KB misses (unmapped audit_ids)",
    ["audit_id"],
)
parecer_geracoes_total = Counter(
    "parecer_geracoes_total",
    "Parecer tecnico generation attempts",
    ["status"],
)
parecer_imagens_total = Counter(
    "parecer_imagens_total",
    "Total images analyzed in parecer workflow",
    ["status"],
)
parecer_workflow_duration = Histogram(
    "parecer_workflow_duration_seconds",
    "Parecer workflow duration",
    buckets=(5, 10, 30, 60, 120, 300, 600),
)

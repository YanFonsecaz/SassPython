from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

_DEFAULTS_PROIBIDOS = {
    "chave-secreta-padrao-mudar-em-producao",
    "jwt-secreto-padrao-mudar-em-producao",
    "chave-encriptacao-padrao-32bytes!!",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ambiente: str = "desenvolvimento"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/seo_saas"

    secret_key: str = "chave-secreta-padrao-mudar-em-producao"
    jwt_secret_key: str = "jwt-secreto-padrao-mudar-em-producao"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires: int = 900
    jwt_refresh_token_expires: int = 604800

    encryption_key: str = "chave-encriptacao-padrao-32bytes!!"

    @field_validator("secret_key", "jwt_secret_key", "encryption_key")
    @classmethod
    def _impedir_default_em_prod(cls, v: str, info) -> str:
        if v in _DEFAULTS_PROIBIDOS:
            ambiente = info.data.get("ambiente", "desenvolvimento")
            if ambiente != "desenvolvimento":
                raise ValueError(
                    f"Secret '{info.field_name}' usa valor default. "
                    f"Defina via .env antes de subir em ambiente={ambiente}."
                )
        return v

    @field_validator("jwt_secret_key", "encryption_key")
    @classmethod
    def _tamanho_minimo(cls, v: str, info) -> str:
        if len(v.encode()) < 32:
            raise ValueError(
                f"Secret '{info.field_name}' deve ter pelo menos 32 bytes. "
                f"Atual: {len(v.encode())} bytes."
            )
        return v

    frontend_url: str = "http://localhost:3000"
    app_url: str = "http://localhost:8000"

    rate_limit_login_max: int = 5
    rate_limit_login_window: int = 900
    rate_limit_geral_max: int = 100
    rate_limit_geral_window: int = 60
    rate_limit_forgot_max: int = 3
    rate_limit_forgot_window: int = 3600
    rate_limit_reset_max: int = 5
    rate_limit_reset_window: int = 60
    rate_limit_mfa_max: int = 10
    rate_limit_mfa_window: int = 900

    login_response_time: float = 1.5

    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "zhipuai"
    llm_model: str = "glm-4.7-flash"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    zhipuai_api_key: str = ""
    openai_api_key: str = ""
    inseridor_llm_model: str = "gpt-4.1"
    reranker_llm_model: str = "gpt-4.1"
    revisor_llm_model: str = "gpt-4.1"
    enriquecedor_llm_model: str = "gpt-4.1"

    inlinks_inseridor_temperature: float = 0.0
    inlinks_revisor_temperature: float = 0.1
    inlinks_reranker_temperature: float = 0.2
    inlinks_enriquecedor_temperature: float = 0.2
    inlinks_cleaner_temperature: float = 0.0
    inlinks_formatador_temperature: float = 0.0
    inlinks_formatador_ativo: bool = True
    inlinks_pisos_legado_distribuir: bool = False
    # SPEC_Inlinks_Remover_Reranker_Redundante — kill-switches com GATE:
    # defaults True (comportamento atual). Só virar False em produção APÓS ~2
    # semanas de funil confirmando que reranker/revisor não mudam resultados.
    # Ver SPEC_Inlinks_Remover_Reranker_Redundante.md (§Gatilho).
    inlinks_reranker_ativo: bool = True
    inlinks_revisor_ativo: bool = True
    # SPEC_Distribuir_Viabilidade_Pelo_Juiz: sem o filtro de threshold no upstream,
    # o juiz poderia receber todas as candidatas acima do piso — este teto limita
    # o pior caso de custo de LLM (excedentes viram sem_match "fora do top-N").
    distribuir_max_julgamentos: int = 30

    cwv_analisador_llm_model: str = "gpt-4o-mini"
    cwv_analisador_llm_temperature: float = 0.1
    cwv_pesquisador_llm_model: str = "gpt-4.1"
    cwv_pesquisador_llm_temperature: float = 0.4
    cwv_admin_reload_token: str = ""
    cwv_alerta_webhook_url: str = ""

    embedding_model: str = "embedding-3"
    embedding_dimensions: int = 1024
    # Cache durável de embeddings (SPEC_Inlinks_Cache_Duravel_Embeddings):
    # L2 em Postgres atrás do Redis. Limpeza semanal por uso.
    embeddings_cache_ttl_dias: int = 90
    embeddings_cache_max_linhas: int = 50000

    serpapi_key: str = ""
    api_context7_key: str = ""
    api_psi_key: str = ""
    api_psi_key2: str = ""
    api_safe_browsing_key: str = ""

    cwv_workflow_timeout: int = 1200
    cwv_max_urls_por_execucao: int = 50
    cwv_pesquisador_max_por_analise: int = 5
    google_trends_enabled: bool = False

    parecer_analisador_model: str = "gpt-4o"
    parecer_documentador_model: str = "gpt-4.1"
    parecer_workflow_timeout: int = 600

    imagem_model: str = "glm-image"

    pesquisa_cache_ttl_days: int = 7

    workflow_timeout_segundos: int = 600
    workflow_max_revisoes: int = 3
    workflow_max_feedback: int = 3

    artigo_revisor_temperature: float = 0.1
    artigo_revisor_model: str | None = None
    artigo_revisor_score_min: int = 70

    arq_max_jobs: int = 20
    arq_job_timeout: int = 2400

    hibp_fail_mode: str = "open"  # "open" | "closed" | "queue"

    workflow_distribuir_inlinks_timeout: int = 1800

    # SPEC_Inlinks_Descoberta_Automatica_Candidatas: timeout do job de indexação
    # do site do cliente (sitemap pode ter centenas de páginas).
    indexar_workflow_timeout: int = 1800

    cors_origins: list[str] = ["http://localhost:3000"]

    langsmith_api_key: str = ""
    langsmith_project: str = "seo-saas"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    sentry_dsn: str = ""

    metrics_allowlist: list[str] = []

    uploads_dir: str = str(BASE_DIR / "uploads")


settings = Settings()

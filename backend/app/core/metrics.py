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

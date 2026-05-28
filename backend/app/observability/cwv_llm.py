"""Helpers de observabilidade do CWV: extrai tokens de respostas LLM e emite metricas."""
from __future__ import annotations

from typing import Any

from app.core.metrics import cwv_llm_custo_usd, cwv_llm_tokens_total

PRECOS_USD_POR_1K = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4.1": {"input": 0.005, "output": 0.015},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
}


def emit_llm_usage(resultado: Any, agente: str, modelo: str) -> None:
    """Extrai usage_metadata de uma resposta LangChain e emite metricas Prometheus.

    Aceita AIMessage, dict ou objeto pydantic. Falha silenciosamente se nao houver metadata.
    """
    usage = _extrair_usage(resultado)
    if not usage:
        return
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    cwv_llm_tokens_total.labels(agente=agente, modelo=modelo, tipo="input").inc(input_tokens)
    cwv_llm_tokens_total.labels(agente=agente, modelo=modelo, tipo="output").inc(output_tokens)
    preco = PRECOS_USD_POR_1K.get(modelo)
    if preco:
        custo = (input_tokens / 1000) * preco["input"] + (output_tokens / 1000) * preco["output"]
        cwv_llm_custo_usd.labels(agente=agente, modelo=modelo).inc(custo)


def _extrair_usage(resultado: Any) -> dict | None:
    if resultado is None:
        return None
    usage = getattr(resultado, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        return usage
    resp_meta = getattr(resultado, "response_metadata", None)
    if isinstance(resp_meta, dict):
        tk = resp_meta.get("token_usage") or resp_meta.get("usage")
        if isinstance(tk, dict):
            return {
                "input_tokens": tk.get("prompt_tokens") or tk.get("input_tokens"),
                "output_tokens": tk.get("completion_tokens") or tk.get("output_tokens"),
            }
    return None

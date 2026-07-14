import asyncio
import json
import logging
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.core.metrics import cwv_psi_quota_exhausted, cwv_psi_request_total

logger = logging.getLogger(__name__)

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
TIMEOUT_SECONDS = 90
_PSI_MAX_RETRY = 2

_PSI_CLIENT: httpx.AsyncClient | None = None

# Teto defensivo do resumo compacto gravado em raw_resumo_json. Screenshots e
# details.items NUNCA entram (pesados); se ainda assim exceder, removemos
# entities e depois audits_score_map (ver _construir_resumo).
_RESUMO_MAX_CHARS = 64_000

# Chaves de audits cujo details.items são pesados e não agregam valor ao
# resumo (screenshots base64, treemap, network). Nunca devem entrar no resumo.
_AUDITS_DESCARTAR_NO_RESUMO = {
    "final-screenshot",
    "full-page-screenshot",
    "screenshot-thumbnails",
    "script-treemap-data",
}


class PSIError(Exception):
    pass


def _psi_keys() -> list[str]:
    keys = [settings.api_psi_key, settings.api_psi_key2]
    return [k for k in keys if k]


def _get_client() -> httpx.AsyncClient:
    global _PSI_CLIENT
    if _PSI_CLIENT is None or _PSI_CLIENT.is_closed:
        _PSI_CLIENT = httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _PSI_CLIENT


async def _fetch_psi_once(url: str, estrategia: str, api_key: str | None) -> dict:
    params = {"url": url, "strategy": estrategia, "category": "performance"}
    if api_key:
        params["key"] = api_key
    resp = await _get_client().get(PSI_ENDPOINT, params=params)
    resp.raise_for_status()
    return resp.json()


async def _fetch_com_retry(url: str, estrategia: str, key: str | None) -> dict:
    for tentativa in range(_PSI_MAX_RETRY + 1):
        try:
            return await _fetch_psi_once(url, estrategia, key)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and tentativa < _PSI_MAX_RETRY:
                await asyncio.sleep(2 ** tentativa)
                continue
            raise
        except httpx.RequestError:
            if tentativa < _PSI_MAX_RETRY:
                await asyncio.sleep(2 ** tentativa)
                continue
            raise
    raise PSIError("Retry esgotado (inexpectado)")


async def fetch_psi(url: str, estrategia: str = "mobile") -> dict:
    keys = _psi_keys() or [None]
    ultimo_erro: Exception | None = None
    for i, key in enumerate(keys):
        try:
            data = await _fetch_com_retry(url, estrategia, key)
            if "lighthouseResult" not in data:
                raise PSIError(f"Resposta PSI sem lighthouseResult: {data.get('error', {}).get('message', 'desconhecido')}")
            cwv_psi_request_total.labels(key_index=str(i + 1), status="ok").inc()
            return data
        except httpx.HTTPStatusError as e:
            ultimo_erro = e
            code = e.response.status_code
            cwv_psi_request_total.labels(key_index=str(i + 1), status=str(code)).inc()
            logger.warning("PSI HTTP %s (key #%d) para url=%s: %s", code, i + 1, url, e.response.text[:300])
            if code in (429, 403) and i + 1 < len(keys):
                continue
            raise PSIError(f"PSI retornou {code}") from e
        except httpx.RequestError as e:
            ultimo_erro = e
            cwv_psi_request_total.labels(key_index=str(i + 1), status="network_error").inc()
            logger.warning("PSI erro de rede (key #%d) para url=%s: %s", i + 1, url, e)
            if i + 1 < len(keys):
                continue
            raise PSIError(f"Erro de rede: {e}") from e
    cwv_psi_quota_exhausted.labels(key_index=str(len(keys))).inc()
    logger.error(
        "cwv.psi.both_keys_failed url=%s",
        url,
        extra={"event_type": "cwv.psi.both_keys_failed", "url": url},
    )
    await _fire_webhook_alert(url)
    raise PSIError(f"PSI falhou em todas as keys: {ultimo_erro}")


def _extrair_field_data(payload: dict) -> dict:
    """Extrai o field data CrUX (usuários reais) do payload PSI.

    Tenta ``loadingExperience`` (nível URL) e cai para
    ``originLoadingExperience`` (nível origem), marcando ``crux_origem_fallback``.
    Se nenhum tem ``metrics`` não-vazio, retorna todos os campos ``None`` e
    fallback ``False``.

    Atenção: ``CUMULATIVE_LAYOUT_SHIFT_SCORE.percentile`` vem multiplicado por
    100 (ex.: 4 = CLS 0.04) — dividimos por 100 ao materializar.
    ``INTERACTION_TO_NEXT_PAINT`` pode estar ausente em payloads antigos → None.
    """
    le = payload.get("loadingExperience") or {}
    ole = payload.get("originLoadingExperience") or {}

    def _metrics(obj):
        return obj.get("metrics") if isinstance(obj, dict) else None

    le_metrics = _metrics(le) or {}
    ole_metrics = _metrics(ole) or {}

    if le_metrics:
        source = le
        fallback = False
    elif ole_metrics:
        source = ole
        fallback = True
    else:
        return {
            "crux_lcp_p75_ms": None,
            "crux_inp_p75_ms": None,
            "crux_cls_p75": None,
            "crux_lcp_categoria": None,
            "crux_inp_categoria": None,
            "crux_cls_categoria": None,
            "crux_overall_categoria": None,
            "crux_origem_fallback": False,
        }

    metrics = source.get("metrics", {})

    def _metric_val(key: str, field: str = "percentile") -> float | None:
        m = metrics.get(key)
        if not m:
            return None
        v = m.get(field)
        return float(v) if v is not None else None

    def _metric_cat(key: str) -> str | None:
        m = metrics.get(key)
        return m.get("category") if m else None

    # CLS vem multiplicado por 100 no percentile (CrUX quirk).
    cls_p75 = _metric_val("CUMULATIVE_LAYOUT_SHIFT_SCORE")
    if cls_p75 is not None:
        cls_p75 = cls_p75 / 100

    return {
        "crux_lcp_p75_ms": _metric_val("LARGEST_CONTENTFUL_PAINT_MS"),
        "crux_inp_p75_ms": _metric_val("INTERACTION_TO_NEXT_PAINT"),
        "crux_cls_p75": cls_p75,
        "crux_lcp_categoria": _metric_cat("LARGEST_CONTENTFUL_PAINT_MS"),
        "crux_inp_categoria": _metric_cat("INTERACTION_TO_NEXT_PAINT"),
        "crux_cls_categoria": _metric_cat("CUMULATIVE_LAYOUT_SHIFT_SCORE"),
        "crux_overall_categoria": source.get("overall_category"),
        "crux_origem_fallback": fallback,
    }


def _construir_resumo(payload: dict) -> dict:
    """Constrói o resumo compacto (≤64KB) do payload PSI.

    Inclui: loading_experience/origin_loading_experience completos, um
    audits_score_map {audit_id: score} para todos os audits com score (habilita
    checklist Pass/Fail completo em specs futuras), stack_packs (ids),
    entities (names, máx 30), metadados do Lighthouse.

    NUNCA inclui: final-screenshot, full-page-screenshot,
    screenshot-thumbnails, details.items de audits. Se ainda exceder o teto,
    remove entities e depois audits_score_map (defesa em profundidade).
    """
    lh = payload.get("lighthouseResult") or {}
    audits = lh.get("audits") or {}

    audits_score_map = {
        aid: a.get("score")
        for aid, a in audits.items()
        if a.get("score") is not None and aid not in _AUDITS_DESCARTAR_NO_RESUMO
    }

    stack_packs = [sp.get("id") for sp in (lh.get("stackPacks") or []) if sp.get("id")]
    entities = [e.get("name") for e in (lh.get("entities") or []) if e.get("name")][:30]
    config_settings = lh.get("configSettings") or {}

    resumo = {
        "loading_experience": payload.get("loadingExperience"),
        "origin_loading_experience": payload.get("originLoadingExperience"),
        "audits_score_map": audits_score_map,
        "stack_packs": stack_packs,
        "entities": entities,
        "lighthouse_version": lh.get("lighthouseVersion"),
        "fetch_time": lh.get("fetchTime"),
        "form_factor": config_settings.get("formFactor"),
    }

    # Truncagem defensiva: remove campos menos críticos até caber no teto.
    if len(json.dumps(resumo, default=str)) > _RESUMO_MAX_CHARS:
        resumo["entities"] = []
    if len(json.dumps(resumo, default=str)) > _RESUMO_MAX_CHARS:
        resumo["audits_score_map"] = {}
    return resumo


def parse_psi(payload: dict) -> dict:
    lh = payload["lighthouseResult"]
    categories = lh.get("categories", {})
    audits = lh.get("audits", {})

    def audit_val(key: str, field: str = "numericValue") -> float | None:
        a = audits.get(key, {})
        return a.get(field) if a.get("score") is not None else None

    network_items = audits.get("network-requests", {}).get("details", {}).get("items", [])
    main_doc_bytes = 0
    for item in network_items:
        url = item.get("url", "")
        if url == lh.get("finalUrl") or url == lh.get("requestedUrl"):
            main_doc_bytes = item.get("transferSize", 0)
            break

    audits_com_score = sum(1 for a in audits.values() if a.get("score") is not None)

    field_data = _extrair_field_data(payload)
    resumo = _construir_resumo(payload)

    return {
        "score_performance": int((categories.get("performance", {}).get("score") or 0) * 100),
        "lcp_ms": audit_val("largest-contentful-paint"),
        "cls": audit_val("cumulative-layout-shift"),
        "inp_ms": audit_val("interaction-to-next-paint") or audit_val("max-potential-fid"),
        "fcp_ms": audit_val("first-contentful-paint"),
        "ttfb_ms": audit_val("server-response-time"),
        "tbt_ms": audit_val("total-blocking-time"),
        "audits_falhos": [
            {
                "id": k,
                "title": a.get("title"),
                "description": a.get("description"),
                "score": a.get("score"),
                "scoreDisplayMode": a.get("scoreDisplayMode"),
                "displayValue": a.get("displayValue"),
                "numericValue": a.get("numericValue"),
                "numericUnit": a.get("numericUnit"),
                "metricSavings": a.get("metricSavings"),
                "warnings": a.get("warnings"),
                "details": a.get("details"),
            }
            for k, a in audits.items()
            if a.get("score") is not None
            and a["score"] < 0.9
            and a.get("scoreDisplayMode") not in ("informative", "notApplicable")
        ],
        "html_inicial": lh.get("finalUrl"),
        "user_agent": lh.get("userAgent"),
        "audits_totais": audits_com_score,
        "n_network_requests": len(network_items),
        "main_document_size_bytes": main_doc_bytes,
        # SPEC_CWV_Field_Data_Retencao_Payload: field data CrUX + resumo compacto.
        **field_data,
        "resumo": resumo,
    }


def normalizar_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return f"{scheme}://{netloc}{path}"


async def _fire_webhook_alert(url: str) -> None:
    webhook_url = settings.cwv_alerta_webhook_url
    if not webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(webhook_url, json={
                "text": f"CWV PSI Alert: ambas as keys falharam para {url}. Verifique quota/rotacao.",
                "event_type": "cwv.psi.both_keys_failed",
                "url": url,
            })
    except Exception:
        logger.warning("Falha ao enviar webhook de alerta PSI", exc_info=True)

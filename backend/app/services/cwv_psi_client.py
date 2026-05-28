import asyncio
import logging
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.core.metrics import cwv_psi_quota_exhausted, cwv_psi_request_total

logger = logging.getLogger(__name__)

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
TIMEOUT_SECONDS = 90


class PSIError(Exception):
    pass


def _psi_keys() -> list[str]:
    keys = [settings.api_psi_key, settings.api_psi_key2]
    return [k for k in keys if k]


async def _fetch_psi_once(url: str, estrategia: str, api_key: str | None) -> dict:
    params = {"url": url, "strategy": estrategia, "category": "performance"}
    if api_key:
        params["key"] = api_key
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        resp = await client.get(PSI_ENDPOINT, params=params)
        resp.raise_for_status()
    return resp.json()


async def fetch_psi(url: str, estrategia: str = "mobile") -> dict:
    keys = _psi_keys() or [None]
    ultimo_erro: Exception | None = None
    for i, key in enumerate(keys):
        try:
            data = await _fetch_psi_once(url, estrategia, key)
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

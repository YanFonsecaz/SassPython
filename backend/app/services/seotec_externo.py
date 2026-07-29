"""Integração PageSpeed Insights + Safe Browsing para itens manuais SEOTec.

Avalia via APIs externas:
- teste-de-velocidade-abaixo-de-80 (PSI score)
- experiencia-na-pagina (PSI CWV metrics)
- verificacao-de-seguranca-e-scanner-de-malware (Google Safe Browsing API)

Fail-open: sem API key → retorna "sem_dados" (item permanece manual).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.services.seotec_auto_avaliador import _SEM_DADOS, ResultadoAuto

logger = logging.getLogger(__name__)


@dataclass
class ResultadoPSI:
    performance_score: int | None
    lcp_ms: int | None
    cls: float | None
    fid_ms: int | None
    url_testada: str
    erro: str | None = None


async def fetch_psi_seotec(url: str) -> ResultadoPSI:
    """Busca PageSpeed Insights para uma URL (estratégia mobile).

    Reusa a mesma API key do CWV se disponível. Sem key → usa endpoint público
    (rate-limited, mas funcional).
    """
    api_key = getattr(settings, "api_psi_key", "") or getattr(settings, "google_psi_api_key", "") or ""
    endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {"url": url, "strategy": "mobile"}
    if api_key:
        params["key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.get(endpoint, params=params)
            if resp.status_code != 200:
                return ResultadoPSI(
                    None, None, None, None, url,
                    erro=f"PSI HTTP {resp.status_code}",
                )
            data = resp.json()
    except Exception as exc:
        logger.warning("psi_erro %s: %s", url, exc)
        return ResultadoPSI(None, None, None, None, url, erro=str(exc))

    try:
        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        perf = categories.get("performance", {})
        score = perf.get("score")
        perf_score = round(score * 100) if score is not None else None

        audits = lighthouse.get("audits", {})
        lcp = audits.get("largest-contentful-paint", {}).get("numericValue")
        cls = audits.get("cumulative-layout-shift", {}).get("numericValue")
        fid = audits.get("max-potential-fid", {}).get("numericValue")

        # Loading do CWV via API experimental
        cwv_data = data.get("loadingExperience", {}).get("metrics", {})
        lcp_cwv = cwv_data.get("LARGEST_CONTENTFUL_PAINT_MS", {}).get("percentile")
        cls_cwv = cwv_data.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {}).get("percentile")
        fid_cwv = cwv_data.get("FIRST_INPUT_DELAY_MS", {}).get("percentile")

        return ResultadoPSI(
            performance_score=perf_score,
            lcp_ms=round(lcp_cwv or lcp) if (lcp_cwv or lcp) else None,
            cls=float(cls_cwv or cls) / 100 if (cls_cwv or cls) else None,
            fid_ms=int(fid_cwv or fid) if (fid_cwv or fid) else None,
            url_testada=url,
        )
    except Exception as exc:
        logger.warning("psi_parse_erro: %s", exc)
        return ResultadoPSI(None, None, None, None, url, erro=str(exc))


def avaliar_velocidade(psi: ResultadoPSI) -> ResultadoAuto:
    """Teste de velocidade abaixo de 80 (GTmetrix/PSI)."""
    if psi.erro or psi.performance_score is None:
        return _SEM_DADOS
    score = psi.performance_score
    ev = {"psi_score": score, "url": psi.url_testada}
    if score >= 80:
        return ResultadoAuto("aprovado", ev)
    elif score >= 50:
        return ResultadoAuto("atencao", ev)
    return ResultadoAuto("reprovado", ev)


def avaliar_experiencia_pagina(psi: ResultadoPSI) -> ResultadoAuto:
    """Experiência na página (Core Web Vitals)."""
    if psi.erro or psi.lcp_ms is None:
        return _SEM_DADOS

    lcp_ok = psi.lcp_ms <= 2500
    cls_ok = psi.cls is None or psi.cls <= 0.1
    fid_ok = psi.fid_ms is None or psi.fid_ms <= 100

    ev = {
        "lcp_ms": psi.lcp_ms,
        "cls": psi.cls,
        "fid_ms": psi.fid_ms,
        "url": psi.url_testada,
    }
    if lcp_ok and cls_ok and fid_ok:
        return ResultadoAuto("aprovado", ev)
    elif lcp_ok or cls_ok:
        return ResultadoAuto("atencao", ev)
    return ResultadoAuto("reprovado", ev)


async def avaliar_safe_browsing(url: str) -> ResultadoAuto:
    """Verificação de segurança e scanner de malware (Google Safe Browsing API).

    Requires `google_safe_browsing_api_key` in settings. Sem key → sem_dados.
    """
    api_key = getattr(settings, "api_safe_browsing_key", "") or ""
    if not api_key:
        return _SEM_DADOS

    endpoint = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={api_key}"
    body = {
        "client": {"clientId": "seosaas", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "THREAT_TYPE_UNSPECIFIED"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(endpoint, json=body)
            if resp.status_code != 200:
                logger.warning("safe_browsing_http_%d", resp.status_code)
                return _SEM_DADOS
            data = resp.json()
    except Exception as exc:
        logger.warning("safe_browsing_erro: %s", exc)
        return _SEM_DADOS

    matches = data.get("matches", [])
    if not matches:
        return ResultadoAuto("aprovado", {"ameacas": 0, "url": url})
    threat_types = [m.get("threatType", "?") for m in matches]
    return ResultadoAuto("reprovado", {"ameacas": len(matches), "tipos": threat_types, "url": url})


async def avaliar_externo(dominio: str) -> dict[str, ResultadoAuto]:
    """Executa todas as avaliações que dependem de APIs externas."""
    resultados: dict[str, ResultadoAuto] = {}

    # PSI (velocidade + experiência)
    psi = await fetch_psi_seotec(dominio)
    r1 = avaliar_velocidade(psi)
    if r1.status != "sem_dados":
        resultados["teste-de-velocidade-abaixo-de-80-usando-gtmetrix-home-page-landing-page"] = r1
    r2 = avaliar_experiencia_pagina(psi)
    if r2.status != "sem_dados":
        resultados["experiencia-na-pagina"] = r2

    # Safe Browsing
    r3 = await avaliar_safe_browsing(dominio)
    if r3.status != "sem_dados":
        resultados["verificacao-de-seguranca-e-scanner-de-malware"] = r3

    logger.info("externo_concluido dominio=%s avaliados=%d", dominio, len(resultados))
    return resultados

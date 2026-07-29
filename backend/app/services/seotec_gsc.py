"""Integração Google Search Console para itens GSC do checklist SEOTec.

Usa service account (JSON key file) para autenticar via google-auth.
Chama a Search Console API v3 (webmasters) + URL Inspection API.

7 itens avaliados:
- google-search-console-acoes-manuais
- google-search-console-pagina-nao-encontrada
- google-search-console-paginas-bloqueadas-por-robots-txt
- google-search-console-paginas-indexadas
- google-search-console-indexacao-de-sitemap
- google-search-console-estatisticas-de-rastreamento
- sitemap-s-xml-da-pagina-estao-listados-no-gsc

Fail-open: sem service account configurado → todos retornam "sem_dados".
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from app.config import settings
from app.services.seotec_auto_avaliador import _SEM_DADOS, ResultadoAuto

logger = logging.getLogger(__name__)

GSC_BASE = "https://www.googleapis.com/webmasters/v3"
GSC_INSPECT = "https://search.google.com/search-console/api/v1/urlInspection"


def _carregar_credenciais() -> dict | None:
    """Carrega service account JSON do path configurado."""
    path = getattr(settings, "gsc_service_account_path", "") or ""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        logger.warning("gsc_service_account_path nao encontrado: %s", path)
        return None
    return json.loads(p.read_text())


async def _obter_access_token(credenciais: dict) -> str | None:
    """Obtem access token via JWT exchange (service account flow)."""
    import time

    import jwt

    now = int(time.time())
    payload = {
        "iss": credenciais["client_email"],
        "scope": "https://www.googleapis.com/auth/webmasters.readonly",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }
    token = jwt.encode(payload, credenciais["private_key"], algorithm="RS256")

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": token,
            },
        )
        if resp.status_code != 200:
            logger.warning("gsc_token_erro HTTP %d", resp.status_code)
            return None
        return resp.json().get("access_token")


def _site_url_gsc(dominio: str) -> str:
    """Converte dominio para formato aceito pela GSC API.

    GSC aceita: sc-domain:exemplo.com ou https://exemplo.com/
    """
    if dominio.startswith("http"):
        return dominio.rstrip("/") + "/"
    return f"sc-domain:{dominio.replace('https://', '').replace('http://', '')}"


async def _gsc_get(token: str, path: str) -> dict | None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.get(
            f"{GSC_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            logger.warning("gsc_get %s HTTP %d", path, resp.status_code)
            return None
        return resp.json()


async def _gsc_post(token: str, path: str, body: dict) -> dict | None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.post(
            f"{GSC_BASE}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
        if resp.status_code != 200:
            logger.warning("gsc_post %s HTTP %d", path, resp.status_code)
            return None
        return resp.json()


async def _inspect_url(token: str, site_url: str, url: str) -> dict | None:
    """URL Inspection API — verifica status de indexação de uma URL."""
    body = {
        "inspectionUrl": url,
        "siteUrl": site_url,
        "languageCode": "pt-BR",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        resp = await client.post(
            f"{GSC_BASE}/urlInspection/index:inspect",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
        if resp.status_code != 200:
            logger.warning("gsc_inspect HTTP %d", resp.status_code)
            return None
        data = resp.json()
        return data.get("inspectionResult", {}).get("indexStatusResult", {})


# --- Avaliadores individuais ---

def _av_acoes_manuais(inspect: dict | None) -> ResultadoAuto:
    if not inspect:
        return _SEM_DADOS
    google_signals = inspect.get("googleSignals", {})
    manual_actions = google_signals.get("manualActions", {})
    if not manual_actions:
        return ResultadoAuto("aprovado", {"acoes_manuais": 0})
    n = len(manual_actions)
    return ResultadoAuto("reprovado", {"acoes_manuais": n, "detalhes": manual_actions})


def _av_pagina_nao_encontrada(inspect: dict | None) -> ResultadoAuto:
    if not inspect:
        return _SEM_DADOS
    verdict = inspect.get("verdict", "")
    coverage = inspect.get("coverageState", "")
    if verdict == "PASS":
        return ResultadoAuto("aprovado", {"verdict": verdict, "coverage": coverage})
    elif "NOT_FOUND" in coverage or "404" in coverage:
        return ResultadoAuto("reprovado", {"verdict": verdict, "coverage": coverage})
    return ResultadoAuto("atencao", {"verdict": verdict, "coverage": coverage})


def _av_bloqueadas_robots(inspect: dict | None) -> ResultadoAuto:
    if not inspect:
        return _SEM_DADOS
    robots_state = inspect.get("robotsTxtState", "")
    verdict = inspect.get("verdict", "")
    if robots_state == "ALLOWED" or verdict != "BLOCKED_BY_ROBOTS_TXT":
        return ResultadoAuto("aprovado", {"robots_txt_state": robots_state})
    return ResultadoAuto("reprovado", {"robots_txt_state": robots_state, "verdict": verdict})


def _av_paginas_indexadas(inspect: dict | None) -> ResultadoAuto:
    if not inspect:
        return _SEM_DADOS
    verdict = inspect.get("verdict", "")
    coverage = inspect.get("coverageState", "")
    if verdict == "PASS" or coverage == "INDEXED":
        return ResultadoAuto("aprovado", {"verdict": verdict, "coverage": coverage})
    elif "DISCOVERED" in coverage or "CRAWLED" in coverage:
        return ResultadoAuto("atencao", {"verdict": verdict, "coverage": coverage})
    return ResultadoAuto("reprovado", {"verdict": verdict, "coverage": coverage})


def _av_sitemaps_gsc(sitemaps_data: dict | None) -> ResultadoAuto:
    if not sitemaps_data:
        return _SEM_DADOS
    sitemaps = sitemaps_data.get("sitemap", [])
    if not sitemaps:
        return ResultadoAuto("reprovado", {"sitemaps_registrados": 0})

    total = len(sitemaps)
    com_erro = sum(1 for s in sitemaps if s.get("errors", 0) > 0)
    ev = {
        "sitemaps_registrados": total,
        "com_erro": com_erro,
        "detalhes": [
            {"path": s.get("path", ""), "errors": s.get("errors", 0), "warnings": s.get("warnings", 0)}
            for s in sitemaps[:5]
        ],
    }
    if com_erro == 0:
        return ResultadoAuto("aprovado", ev)
    return ResultadoAuto("atencao", ev)


def _av_sitemap_listado_gsc(sitemaps_data: dict | None) -> ResultadoAuto:
    if not sitemaps_data:
        return _SEM_DADOS
    sitemaps = sitemaps_data.get("sitemap", [])
    if sitemaps:
        return ResultadoAuto("aprovado", {"sitemaps_no_gsc": len(sitemaps)})
    return ResultadoAuto("reprovado", {"sitemaps_no_gsc": 0})


def _av_estatisticas_rastreamento(search_data: dict | None) -> ResultadoAuto:
    """Estatísticas de rastreamento — inferidas do searchAnalytics."""
    if not search_data:
        return _SEM_DADOS
    rows = search_data.get("rows", [])
    if not rows:
        return ResultadoAuto("reprovado", {"impressoes": 0, "motivo": "sem_dados_gsc"})
    total_imp = sum(int(r.get("impressions", 0)) for r in rows)
    total_clicks = sum(int(r.get("clicks", 0)) for r in rows)
    ev = {"impressoes": total_imp, "cliques": total_clicks}
    if total_imp > 100:
        return ResultadoAuto("aprovado", ev)
    elif total_imp > 10:
        return ResultadoAuto("atencao", ev)
    return ResultadoAuto("reprovado", ev)


# --- Orquestrador ---

async def avaliar_gsc(dominio: str) -> dict[str, ResultadoAuto]:
    """Executa todas as avaliações GSC para o domínio.

    Requer service account configurado (settings.gsc_service_account_path).
    Sem credenciais → retorna dict vazio (fail-open).
    """
    credenciais = _carregar_credenciais()
    if not credenciais:
        logger.info("gsc_sem_credenciais — pulando avaliacao GSC")
        return {}

    token = await _obter_access_token(credenciais)
    if not token:
        return {}

    site_url = _site_url_gsc(dominio)
    resultados: dict[str, ResultadoAuto] = {}

    # 1. URL Inspection da homepage
    try:
        inspect = await _inspect_url(token, site_url, dominio)
        resultados["google-search-console-acoes-manuais"] = _av_acoes_manuais(inspect)
        resultados["google-search-console-pagina-nao-encontrada"] = _av_pagina_nao_encontrada(inspect)
        resultados["google-search-console-paginas-bloqueadas-por-robots-txt"] = _av_bloqueadas_robots(inspect)
        resultados["google-search-console-paginas-indexadas"] = _av_paginas_indexadas(inspect)
    except Exception:
        logger.warning("gsc_inspect falhou (fail-open)", exc_info=True)

    # 2. Sitemaps registrados no GSC
    try:
        sitemaps_data = await _gsc_get(token, f"/sites/{site_url}/sitemaps")
        resultados["google-search-console-indexacao-de-sitemap"] = _av_sitemaps_gsc(sitemaps_data)
        resultados["sitemap-s-xml-da-pagina-estao-listados-no-gsc"] = _av_sitemap_listado_gsc(sitemaps_data)
    except Exception:
        logger.warning("gsc_sitemaps falhou (fail-open)", exc_info=True)

    # 3. Search Analytics (impressões/cliques como proxy de rastreamento)
    try:
        search_data = await _gsc_post(
            token,
            f"/sites/{site_url}/searchAnalytics/query",
            {"startDate": "2026-06-01", "endDate": "2026-07-01", "dimensions": ["page"], "rowLimit": 1},
        )
        resultados["google-search-console-estatisticas-de-rastreamento"] = _av_estatisticas_rastreamento(search_data)
    except Exception:
        logger.warning("gsc_search_analytics falhou (fail-open)", exc_info=True)

    logger.info("gsc_concluido dominio=%s avaliados=%d", dominio, len(resultados))
    return resultados

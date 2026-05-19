import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.scraper import ScrapeResult, scrape_url

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, ScrapeResult], Awaitable[None]]


@dataclass
class ExtracaoLote:
    resultados: list[ScrapeResult]
    n_sucessos: int = 0
    n_falhas: int = 0


async def extrair_pilar(url: str | None, markdown: str | None) -> ScrapeResult:
    if markdown:
        from app.core.scraper import _estimate_tokens, _normalizar_url

        url_canonica = _normalizar_url(url) if url else ""
        return ScrapeResult(
            url=url or "",
            url_canonica=url_canonica,
            conteudo_md=markdown.strip(),
            titulo="Conteudo pilar (fornecido)",
            tokens=_estimate_tokens(markdown),
        )

    if not url:
        return ScrapeResult(url="", falhou=True, erro="URL ou markdown do pilar e obrigatorio")

    return await scrape_url(url)


async def extrair_candidatas(
    urls: list[str],
    on_progress: ProgressCallback | None = None,
) -> ExtracaoLote:
    resultado = ExtracaoLote(resultados=[None] * len(urls))  # type: ignore[arg-type]
    total = len(urls)
    progresso_lock = asyncio.Lock()
    contador = {"feito": 0}

    async def _fetch(idx: int, url: str):
        try:
            r = await scrape_url(url)
        except Exception as e:
            logger.error("extrair_candidatas: %s -> EXCEPTION: %s", url, e)
            r = ScrapeResult(url=url, falhou=True, erro=str(e))

        if r.falhou:
            logger.error("extrair_candidatas: %s -> FALHOU: %s", url, r.erro)
            resultado.n_falhas += 1
        else:
            logger.info("extrair_candidatas: %s -> OK (%d tokens)", url, r.tokens)
            resultado.n_sucessos += 1
        resultado.resultados[idx] = r

        if on_progress:
            async with progresso_lock:
                contador["feito"] += 1
                feito = contador["feito"]
            try:
                await on_progress(feito, total, r)
            except Exception as e:
                logger.debug("on_progress callback falhou: %s", e)

    await asyncio.gather(*(_fetch(i, u) for i, u in enumerate(urls)), return_exceptions=False)
    return resultado

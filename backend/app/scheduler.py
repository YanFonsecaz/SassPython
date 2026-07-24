import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def job_renovar_ciclos():
    logger.info("Iniciando renovacao de ciclos de creditos")
    async with async_session_factory() as session:
        try:
            from app.services.credito_service import renovar_ciclos_vencidos

            count = await renovar_ciclos_vencidos(session)
            await session.commit()
            logger.info("Renovados %d ciclos de creditos", count)
        except Exception as e:
            await session.rollback()
            logger.error("Erro na renovacao de ciclos: %s", e)


async def job_limpar_checkpoints():
    logger.info("Iniciando limpeza de checkpoints antigos")
    async with async_session_factory() as session:
        try:
            from sqlalchemy import and_, delete

            from app.models.execucao_ferramenta import ExecucaoFerramenta

            cutoff = datetime.now(UTC) - timedelta(days=7)
            await session.execute(
                delete(ExecucaoFerramenta).where(
                    and_(
                        ExecucaoFerramenta.status.in_(["concluida", "falhou", "cancelada"]),
                        ExecucaoFerramenta.concluida_em < cutoff,
                    )
                )
            )
            await session.commit()
            logger.info("Checkpoints antigos limpos")
        except Exception as e:
            await session.rollback()
            logger.error("Erro na limpeza de checkpoints: %s", e)


async def job_cancelar_abandonadas():
    logger.info("Iniciando cancelamento de execucoes abandonadas")
    async with async_session_factory() as session:
        try:
            from sqlalchemy import select

            from app.models.execucao_ferramenta import ExecucaoFerramenta

            cutoff = datetime.now(UTC) - timedelta(days=30)
            resultado = await session.execute(
                select(ExecucaoFerramenta).where(
                    ExecucaoFerramenta.status.in_(["aguardando_aprovacao", "aguardando_revisao"]),
                    ExecucaoFerramenta.criado_em < cutoff,
                )
            )
            execucoes = resultado.scalars().all()
            for exe in execucoes:
                exe.status = "cancelada"
                exe.creditos_cobrados = 0
                exe.concluida_em = datetime.now(UTC)
            await session.commit()
            logger.info("Canceladas %d execucoes abandonadas", len(execucoes))
        except Exception as e:
            await session.rollback()
            logger.error("Erro no cancelamento de abandonadas: %s", e)


async def job_limpar_versoes():
    logger.info("Iniciando limpeza de versoes antigas")
    async with async_session_factory() as session:
        try:
            from sqlalchemy import and_, delete, select

            from app.models.execucao_ferramenta import ExecucaoFerramenta
            from app.models.versao_artigo import VersaoArtigo

            cutoff = datetime.now(UTC) - timedelta(days=30)
            await session.execute(
                delete(VersaoArtigo).where(
                    VersaoArtigo.execucao_id.in_(
                        select(ExecucaoFerramenta.id).where(
                            and_(
                                ExecucaoFerramenta.status == "concluida",
                                ExecucaoFerramenta.concluida_em < cutoff,
                            )
                        )
                    )
                )
            )
            await session.commit()
            logger.info("Versoes antigas limpas")
        except Exception as e:
            await session.rollback()
            logger.error("Erro na limpeza de versoes: %s", e)


async def job_limpar_cache():
    logger.info("Iniciando limpeza de cache expirado")
    async with async_session_factory() as session:
        try:
            from sqlalchemy import delete

            from app.models.pesquisa_cache import PesquisaCache

            now = datetime.now(UTC)
            await session.execute(delete(PesquisaCache).where(PesquisaCache.expira_em < now))
            await session.commit()
            logger.info("Cache expirado limpo")
        except Exception as e:
            await session.rollback()
            logger.error("Erro na limpeza de cache: %s", e)


async def job_limpar_embeddings_cache():
    """SPEC_Inlinks_Cache_Duravel_Embeddings: limpeza semanal por uso da L2.

    Remove linhas não usadas há mais que embeddings_cache_ttl_dias e, se a
    tabela exceder embeddings_cache_max_linhas, apaga as mais antigas por
    usado_em até voltar ao teto.
    """
    logger.info("Iniciando limpeza do embeddings_cache (L2)")
    async with async_session_factory() as session:
        try:
            from sqlalchemy import text

            from app.config import settings

            # 1) TTL por uso.
            await session.execute(
                text(
                    "DELETE FROM embeddings_cache "
                    "WHERE usado_em < NOW() - make_interval(days => :dias)"
                ),
                {"dias": settings.embeddings_cache_ttl_dias},
            )

            # 2) Teto de linhas — remove as mais antigas (por usado_em) acima do teto.
            await session.execute(
                text(
                    """
                    DELETE FROM embeddings_cache
                    WHERE chave IN (
                        SELECT chave FROM embeddings_cache
                        ORDER BY usado_em ASC
                        OFFSET :max_linhas
                    )
                    """
                ),
                {"max_linhas": settings.embeddings_cache_max_linhas},
            )

            await session.commit()
            logger.info("embeddings_cache limpo")
        except Exception as e:
            await session.rollback()
            # Tabela pode não existir ainda (pré-migration) — loga em debug, não é erro fatal.
            logger.debug("Limpeza do embeddings_cache pulada: %s", e)


async def job_sanear_execucoes_orfas():
    """SPEC_Saneamento_Execucoes_Orfas: marca como ``falhou`` execuções presas
    em ``status='executando'`` após o prazo (worker morreu/OOM/deploy).

    Margem de 10 min sobre ``timeout_em`` para não competir com worker vivo que
    ainda vai estourar o próprio timeout. Libera a reserva de créditos via
    ``_obter_reserva_estimada`` (mesma conta usada por ``finalizar_falha``) e é
    idempotente: depois de virar ``falhou``, o WHERE não match mais; dentro da
    transação, re-check do status + ``with_for_update(skip_locked=True)`` para
    concorrência.
    """
    logger.info("Iniciando saneamento de execucoes orfas")
    async with async_session_factory() as session:
        try:
            from sqlalchemy import select

            from app.models.execucao_ferramenta import ExecucaoFerramenta
            from app.services import credito_service
            from app.services.ferramenta_service import _obter_reserva_estimada

            margem = datetime.now(UTC) - timedelta(minutes=10)
            res = await session.execute(
                select(ExecucaoFerramenta)
                .where(
                    ExecucaoFerramenta.status == "executando",
                    ExecucaoFerramenta.timeout_em < margem,
                )
                .with_for_update(skip_locked=True)
            )
            execucoes = res.scalars().all()
            n_saneadas = 0
            for exe in execucoes:
                # Re-check idempotente dentro da transação (segurança extra).
                if exe.status != "executando":
                    continue
                exe.status = "falhou"
                exe.erro_msg = "Execução interrompida (worker reiniciado ou falha inesperada)"
                exe.concluida_em = datetime.now(UTC)
                reserva = _obter_reserva_estimada(exe.ferramenta or "", exe)
                if reserva > 0:
                    try:
                        await credito_service.liberar_reserva(
                            session, str(exe.usuario_id), reserva
                        )
                    except Exception as exc:
                        # Fail-open na devolução: ainda assim marca como falhou
                        # para destravar o usuário; loga para acompanhamento.
                        logger.warning(
                            "Falha ao liberar reserva da execucao %s: %s",
                            exe.id, exc,
                        )
                n_saneadas += 1
            await session.commit()
            if n_saneadas:
                logger.info("Saneadas %d execucoes orfas", n_saneadas)
            else:
                logger.debug("Nenhuma execucao orfa encontrada")
        except Exception as e:
            await session.rollback()
            logger.error("Erro no saneamento de execucoes orfas: %s", e)


def criar_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(job_renovar_ciclos, "cron", hour=0, minute=0, id="renovar_ciclos")
    scheduler.add_job(job_limpar_checkpoints, "cron", hour=3, minute=0, id="limpar_checkpoints")
    scheduler.add_job(job_cancelar_abandonadas, "cron", day_of_week="mon", hour=2, minute=0, id="cancelar_abandonadas")
    scheduler.add_job(job_limpar_versoes, "cron", hour=4, minute=0, id="limpar_versoes")
    scheduler.add_job(job_limpar_cache, "cron", hour=5, minute=0, id="limpar_cache")
    scheduler.add_job(
        job_limpar_embeddings_cache,
        "cron",
        day_of_week="mon",
        hour=6,
        minute=0,
        id="limpar_embeddings_cache",
    )
    # SPEC_Saneamento_Execucoes_Orfas: horário, margem 10 min cobre latência.
    scheduler.add_job(
        job_sanear_execucoes_orfas,
        "cron",
        minute=15,
        id="sanear_execucoes_orfas",
    )

    return scheduler

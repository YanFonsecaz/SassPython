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


def criar_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(job_renovar_ciclos, "cron", hour=0, minute=0, id="renovar_ciclos")
    scheduler.add_job(job_limpar_checkpoints, "cron", hour=3, minute=0, id="limpar_checkpoints")
    scheduler.add_job(job_cancelar_abandonadas, "cron", day_of_week="mon", hour=2, minute=0, id="cancelar_abandonadas")
    scheduler.add_job(job_limpar_versoes, "cron", hour=4, minute=0, id="limpar_versoes")
    scheduler.add_job(job_limpar_cache, "cron", hour=5, minute=0, id="limpar_cache")

    return scheduler

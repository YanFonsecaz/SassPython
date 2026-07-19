"""E2E SEOTEC Onda 1: upload de pacote fixture -> workflow -> score persistido.

Pré-requisito: Postgres dev de pé + `alembic upgrade head` + 1 usuário existente.
Roda o workflow inline (sem worker ARQ) chamando executar_auditoria_seotec.
"""
import asyncio
import logging
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, text

from app.config import settings
from app.db.session import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _usuario_qualquer() -> str:
    async with async_session_factory() as s:
        uid = (await s.execute(text("SELECT id FROM usuarios LIMIT 1"))).scalar()
        if uid:
            return str(uid)
        uid = str(uuid.uuid4())
        await s.execute(
            text("INSERT INTO usuarios (id, email, nome, senha_hash, email_verificado, mfa_ativo, ativo) "
                 "VALUES (:id, :email, 'Usuário E2E SEOTEC', 'x', true, false, true)"),
            {"id": uid, "email": f"e2e-seotec-{uid[:8]}@teste.local"},
        )
        await s.commit()
        return str(uid)


async def preparar(usuario_id: str) -> tuple[str, str, str, str]:
    from app.models.execucao_ferramenta import ExecucaoFerramenta
    from app.models.seo_auditoria import SeoAuditoria
    from app.models.seo_crawl import SeoCrawl

    async with async_session_factory() as s:
        cliente_id = str(uuid.uuid4())
        await s.execute(
            text("INSERT INTO clientes (id, usuario_id, nome, site_url, config_json, ativo) "
                 "VALUES (:id, :uid, 'Cliente E2E SEOTEC', NULL, '{}', true)"),
            {"id": cliente_id, "uid": usuario_id},
        )
        auditoria = SeoAuditoria(usuario_id=usuario_id, cliente_id=cliente_id,
                                 dominio="https://exemplo.com.br")
        s.add(auditoria)
        await s.flush()
        execucao = ExecucaoFerramenta(
            usuario_id=usuario_id, cliente_id=cliente_id,
            ferramenta="auditoria_seo_tecnico", status="enfileirado",
            entrada_json={"auditoria_id": str(auditoria.id), "fase_destino": "before"},
            # thread_id e timeout_em são NOT NULL em ExecucaoFerramenta (ver
            # app/models/execucao_ferramenta.py) — não constavam no brief, ajustado
            # seguindo o padrão de app/routers/ferramentas_cwv_auditoria.py.
            thread_id=str(uuid.uuid4()),
            timeout_em=datetime.now(UTC) + timedelta(seconds=settings.workflow_timeout_segundos),
        )
        s.add(execucao)
        await s.flush()
        crawl = SeoCrawl(auditoria_id=auditoria.id, execucao_id=execucao.id,
                         fase_destino="before", origem="upload", schema_version=1)
        s.add(crawl)
        await s.flush()
        ids = (str(auditoria.id), str(crawl.id), str(execucao.id), cliente_id)
        await s.commit()
        return ids


def _pacote_fixture() -> bytes:
    from tests.unit.helpers_seotec import montar_pacote_zip

    return montar_pacote_zip({
        "page_titles": [
            {"address": "https://exemplo.com.br/", "title": "", "title_length": 0, "ocorrencias": 1},
            {"address": "https://exemplo.com.br/sobre", "title": "Sobre nós", "title_length": 9, "ocorrencias": 1},
        ],
        "meta_description": [
            {"address": "https://exemplo.com.br/", "meta_description": "x" * 200,
             "meta_description_length": 200, "ocorrencias": 1},
        ],
        "h1": [
            {"address": "https://exemplo.com.br/", "h1": "Home", "ocorrencias": 1},
        ],
        "internal": [
            {"address": "https://exemplo.com.br/", "status_code": 200, "crawl_depth": 0,
             "word_count": 800, "response_time": 0.4},
        ],
        "response_codes": [
            {"address": "https://exemplo.com.br/quebrada", "status_code": 404},
        ],
        "robots": [{"existe": True, "status_code": 200, "sitemaps_declarados": ["https://exemplo.com.br/sitemap.xml"]}],
        "sitemaps": [{"sitemap_url": "https://exemplo.com.br/sitemap.xml", "status_code": 200, "total_urls": 10}],
        "images": [],
        "redirects": [],
    })


async def rodar() -> None:
    from app.agents.seotec.workflow import executar_auditoria_seotec

    usuario_id = await _usuario_qualquer()
    auditoria_id, crawl_id, execucao_id, cliente_id = await preparar(usuario_id)

    # garante saldo reservado para o débito do workflow
    # (__tablename__ real de ContaCredito é "contas_creditos" — confirmado em
    # app/models/conta_credito.py; usamos o service ORM, sem UPDATE cru)
    async with async_session_factory() as s:
        from app.services import credito_service
        conta = await credito_service.buscar_ou_criar_conta(s, usuario_id)
        conta.saldo_plano += 100
        await credito_service.reservar_creditos(s, usuario_id, 30)
        await s.commit()

    Path(settings.seotec_upload_dir).mkdir(parents=True, exist_ok=True)
    (Path(settings.seotec_upload_dir) / f"{crawl_id}.zip").write_bytes(_pacote_fixture())

    await executar_auditoria_seotec(execucao_id, crawl_id)

    from app.models.seo_auditoria import SeoAuditoria
    from app.models.seo_crawl import SeoCrawl
    from app.models.seo_item_resultado import SeoItemResultado

    async with async_session_factory() as s:
        auditoria = await s.get(SeoAuditoria, auditoria_id)
        crawl = await s.get(SeoCrawl, crawl_id)
        itens = list((await s.execute(
            select(SeoItemResultado).where(SeoItemResultado.auditoria_id == auditoria_id)
        )).scalars())

        assert crawl.status == "processado", crawl.erro_msg
        assert auditoria.score_antes is not None and 0 < float(auditoria.score_antes) < 100
        assert len(itens) == 124
        por_slug = {i.item_slug: i for i in itens}
        assert por_slug["title-tag-ausente-ou-vazia"].status_antes == "reprovado"
        assert por_slug["ha-um-robots-txt-configurado-corretamente-no-site"].status_antes == "aprovado"
        assert por_slug["erros-no-lado-do-cliente-40x"].status_antes == "reprovado"
        assert por_slug["redirecionamentos-302"].status_antes == "na"
        assert por_slug["conteudo-duplicado"].status_antes == "sem_dados"
        assert por_slug["analise-de-logfile"].modo == "manual"
        ev = por_slug["title-tag-ausente-ou-vazia"].evidencias_json
        assert ev["total_afetadas"] == 1 and ev["amostra"]

    # cleanup
    # `confirmar_debito` grava uma linha em transacoes_creditos com FK para
    # execucoes_ferramentas.id (sem ondelete) — precisa ser removida antes,
    # senão o DELETE de execucoes_ferramentas viola a FK
    # (transacoes_creditos_execucao_id_fkey).
    async with async_session_factory() as s:
        await s.execute(text("DELETE FROM transacoes_creditos WHERE execucao_id = :id"), {"id": execucao_id})
        await s.execute(text("DELETE FROM seo_auditoria WHERE id = :id"), {"id": auditoria_id})
        await s.execute(text("DELETE FROM execucoes_ferramentas WHERE id = :id"), {"id": execucao_id})
        await s.execute(text("DELETE FROM clientes WHERE id = :id"), {"id": cliente_id})
        await s.commit()
    logger.info("[OK] E2E SEOTEC completo — score_antes=%s", auditoria.score_antes)


def test_e2e_seotec():
    asyncio.run(rodar())

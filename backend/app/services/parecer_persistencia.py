import logging

from sqlalchemy import select

from app.models.parecer import Parecer

logger = logging.getLogger(__name__)


async def criar_parecer(
    session,
    *,
    execucao_id: str,
    cliente_id: str,
    usuario_id: str,
    cliente_nome: str,
    estrutura: dict,
    parecer_html: str,
    n_imagens: int,
    modelo: str,
) -> Parecer:
    escopo_linha = estrutura.get("escopo_linha")
    p = Parecer(
        execucao_id=execucao_id,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        cliente_nome=cliente_nome,
        titulo=estrutura.get("titulo", ""),
        subtitulo=estrutura.get("subtitulo"),
        site=escopo_linha,  # linha de escopo (exibida na listagem "Meus Pareceres")
        plataforma=None,
        meta_json={"subtitulo": estrutura.get("subtitulo"), "escopo_linha": escopo_linha},
        estrutura_json=estrutura,
        parecer_html=parecer_html,
        n_imagens=n_imagens,
        modelo=modelo,
        status="concluido",
    )
    session.add(p)
    await session.flush()
    return p


async def atualizar_html(session, parecer_id: str, usuario_id: str, html: str) -> Parecer | None:
    res = await session.execute(
        select(Parecer).where(Parecer.id == parecer_id, Parecer.usuario_id == usuario_id)
    )
    p = res.scalar_one_or_none()
    if p:
        p.parecer_html = html
    return p


async def buscar_parecer(session, parecer_id: str, usuario_id: str) -> Parecer | None:
    res = await session.execute(
        select(Parecer).where(Parecer.id == parecer_id, Parecer.usuario_id == usuario_id)
    )
    return res.scalar_one_or_none()


async def buscar_parecer_por_execucao(session, execucao_id: str) -> Parecer | None:
    res = await session.execute(
        select(Parecer).where(Parecer.execucao_id == execucao_id)
    )
    return res.scalar_one_or_none()


async def listar_pareceres(
    session,
    usuario_id: str,
    cliente_id: str | None = None,
    limite: int = 50,
    offset: int = 0,
) -> list[Parecer]:
    q = select(Parecer).where(Parecer.usuario_id == usuario_id)
    if cliente_id:
        q = q.where(Parecer.cliente_id == cliente_id)
    q = q.order_by(Parecer.criado_em.desc()).limit(limite).offset(offset)
    res = await session.execute(q)
    return list(res.scalars().all())


def parecer_to_dict(p: Parecer) -> dict:
    return {
        "id": str(p.id),
        "execucao_id": str(p.execucao_id),
        "cliente_id": str(p.cliente_id),
        "usuario_id": str(p.usuario_id),
        "titulo": p.titulo,
        "subtitulo": p.subtitulo,
        "site": p.site,
        "plataforma": p.plataforma,
        "cliente_nome": p.cliente_nome,
        "meta": p.meta_json,
        "estrutura": p.estrutura_json,
        "parecer_html": p.parecer_html,
        "n_imagens": p.n_imagens,
        "modelo": p.modelo,
        "status": p.status,
        "criado_em": p.criado_em.isoformat() if p.criado_em else "",
        "atualizado_em": p.atualizado_em.isoformat() if p.atualizado_em else "",
    }


def parecer_resumo_dict(p: Parecer) -> dict:
    return {
        "id": str(p.id),
        "execucao_id": str(p.execucao_id),
        "cliente_id": str(p.cliente_id),
        "cliente_nome": p.cliente_nome,
        "titulo": p.titulo,
        "subtitulo": p.subtitulo,
        "site": p.site,
        "plataforma": p.plataforma,
        "n_imagens": p.n_imagens,
        "status": p.status,
        "criado_em": p.criado_em.isoformat() if p.criado_em else "",
    }

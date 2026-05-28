"""Auditoria de gaps da KB CWV.

Roda contra o DB para gerar relatorio priorizado de audits faltantes.

Uso:
    python -m scripts.cwv_kb_audit                  # imprime no stdout
    python -m scripts.cwv_kb_audit > relatorio.md   # salva em Markdown
"""
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.cwv_problema import CwvProblema
from app.services.cwv_kb import (
    AUDITS_IGNORADOS,
    listar_kb_codigos,
    mapeamento_audit_kb,
)


async def main() -> None:
    diretos = mapeamento_audit_kb()
    kb_codigos = {c["codigo"] for c in listar_kb_codigos()}

    desde = datetime.now(timezone.utc) - timedelta(days=90)
    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with async_session_factory() as s:
        result = await s.execute(
            select(CwvProblema.contexto_especifico, CwvProblema.audit_id)
            .where(CwvProblema.kb_codigo.is_(None))
            .where(CwvProblema.criado_em >= desde)
        )
        rows = result.all()

    contador_audit: Counter[str] = Counter()
    titulos: dict[str, str] = {}
    for ctx, audit_id in rows:
        aid = audit_id or (ctx.get("audit_id") if ctx else None)
        if not aid:
            continue
        contador_audit[aid] += 1
        if aid not in titulos and ctx and ctx.get("title"):
            titulos[aid] = ctx["title"]

    print(f"# Auditoria de gaps da KB CWV — {hoje}")
    print()
    print(f"- KB atual: **{len(kb_codigos)}** codigos")
    print(f"- Audits mapeados (fast-path): **{len(diretos)}**")
    print(f"- AUDITS_IGNORADOS (filtrados antes do LLM): **{len(AUDITS_IGNORADOS)}**")
    print("- Janela analisada: ultimos 90 dias")
    print()

    print("## Audits sem mapeamento KB (priorizar entrada nova)")
    print()
    if not contador_audit:
        print("Nenhum audit sem mapeamento nos ultimos 90 dias. KB esta saturada.")
    else:
        print("| audit_id | ocorrencias | titulo Lighthouse |")
        print("|---|---:|---|")
        for aid, n in contador_audit.most_common(30):
            titulo = titulos.get(aid, "-")[:80]
            print(f"| `{aid}` | {n} | {titulo} |")
    print()

    async with async_session_factory() as s:
        result = await s.execute(
            select(CwvProblema.kb_codigo)
            .where(CwvProblema.kb_codigo.isnot(None))
            .where(CwvProblema.criado_em >= desde)
        )
        usados = {r for r in result.scalars().all()}

    nao_usados = sorted(kb_codigos - usados)
    print("## Codigos da KB sem ocorrencia nos ultimos 90 dias")
    print()
    if not nao_usados:
        print("Todos os codigos da KB foram usados.")
    else:
        print("Estes codigos podem estar mal mapeados (`audits_lighthouse` incorretos) ou cobrindo audits raros:")
        print()
        for c in nao_usados:
            print(f"- `{c}`")


if __name__ == "__main__":
    asyncio.run(main())

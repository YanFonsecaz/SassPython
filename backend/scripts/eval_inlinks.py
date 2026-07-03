"""Harness de avaliação dos inlinks contra o golden set rotulado.

Roda o pipeline real (enriquecedor → rerank → juiz/inseridor → revisor) sobre
fixtures com conteúdo gravado (sem rede/scraper/DB) e compara o status final de
cada candidata com o rótulo esperado.

Uso:
    python -m scripts.eval_inlinks                 # todos os casos, LLM real
    python -m scripts.eval_inlinks --caso cnae_agilize
    python -m scripts.eval_inlinks --llm cache     # record/replay (barato, determinístico)

Gate de merge (SPEC_Inlinks_Eval_Golden_Set):
    - >=70% dos `deve_aplicar` terminam `aplicado`
    - 0 `nao_linkar` terminam `aplicado`
    - 0 alucinações (todo trecho aplicado existe no texto ORIGINAL)
    - 0 itens não-aplicados sem motivo
"""
import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

FIXTURES_DIR = BACKEND_DIR / "tests" / "eval" / "fixtures" / "inlinks_golden"
CACHE_DIR = BACKEND_DIR / "tests" / "eval" / "cache"

PISO_RUIDO = 0.25  # espelha _PISO_RUIDO_SEMANTICO do workflow


def instalar_cache_llm() -> None:
    """Record/replay de LLM structured + embeddings, keyed por sha256 do prompt."""
    from app.agents.base import BaseAgent
    from app.core import embeddings as emb_mod

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    orig_structured = BaseAgent.invoke_structured

    async def cached_structured(self, prompt, schema):  # type: ignore[no-untyped-def]
        key = hashlib.sha256(f"{schema.__name__}:{prompt}".encode()).hexdigest()
        f = CACHE_DIR / f"{key}.llm.json"
        if f.exists():
            return schema.model_validate(json.loads(f.read_text()))
        result = await orig_structured(self, prompt, schema)
        f.write_text(result.model_dump_json())
        return result

    BaseAgent.invoke_structured = cached_structured  # type: ignore[method-assign]

    orig_batch = emb_mod.gerar_embeddings_batch

    async def cached_batch(textos, usuario_id):  # type: ignore[no-untyped-def]
        out: list[Any] = [None] * len(textos)
        faltantes: list[str] = []
        idxs: list[int] = []
        for i, t in enumerate(textos):
            k = hashlib.sha256(f"emb:{t}".encode()).hexdigest()
            f = CACHE_DIR / f"{k}.emb.json"
            if f.exists():
                out[i] = json.loads(f.read_text())
            else:
                faltantes.append(t)
                idxs.append(i)
        if faltantes:
            novos = await orig_batch(faltantes, usuario_id)
            for t, e, i in zip(faltantes, novos, idxs, strict=False):
                if e is not None:
                    k = hashlib.sha256(f"emb:{t}".encode()).hexdigest()
                    (CACHE_DIR / f"{k}.emb.json").write_text(json.dumps(e))
                out[i] = e
        return out

    emb_mod.gerar_embeddings_batch = cached_batch  # type: ignore[assignment]
    # módulos que importaram a função por nome
    from app.agents.inlinks import inseridor as _ins

    _ins.gerar_embeddings_batch = cached_batch  # type: ignore[assignment]


def _find_trecho(paragrafos: list[str], trecho: str) -> bool:
    from app.agents.inlinks.inseridor import _find_trecho_in_paragrafo

    return any(_find_trecho_in_paragrafo(p, trecho) is not None for p in paragrafos)


async def _montar_candidato(c: dict[str, Any], emb: Any, pilar_emb: Any, usuario_id: str) -> dict[str, Any]:
    from app.agents.inlinks.enriquecedor_metadados import enriquecer_metadados
    from app.core.embeddings import cosine_seguro

    md = await enriquecer_metadados(c["conteudo_md"], c.get("titulo", ""), usuario_id)
    score = cosine_seguro(pilar_emb, emb) if (pilar_emb is not None and emb is not None) else 0.0
    return {
        "url": c["url"],
        "url_canonica": c["url"],
        "titulo": c.get("titulo", ""),
        "resumo": c.get("resumo") or md.resumo,
        "categoria": md.categoria,
        "palavras_chave": c.get("palavras_chave") or md.palavras_chave,
        "score_semantico": float(score),
    }


async def rodar_caso_receber(caso: dict[str, Any], usuario_id: str) -> list[dict[str, Any]]:
    from app.agents.inlinks.inseridor import inserir_inlinks
    from app.agents.inlinks.reranker import rerank_candidatos
    from app.agents.inlinks.revisor import revisar_inlinks
    from app.core import embeddings as emb_mod

    pilar = caso["pilar"]
    candidatas = caso["candidatas"]
    textos = [pilar["conteudo_md"][:8000]] + [c["conteudo_md"][:8000] for c in candidatas]
    embs = await emb_mod.gerar_embeddings_batch(textos, usuario_id)
    pilar_emb = embs[0]

    cands = [
        await _montar_candidato(c, e, pilar_emb, usuario_id)
        for c, e in zip(candidatas, embs[1:], strict=False)
    ]

    reranked = await rerank_candidatos(
        pilar["titulo"], pilar["conteudo_md"][:2000], {}, cands, usuario_id
    )
    filtradas = [c for c in reranked if c.get("score_semantico", 0) >= PISO_RUIDO]
    cortadas = [c for c in reranked if c.get("score_semantico", 0) < PISO_RUIDO]

    params = caso.get("params", {})
    texto, inseridos = await inserir_inlinks(
        pilar["conteudo_md"], filtradas, usuario_id,
        max_inlinks=params.get("max_inlinks", 8),
        ancoras_preferidas=params.get("ancoras_preferidas") or None,
        permitir_cta_fallback=params.get("permitir_cta_fallback", False),
        objetivo_linkagem=params.get("objetivo_linkagem"),
    )
    dicts = [asdict(i) for i in inseridos]
    dicts = await revisar_inlinks(pilar["conteudo_md"], texto, dicts, usuario_id)

    itens = []
    paragrafos_originais = pilar["conteudo_md"].split("\n\n")
    for d in dicts:
        alucinou = bool(
            d.get("status") == "aplicado"
            and d.get("trecho_original")
            and not _find_trecho(paragrafos_originais, d["trecho_original"])
        )
        itens.append({
            "url": d["url_destino"],
            "status": d.get("status", "?"),
            "anchor": d.get("anchor_text", ""),
            "motivo": d.get("motivo_rejeicao") or d.get("motivo_sugestao") or d.get("motivo_contexto") or "",
            "alucinou": alucinou,
            "confianca": d.get("confianca"),
            "categoria_match": d.get("categoria_match"),
        })
    for c in cortadas:
        itens.append({
            "url": c["url"], "status": "cortada_piso_ruido", "anchor": "",
            "motivo": f"cosine {c.get('score_semantico', 0):.2f} < {PISO_RUIDO}", "alucinou": False,
        })
    return itens


async def rodar_caso_distribuir(caso: dict[str, Any], usuario_id: str) -> list[dict[str, Any]]:
    from app.agents.inlinks.inseridor import inserir_inlinks
    from app.core import embeddings as emb_mod

    alvo = caso["alvo"]
    params = caso.get("params", {})
    itens = []
    for c in caso["candidatas"]:
        embs = await emb_mod.gerar_embeddings_batch(
            [alvo["conteudo_md"][:8000], c["conteudo_md"][:8000]], usuario_id
        )
        score = emb_mod.cosine_seguro(embs[0], embs[1]) if all(e is not None for e in embs) else 0.0
        candidato_alvo = {
            "url": alvo["url"],
            "url_canonica": alvo["url"],
            "url_destino": alvo["url"],
            "titulo": alvo.get("titulo", ""),
            "resumo": alvo.get("resumo", ""),
            "palavras_chave": alvo.get("palavras_chave", []),
            "categoria": "",
            "score_semantico": float(score),
            "score_contexto": float(score),
            "score_total": float(score),
        }
        _texto, inseridos = await inserir_inlinks(
            c["conteudo_md"], [candidato_alvo], usuario_id,
            max_inlinks=params.get("max_inlinks_por_candidata", 1),
            ancoras_preferidas=params.get("ancoras_preferidas") or None,
            permitir_cta_fallback=params.get("permitir_cta_fallback", True),
            objetivo_linkagem=params.get("objetivo_linkagem"),
        )
        if not inseridos:
            itens.append({"url": c["url"], "status": "sem_match", "anchor": "",
                          "motivo": "Inseridor nao encontrou trecho", "alucinou": False})
            continue
        il = inseridos[0]
        status = "sem_match" if il.status == "rejeitado" else il.status
        paragrafos = c["conteudo_md"].split("\n\n")
        alucinou = bool(
            status == "aplicado" and il.trecho_original
            and not _find_trecho(paragrafos, il.trecho_original)
        )
        itens.append({
            "url": c["url"], "status": status, "anchor": il.anchor_text,
            "motivo": il.motivo_rejeicao or il.motivo_sugestao or il.motivo_contexto or "",
            "alucinou": alucinou,
            "confianca": il.confianca,
            "categoria_match": il.categoria_match,
        })
    return itens


def avaliar(caso: dict[str, Any], itens: list[dict[str, Any]]) -> dict[str, Any]:
    rotulos: dict[str, str] = caso.get("rotulos", {})
    por_url = {i["url"]: i for i in itens}
    resultado = {
        "caso": caso["nome"],
        "deve_aplicar_ok": 0, "deve_aplicar_total": 0,
        "nao_linkar_violado": 0, "nao_linkar_total": 0,
        "alucinacoes": sum(1 for i in itens if i["alucinou"]),
        "sem_motivo": sum(1 for i in itens if i["status"] not in ("aplicado",) and not i["motivo"]),
        "detalhes": [],
    }
    for url, rotulo in rotulos.items():
        item = por_url.get(url, {"status": "ausente", "anchor": "", "motivo": ""})
        ok: bool | None = None
        if rotulo == "deve_aplicar":
            resultado["deve_aplicar_total"] += 1
            ok = item["status"] == "aplicado"
            resultado["deve_aplicar_ok"] += int(ok)
        elif rotulo == "nao_linkar":
            resultado["nao_linkar_total"] += 1
            violado = item["status"] == "aplicado"
            resultado["nao_linkar_violado"] += int(violado)
            ok = not violado
        resultado["detalhes"].append({
            "url": url.rsplit("/", 2)[-2:], "rotulo": rotulo,
            "status": item["status"], "anchor": item["anchor"],
            "motivo": item["motivo"][:110], "ok": ok,
        })
    return resultado


def _imprimir_distribuicao_confianca(itens: list[dict[str, Any]]) -> None:
    """Histograma de confiança por status — calibra os thresholds das badges."""
    buckets = {"alta (≥0.85)": 0, "boa (0.70-0.85)": 0, "baixa (<0.70)": 0, "sem confiança": 0}
    por_status: dict[str, dict[str, int]] = {}
    for it in itens:
        c = it.get("confianca")
        if it.get("status") != "aplicado":
            continue
        chave = (
            "alta (≥0.85)" if isinstance(c, (int, float)) and c >= 0.85
            else "boa (0.70-0.85)" if isinstance(c, (int, float)) and c >= 0.70
            else "baixa (<0.70)" if isinstance(c, (int, float))
            else "sem confiança"
        )
        buckets[chave] += 1
        cat = it.get("categoria_match") or "—"
        por_status.setdefault(cat, {}).setdefault(chave, 0)
        por_status[cat][chave] += 1
    total = sum(buckets.values())
    if not total:
        return
    print("\n=== DISTRIBUIÇÃO DE CONFIANÇA (itens aplicados) ===")
    print(f"  total aplicados: {total}")
    for chave, n in buckets.items():
        pct = (n / total * 100) if total else 0
        print(f"  {chave:<18}: {n:>3} ({pct:5.1f}%)")
    if por_status:
        print("  por categoria_match:")
        for cat, dist in sorted(por_status.items()):
            print(f"    {cat}: {dist}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caso", help="Nome de um caso específico (sem .json)")
    parser.add_argument("--llm", choices=["real", "cache"], default="real")
    args = parser.parse_args()

    if args.llm == "cache":
        instalar_cache_llm()

    arquivos = sorted(FIXTURES_DIR.glob("*.json"))
    if args.caso:
        arquivos = [f for f in arquivos if f.stem == args.caso]
    if not arquivos:
        print(f"Nenhuma fixture encontrada em {FIXTURES_DIR}")
        return 2

    usuario_id = "eval-inlinks"
    agregado = {"deve_ok": 0, "deve_total": 0, "nao_violado": 0, "alucinacoes": 0, "sem_motivo": 0}
    todos_itens: list[dict[str, Any]] = []

    for f in arquivos:
        caso = json.loads(f.read_text())
        print(f"\n=== {caso['nome']} ({caso['ferramenta']}) ===")
        if caso["ferramenta"] == "receber":
            itens = await rodar_caso_receber(caso, usuario_id)
        else:
            itens = await rodar_caso_distribuir(caso, usuario_id)
        todos_itens.extend(itens)
        r = avaliar(caso, itens)
        agregado["deve_ok"] += r["deve_aplicar_ok"]
        agregado["deve_total"] += r["deve_aplicar_total"]
        agregado["nao_violado"] += r["nao_linkar_violado"]
        agregado["alucinacoes"] += r["alucinacoes"]
        agregado["sem_motivo"] += r["sem_motivo"]
        for d in r["detalhes"]:
            marca = "✅" if d["ok"] else ("❌" if d["ok"] is False else "·")
            print(f"  {marca} [{d['rotulo']:>18}] {d['status']:<16} {'/'.join(d['url'])}")
            if d["anchor"]:
                print(f"       âncora: “{d['anchor']}”")
            if d["motivo"]:
                print(f"       motivo: {d['motivo']}")

    # Distribuição de confiança por categoria de badge — calibra os thresholds
    # (0.85 / 0.70) da SPEC_Inlinks_Badges_Pela_Decisao_Do_Juiz.
    _imprimir_distribuicao_confianca(todos_itens)

    recall = (agregado["deve_ok"] / agregado["deve_total"]) if agregado["deve_total"] else 1.0
    print("\n=== GATE DE MERGE ===")
    print(f"deve_aplicar → aplicado: {agregado['deve_ok']}/{agregado['deve_total']} ({recall:.0%}) [exigido ≥70%]")
    print(f"nao_linkar → aplicado (violações): {agregado['nao_violado']} [exigido 0]")
    print(f"alucinações (trecho inexistente): {agregado['alucinacoes']} [exigido 0]")
    print(f"itens sem motivo: {agregado['sem_motivo']} [exigido 0]")

    passou = (
        recall >= 0.70
        and agregado["nao_violado"] == 0
        and agregado["alucinacoes"] == 0
        and agregado["sem_motivo"] == 0
    )
    print("\nRESULTADO:", "✅ PASSOU" if passou else "❌ REPROVADO")
    return 0 if passou else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

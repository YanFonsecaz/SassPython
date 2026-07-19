"""Gera backend/app/data/seotec_checklist/*.yaml a partir da planilha NPBR.

Uso (de backend/): python scripts/seed_seotec_checklist.py [--dry-run]
--dry-run: regenera em memória e compara com os YAMLs commitados (exit 1 se divergir).
Dependência dev: openpyxl (não é dependência de runtime do backend).
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

import yaml

RAIZ_REPO = Path(__file__).parents[2]
DESTINO = Path(__file__).parents[1] / "app" / "data" / "seotec_checklist"
OVERLAY = Path(__file__).parent / "seed_overlay_seotec.yaml"

ARQUIVO_POR_CATEGORIA = {
    "Problemas de Accessibilidade/Encontrabilidade": "acessibilidade",
    "Sitemaps XML da Página": "sitemaps-xml",
    "Arquitetura": "arquitetura",
    "Problemas da URL": "problemas-url",
    "Otimização para Mobile": "mobile",
    "Problemas com Tags na Página/Markup": "tags-markup",
    "Tag <title>": "tag-title",
    "Tag <meta description>": "tag-meta-description",
    "Headings da Página (H1-H6)": "headings",
    "Dados Estruturados": "dados-estruturados",
    "Conteúdo do Corpo Principal": "conteudo-principal",
    "Conteúdo não indexável (ex: uso de JS)": "conteudo-nao-indexavel",
    "Imagens de SEO": "imagens-seo",
    "SEO Internacional": "seo-internacional",
    "Páginas AMP": "paginas-amp",
    "Potenciais Gatilhos de Conteúdo Duplicado": "conteudo-duplicado",
    "Autoridade": "autoridade",
    "Problemas com Links": "problemas-links",
    "Problemas com Google Search Console": "google-search-console",
    "Problemas de Segurança": "seguranca",
    "Propriedade de SEO": "propriedade-seo",
    "Velocidade da Página": "velocidade",
}

PRIORIDADE = {"Low": "low", "Medium": "medium", "High": "high", "Very High": "very-high"}
IMPLEMENTACAO = {"Obrigatória": "obrigatoria", "É bom ter": "bom-ter", "Não é essencial": "nao-essencial"}
RESPONSAVEL = {"Desenvolvedor": "dev", "Time de marketing": "marketing"}


def slugify(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return s.strip("-")


def _achar_planilha() -> Path:
    candidatos = list(RAIZ_REPO.glob("*Auditoria de SEO*NPBR*.xlsx"))
    if not candidatos:
        sys.exit("Planilha NPBR não encontrada na raiz do repo")
    return candidatos[0]


def extrair() -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(_achar_planilha(), data_only=True)
    ws = wb["Checklist"]
    overlay = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    fontes, regras = overlay["fontes"], overlay["regras"]

    categorias: list[dict] = []
    atual: dict | None = None
    for row in ws.iter_rows(min_row=5, max_col=24, values_only=True):
        nome = (row[0] or "").strip() if isinstance(row[0], str) else row[0]
        categoria_x = row[23]
        if not nome:
            continue
        if not categoria_x:  # linha de categoria (coluna X vazia)
            atual = {"categoria": nome, "itens": []}
            categorias.append(atual)
            continue
        if atual is None:
            continue
        slug = slugify(nome)
        if slug not in fontes:
            sys.exit(f"Slug fora do overlay (fontes): {slug}")
        responsaveis = [RESPONSAVEL[p.strip()] for p in str(row[12]).split("/") if p.strip() in RESPONSAVEL]
        item = {
            "slug": slug,
            "nome": nome,
            "peso": int(row[16]),
            "prioridade": PRIORIDADE[str(row[10]).strip()],
            "implementacao": IMPLEMENTACAO[str(row[11]).strip()],
            "responsavel": responsaveis or ["dev"],
            "impacto": {"direto": bool(row[8]), "indireto": bool(row[9])},
            "fonte": fontes[slug],
        }
        if isinstance(row[21], str) and row[21].strip():
            item["descricao"] = row[21].strip()
        if isinstance(row[22], str) and row[22].strip():
            item["importancia"] = row[22].strip()
        if slug in regras:
            item["regra"] = regras[slug]["regra"]
            item["evidencia"] = regras[slug].get("evidencia")
        atual["itens"].append(item)
    return categorias


def render(categorias: list[dict]) -> dict[str, str]:
    saida: dict[str, str] = {}
    for cat in categorias:
        arquivo = ARQUIVO_POR_CATEGORIA[cat["categoria"]]
        saida[f"{arquivo}.yaml"] = yaml.safe_dump(
            cat, allow_unicode=True, sort_keys=False, width=100
        )
    return saida


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    arquivos = render(extrair())
    if args.dry_run:
        divergentes = [
            n for n, conteudo in arquivos.items()
            if not (DESTINO / n).exists() or (DESTINO / n).read_text(encoding="utf-8") != conteudo
        ]
        if divergentes:
            sys.exit(f"Divergência com YAMLs commitados: {divergentes}")
        print("OK: regeneração confere")
        return
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in arquivos.items():
        (DESTINO / nome).write_text(conteudo, encoding="utf-8")
    print(f"{len(arquivos)} arquivos gerados em {DESTINO}")


if __name__ == "__main__":
    main()

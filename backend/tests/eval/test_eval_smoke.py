"""Smoke do harness de avaliação de inlinks (golden set).

Roda com `pytest -m eval` e exige OPENAI_API_KEY (ou cache gravado em
tests/eval/cache). Fora disso, é skipado — CI segue intacto.
"""
import json
from pathlib import Path

import pytest

from app.config import settings

FIXTURES = Path(__file__).parent / "fixtures" / "inlinks_golden"


def test_fixtures_bem_formadas():
    """Sempre roda: as fixtures do golden set são JSON válidos e completos."""
    arquivos = list(FIXTURES.glob("*.json"))
    assert arquivos, "golden set vazio"
    for f in arquivos:
        caso = json.loads(f.read_text())
        assert caso["ferramenta"] in ("receber", "distribuir"), f.name
        assert caso.get("rotulos"), f.name
        conteudos = (
            [caso["pilar"]["conteudo_md"]] if caso["ferramenta"] == "receber" else [caso["alvo"]["conteudo_md"]]
        ) + [c["conteudo_md"] for c in caso["candidatas"]]
        assert all(len(c) > 200 for c in conteudos), f"{f.name}: conteúdo curto demais"
        urls = {c["url"] for c in caso["candidatas"]}
        assert set(caso["rotulos"]).issubset(urls), f"{f.name}: rótulo de URL desconhecida"


@pytest.mark.eval
@pytest.mark.skipif(
    not (settings.openai_api_key and settings.llm_provider == "openai"),
    reason="eval exige OPENAI_API_KEY/provider openai",
)
def test_gate_golden_set():
    """Gate de merge: roda o pipeline real contra o golden set (custa LLM)."""
    import asyncio
    import sys

    from scripts.eval_inlinks import main as eval_main

    argv_bkp = sys.argv
    sys.argv = ["eval_inlinks", "--llm", "cache"]
    try:
        exit_code = asyncio.run(eval_main())
    finally:
        sys.argv = argv_bkp
    assert exit_code == 0, "gate do golden set reprovado — ver saída acima"

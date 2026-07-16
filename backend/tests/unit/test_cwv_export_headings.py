"""Testes dos helpers de rebaixamento de headings (SPEC_CWV_Relatorio_Headings_DOCX)."""
from app.services.cwv_export import _rebaixar_headings_md, _remover_heading_titulo


def test_rebaixar_headings_delta():
    assert _rebaixar_headings_md("## A\n### B", 3) == "### A\n#### B"


def test_rebaixar_headings_sem_heading_intacto():
    assert _rebaixar_headings_md("Texto sem heading", 3) == "Texto sem heading"


def test_rebaixar_headings_cap_h6():
    result = _rebaixar_headings_md("## A\n###### B", 3)
    assert "###### B" in result  # capped at h6


def test_rebaixar_headings_respeita_fence():
    md = "## Título\n\n```\n## código\n```\n\nTexto"
    result = _rebaixar_headings_md(md, 3)
    assert "### Título" in result
    assert "## código" in result  # inside fence, unchanged


def test_rebaixar_headings_delta_zero():
    # Already at base level — no change.
    assert _rebaixar_headings_md("### A", 3) == "### A"


def test_remover_heading_titulo_match():
    result = _remover_heading_titulo("# Sumário Executivo\n\ntexto", "Sumário executivo")
    assert "Sumário Executivo" not in result
    assert "texto" in result


def test_remover_heading_titulo_sem_match():
    result = _remover_heading_titulo("# Visão geral\n\ntexto", "Sumário executivo")
    assert "Visão geral" in result  # unchanged


def test_remover_heading_titulo_acentos():
    result = _remover_heading_titulo("# Diagnóstico Técnico\n\ntexto", "Diagnóstico técnico")
    assert "Diagnóstico" not in result
    assert "texto" in result


def test_rebaixar_headings_tilde_fence():
    """~~~ é fence válido no python-markdown; headings dentro devem sobreviver."""
    md = "## Título\n\n~~~\n## código\n~~~\n\nTexto"
    result = _rebaixar_headings_md(md, 3)
    assert "### Título" in result
    assert "## código" in result  # dentro de ~~~, intacto


def test_remover_heading_titulo_closing_hash():
    """ATX closing hashes (# Título #) devem ser stripped antes de comparar."""
    result = _remover_heading_titulo("# Sumário Executivo #\n\ntexto", "Sumário executivo")
    assert "Sumário Executivo" not in result
    assert "texto" in result


def test_rebaixar_headings_string_vazia():
    assert _rebaixar_headings_md("", 3) == ""


def test_remover_heading_titulo_sem_heading():
    """Texto sem nenhum heading deve retornar intacto."""
    md = "Apenas parágrafos.\n\nSem heading aqui."
    assert _remover_heading_titulo(md, "Sumário executivo") == md


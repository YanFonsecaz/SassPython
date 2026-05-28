import pytest

from app.agents.cwv.documentador import (
    AUDIT_METRICAS,
    CWVDocumentadorAgent,
    _metricas_por_audit,
    _severidade_por_savings,
)


def test_severidade_por_savings_ms():
    assert _severidade_por_savings(1500, None) == 5
    assert _severidade_por_savings(700, None) == 4
    assert _severidade_por_savings(300, None) == 3
    assert _severidade_por_savings(100, None) == 2
    assert _severidade_por_savings(30, None) == 1
    assert _severidade_por_savings(0, None) == 1


def test_severidade_por_savings_bytes():
    assert _severidade_por_savings(None, 300 * 1024) == 5
    assert _severidade_por_savings(None, 150 * 1024) == 4
    assert _severidade_por_savings(None, 60 * 1024) == 3
    assert _severidade_por_savings(None, 30 * 1024) == 2
    assert _severidade_por_savings(None, 10 * 1024) == 1


def test_severidade_por_savings_ms_takes_priority_over_bytes():
    assert _severidade_por_savings(2000, 100) == 5


def test_severidade_por_savings_none():
    assert _severidade_por_savings(None, None) == 1


def test_metricas_por_audit_known():
    assert _metricas_por_audit("largest-contentful-paint") == ["LCP"]
    assert _metricas_por_audit("first-contentful-paint") == ["FCP"]
    assert _metricas_por_audit("total-blocking-time") == ["TBT"]
    assert _metricas_por_audit("cumulative-layout-shift") == ["CLS"]
    assert _metricas_por_audit("interactive") == ["INP", "TBT"]


def test_metricas_por_audit_unknown():
    result = _metricas_por_audit("completely-unknown-audit")
    assert result == ["LCP"]


def test_metricas_por_audit_empty():
    result = _metricas_por_audit("")
    assert result == ["LCP"]


def test_audit_metricas_is_dict():
    assert isinstance(AUDIT_METRICAS, dict)
    assert len(AUDIT_METRICAS) >= 20


@pytest.mark.asyncio
async def test_documentar_with_kb_entry():
    agente = CWVDocumentadorAgent()
    problemas = [
        {
            "kb_codigo": "imagens-tamanho-correto",
            "audit_id": "uses-responsive-images",
            "contexto_especifico": {
                "title": "Properly size images",
                "display_value": "2.5s",
                "description": "Serves images with correct size",
                "items": [{"url": "https://example.com/img.jpg", "label": "hero"}],
                "savings_ms": 800,
                "savings_bytes": 150000,
            },
        }
    ]
    docs = await agente.documentar(problemas=problemas, plataforma="shopify")
    assert len(docs) == 1
    assert docs[0]["kb_codigo"] == "imagens-tamanho-correto"
    assert docs[0]["audit_id"] == "uses-responsive-images"
    assert docs[0]["titulo"] != ""
    assert "Properly size images" in docs[0]["documentacao_md"] or "imagens" in docs[0]["documentacao_md"].lower()
    assert docs[0]["severidade"] >= 1
    assert "Valor medido" not in docs[0]["documentacao_md"]
    assert "Elementos afetados" not in docs[0]["documentacao_md"]


@pytest.mark.asyncio
async def test_documentar_without_kb_entry_generates_skeleton():
    agente = CWVDocumentadorAgent()
    problemas = [
        {
            "kb_codigo": None,
            "audit_id": "custom-unknown-audit",
            "contexto_especifico": {
                "title": "Custom Unknown Audit",
                "display_value": "1.2s",
                "description": "Some unknown issue found by Lighthouse",
                "savings_ms": 600,
            },
        }
    ]
    docs = await agente.documentar(problemas=problemas, plataforma="geral")
    assert len(docs) == 1
    assert docs[0]["kb_codigo"] is None
    assert docs[0]["audit_id"] == "custom-unknown-audit"
    assert docs[0]["titulo"] == "Custom Unknown Audit"
    assert docs[0]["severidade"] == 4
    assert "Custom Unknown Audit" in docs[0]["documentacao_md"]
    assert "documentacao oficial" in docs[0]["documentacao_md"].lower()
    assert "Valor medido" not in docs[0]["documentacao_md"]


@pytest.mark.asyncio
async def test_documentar_without_kb_low_savings():
    agente = CWVDocumentadorAgent()
    problemas = [
        {
            "kb_codigo": None,
            "audit_id": "low-impact-audit",
            "contexto_especifico": {
                "title": "Low Impact",
                "description": "Minor issue",
                "savings_ms": 10,
            },
        }
    ]
    docs = await agente.documentar(problemas=problemas, plataforma="geral")
    assert len(docs) == 1
    assert docs[0]["severidade"] == 1


@pytest.mark.asyncio
async def test_documentar_without_kb_no_contexto():
    agente = CWVDocumentadorAgent()
    problemas = [
        {
            "kb_codigo": None,
            "audit_id": "some-audit",
            "contexto_especifico": {},
        }
    ]
    docs = await agente.documentar(problemas=problemas, plataforma="geral")
    assert len(docs) == 1
    assert docs[0]["audit_id"] == "some-audit"
    assert docs[0]["severidade"] == 1
    assert docs[0]["metricas_afetadas"] == ["LCP"]


@pytest.mark.asyncio
async def test_documentar_mixed_kb_and_unmapped():
    agente = CWVDocumentadorAgent()
    problemas = [
        {
            "kb_codigo": "imagens-formato-moderno",
            "audit_id": "modern-image-formats",
            "contexto_especifico": {"title": "Use modern formats", "savings_ms": 200},
        },
        {
            "kb_codigo": None,
            "audit_id": "some-unknown",
            "contexto_especifico": {"title": "Unknown", "savings_ms": 100},
        },
    ]
    docs = await agente.documentar(problemas=problemas, plataforma="wordpress")
    assert len(docs) == 2
    assert docs[0]["kb_codigo"] == "imagens-formato-moderno"
    assert docs[1]["kb_codigo"] is None
    assert docs[1]["audit_id"] == "some-unknown"


@pytest.mark.asyncio
async def test_documentar_empty_list():
    agente = CWVDocumentadorAgent()
    docs = await agente.documentar(problemas=[], plataforma="geral")
    assert docs == []

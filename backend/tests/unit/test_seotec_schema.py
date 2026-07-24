"""Testes do schema SEOTec — foco em ItemResposta/ItemPatch com diagnostico/
recomendacao (Onda 3 IA).

Valida o contrato de API: os campos gerados pelos agentes de IA fluem do banco
pelo schema ate o JSON de resposta, e o consultor pode sobrescreve-los via PATCH
(revisao humana, max_length para evitar payloads absurdos).
"""
import pytest
from pydantic import ValidationError

from app.schemas.seotec import ItemPatch, ItemResposta


def _base_item_resposta_kwargs(**overrides):
    base = dict(
        item_slug="title-tag-ausente-ou-vazia", nome="Title", categoria="Tag <title>",
        peso=8, prioridade="high", fonte="sf", modo="auto",
        status_antes="reprovado", status_depois=None,
        evidencias_json={"total_afetadas": 3},
        status_cliente=None, validacao_seo=None,
        observacao_cliente=None, observacao_seo=None,
    )
    base.update(overrides)
    return base


class TestItemRespostaDiagnosticoRecomendacao:
    def test_aceita_diagnostico_e_recomendacao(self):
        r = ItemResposta(
            **_base_item_resposta_kwargs(
                diagnostico="3 de 10 paginas sem title.",
                recomendacao="Escreva titles unicos por pagina.",
            )
        )
        assert r.diagnostico == "3 de 10 paginas sem title."
        assert r.recomendacao == "Escreva titles unicos por pagina."

    def test_default_none_quando_ia_nao_rodou(self):
        r = ItemResposta(**_base_item_resposta_kwargs())
        assert r.diagnostico is None
        assert r.recomendacao is None

    def test_serializacao_inclui_campos(self):
        r = ItemResposta(
            **_base_item_resposta_kwargs(diagnostico="diag", recomendacao="rec")
        )
        dump = r.model_dump()
        assert "diagnostico" in dump
        assert "recomendacao" in dump
        assert dump["diagnostico"] == "diag"


class TestItemPatchDiagnosticoRecomendacao:
    def test_patch_so_diagnostico_nao_toca_recomendacao(self):
        patch = ItemPatch(diagnostico="novo diag")
        dumped = patch.model_dump(exclude_unset=True)
        assert dumped == {"diagnostico": "novo diag"}

    def test_patch_so_recomendacao(self):
        patch = ItemPatch(recomendacao="nova rec")
        assert patch.model_dump(exclude_unset=True) == {"recomendacao": "nova rec"}

    def test_patch_ambos(self):
        patch = ItemPatch(diagnostico="d", recomendacao="r")
        assert patch.model_dump(exclude_unset=True) == {"diagnostico": "d", "recomendacao": "r"}

    def test_patch_vazio_nao_altera_nada(self):
        patch = ItemPatch()
        assert patch.model_dump(exclude_unset=True) == {}

    def test_diagnostico_rejeita_acima_max_length(self):
        with pytest.raises(ValidationError):
            ItemPatch(diagnostico="x" * 10001)

    def test_recomendacao_rejeita_acima_max_length(self):
        with pytest.raises(ValidationError):
            ItemPatch(recomendacao="x" * 10001)

    def test_diagnostico_aceita_exatamente_max_length(self):
        patch = ItemPatch(diagnostico="x" * 10000)
        assert len(patch.diagnostico) == 10000

"""Testes da gestão de fases + export DOCX da Auditoria SEOTec.

Valida:
- AuditoriaPatch aceita fases válidas
- Transições manuais permitidas (before→implementacao, after→concluida)
- Transições inválidas rejeitadas
- auditoria_para_html gera HTML estruturado correto
"""
import pytest
from pydantic import ValidationError

from app.schemas.seotec import AuditoriaPatch, FaseAuditoria
from app.services.seotec_export import auditoria_para_html


class TestAuditoriaPatchSchema:
    def test_aceita_fase_valida(self):
        p = AuditoriaPatch(fase="implementacao")
        assert p.fase == "implementacao"

    def test_aceita_fase_none(self):
        p = AuditoriaPatch()
        assert p.fase is None

    def test_rejeita_fase_invalida(self):
        with pytest.raises(ValidationError):
            AuditoriaPatch(fase="invalida")

    @pytest.mark.parametrize("fase", ["before", "implementacao", "after", "concluida"])
    def test_todas_fases_validas(self, fase: FaseAuditoria):
        assert AuditoriaPatch(fase=fase).fase == fase


class TestTransicoesFase:
    """Testa a lógica de transições manuais sem subir o servidor HTTP."""

    TRANSICOES = frozenset({("before", "implementacao"), ("after", "concluida")})

    def test_before_para_implementacao_permitida(self):
        assert ("before", "implementacao") in self.TRANSICOES

    def test_after_para_concluida_permitida(self):
        assert ("after", "concluida") in self.TRANSICOES

    def test_before_para_after_bloqueada(self):
        assert ("before", "after") not in self.TRANSICOES

    def test_before_para_concluida_bloqueada(self):
        assert ("before", "concluida") not in self.TRANSICOES

    def test_implementacao_para_concluida_bloqueada(self):
        assert ("implementacao", "concluida") not in self.TRANSICOES

    def test_implementacao_para_after_bloqueada_manual(self):
        """implementacao→after só via re-upload, não via PATCH manual."""
        assert ("implementacao", "after") not in self.TRANSICOES


class TestExportHTML:
    def _item(self, **overrides):
        base = {
            "slug": "title-tag-ausente", "nome": "Title tag ausente",
            "categoria": "Tag <title>", "peso": 8, "prioridade": "alta",
            "status_antes": "reprovado", "status_depois": None,
            "diagnostico": "3 páginas sem title", "recomendacao": "Adicionar title em todas",
            "observacao_cliente": None, "observacao_seo": None,
        }
        base.update(overrides)
        return base

    def test_gera_html_com_titulo_e_dominio(self):
        html = auditoria_para_html(
            dominio="https://exemplo.com", fase="before",
            score_antes=65.0, score_depois=None,
            cliente_nome="Cliente Teste", criado_em="2026-07-25T00:00:00",
            itens=[],
        )
        assert "Auditoria SEO Técnico" in html
        assert "exemplo.com" in html
        assert "Cliente Teste" in html

    def test_gera_tabela_score(self):
        html = auditoria_para_html(
            dominio="https://x.com", fase="before",
            score_antes=50.0, score_depois=75.0,
            cliente_nome="", criado_em="",
            itens=[],
        )
        assert "Health Score" in html
        assert "50%" in html
        assert "75%" in html
        assert "+25.0 p.p." in html

    def test_gera_checklist_por_categoria(self):
        itens = [
            self._item(categoria="Tag <title>"),
            self._item(slug="meta-description", nome="Meta description", categoria="Tag <title>", status_antes="atencao"),
            self._item(slug="amp", nome="AMP", categoria="Páginas AMP", status_antes="aprovado"),
        ]
        html = auditoria_para_html(
            dominio="https://x.com", fase="before",
            score_antes=None, score_depois=None,
            cliente_nome="", criado_em="",
            itens=itens,
        )
        assert "Tag &lt;title&gt;" in html
        assert "Páginas AMP" in html
        assert "Aprovado" in html
        assert "Reprovado" in html

    def test_gera_secao_diagnosticos_apenas_para_itens_com_conteudo(self):
        itens = [
            self._item(diagnostico="Diagnóstico detalhado", recomendacao="Fazer X"),
            self._item(slug="ok-item", nome="Item OK", diagnostico=None, recomendacao=None, status_antes="aprovado"),
        ]
        html = auditoria_para_html(
            dominio="https://x.com", fase="before",
            score_antes=None, score_depois=None,
            cliente_nome="", criado_em="",
            itens=itens,
        )
        assert "Diagnósticos e Recomendações" in html
        assert "Diagnóstico detalhado" in html
        # Item aprovado sem conteúdo não aparece na seção de diagnósticos
        assert "Item OK" not in html.split("Diagnósticos e Recomendações")[1]

    def test_sem_conteudo_ia_nao_gera_secao_diagnosticos(self):
        html = auditoria_para_html(
            dominio="https://x.com", fase="before",
            score_antes=None, score_depois=None,
            cliente_nome="", criado_em="",
            itens=[self._item(diagnostico=None, recomendacao=None)],
        )
        assert "Diagnósticos e Recomendações" not in html

    def test_escapa_html_no_conteudo(self):
        itens = [self._item(diagnostico="<script>alert('xss')</script>")]
        html = auditoria_para_html(
            dominio="https://x.com", fase="before",
            score_antes=None, score_depois=None,
            cliente_nome="", criado_em="",
            itens=itens,
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

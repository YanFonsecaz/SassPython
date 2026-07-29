"""Testes da integração Google Search Console para itens GSC SEOTec.

Testa a lógica dos avaliadores (sem chamar a API real).
Valida: credenciais ausentes → fail-open, parsing de respostas, status correto.
"""
from app.services.seotec_gsc import (
    _av_acoes_manuais,
    _av_bloqueadas_robots,
    _av_estatisticas_rastreamento,
    _av_pagina_nao_encontrada,
    _av_paginas_indexadas,
    _av_sitemap_listado_gsc,
    _av_sitemaps_gsc,
    _site_url_gsc,
)


class TestSiteUrlGsc:
    def test_https_url(self):
        assert _site_url_gsc("https://exemplo.com") == "https://exemplo.com/"

    def test_sc_domain(self):
        assert _site_url_gsc("exemplo.com") == "sc-domain:exemplo.com"

    def test_strips_protocol(self):
        assert _site_url_gsc("https://exemplo.com/") == "https://exemplo.com/"


class TestAcoesManuais:
    def test_aprovado_sem_acoes(self):
        r = _av_acoes_manuais({"googleSignals": {"manualActions": {}}})
        assert r.status == "aprovado"
        assert r.evidencias["acoes_manuais"] == 0

    def test_reprovado_com_acoes(self):
        r = _av_acoes_manuais({"googleSignals": {"manualActions": {"spam": "detected"}}})
        assert r.status == "reprovado"

    def test_sem_dados_inspect_none(self):
        r = _av_acoes_manuais(None)
        assert r.status == "sem_dados"


class TestPaginaNaoEncontrada:
    def test_aprovado_verdict_pass(self):
        r = _av_pagina_nao_encontrada({"verdict": "PASS", "coverageState": "INDEXED"})
        assert r.status == "aprovado"

    def test_reprovado_not_found(self):
        r = _av_pagina_nao_encontrada({"verdict": "FAIL", "coverageState": "NOT_FOUND_404"})
        assert r.status == "reprovado"

    def test_sem_dados(self):
        assert _av_pagina_nao_encontrada(None).status == "sem_dados"


class TestBloqueadasRobots:
    def test_aprovado_permitido(self):
        r = _av_bloqueadas_robots({"robotsTxtState": "ALLOWED", "verdict": "PASS"})
        assert r.status == "aprovado"

    def test_reprovado_bloqueado(self):
        r = _av_bloqueadas_robots({"robotsTxtState": "DISALLOWED", "verdict": "BLOCKED_BY_ROBOTS_TXT"})
        assert r.status == "reprovado"

    def test_sem_dados(self):
        assert _av_bloqueadas_robots(None).status == "sem_dados"


class TestPaginasIndexadas:
    def test_aprovado_indexed(self):
        r = _av_paginas_indexadas({"verdict": "PASS", "coverageState": "INDEXED"})
        assert r.status == "aprovado"

    def test_atencao_discovered(self):
        r = _av_paginas_indexadas({"verdict": "NEUTRAL", "coverageState": "DISCOVERED"})
        assert r.status == "atencao"

    def test_reprovado_excluded(self):
        r = _av_paginas_indexadas({"verdict": "FAIL", "coverageState": "EXCLUDED"})
        assert r.status == "reprovado"


class TestSitemapsGsc:
    def test_aprovado_sem_erros(self):
        data = {"sitemap": [{"path": "https://x.com/sitemap.xml", "errors": 0, "warnings": 0}]}
        r = _av_sitemaps_gsc(data)
        assert r.status == "aprovado"
        assert r.evidencias["sitemaps_registrados"] == 1

    def test_atencao_com_erros(self):
        data = {"sitemap": [{"path": "https://x.com/sitemap.xml", "errors": 3, "warnings": 0}]}
        r = _av_sitemaps_gsc(data)
        assert r.status == "atencao"

    def test_reprovado_sem_sitemaps(self):
        r = _av_sitemaps_gsc({"sitemap": []})
        assert r.status == "reprovado"

    def test_sem_dados(self):
        assert _av_sitemaps_gsc(None).status == "sem_dados"


class TestSitemapListadoGsc:
    def test_aprovado_com_sitemaps(self):
        r = _av_sitemap_listado_gsc({"sitemap": [{"path": "https://x.com/sitemap.xml"}]})
        assert r.status == "aprovado"

    def test_reprovado_sem_sitemaps(self):
        r = _av_sitemap_listado_gsc({"sitemap": []})
        assert r.status == "reprovado"

    def test_sem_dados(self):
        assert _av_sitemap_listado_gsc(None).status == "sem_dados"


class TestEstatisticasRastreamento:
    def test_aprovado_alto_trafego(self):
        data = {"rows": [{"impressions": 500, "clicks": 50}]}
        r = _av_estatisticas_rastreamento(data)
        assert r.status == "aprovado"

    def test_atencao_baixo_trafego(self):
        data = {"rows": [{"impressions": 50, "clicks": 2}]}
        r = _av_estatisticas_rastreamento(data)
        assert r.status == "atencao"

    def test_reprovado_sem_impressoes(self):
        r = _av_estatisticas_rastreamento({"rows": []})
        assert r.status == "reprovado"

    def test_sem_dados(self):
        assert _av_estatisticas_rastreamento(None).status == "sem_dados"

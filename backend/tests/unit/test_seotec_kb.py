"""Testes da KB de soluções SEOTEC (SPEC_SEOTEC_Agentes_IA §2).

Valida: loader pydantic, buscar/render_recomendacao (canônica + variação
plataforma), slugs_orfaos (KB nunca referencia slug inexistente no checklist).
"""
from app.services import seotec_kb
from app.services.seotec_checklist import carregar_checklist


def test_carregar_kb_nao_estoura():
    kb = seotec_kb.carregar_kb()
    assert isinstance(kb.categorias, list)


def test_buscar_hit_retorna_entrada():
    # Slug coberto pelos YAMLs atuais (headings.yaml).
    entrada = seotec_kb.buscar("tag-h1-ausente-ou-vazia")
    assert entrada is not None
    assert entrada.slug == "tag-h1-ausente-ou-vazia"
    assert "h1" in entrada.recomendacao.lower()


def test_buscar_miss_retorna_none():
    # Slug inexistente na KB → fallback LLM no recomendador.
    assert seotec_kb.buscar("slug-que-nao-existe-na-kb") is None


def test_render_recomendacao_canonica_quando_sem_variacao():
    entrada = seotec_kb.buscar("tags-h1-duplicadas-em-varias-paginas")
    assert entrada is not None
    # Este slug só tem recomendacao canônica (sem solucoes.wordpress/vtex/...).
    texto = seotec_kb.render_recomendacao(entrada, "wordpress")
    assert texto == entrada.recomendacao


def test_render_recomendacao_usa_variacao_plataforma():
    entrada = seotec_kb.buscar("tag-h1-ausente-ou-vazia")
    assert entrada is not None and "wordpress" in entrada.solucoes
    texto_wp = seotec_kb.render_recomendacao(entrada, "wordpress")
    texto_geral = seotec_kb.render_recomendacao(entrada, "geral")
    assert texto_wp != texto_geral
    assert "Elementor" in texto_wp or "Divi" in texto_wp or "tema" in texto_wp.lower()


def test_render_recomendacao_fallback_canonica_para_plataforma_sem_variacao():
    entrada = seotec_kb.buscar("tag-h1-ausente-ou-vazia")
    # Plataforma sem variação específica cai na recomendação canônica.
    texto = seotec_kb.render_recomendacao(entrada, "shopify")
    assert texto == entrada.recomendacao


def test_slugs_orfaos_vazio_contra_checklist_real():
    """SPEC §2: KB nunca referencia slug inexistente no checklist."""
    ck = carregar_checklist()
    slugs_checklist = {i.slug for i in ck.itens()}
    orfaos = seotec_kb.slugs_orfaos(slugs_checklist)
    assert orfaos == set(), f"Slugs órfãos na KB: {orfaos}"


def test_recarregar_kb_limpa_cache():
    seotec_kb.recarregar_kb()
    kb1 = seotec_kb.carregar_kb()
    seotec_kb.recarregar_kb()
    kb2 = seotec_kb.carregar_kb()
    assert {i.slug for i in kb1.itens()} == {i.slug for i in kb2.itens()}


def test_slug_unico_na_kb():
    """Invariant pydantic: slugs únicos dentro da KB."""
    kb = seotec_kb.carregar_kb()
    slugs = [i.slug for i in kb.itens()]
    assert len(slugs) == len(set(slugs))

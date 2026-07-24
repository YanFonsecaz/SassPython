"""Testes do detector de plataforma SEOTec (SPEC_SEOTEC_Agentes_IA §2).

Reusa marcadores de URL do CWV (`URL_SIGNATURES`) escaneando o export `internal`.
Valida: detecção por consenso, fail-open para export ausente/vazio, mapeamento
outros/desconhecida -> geral.
"""
from app.services.seotec_ingestao import ExportNormalizado, PacoteIngestao
from app.services.seotec_plataforma import detectar_plataforma


def _pacote_com_internal(urls: list[str]) -> PacoteIngestao:
    return PacoteIngestao(
        schema_version=1,
        dominio="exemplo.com",
        exports={"internal": ExportNormalizado(
            linhas=[{"address": u} for u in urls], total_antes_corte=len(urls),
        )},
    )


def test_wordpress_detectado_por_wp_content():
    pacote = _pacote_com_internal([
        "https://x.com/wp-content/themes/estilo.css",
        "https://x.com/wp-includes/js/jquery.js",
        "https://x.com/blog/post-1",
    ])
    assert detectar_plataforma(pacote) == "wordpress"


def test_vtex_detectado_por_dominio_vtex():
    pacote = _pacote_com_internal([
        "https://x.vtexassets.com/arquivos/id.png",
        "https://x.com/produto",
    ])
    assert detectar_plataforma(pacote) == "vtex"


def test_nextjs_detectado_por_next_static():
    pacote = _pacote_com_internal([
        "https://x.com/_next/static/chunks/main.js",
        "https://x.com/_next/data/build.json",
    ])
    assert detectar_plataforma(pacote) == "nextjs"


def test_shopify_detectado():
    pacote = _pacote_com_internal([
        "https://cdn.shopify.com/s/files/1/img.jpg",
        "https://x.com/products/camiseta",
    ])
    assert detectar_plataforma(pacote) == "shopify"


def test_consenso_vence_empate_mistura_wordpress_e_nextjs():
    # 3 URLs WP vs 1 Next -> wordpress por maioria.
    pacote = _pacote_com_internal([
        "https://x.com/wp-content/a.css",
        "https://x.com/wp-includes/b.js",
        "https://x.com/wp-json/wp/v2",
        "https://x.com/_next/static/rare.js",
    ])
    assert detectar_plataforma(pacote) == "wordpress"


def test_sem_marcador_retorna_geral():
    pacote = _pacote_com_internal([
        "https://x.com/sobre",
        "https://x.com/contato",
    ])
    assert detectar_plataforma(pacote) == "geral"


def test_export_internal_ausente_retorna_geral():
    pacote = PacoteIngestao(schema_version=1, dominio="x.com", exports={})
    assert detectar_plataforma(pacote) == "geral"


def test_export_internal_vazio_retorna_geral():
    pacote = PacoteIngestao(
        schema_version=1, dominio="x.com",
        exports={"internal": ExportNormalizado(linhas=[], total_antes_corte=0)},
    )
    assert detectar_plataforma(pacote) == "geral"


def test_linhas_sem_address_sao_ignoradas():
    pacote = _pacote_com_internal([
        "https://x.com/wp-content/a.css",
        "",  # vazia ignorada
    ])
    # A WP conta 1 voto; sem concorrente -> wordpress.
    assert detectar_plataforma(pacote) == "wordpress"


def test_um_voto_por_url_nao_duplica():
    # URL com 2 marcadores WP conta só 1 vez (break no primeiro match).
    pacote = _pacote_com_internal([
        "https://x.com/wp-content/wp-includes/duplo.css",
    ])
    assert detectar_plataforma(pacote) == "wordpress"

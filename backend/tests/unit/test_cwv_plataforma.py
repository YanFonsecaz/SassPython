from app.services.cwv_plataforma import detectar_plataforma


def _psi_payload(stack_packs: list[dict] | None = None, network_urls: list[str] | None = None) -> dict:
    stack_packs = stack_packs or []
    network_items = [{"url": u} for u in (network_urls or [])]
    return {
        "lighthouseResult": {
            "stackPacks": stack_packs,
            "audits": {
                "network-requests": {
                    "details": {"items": network_items},
                }
            },
        }
    }


def test_stackpack_wordpress():
    payload = _psi_payload(stack_packs=[{"id": "wordpress"}])
    assert detectar_plataforma(payload) == "wordpress"


def test_stackpack_magento():
    payload = _psi_payload(stack_packs=[{"id": "magento"}])
    assert detectar_plataforma(payload) == "magento"


def test_stackpack_wix():
    payload = _psi_payload(stack_packs=[{"id": "wix"}])
    assert detectar_plataforma(payload) == "wix"


def test_stackpack_nextjs():
    payload = _psi_payload(stack_packs=[{"id": "next"}])
    assert detectar_plataforma(payload) == "nextjs"


def test_stackpack_takes_priority_over_network():
    payload = _psi_payload(
        stack_packs=[{"id": "wordpress"}],
        network_urls=["https://cdn.shopify.com/s/file/foo.js"],
    )
    assert detectar_plataforma(payload) == "wordpress"


def test_network_vtex():
    payload = _psi_payload(network_urls=["https://storecomponent.vtexassets.com/arquivos/ids/foo.jpg"])
    assert detectar_plataforma(payload) == "vtex"


def test_network_vtex_path():
    payload = _psi_payload(network_urls=["https://store.com/vtex/storefront/logo.png"])
    assert detectar_plataforma(payload) == "vtex"


def test_network_wordpress_wp_content():
    payload = _psi_payload(network_urls=["https://site.com/wp-content/themes/style.css"])
    assert detectar_plataforma(payload) == "wordpress"


def test_network_wordpress_wp_includes():
    payload = _psi_payload(network_urls=["https://site.com/wp-includes/js/jquery.js"])
    assert detectar_plataforma(payload) == "wordpress"


def test_network_nextjs():
    payload = _psi_payload(network_urls=["https://site.com/_next/static/chunks/main.js"])
    assert detectar_plataforma(payload) == "nextjs"


def test_network_shopify():
    payload = _psi_payload(network_urls=["https://cdn.shopify.com/s/files/1/foo.js"])
    assert detectar_plataforma(payload) == "shopify"


def test_network_myshopify():
    payload = _psi_payload(network_urls=["https://loja.myshopify.com/"])
    assert detectar_plataforma(payload) == "shopify"


def test_desconhecida_sem_pistas():
    payload = _psi_payload(network_urls=["https://site.com/assets/main.js"])
    assert detectar_plataforma(payload) == "desconhecida"


def test_desconhecida_vazio():
    assert detectar_plataforma({"lighthouseResult": {}}) == "desconhecida"

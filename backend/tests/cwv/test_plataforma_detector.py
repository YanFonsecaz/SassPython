import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("fixture,esperado", [
    ("psi_payload_wordpress.json", "wordpress"),
    ("psi_payload_nextjs.json", "nextjs"),
    ("psi_payload_vtex.json", "vtex"),
])
def test_detecta_plataforma_via_stackpacks(fixture, esperado):
    from app.services.cwv_plataforma import detectar_plataforma
    payload = json.loads((FIXTURES / fixture).read_text())
    assert detectar_plataforma(payload) == esperado


def test_detecta_vtex_via_network_quando_stackpacks_vazio():
    from app.services.cwv_plataforma import detectar_plataforma
    payload = {
        "lighthouseResult": {
            "stackPacks": [],
            "audits": {"network-requests": {"details": {"items": [
                {"url": "https://lojax.vtexassets.com/img/a.png"},
            ]}}},
        }
    }
    assert detectar_plataforma(payload) == "vtex"


def test_detecta_wordpress_via_network():
    from app.services.cwv_plataforma import detectar_plataforma
    payload = {
        "lighthouseResult": {
            "stackPacks": [],
            "audits": {"network-requests": {"details": {"items": [
                {"url": "https://site.com/wp-content/themes/style.css"},
            ]}}},
        }
    }
    assert detectar_plataforma(payload) == "wordpress"


def test_detecta_nextjs_via_network():
    from app.services.cwv_plataforma import detectar_plataforma
    payload = {
        "lighthouseResult": {
            "stackPacks": [],
            "audits": {"network-requests": {"details": {"items": [
                {"url": "https://site.com/_next/static/chunks/main.js"},
            ]}}},
        }
    }
    assert detectar_plataforma(payload) == "nextjs"


def test_detecta_shopify_via_network():
    from app.services.cwv_plataforma import detectar_plataforma
    payload = {
        "lighthouseResult": {
            "stackPacks": [],
            "audits": {"network-requests": {"details": {"items": [
                {"url": "https://cdn.shopify.com/s/files/1/foo.js"},
            ]}}},
        }
    }
    assert detectar_plataforma(payload) == "shopify"


def test_stackpack_takes_priority_over_network():
    from app.services.cwv_plataforma import detectar_plataforma
    payload = {
        "lighthouseResult": {
            "stackPacks": [{"id": "wordpress"}],
            "audits": {"network-requests": {"details": {"items": [
                {"url": "https://cdn.shopify.com/s/file/foo.js"},
            ]}}},
        }
    }
    assert detectar_plataforma(payload) == "wordpress"


def test_payload_vazio_retorna_desconhecida():
    from app.services.cwv_plataforma import detectar_plataforma
    assert detectar_plataforma({}) == "desconhecida"
    assert detectar_plataforma({"lighthouseResult": {}}) == "desconhecida"

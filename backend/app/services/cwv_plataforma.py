import re
from typing import Literal

Plataforma = Literal[
    "vtex",
    "wordpress",
    "nextjs",
    "shopify",
    "wix",
    "squarespace",
    "magento",
    "hugo",
    "jekyll",
    "webflow",
    "outros",
    "desconhecida",
]

STACKPACK_MAP: dict[str, Plataforma] = {
    "wordpress": "wordpress",
    "magento": "magento",
    "wix": "wix",
    "next": "nextjs",
    "drupal": "outros",
    "joomla": "outros",
}

URL_SIGNATURES: list[tuple[str, Plataforma]] = [
    ("vtexassets.com", "vtex"),
    ("/vtex/", "vtex"),
    ("myvtex.com", "vtex"),
    ("wp-content/", "wordpress"),
    ("wp-includes/", "wordpress"),
    ("wp-json/", "wordpress"),
    ("_next/static/", "nextjs"),
    ("_next/data/", "nextjs"),
    ("cdn.shopify.com", "shopify"),
    ("myshopify.com", "shopify"),
    ("cdn.shopifycloud.com", "shopify"),
    ("static.parastorage.com", "wix"),
    ("static.squarespace.com", "squarespace"),
    ("assets.squarespace.com", "squarespace"),
    ("assets.webflow.com", "webflow"),
    ("webflow.io", "webflow"),
]

GENERATOR_MAP: dict[str, Plataforma] = {
    "wordpress": "wordpress",
    "hugo": "hugo",
    "jekyll": "jekyll",
    "drupal": "outros",
    "joomla": "outros",
    "ghost": "outros",
    "next.js": "nextjs",
    "shopify": "shopify",
}

HEADER_SIGNATURES: dict[str, dict[str, Plataforma]] = {
    "x-powered-by": {"wordpress": "wordpress", "next.js": "nextjs"},
    "x-shopify-shop-id": {"*": "shopify"},
    "x-vtex-storefront": {"*": "vtex"},
}

_META_GENERATOR_RE = re.compile(
    r'<meta[^>]*name=["\']generator["\'][^>]*content=["\']([^"\']+)["\']', re.IGNORECASE
)


def _extrair_headers(lh: dict) -> dict[str, str]:
    md = lh.get("audits", {}).get("main-document", {}).get("details", {})
    headers = md.get("headers", [])
    return {h.get("name", "").lower(): h.get("value", "") for h in headers}


def _extrair_network_blob(lh: dict) -> str:
    network = lh.get("audits", {}).get("network-requests", {}).get("details", {}).get("items", [])
    return " ".join(item.get("url", "") for item in network)


def _extrair_generator(lh: dict) -> str:
    md = lh.get("audits", {}).get("main-document", {}).get("details", {})
    snippet = md.get("snippet", "") or ""
    m = _META_GENERATOR_RE.search(snippet)
    return m.group(1) if m else ""


def detectar_plataforma(psi_payload: dict) -> Plataforma:
    lh = psi_payload.get("lighthouseResult", {})

    # Camada 1 — stackPacks
    for stack in lh.get("stackPacks", []):
        sid = stack.get("id", "").lower()
        if sid in STACKPACK_MAP:
            return STACKPACK_MAP[sid]

    # Camada 2 — Headers HTTP (x-powered-by, x-shopify-shop-id, x-vtex-storefront)
    headers = _extrair_headers(lh)
    for header_name, mapa in HEADER_SIGNATURES.items():
        valor = headers.get(header_name, "").lower()
        if not valor:
            continue
        for marcador, plataforma in mapa.items():
            if marcador == "*":
                return plataforma
            if marcador in valor:
                return plataforma

    # Camada 3 — Network requests (URLs de assets)
    network_blob = _extrair_network_blob(lh).lower()
    for marker, plataforma in URL_SIGNATURES:
        if marker.lower() in network_blob:
            return plataforma

    # Camada 4 — meta generator
    generator = _extrair_generator(lh).lower()
    for marker, plataforma in GENERATOR_MAP.items():
        if marker in generator:
            return plataforma

    # Camada 5 — sinais fracos (analytics, gtag, fbq) → outros
    if any(sinal in network_blob for sinal in ["google-analytics", "googletagmanager", "gtag", "facebook.net/", "fbq("]):
        return "outros"

    return "desconhecida"

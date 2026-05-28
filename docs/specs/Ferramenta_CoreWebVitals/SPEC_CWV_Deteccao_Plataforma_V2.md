# SPEC — CWV Detecção de Plataforma V2

**Status:** a aplicar · **Escopo:** backend (detector reforçado) + frontend (indicador visual quando detecção falha)
**Dependências:** [[SPEC_Ferramenta_Core_Web_Vitals]] (§3.3)
**Esforço estimado:** ~1.5 dias

## 1. Problema

A detecção atual (`cwv_plataforma.py:detectar_plataforma`) caiu em `"desconhecida"` para:
- **web.dev** (Hugo + GTM, sem stack-pack Lighthouse)
- **nextjs.org** (falhou antes de detectar — caso de borda PSI 429)

A SPEC original cobre 5 plataformas (VTEX, WordPress, Next.js, Shopify, Wix, Magento). Faltam sinais para:
- **Shopify** (regex atual cobre só `cdn.shopify.com`/`myshopify.com`)
- **Hugo / Jekyll / sites estáticos** (sem detecção)
- **Webflow** (sem detecção)
- **Squarespace / Wix** (Wix tem stack-pack, Squarespace não)
- **Site customizado** (deveria sinalizar "outros" com confiança em vez de "desconhecida")

Adicionalmente:
- A KB tem soluções por plataforma. Quando a plataforma é "desconhecida", o usuário recebe **só** a solução geral — perdendo o diferencial da ferramenta ("solução adaptada à plataforma").
- O frontend exibe a plataforma como badge, mas quando é "desconhecida" não há indicação de **por que** ou se o usuário pode ajudar.

## 2. Objetivos

1. **Aumentar cobertura** para 8+ plataformas (atuais 5 + Hugo, Webflow, Squarespace, Magento 1 vs 2)
2. **Estado "outros" explícito** (em vez de "desconhecida") quando há sinais claros de site customizado/desconhecido
3. **Frontend**: permitir o usuário **declarar manualmente** a plataforma quando detecção falhar, recarregando a documentação adaptada

## 3. Backend

### 3.1 Detector V2 (`app/services/cwv_plataforma.py`)

Expandir tipo:

```python
Plataforma = Literal[
    "vtex", "wordpress", "nextjs", "shopify", "wix", "squarespace",
    "magento", "hugo", "jekyll", "webflow", "outros", "desconhecida"
]
```

Algoritmo em camadas (do mais confiável ao menos):

**Camada 1 — stackPacks do Lighthouse** (alta confiança):
```python
STACKPACK_MAP = {
    "wordpress": "wordpress",
    "magento": "magento",
    "wix": "wix",
    "next": "nextjs",
    "shopify": "shopify",  # adicionar se Lighthouse expor
    "drupal": "outros",     # sem solução específica V1 → outros
}
```

**Camada 2 — Headers HTTP** (extraídos de PSI `network-requests` → `responseHeaders`):
```python
HEADER_SIGNATURES = {
    "x-powered-by": {"wordpress": "wordpress", "express": "outros", "nextjs": "nextjs"},
    "server": {"litespeed": "wordpress", "cowboy": "outros", "cloudflare": None},
    "x-shopify-shop-id": {"*": "shopify"},
    "x-vtex-storefront": {"*": "vtex"},
}
```

**Camada 3 — Network requests** (URLs de assets):
```python
URL_SIGNATURES = [
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
    ("static.parastorage.com", "wix"),       # Wix CDN
    ("static.squarespace.com", "squarespace"),
    ("assets.squarespace.com", "squarespace"),
    ("assets.webflow.com", "webflow"),
    ("/index.xml", "hugo"),                   # Hugo default RSS
    ("hugo-", "hugo"),                        # tema com prefixo
    ("/_app.css", "sveltekit"),
]
```

**Camada 4 — HTML meta** (PSI traz HTML como `main-thread-tasks`/snippet em alguns audits — extrair `<meta name="generator">`):
```python
GENERATOR_MAP = {
    "wordpress": "wordpress",
    "hugo": "hugo",
    "jekyll": "jekyll",
    "drupal": "outros",
    "joomla": "outros",
    "ghost": "outros",
}
```

**Camada 5 — Fallback**:
- Se houve QUALQUER sinal de tecnologia identificável (mesmo que cai em "outros"), retorna `"outros"` (= "site customizado/CMS não suportado V1")
- Senão, retorna `"desconhecida"` (= "não conseguimos analisar")

```python
def detectar_plataforma(psi_payload: dict) -> Plataforma:
    lh = psi_payload.get("lighthouseResult", {})
    
    # Camada 1: stackPacks
    for stack in lh.get("stackPacks", []):
        sid = stack.get("id", "").lower()
        if sid in STACKPACK_MAP:
            return STACKPACK_MAP[sid]
    
    # Camada 2: headers
    headers_dict = _extrair_headers_de_psi(lh)
    for header, mapa in HEADER_SIGNATURES.items():
        valor = headers_dict.get(header, "").lower()
        for marcador, plataforma in mapa.items():
            if marcador == "*" and valor:
                return plataforma
            if marcador in valor:
                return plataforma
    
    # Camada 3: URLs
    network_blob = _extrair_network_blob(lh).lower()
    for marker, plataforma in URL_SIGNATURES:
        if marker.lower() in network_blob:
            return plataforma
    
    # Camada 4: meta generator
    generator = _extrair_generator_meta(lh).lower()
    for marker, plataforma in GENERATOR_MAP.items():
        if marker in generator:
            return plataforma
    
    # Camada 5: sinais fracos → outros
    if any(sinal in network_blob for sinal in ["analytics", "gtag", "fbq"]):
        return "outros"
    
    return "desconhecida"


def _extrair_headers_de_psi(lh: dict) -> dict[str, str]:
    """PSI inclui responseHeaders no main-document audit"""
    md = lh.get("audits", {}).get("main-document", {}).get("details", {})
    headers = md.get("headers", [])
    return {h.get("name", "").lower(): h.get("value", "") for h in headers}


def _extrair_network_blob(lh: dict) -> str:
    network = lh.get("audits", {}).get("network-requests", {}).get("details", {}).get("items", [])
    return " ".join(item.get("url", "") for item in network)


def _extrair_generator_meta(lh: dict) -> str:
    """Heurística: procura <meta name="generator"> no script-treemap-data ou main-document"""
    md = lh.get("audits", {}).get("main-document", {}).get("details", {})
    snippet = md.get("snippet", "")
    import re
    m = re.search(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\']([^"\']+)["\']', snippet, re.I)
    return m.group(1) if m else ""
```

### 3.2 Override manual (NOVO endpoint)

```python
@router.patch("/core-web-vitals/analise/{analise_id}/plataforma")
async def override_plataforma(
    analise_id: str,
    body: PlataformaOverrideRequest,  # { "plataforma": "vtex" }
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """
    Permite usuário corrigir manualmente a plataforma detectada.
    Re-renderiza documentacao_md de todos os problemas com a plataforma nova.
    """
    analise = await buscar_analise_por_id(db, analise_id)
    if not analise or analise.usuario_id != usuario.id:
        raise HTTPException(404)
    
    analise.plataforma_detectada = body.plataforma
    
    # Re-gerar markdown dos problemas
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    agente = CWVDocumentadorAgent()
    problemas = await db.execute(select(CwvProblema).where(CwvProblema.analise_id == analise_id))
    for p in problemas.scalars():
        kb_entry = buscar_entrada(p.kb_codigo)
        if kb_entry:
            p.documentacao_md = agente._gerar_doc(kb_entry, body.plataforma, p.contexto_especifico or {})
    
    await db.commit()
    return {"plataforma": body.plataforma, "n_problemas_atualizados": ...}
```

Schema:
```python
PlataformaValida = Literal["vtex", "wordpress", "nextjs", "shopify", "wix", "squarespace", "magento", "hugo", "jekyll", "webflow", "outros"]

class PlataformaOverrideRequest(BaseModel):
    plataforma: PlataformaValida
```

### 3.3 KB — adicionar soluções para novas plataformas

Ampliar `cwv_kb.py`:
```python
Plataforma = Literal[
    "geral", "vtex", "wordpress", "nextjs", "shopify", "wix",
    "squarespace", "magento", "hugo", "jekyll", "webflow"
]
```

Para cada entrada da KB que tenha solução específica adicional (~10 entradas críticas como `lcp-imagem-grande`, `js-bundle-grande`, etc), incrementar com seções para Hugo, Webflow, Squarespace.

Restantes podem deixar só "geral" — a documentação determinística do `CWVDocumentadorAgent._gerar_doc` já lida com plataforma ausente.

## 4. Frontend

### 4.1 Dashboard URL — Badge clicável de plataforma

Modificar `cwv-dashboard-client.tsx`:

```tsx
{analiseAtual.plataforma_detectada === "desconhecida" ? (
  <PlataformaSelectorButton analiseId={analiseAtual.id} />
) : (
  <Badge variant="outline" className="cursor-pointer" onClick={() => setOverrideOpen(true)}>
    {analiseAtual.plataforma_detectada}
    <PencilIcon className="size-3 ml-1" />
  </Badge>
)}
<PlataformaOverrideDialog
  analiseId={analiseAtual.id}
  open={overrideOpen}
  onOpenChange={setOverrideOpen}
  plataformaAtual={analiseAtual.plataforma_detectada}
  onSuccess={recarregarAnalise}
/>
```

### 4.2 Novo componente `PlataformaOverrideDialog`

`frontend/src/components/cwv/cwv-plataforma-override-dialog.tsx`:

```tsx
"use client";

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { overridePlataformaCwv } from "@/lib/api/cwv";

const PLATAFORMAS = [
  { value: "vtex", label: "VTEX" },
  { value: "wordpress", label: "WordPress" },
  { value: "nextjs", label: "Next.js" },
  { value: "shopify", label: "Shopify" },
  { value: "wix", label: "Wix" },
  { value: "squarespace", label: "Squarespace" },
  { value: "magento", label: "Magento" },
  { value: "hugo", label: "Hugo" },
  { value: "jekyll", label: "Jekyll" },
  { value: "webflow", label: "Webflow" },
  { value: "outros", label: "Outra / Customizado" },
] as const;

interface Props {
  analiseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  plataformaAtual: string;
  onSuccess: () => void;
}

export function PlataformaOverrideDialog({ analiseId, open, onOpenChange, plataformaAtual, onSuccess }: Props) {
  const [selecionada, setSelecionada] = useState(plataformaAtual);
  const [enviando, setEnviando] = useState(false);

  async function salvar() {
    setEnviando(true);
    try {
      await overridePlataformaCwv(analiseId, selecionada);
      onSuccess();
      onOpenChange(false);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Qual a plataforma deste site?</DialogTitle>
          <DialogDescription>
            Não conseguimos detectar automaticamente. Selecione para recebermos soluções
            adaptadas à sua plataforma.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-2 my-4">
          {PLATAFORMAS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setSelecionada(p.value)}
              className={cn(
                "rounded-lg border px-3 py-2 text-sm transition-colors",
                selecionada === p.value ? "border-brand bg-brand/5" : "hover:bg-surface-light"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={enviando}>Cancelar</Button>
          <Button onClick={salvar} disabled={enviando || selecionada === plataformaAtual}>
            {enviando ? "Salvando..." : "Salvar e recarregar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

### 4.3 Cliente API

```ts
// lib/api/cwv.ts
export async function overridePlataformaCwv(
  analiseId: string, plataforma: string
): Promise<{ plataforma: string; n_problemas_atualizados: number }> {
  return api.patch(`/ferramentas/core-web-vitals/analise/${analiseId}/plataforma`, { plataforma });
}
```

### 4.4 Estado visual quando plataforma é "desconhecida"

No dashboard URL, quando `plataforma_detectada === "desconhecida"`, mostrar:

```
┌─ ⚠ Plataforma não detectada ──────────────────────┐
│  Não conseguimos identificar a plataforma do site.│
│  As soluções abaixo são genéricas.                │
│  [ Selecionar plataforma manualmente → ]          │
└────────────────────────────────────────────────────┘
```

CTA grande/visível acima do `PlanoAcaoAccordion`.

## 5. Backend tests

Adicionar fixtures de payload PSI reais (sanitizados) para 8 plataformas em `backend/tests/cwv/fixtures/`:
- `psi_payload_hugo.json` (web.dev real)
- `psi_payload_squarespace.json`
- `psi_payload_webflow.json`
- `psi_payload_shopify_headers.json` (com `x-shopify-shop-id`)
- `psi_payload_meta_generator_wordpress.json` (sem stackPack, só meta)

Em `test_plataforma_detector.py`, expandir parametrize para cobrir todas.

## 6. Plano de execução

| Fase | O que | Esforço |
|---|---|---|
| P1 | Backend: detector V2 com 5 camadas + fixtures de payload | 0.5 dia |
| P2 | Backend: endpoint `PATCH /plataforma` + tests | 0.25 dia |
| P3 | KB: expandir 10 entradas críticas com Hugo/Webflow/Squarespace | 0.25 dia |
| P4 | Frontend: dialog + badge clicável + cliente API | 0.5 dia |
| **Total** | | **~1.5 dias** |

## 7. Critério de pronto

- [ ] Detector V2 retorna corretamente para os 8+ tipos de payload de teste
- [ ] web.dev real é detectado como `hugo` (ou `outros`, não `desconhecida`)
- [ ] Endpoint `PATCH /plataforma` muda a plataforma e regenera `documentacao_md` de todos os problemas
- [ ] UI: badge da plataforma é clicável quando detectada
- [ ] UI: alerta com CTA quando plataforma é `desconhecida`
- [ ] Dialog lista as 11 plataformas suportadas
- [ ] Cobertura de testes em `test_plataforma_detector.py` ≥ 95%
- [ ] E2E manual: análise → override → ver markdown atualizado com solução específica

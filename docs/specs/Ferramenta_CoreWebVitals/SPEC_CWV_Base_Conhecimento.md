# SPEC — Base de Conhecimento curada (Core Web Vitals)

**Status:** a aplicar · **Escopo:** estrutura de dados em YAML + loader + lista inicial de problemas + processo de manutenção
**Spec mãe:** [[SPEC_Ferramenta_Core_Web_Vitals]]
**Por que separada:** o conteúdo da KB é independente do código, evolui em cadência própria, e merece governança própria (revisão trimestral, conforme Lighthouse muda audits)

## 1. Visão geral

A base de conhecimento (KB) é o coração do diferencial da ferramenta: substitui o uso de "MCP context7" ou web search ao vivo por um catálogo curado de problemas conhecidos do Core Web Vitals, com soluções adaptadas por plataforma.

### 1.1 Por que curada (vs. busca ao vivo ou RAG)

- **Zero custo por query** — análise em escala não cobra por busca
- **Zero alucinação** — texto revisado por humano, sem links/conceitos inventados
- **Adaptação por plataforma** — VTEX, WordPress, Next.js têm soluções fundamentalmente diferentes para o mesmo problema; LLM genérico não dá esse nível de especificidade confiável
- **Atualizações controladas** — quando Lighthouse muda audits ou surge nova prática, atualizamos a KB e todas as análises futuras já refletem

### 1.2 Trade-off aceito

A KB cobre os problemas **conhecidos**. Audits novos ou raros caem em fallback genérico até serem adicionados manualmente. Esse é o custo da abordagem — aceitamos em troca da qualidade e custo zero por execução.

## 2. Estrutura

### 2.1 Arquivo único

`backend/app/data/cwv_knowledge_base.yaml`

Por que YAML: legível pra revisão humana (texto em blocos `|`), suporta multi-linha sem escapes, fácil de revisar em PR. Validado contra schema Pydantic no boot.

### 2.2 Schema de uma entrada

```yaml
- codigo: lcp-imagem-grande              # snake-case, único, estável
  titulo: "Imagem do LCP muito grande"   # exibido no accordion
  severidade: 5                           # 1=leve, 5=crítico
  metricas_afetadas: [LCP]                # uma ou mais: LCP, CLS, INP, TBT, FCP, TTFB
  audits_lighthouse:                      # IDs canônicos de audit Lighthouse mapeados pra este código
    - largest-contentful-paint-element
    - uses-optimized-images
    - modern-image-formats
  descricao: |                            # markdown; explicação do problema em PT-BR
    O maior elemento visível na primeira dobra (LCP) está demorando para carregar porque a imagem
    tem tamanho excessivo. Isso atrasa diretamente a métrica LCP, que mede quando o usuário vê
    o conteúdo principal da página.
  solucoes:                               # mapa plataforma -> markdown da solução
    geral: |
      1. **Converter para formato moderno** (WebP ou AVIF) — economia típica de 30-50% no tamanho
      2. **Servir em tamanho responsivo** com `srcset` e `sizes`
      3. **Adicionar `fetchpriority="high"`** na tag `<img>` do LCP
      4. **Pré-carregar com `<link rel="preload">`** se a imagem está sempre presente
    vtex: |
      No VTEX IO:
      1. Use o componente `<img-vtex>` (não `<img>` puro) — gera srcset automaticamente
      2. Configure `width`/`height` explícitos no bloco `image` do site editor
      3. Adicione `priority="true"` no bloco que renderiza o LCP (ex: `image#hero`)
      4. Habilite no admin: **Loja → CMS → Configurações de Performance → Otimização de imagens**
    wordpress: |
      1. Instale **EWWW Image Optimizer** ou **ShortPixel** — converte para WebP automaticamente
      2. Adicione plugin de cache (WP Rocket, LiteSpeed Cache) com lazy load desativado pra LCP
      3. No tema, edite `header.php` para adicionar `<link rel="preload" as="image" href="...">` da imagem do banner
      4. Se usar Elementor/Divi, marque a imagem hero como "prioridade alta" nas configurações da seção
    nextjs: |
      1. Substitua `<img>` por `next/image` com `priority`:
         ```tsx
         import Image from 'next/image'
         <Image src="/hero.jpg" alt="..." width={1200} height={600} priority />
         ```
      2. Configure `next.config.js` com `images.formats: ['image/avif', 'image/webp']`
      3. Para imagens externas, adicione domínio em `images.remotePatterns`
    shopify: |
      1. Use a tag Liquid `{{ image | image_url: width: 1200 | image_tag: loading: 'eager', fetchpriority: 'high' }}`
      2. Habilite **Online Store → Themes → Settings → Image optimization**
      3. No `theme.liquid`, adicione `<link rel="preload" as="image" href="{{ ... }}">` para a imagem hero
  links_referencia:                       # opcional: links para docs externas no rodapé do accordion
    - titulo: "web.dev — Optimize LCP"
      url: "https://web.dev/articles/optimize-lcp"
    - titulo: "web.dev — Modern image formats"
      url: "https://web.dev/articles/uses-webp-images"
```

### 2.3 Schema Pydantic de validação (`app/services/cwv_kb.py`)

```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator

Plataforma = Literal["geral", "vtex", "wordpress", "nextjs", "shopify", "wix", "magento"]
Metrica = Literal["LCP", "CLS", "INP", "TBT", "FCP", "TTFB"]


class LinkReferencia(BaseModel):
    titulo: str
    url: str


class EntradaKB(BaseModel):
    codigo: str = Field(pattern=r"^[a-z0-9-]+$", min_length=3, max_length=80)
    titulo: str = Field(min_length=5, max_length=200)
    severidade: int = Field(ge=1, le=5)
    metricas_afetadas: list[Metrica] = Field(min_length=1)
    audits_lighthouse: list[str] = Field(default_factory=list)
    descricao: str = Field(min_length=20)
    solucoes: dict[Plataforma, str]
    links_referencia: list[LinkReferencia] = Field(default_factory=list)

    @field_validator("solucoes")
    @classmethod
    def precisa_solucao_geral(cls, v: dict) -> dict:
        if "geral" not in v:
            raise ValueError("Toda entrada precisa de solução 'geral'")
        return v


class BaseKB(BaseModel):
    entradas: list[EntradaKB]

    @field_validator("entradas")
    @classmethod
    def codigos_unicos(cls, v: list[EntradaKB]) -> list[EntradaKB]:
        codigos = [e.codigo for e in v]
        dup = {c for c in codigos if codigos.count(c) > 1}
        if dup:
            raise ValueError(f"Códigos duplicados na KB: {dup}")
        return v
```

### 2.4 Loader com cache

```python
# app/services/cwv_kb.py
from functools import lru_cache
from pathlib import Path
import yaml

KB_PATH = Path(__file__).parent.parent / "data" / "cwv_knowledge_base.yaml"


@lru_cache(maxsize=1)
def carregar_kb() -> BaseKB:
    with open(KB_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return BaseKB(entradas=raw)


def buscar_entrada(codigo: str) -> dict | None:
    kb = carregar_kb()
    for entrada in kb.entradas:
        if entrada.codigo == codigo:
            return entrada.model_dump()
    return None


def listar_kb_codigos() -> list[dict]:
    """Retorna lista de {codigo, titulo, metricas_afetadas} pro prompt do Analisador."""
    kb = carregar_kb()
    return [
        {"codigo": e.codigo, "titulo": e.titulo, "metricas_afetadas": e.metricas_afetadas}
        for e in kb.entradas
    ]


def mapeamento_audit_kb() -> dict[str, str]:
    """Retorna dict {audit_lighthouse_id: kb_codigo} pra fast-path do Analisador.

    Se o mesmo audit aparece em múltiplas entradas, usa a primeira (mais específica deve vir antes).
    """
    kb = carregar_kb()
    mapa = {}
    for entrada in kb.entradas:
        for audit in entrada.audits_lighthouse:
            if audit not in mapa:  # primeira ocorrência ganha
                mapa[audit] = entrada.codigo
    return mapa


def recarregar_kb() -> None:
    """Limpa cache — chamar em hot-reload de dev ou comando admin."""
    carregar_kb.cache_clear()
```

### 2.5 Validação no boot

Em `app/main.py`, no startup event:

```python
@app.on_event("startup")
async def validar_kb():
    from app.services.cwv_kb import carregar_kb
    try:
        kb = carregar_kb()
        logger.info("KB Core Web Vitals carregada: %d entradas", len(kb.entradas))
    except Exception as e:
        logger.error("KB CWV inválida — ferramenta NÃO funcionará: %s", e)
        # Não derruba o app; só loga. CWV vai falhar com erro claro se chamada.
```

## 3. Conteúdo inicial (V1)

Lista mínima de **35 entradas** cobrindo os audits mais frequentes do Lighthouse. Agrupados por métrica:

### 3.1 LCP — Largest Contentful Paint (8 entradas)

| Código | Audits Lighthouse | Severidade |
|---|---|---|
| `lcp-imagem-grande` | `largest-contentful-paint-element`, `uses-optimized-images`, `modern-image-formats` | 5 |
| `lcp-imagem-sem-dimensoes` | `unsized-images` | 4 |
| `lcp-imagem-lazy-load` | `lcp-lazy-loaded` | 5 |
| `lcp-preload-faltando` | `uses-rel-preload` | 4 |
| `lcp-fonte-bloqueante` | `font-display`, `preload-fonts` | 4 |
| `lcp-ttfb-alto` | `server-response-time` | 4 |
| `lcp-script-no-head` | `render-blocking-resources` | 4 |
| `lcp-css-bloqueante` | `unminified-css`, `unused-css-rules` | 3 |

### 3.2 CLS — Cumulative Layout Shift (6 entradas)

| Código | Audits Lighthouse | Severidade |
|---|---|---|
| `cls-imagem-sem-dimensoes` | `unsized-images` | 5 |
| `cls-fonte-web-flash` | `font-display` | 4 |
| `cls-ad-injetado` | `non-composited-animations` | 3 |
| `cls-iframe-sem-dimensoes` | (heurística sobre `layout-shift-elements`) | 4 |
| `cls-conteudo-injetado-dinamicamente` | `layout-shift-elements` | 4 |
| `cls-animacao-sem-transform` | `non-composited-animations` | 3 |

### 3.3 INP/TBT — Interatividade (7 entradas)

| Código | Audits Lighthouse | Severidade |
|---|---|---|
| `js-bundle-grande` | `total-byte-weight`, `unused-javascript` | 4 |
| `js-bloqueante-thirdparty` | `third-party-summary`, `third-party-facades` | 5 |
| `js-long-task` | `long-tasks`, `mainthread-work-breakdown` | 4 |
| `js-execucao-pesada-no-load` | `bootup-time` | 4 |
| `dom-muito-grande` | `dom-size` | 3 |
| `event-handler-pesado` | (derivado de `total-blocking-time`) | 4 |
| `polyfill-desnecessario` | `legacy-javascript` | 3 |

### 3.4 FCP/TTFB — Renderização inicial (5 entradas)

| Código | Audits Lighthouse | Severidade |
|---|---|---|
| `fcp-render-blocking` | `render-blocking-resources` | 4 |
| `fcp-critical-path-longo` | `critical-request-chains` | 3 |
| `ttfb-sem-cache-cdn` | `uses-long-cache-ttl`, `efficient-animated-content` | 4 |
| `ttfb-redirect-chain` | `redirects` | 3 |
| `ttfb-compress-faltando` | `uses-text-compression` | 4 |

### 3.5 Higiene técnica (5 entradas)

| Código | Audits Lighthouse | Severidade |
|---|---|---|
| `https-mixed-content` | `is-on-https` | 5 |
| `viewport-faltando` | `viewport` | 5 |
| `imagens-sem-alt` | `image-alt` | 2 (a11y) |
| `links-quebrados` | (não detectado por Lighthouse; pode adiar) | — |
| `meta-description-faltando` | `meta-description` | 2 |

### 3.6 Cauda longa (4 entradas)

Para casos não cobertos diretamente, mas detectáveis:

| Código | Origem |
|---|---|
| `cache-headers-inadequados` | `uses-long-cache-ttl` |
| `js-passive-listeners-faltando` | `uses-passive-event-listeners` |
| `cookies-thirdparty` | `third-party-cookies` |
| `outros` | Fallback genérico quando LLM não encontra match |

### 3.7 Plataformas suportadas no V1

Cada entrada deve ter solução pra:
- `geral` (obrigatório, fallback)
- `vtex` (alta prioridade — clientes target do SaaS)
- `wordpress` (alta prioridade — bem comum)
- `nextjs` (média prioridade)
- `shopify` (média prioridade)

Plataformas `wix`/`magento` são opcionais no V1; caem no `geral` se faltarem.

## 4. Processo de manutenção

### 4.1 Quando adicionar entradas

- Lighthouse lançou audit novo (acompanhar release notes a cada update major do Chrome)
- Aparece audit em análise real que cai em fallback `outros` repetidamente (queries log)
- Usuário reporta problema relevante não coberto

### 4.2 Quando atualizar entradas

- Plataforma muda de API/componente (ex: VTEX libera novo image component)
- Best practice da W3C/web.dev muda (ex: troca de recomendação `preload` → `fetchpriority`)
- Texto da solução fica confuso (sinal: usuário fez ticket)

### 4.3 Quando remover entradas

- Audit foi removido do Lighthouse (raro)
- Consolidar duplicatas

### 4.4 Fluxo de PR

1. Editar `app/data/cwv_knowledge_base.yaml`
2. Rodar `pytest tests/unit/test_cwv_kb.py -k validacao` (valida schema + checa duplicatas)
3. PR com label `cwv-kb`
4. Review focado em: clareza do texto, links válidos, código de plataforma correto
5. Merge dispara cache invalidation no próximo deploy (loader tem `lru_cache`, próximo restart pega versão nova)

### 4.5 Observabilidade

Log estruturado quando Analisador cai em fallback `outros`:

```
{
  "event": "cwv_kb_miss",
  "audit_id": "...",
  "audit_title": "...",
  "url": "..."
}
```

Dashboard mensal: top 10 audits com mais `kb_miss` → priorizar adição.

## 5. Testes

### 5.1 `tests/unit/test_cwv_kb.py`

```python
def test_kb_carrega_sem_erro():
    from app.services.cwv_kb import carregar_kb
    kb = carregar_kb()
    assert len(kb.entradas) >= 30  # garantia de baseline mínimo


def test_kb_codigos_unicos():
    from app.services.cwv_kb import carregar_kb
    kb = carregar_kb()
    codigos = [e.codigo for e in kb.entradas]
    assert len(codigos) == len(set(codigos))


def test_kb_toda_entrada_tem_solucao_geral():
    from app.services.cwv_kb import carregar_kb
    kb = carregar_kb()
    for e in kb.entradas:
        assert "geral" in e.solucoes
        assert len(e.solucoes["geral"]) > 30


def test_kb_metricas_afetadas_validas():
    from app.services.cwv_kb import carregar_kb
    kb = carregar_kb()
    validas = {"LCP", "CLS", "INP", "TBT", "FCP", "TTFB"}
    for e in kb.entradas:
        assert set(e.metricas_afetadas).issubset(validas)


def test_mapeamento_audit_kb_consistente():
    from app.services.cwv_kb import mapeamento_audit_kb
    mapa = mapeamento_audit_kb()
    # Todo audit declarado deve mapear pra um código existente
    from app.services.cwv_kb import carregar_kb
    codigos = {e.codigo for e in carregar_kb().entradas}
    for audit, kb_codigo in mapa.items():
        assert kb_codigo in codigos


def test_buscar_entrada_existente():
    from app.services.cwv_kb import buscar_entrada
    e = buscar_entrada("lcp-imagem-grande")
    assert e is not None
    assert e["severidade"] == 5


def test_buscar_entrada_inexistente_retorna_none():
    from app.services.cwv_kb import buscar_entrada
    assert buscar_entrada("codigo-fake-que-nao-existe") is None
```

### 5.2 `tests/unit/test_cwv_documentador.py`

Testa formatação determinística:
- KB hit + plataforma conhecida → markdown tem seção "Para sua plataforma"
- KB hit + plataforma desconhecida → só mostra solução geral
- KB miss (código inválido) → entrada é ignorada, não quebra

## 6. Plano de execução

### Fase A — Schema + loader (0.5 dia)

1. Criar `app/data/` (se não existir)
2. Implementar `app/services/cwv_kb.py` com schema Pydantic + loader + helpers
3. Escrever testes de validação (`test_cwv_kb.py`)
4. Adicionar pyyaml em deps (`uv add pyyaml`)

### Fase B — Conteúdo inicial 35 entradas (3 dias de redação)

Distribuição sugerida:
- Dia 1: LCP (8) + CLS (6)
- Dia 2: INP/TBT (7) + FCP/TTFB (5)
- Dia 3: Higiene (5) + Cauda longa (4) + revisão final

Para cada entrada, redator precisa:
- Ler a doc oficial do audit no Lighthouse (https://web.dev/lighthouse-performance/)
- Escrever descrição em PT-BR clara pra leigo
- Pesquisar solução específica de cada plataforma (web.dev, docs VTEX, docs WP, docs Next)
- Validar links de referência

Estimativa: ~45 min por entrada × 35 = ~26h. Pode ser paralelizado entre 2 pessoas.

### Fase C — Validação manual (0.5 dia)

1. Rodar análise real em 5 URLs variadas (e-commerce VTEX, blog WP, app Next, landing Shopify)
2. Confirmar que todo audit falho mapeia pra KB ou cai em `outros`
3. Ajustar entradas onde texto fica confuso/genérico
4. Validar acordion renderiza markdown corretamente (ver [[SPEC_CWV_Dashboard_Historico]])

## 7. Não-objetivos

- Tradução automática para outros idiomas (V2)
- Geração de KB via LLM a partir de docs (sempre humano-revisado)
- Versionamento por entrada (toda KB é versionada via git; não precisa de v1/v2 por código)
- UI admin pra editar KB (editar via PR no git é suficiente; baixo volume de edits)

## 8. Critério de pronto

- `app/data/cwv_knowledge_base.yaml` existe com ≥30 entradas validadas
- `app/services/cwv_kb.py` carrega + valida no boot sem erros
- Testes passam: schema, unicidade, completude
- 5 URLs reais analisadas: pelo menos 80% dos audits falhos foram mapeados pra códigos KB (não `outros`)
- Markdown gerado pelo Documentador renderiza corretamente no accordion (sem escapes quebrados)
- Documentação inline da KB (este arquivo) está consistente com o YAML real

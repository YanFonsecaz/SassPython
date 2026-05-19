# SPEC — Inlinks: pular cabeçalhos, comparador lado a lado e entrada no sidebar

**Status:** pendente · **Escopo:** backend + frontend · **Migration?** não · **Crédito:** não muda

## 1. Resumo

Três entregas independentes, todas em torno da ferramenta `inlinks_automaticos`:

- **A. Não injetar dentro de cabeçalhos.** O injector deve pular candidatos cuja âncora caia em uma linha que comece com `^#{1,6}\s` (ATX). O ancorador (LLM) também recebe instrução pra evitar âncoras dentro de títulos.
- **B. Comparador lado a lado.** Persistir o pilar original em `resultado_json.pilar_original` e renderizar uma view de duas colunas (original × modificado) com inlinks destacados na coluna direita.
- **C. Entrada no sidebar.** Adicionar item "Inlinks" abaixo de "Gerar Artigo" no `NAV_ITEMS`.

Total: 3 arquivos backend, 3 arquivos frontend, 1 teste novo. Sem migration, sem mudança de schema, sem mudança de créditos.

## 2. Entrega A — Pular cabeçalhos no injector

### Sintoma

`versoes_artigo.conteudo_markdown` da execução `6e823d6e-2f3a-446e-9b09-3405382613ec` contém:
```
## Por que é importante [construir um portfólio](https://.../curriculo-programacao) desde o início?
```

Inlinks dentro de `<h1>`/`<h2>`/etc. são considerados má prática de SEO (alteram semântica do título e podem afetar como o Google indexa).

### Causa raiz

`backend/app/agents/inlinks/injector.py`, função `injetar_inlinks` (linhas 124-227): o match da âncora não considera o contexto da linha. O ancorador, em `app/agents/inlinks/ancorador.py`, recebe o pilar markdown completo (incluindo `##`) e às vezes escolhe trechos que estão dentro de uma linha de cabeçalho.

**Confirmado via DB**: trafilatura **preserva** cabeçalhos ATX (`## Título`) no markdown extraído — não foi conjectura.

### Solução

#### Backend — injector.py

Adicionar helper privado (junto às outras funções utilitárias do arquivo):

```python
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")


def _esta_em_cabecalho(texto: str, offset: int) -> bool:
    """True se a linha que contém `offset` for um cabeçalho ATX (`#`..`######`).

    Usa a fronteira de linha mais próxima antes/depois do offset. Não trata
    headings setext (`Titulo\\n===`) — raríssimos em saída de trafilatura,
    documentados como edge não coberto.
    """
    inicio_linha = texto.rfind("\n", 0, offset) + 1
    fim_linha = texto.find("\n", offset)
    if fim_linha < 0:
        fim_linha = len(texto)
    linha = texto[inicio_linha:fim_linha]
    return bool(_HEADING_RE.match(linha))
```

Em `injetar_inlinks`, dentro do loop que itera `ancoras` (logo após o `hit = _search_tolerant(...)` ter sucesso, **antes** de montar o `match_info`):

```python
for anchor in ancoras:
    if not anchor:
        continue
    hit = _search_tolerant(pilar_markdown, anchor)
    if hit:
        start, end, matched_text = hit
        if _esta_em_cabecalho(pilar_markdown, start):
            continue  # tentar a próxima opção de âncora deste candidato
        match_info = { ... }  # bloco existente, sem alteração
        break
```

Comportamento: se todas as `ancoras_opcoes` daquele candidato caírem em cabeçalho, o candidato é descartado silenciosamente (mesmo padrão atual quando nenhuma âncora casa).

#### Backend — ancorador.py (defesa em profundidade)

Em `backend/app/agents/inlinks/ancorador.py`, dentro do prompt (na lista de "REGRAS CRÍTICAS"), adicionar uma regra logo após "Evite trechos genéricos como 'clique aqui' ou 'saiba mais'":

```
- NÃO escolha trechos que estejam DENTRO de cabeçalhos (linhas iniciadas por `#`, `##`, `###` etc.). Cabeçalhos têm semântica especial e não devem virar âncora de inlink.
```

### Testes (Entrega A)

Adicionar em `backend/tests/test_inlinks_injector.py` (arquivo já existe):

```python
from app.agents.inlinks.injector import _esta_em_cabecalho, injetar_inlinks


def test_detecta_heading_atx():
    md = "Texto comum.\n\n## Título com palavra-chave aqui\n\nMais texto."
    pos_h2 = md.index("palavra-chave")
    pos_normal = md.index("Texto comum")
    assert _esta_em_cabecalho(md, pos_h2) is True
    assert _esta_em_cabecalho(md, pos_normal) is False


def test_detecta_h1_a_h6():
    for prefixo in ["#", "##", "###", "####", "#####", "######"]:
        md = f"{prefixo} Cabeçalho aqui"
        assert _esta_em_cabecalho(md, md.index("aqui")) is True


def test_nao_confunde_hashtag_inline():
    md = "Use a hashtag #python no Twitter."
    assert _esta_em_cabecalho(md, md.index("python")) is False


def test_injector_pula_candidato_em_cabecalho():
    md = (
        "Antes do título.\n\n"
        "## Por que é importante construir um portfólio desde o início?\n\n"
        "Construir um portfólio leva tempo, mas vale a pena no longo prazo."
    )
    candidatos = [{
        "url": "https://ex.com/portfolio",
        "titulo": "Guia de portfólio",
        "ancoras_opcoes": ["construir um portfólio"],  # aparece no H2 E no parágrafo
        "score_total": 0.8, "score_semantico": 0.85, "score_contexto": 0.75,
    }]
    modificado, injetados = injetar_inlinks(md, candidatos)
    # A primeira ocorrência (no H2) deve ser descartada; a segunda (no parágrafo) usada
    assert "## Por que é importante construir um portfólio desde o início?" in modificado
    assert "[construir um portfólio](https://ex.com/portfolio)" in modificado
    assert len(injetados) == 1
    assert injetados[0].paragrafo_idx >= 2  # parágrafo, não cabeçalho
```

> **Atenção ao implementar:** o `_search_tolerant` atual retorna a **primeira** ocorrência. Se a primeira está em cabeçalho, hoje o código pula a âncora inteira — mas a regra-chave (não inserir em heading) já é cumprida.
>
> Para o teste `test_injector_pula_candidato_em_cabecalho` passar como escrito (achar a 2ª ocorrência fora do heading), o `_search_tolerant` precisa suportar `start_from: int = 0`. Sugestão: implementar essa parametrização junto com a Entrega A. **O teste do helper `_esta_em_cabecalho` passa de qualquer forma.**

## 3. Entrega B — Comparador lado a lado

### Backend — workflow_inlinks.py

Em `backend/app/agents/workflow_inlinks.py`, função `node_persistir`, no dict `resultado_final` (linhas ~444-462), adicionar `pilar_original`:

```python
resultado_final = {
    "n_candidatas_validas": n_validas,
    "n_aplicadas": n_aplicados,
    "n_rejeitadas": n_rejeitados,
    "top_scores": top_scores,
    "artigo_titulo": estado.get("pilar_resultado", {}).get("titulo", ""),
    "artigo": pilar_modificado,
    "conteudo_markdown": pilar_modificado,
    "pilar_original": pilar_original,  # NOVO — variável já existe (linha ~387)
    "imagem_url": None,
    "inlinks": inlinks,
}
```

Idem em `_extrair_resultado_inlinks` (mesmo arquivo, função no fim), adicionar `"pilar_original": estado.get("pilar_resultado", {}).get("conteudo_md", "")` ao dict de fallback.

Sem migration, sem mudança de schema — `resultado_json` é JSONB.

### Frontend — types

Em `frontend/src/types/ferramenta.ts`, no `interface ResultadoInlinks`, adicionar:

```ts
export interface ResultadoInlinks {
  // ... campos existentes
  pilar_original: string;
}
```

### Frontend — novo componente

Criar `frontend/src/components/ferramentas/comparador-pilar-inlinks.tsx`:

```tsx
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { CopyIcon, CheckIcon } from "lucide-react";
import { useState } from "react";

interface Props {
  titulo: string;
  pilarOriginal: string;
  pilarModificado: string;
  qtdInlinksAplicados: number;
}

export function ComparadorPilarInlinks({
  titulo,
  pilarOriginal,
  pilarModificado,
  qtdInlinksAplicados,
}: Props) {
  const [copiado, setCopiado] = useState(false);

  async function copiarFinal() {
    try {
      await navigator.clipboard.writeText(`# ${titulo}\n\n${pilarModificado}`);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <section className="rounded-2xl border bg-card overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-border">
        <div>
          <h3 className="font-heading text-base font-semibold">Comparar pilar</h3>
          <p className="text-xs text-muted-foreground">
            {qtdInlinksAplicados} inlink{qtdInlinksAplicados === 1 ? "" : "s"} adicionado
            {qtdInlinksAplicados === 1 ? "" : "s"} · destacados na coluna da direita
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={copiarFinal}>
          {copiado ? (
            <><CheckIcon className="size-3.5" />Copiado</>
          ) : (
            <><CopyIcon className="size-3.5" />Copiar final</>
          )}
        </Button>
      </header>

      <div className="grid gap-0 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border">
        <ColunaPilar rotulo="Original" conteudo={pilarOriginal} variant="original" />
        <ColunaPilar rotulo="Com inlinks" conteudo={pilarModificado} variant="modificado" />
      </div>
    </section>
  );
}

function ColunaPilar({
  rotulo,
  conteudo,
  variant,
}: {
  rotulo: string;
  conteudo: string;
  variant: "original" | "modificado";
}) {
  return (
    <div className="flex flex-col">
      <div className="px-5 py-2 border-b border-border bg-surface-light text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {rotulo}
      </div>
      <div className="prose prose-sm max-w-none px-5 py-5 overflow-y-auto max-h-[70vh]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={
            variant === "modificado"
              ? {
                  a: ({ node, ...props }) => (
                    <a
                      {...props}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded bg-brand/15 px-1 py-0.5 font-medium text-brand-dark underline decoration-brand/40 underline-offset-2 hover:bg-brand/25"
                    />
                  ),
                }
              : undefined
          }
        >
          {conteudo}
        </ReactMarkdown>
      </div>
    </div>
  );
}
```

Notas:
- Em viewports `< lg` (mobile), as colunas empilham verticalmente automaticamente.
- A coluna da direita estiliza `<a>` tags para que os inlinks fiquem visualmente óbvios. A coluna da esquerda usa o estilo padrão do `prose`.
- `max-h-[70vh] overflow-y-auto` evita que um pilar muito longo estoure a página; cada coluna rola independentemente.

### Frontend — montagem

Em `frontend/src/components/ferramentas/execucao-detalhe-conteudo.tsx`:

1. Importar `ComparadorPilarInlinks`.
2. Substituir o bloco que renderiza `<PreviewArtigo …/>` para a ferramenta `inlinks_automaticos` (manter `PreviewArtigo` para outras ferramentas).

Diff conceitual:

```tsx
{(isAguardando || execucao.status === "concluida") && artigoConteudo && (
  execucao.ferramenta === "inlinks_automaticos" ? (
    <ComparadorPilarInlinks
      titulo={artigoTitulo}
      pilarOriginal={(resultado.pilar_original as string) || ""}
      pilarModificado={artigoConteudo}
      qtdInlinksAplicados={
        Array.isArray(resultado.inlinks)
          ? (resultado.inlinks as InlinkAplicado[]).filter((i) => i.status === "aplicado").length
          : 0
      }
    />
  ) : (
    <PreviewArtigo
      titulo={artigoTitulo}
      conteudo={artigoConteudo}
      imagemUrl={imagemUrl || undefined}
    />
  )
)}
```

## 4. Entrega C — Entrada no sidebar

Em `frontend/src/components/layout/sidebar.tsx`:

1. Adicionar `Link2Icon` ao import de `lucide-react`:
   ```ts
   import {
     // ... existentes
     Link2Icon,
   } from "lucide-react";
   ```
2. No array `NAV_ITEMS` (linha 28-35), inserir item **logo abaixo** de "Gerar Artigo":
   ```ts
   const NAV_ITEMS: NavItem[] = [
     { href: "/ferramentas", label: "Dashboard", icon: LayoutDashboardIcon },
     { href: "/ferramentas/gerar-artigo", label: "Gerar Artigo", icon: PenToolIcon },
     { href: "/ferramentas/inlinks", label: "Inlinks", icon: Link2Icon },  // NOVO
     { href: "/ferramentas/historico", label: "Histórico", icon: ClockIcon },
     // ...
   ];
   ```

A rota `/ferramentas/inlinks` já existe (`frontend/src/app/(app)/ferramentas/inlinks/page.tsx`), nada mais é necessário. O sidebar mobile usa o mesmo `NAV_ITEMS` (não há arquivo separado).

## 5. Verificação ponta a ponta

1. Backend: rodar `pytest backend/tests/test_inlinks_injector.py` (ou execução direta via `python3 -c …` se o `conftest.py` estiver com problema pré-existente de fixture async).
2. Reiniciar `uvicorn` e o worker `arq` para carregar o código novo.
3. Submeter execução nova com a mesma entrada do teste anterior:
   - Pilar: `https://www.hashtagtreinamentos.com/como-comecar-trabalhar-com-programacao`
   - Candidatas: 4 URLs do `hashtagtreinamentos.com` (`/roadmap-programacao`, `/curriculo-programacao`, `/melhor-linguagem-de-programacao-iniciantes`, `/qual-a-linguagem-de-programacao-mais-facil-python`).
4. Após `concluida`, verificar via SQL:
   ```sql
   SELECT conteudo_markdown FROM versoes_artigo WHERE execucao_id = '…';
   -- não deve conter `## ... [...](...) ...` (link dentro de heading)

   SELECT resultado_json->>'pilar_original' FROM execucoes_ferramentas WHERE id = '…';
   -- deve trazer o markdown original sem inlinks
   ```
5. Frontend: rodar `npm run dev` no `frontend/`, abrir `/ferramentas/historico/<id>`. Conferir:
   - Comparador renderiza em duas colunas em desktop e empilhado em mobile.
   - Coluna direita destaca os links com background `bg-brand/15`.
   - Botão "Copiar final" copia apenas o pilar com inlinks aplicados.
   - Sidebar mostra "Inlinks" como item ativo quando em `/ferramentas/inlinks`.

## 6. Fora de escopo (NÃO fazer agora)

- Detecção de cabeçalhos setext (`Titulo\n===`) — raros em saída de trafilatura.
- Diff char-a-char entre original e modificado (tipo `react-diff-viewer`) — a marcação de links na coluna direita já comunica o "o que mudou".
- Mutação de texto para inserir inlinks (decisão pendente, aguardando dados de uso).

## 7. Riscos

- **Busca de âncora só na primeira ocorrência:** se a única ocorrência da âncora estiver em um cabeçalho, o candidato é descartado mesmo que o termo apareça em texto corrido depois. Mitigação: tornar `_search_tolerant` capaz de iterar (`start_from`). Recomendado implementar junto.
- **Ancorador LLM ignorando a regra:** o prompt instrui a evitar trechos em cabeçalhos, mas LLM pode falhar. O injector é a rede de proteção final.
- **`pilar_original` em `resultado_json`:** vai engordar o JSONB em ~5–30 KB por execução. Aceitável (tabela `execucoes_ferramentas` já guarda artigo modificado de tamanho similar).
- **Componente `prose` Tailwind:** depende de `@tailwindcss/typography`. Verificar `frontend/tailwind.config.*` antes de implementar; se não estiver, trocar `prose prose-sm max-w-none` por estilos manuais (`text-sm leading-relaxed [&>h2]:font-semibold [&>h2]:mt-4 [&>p]:mt-2` etc.).

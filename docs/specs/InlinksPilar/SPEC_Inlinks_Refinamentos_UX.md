# SPEC — Inlinks: refinamentos de UX (densidade, conector, formatação, cópia)

**Status:** pendente · **Escopo:** backend + frontend · **Migration:** não · **Crédito:** não muda · **Depende de:** `SPEC_Inlinks_Arquitetura_IA.md` aplicada

## 1. Resumo

Quatro entregas, todas pós-arquitetura IA já operante:

- **A.** Densidade dinâmica de inlinks (4-5 por 1000 palavras).
- **B.** Refino do prompt do inseridor para detectar e suprimir conector redundante.
- **C.** Agente formatador IA — melhora estrutura do pilar (quebra parágrafos longos, adiciona sub-headings) após o inseridor.
- **D.** Botões "Copiar Markdown" e "Copiar HTML" no comparador.

Total: 3 arquivos backend alterados, 1 novo agente backend, 2 arquivos frontend alterados, 1 helper frontend novo, 1 nova dependência npm (`remark-html`).

**Fora de escopo:** treino do reranker via histórico/penalização (próxima SPEC).

## 2. Entrega A — Densidade dinâmica de inlinks

### Sintoma

`max_inlinks` é constante em 8 (defaults em `workflow_inlinks.py`). Pilar de 500 palavras com 8 links vira spam; pilar de 3000 palavras com 8 links fica sub-utilizado. A heurística SEO de mercado é **4-5 inlinks por mil palavras**.

### Mudança em `backend/app/agents/workflow_inlinks.py`

Adicionar helper no topo do módulo (após `_MIN_SEMANTIC_SCORE`):

```python
def _calcular_max_inlinks_dinamico(pilar_md: str, teto_usuario: int) -> int:
    """4-5 inlinks por 1000 palavras, clamp [2, 12], limitado pelo teto do usuário."""
    palavras = len(pilar_md.split())
    dinamico = max(2, min(12, round(palavras / 222)))
    return min(dinamico, teto_usuario)
```

Atualizar `node_inserir` (linhas 467-510) para calcular o teto **antes** de chamar `inserir_inlinks`:

```python
async def node_inserir(estado: EstadoInlinks) -> dict:
    from app.agents.inlinks.inseridor import inserir_inlinks
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "inserir", "Inserindo inlinks no texto...")

    pilar_md = estado.get("pilar_resultado", {}).get("conteudo_md", "")
    candidatos = estado.get("candidatos_reranked", [])
    teto_usuario = estado.get("max_inlinks", 8)
    max_inlinks = _calcular_max_inlinks_dinamico(pilar_md, teto_usuario)

    await publish_event(
        eid, "node_progress", "inserir",
        f"Densidade alvo: {max_inlinks} inlinks ({len(pilar_md.split())} palavras)"
    )

    pilar_modificado, inseridos = await inserir_inlinks(
        pilar_md, candidatos, estado["usuario_id"], max_inlinks=max_inlinks
    )
    # ... resto do nó igual ao atual
```

### Tabela da fórmula

| Palavras | `max_inlinks` |
|---|---|
| 444 | 2 |
| 1000 | 5 |
| 1500 | 7 |
| 2000 | 9 |
| 2664+ | 12 (clamp) |

### Frontend

Em `frontend/src/components/ferramentas/formulario-inlinks.tsx`, localizar o campo `Max inlinks` (visível no resumo da execução com label "Max inlinks") e:

- Mudar o label para **"Teto de inlinks"**.
- Adicionar dica abaixo:
  > "Calculamos automaticamente 4-5 inlinks por mil palavras do pilar. Este valor é apenas um limite superior."

Manter default 8.

## 3. Entrega B — Refino do prompt do inseridor (conector redundante)

### Sintoma observado em produção

Execução real E2E gerou:
```
Trecho contexto: "...Veja o artigo sobre Veja o[roadmap de programação](https://...)"
```
LLM escolheu trecho "roadmap de programação" + `conector_antes="Veja o"`, mas o parágrafo já dizia "Veja o artigo sobre". Resultado fica artificial.

### Mudança 1 — atualizar prompt em `backend/app/agents/inlinks/inseridor.py`

Em `_build_prompt` (linhas 85-125), **substituir a regra 4 atual** por:

```
4. Conectores opcionais para fluidez (`conector_antes`, `conector_depois`):
   até 3 palavras cada, fora da âncora. Use SÓ quando o trecho original
   ficar travado sem o conector. ANTES de propor um conector, leia as
   ~5 palavras imediatamente antes e depois do `trecho_original` no
   parágrafo. Se essas palavras já contêm verbos como "veja", "leia",
   "confira", "saiba", "assista", "descubra", "entenda" — ou
   preposições como "sobre", "em", "no", "na" — NÃO adicione conector;
   deixe os campos vazios. O trecho original já está conectado ao
   contexto.

   Exemplos de quando NÃO usar:
   - "...Veja o artigo sobre roadmap de programação..."
     → conector vazio. Já tem "Veja o artigo sobre".
   - "...para entender melhor a melhor linguagem para iniciantes..."
     → conector vazio. Já tem "para entender melhor".

   Exemplos de quando USAR:
   - "...Python e JavaScript são fáceis de aprender. C exige mais. O
     ponto principal é a legibilidade..."
     Âncora: "C exige mais" / conector_depois: " sobre ponteiros"
     → válido. O trecho fica seco sem o conector.
```

Adicionar **nova regra 10** depois da regra 9 ("Vazio é aceitável"):

```
10. Distribuição uniforme da meta de inlinks: o sistema vai aceitar no
    máximo {max_inlinks} inserções. Se houver mais candidatos do que o
    teto, prefira os mais relevantes; mas tente DISTRIBUIR ao longo
    do pilar (início, meio, fim), não concentrar em uma só seção.
```

`{max_inlinks}` é injetado dinamicamente pela Entrega A (`_build_prompt` já recebe o valor como argumento — verificar assinatura).

### Mudança 2 — defesa em profundidade em `_aplicar_insercoes`

No mesmo arquivo, antes do bloco `_aplicar_insercoes` (linha 168), adicionar:

```python
_CONECTOR_REDUNDANTE_RE = re.compile(
    r"\b(veja|leia|confira|saiba|assista|descubra|entenda|sobre|em|no|na)\b",
    re.IGNORECASE,
)


def _ha_conector_no_entorno(paragrafo: str, local_offset: int) -> bool:
    """Verifica se há conector/preposição similar nas ~30 chars antes do offset."""
    janela = paragrafo[max(0, local_offset - 30):local_offset]
    return bool(_CONECTOR_REDUNDANTE_RE.search(janela))
```

Dentro do loop principal de `_aplicar_insercoes`, depois de definir `local_offset` e antes do append em `validas`, adicionar:

```python
conector_antes = _truncate_conector(ins.get("conector_antes", ""))
conector_depois = _truncate_conector(ins.get("conector_depois", ""))

# Defesa: se LLM propôs conector_antes redundante, limpar
if conector_antes and _ha_conector_no_entorno(paragrafo, local_offset):
    conector_antes = ""
```

Não rejeitar a inserção — só limpar o conector. A inserção pura (sem conector) costuma ser perfeitamente válida.

## 4. Entrega C — Agente formatador IA

### Sintoma

Comparador lado a lado mostra parágrafos muito longos e mudanças de tema sem H3, prejudicando legibilidade do resultado final.

### Arquivo novo `backend/app/agents/inlinks/formatador.py`

```python
import json
import logging
import re

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")


def _count_links(md: str) -> int:
    return len(_LINK_RE.findall(md))


async def formatar_pilar(markdown: str, usuario_id: str) -> str:
    """Refina estrutura do markdown sem mudar conteúdo nem links.

    Quebra parágrafos longos (>120 palavras) em pontos finais naturais,
    adiciona sub-headings H3 onde temas mudam, preserva todos os links
    markdown `[texto](url)` exatamente como estão. Não inventa texto.
    Fallback: retorna o markdown original em caso de falha ou se o
    LLM alterou a contagem de links.
    """
    if not markdown or not markdown.strip():
        return markdown

    agente = _FormatadorAgent(usuario_id)
    prompt = _build_prompt(markdown)
    try:
        resposta = await agente._invoke_llm(prompt)
        formatado = _parse(resposta)
        if formatado and _count_links(formatado) == _count_links(markdown):
            return formatado
        if formatado:
            logger.warning(
                "Formatador alterou número de links (%d -> %d); usando original",
                _count_links(markdown), _count_links(formatado),
            )
    except Exception as e:
        logger.warning("Formatador falhou: %s", e)
    return markdown


class _FormatadorAgent(BaseAgent):
    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content


def _build_prompt(markdown: str) -> str:
    return f"""Você é um editor focado em legibilidade. Recebe um markdown de artigo
(já com inlinks aplicados) e devolve uma versão com MELHOR ESTRUTURA, sem mudar
o significado.

REGRAS:
1. Quebre parágrafos com mais de 120 palavras em parágrafos menores,
   nos pontos finais naturais (depois de "."). Não corte uma sentença
   no meio.
2. Onde o tema muda claramente, adicione um sub-heading `### Título`
   curto (3-6 palavras). Use no máximo 1 sub-heading novo a cada
   ~400 palavras.
3. NÃO mude o texto das frases. NÃO traduza. NÃO reescreva. Apenas
   reorganize a estrutura.
4. PRESERVE TODOS os links markdown `[texto](url)` exatamente como
   estão — mesma palavra-texto, mesma URL, na mesma sequência.
5. NÃO adicione listas, citações, blocos de código novos. Mantenha
   listas e blocos de código existentes.
6. Mantenha os headings existentes (H1, H2). Pode adicionar H3
   conforme regra 2, nunca remover headings.

Saída APENAS em JSON:
{{"markdown_formatado": "..."}}

Markdown original:
<<<
{markdown}
>>>"""


def _parse(response: str) -> str | None:
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            md = data.get("markdown_formatado", "")
            if md and len(md.strip()) > 50:
                return md
    except (json.JSONDecodeError, ValueError):
        pass
    return None
```

### Integração no workflow

Em `backend/app/agents/workflow_inlinks.py`, adicionar novo nó `node_formatar` ENTRE `revisar` e `persistir`:

```python
async def node_formatar(estado: EstadoInlinks) -> dict:
    from app.agents.inlinks.formatador import formatar_pilar
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "formatar", "Formatando texto final...")

    pilar_mod = estado.get("pilar_modificado", "")
    pilar_formatado = await formatar_pilar(pilar_mod, estado["usuario_id"])

    n_antes = len([p for p in pilar_mod.split("\n\n") if p.strip()])
    n_depois = len([p for p in pilar_formatado.split("\n\n") if p.strip()])
    await publish_event(
        eid, "node_complete", "formatar",
        f"Formatação aplicada: {n_antes} → {n_depois} parágrafos"
    )
    return _sanitize({"pilar_modificado": pilar_formatado})
```

Atualizar `criar_workflow_inlinks` (linhas 647-669):

```python
workflow.add_node("formatar", node_formatar)
# ... outros add_node existentes ...

# Substituir a edge atual "revisar → persistir" por:
workflow.add_edge("revisar", "formatar")
workflow.add_edge("formatar", "persistir")
```

### Por que depois do revisar?

- Revisor pode remover inlinks rejeitados; formatar antes seria retrabalho.
- Formatador só ajusta estrutura, não substância; é estável depois das filtragens.

### Por que sanity check de contagem de links?

LLM pode "limpar demais" e remover links junto. `_count_links` antes/depois protege contra isso — se a contagem mudou, abortamos e usamos o markdown pré-formatação.

## 5. Entrega D — Copiar Markdown E Copiar HTML

### Dependência

```bash
cd frontend && npm install remark-html
```

`remark-html` integra com `remark` + `remark-gfm` (já em uso no projeto via `react-markdown`).

### Helper novo `frontend/src/lib/markdown.ts`

```typescript
import { remark } from "remark";
import remarkGfm from "remark-gfm";
import remarkHtml from "remark-html";

export async function markdownToHtml(md: string): Promise<string> {
  const resultado = await remark()
    .use(remarkGfm)
    .use(remarkHtml, { sanitize: false })
    .process(md);
  return String(resultado);
}
```

### Modificar `frontend/src/components/ferramentas/comparador-pilar-inlinks.tsx`

Substituir o estado e a função existentes (linhas 22-32) por:

```tsx
const [copiadoTipo, setCopiadoTipo] = useState<"md" | "html" | null>(null);

async function copiarMarkdown() {
  try {
    await navigator.clipboard.writeText(`# ${titulo}\n\n${pilarModificado}`);
    setCopiadoTipo("md");
    setTimeout(() => setCopiadoTipo(null), 2000);
  } catch {
    /* ignore */
  }
}

async function copiarHtml() {
  try {
    const { markdownToHtml } = await import("@/lib/markdown");
    const html = await markdownToHtml(`# ${titulo}\n\n${pilarModificado}`);
    await navigator.clipboard.writeText(html);
    setCopiadoTipo("html");
    setTimeout(() => setCopiadoTipo(null), 2000);
  } catch {
    /* ignore */
  }
}
```

Substituir o botão único (linhas 52-58) por:

```tsx
<div className="flex items-center gap-2">
  <Button variant="outline" size="sm" onClick={copiarMarkdown}>
    {copiadoTipo === "md" ? (
      <><CheckIcon className="size-3.5" />Copiado</>
    ) : (
      <><CopyIcon className="size-3.5" />Copiar Markdown</>
    )}
  </Button>
  <Button variant="outline" size="sm" onClick={copiarHtml}>
    {copiadoTipo === "html" ? (
      <><CheckIcon className="size-3.5" />Copiado</>
    ) : (
      <><CopyIcon className="size-3.5" />Copiar HTML</>
    )}
  </Button>
</div>
```

Import dinâmico (`await import("@/lib/markdown")`) garante que `remark-html` só é baixado quando o usuário clica em "Copiar HTML", evitando inflar o bundle inicial.

### Sanitização

`sanitize: false` preserva atributos `target`/`rel` dos links se houver. Não há risco de XSS porque o markdown vem do pipeline IA controlado, não de input do usuário final. Se quiser ser defensivo, mudar para `sanitize: true` (sanitizer padrão do remark).

## 6. Verificação ponta a ponta

### Build e restart

```bash
# Backend
pkill -f uvicorn; pkill -f arq
cd backend && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
cd backend && nohup python3 -m arq app.worker.WorkerSettings > /tmp/arq.log 2>&1 &

# Frontend
cd frontend && npm install
npm run build && cp -r out/* ../backend/static/
```

### Casos de teste

1. **Densidade dinâmica — pilar curto (~500 palavras):**
   - Submeter via UI um pilar de 400-600 palavras.
   - `grep "Densidade alvo" /tmp/arq.log` deve mostrar valor 2.
   - UI exibe no máximo 2 inlinks aplicados.

2. **Densidade dinâmica — pilar longo (~2000 palavras):**
   - URLs do hashtagtreinamentos (mesmas do E2E anterior).
   - `grep "Densidade alvo" /tmp/arq.log` deve mostrar ~9.
   - UI exibe inlinks distribuídos por início, meio e fim do pilar.

3. **Conector redundante:**
   - Mesma execução do hashtagtreinamentos.
   - No comparador (UI), na coluna "Com inlinks", NÃO deve haver string "Veja o ...Veja o[link]" ou similar.
   - Query DB:
     ```sql
     SELECT anchor_text, conector_antes, trecho_contexto
     FROM inlinks_sugeridos
     WHERE execucao_id = '<eid>' AND status='aplicado';
     ```
     `conector_antes` deve vir `NULL`/vazio quando o `trecho_contexto` mostra preposição/verbo nas ~5 palavras anteriores à âncora.

4. **Formatador:**
   - `grep "Formatação aplicada" /tmp/arq.log` mostra `N → M parágrafos` com `M > N`.
   - Comparar lado a lado UI: a coluna "Com inlinks" tem mais parágrafos quebrados e pode ter `### Subtítulos` adicionados.
   - Contagem de links no markdown final = `n_aplicadas` da execução. Se não bater, o formatador foi abortado — checar `grep "Formatador alterou" /tmp/arq.log`.

5. **Copiar Markdown:**
   - Clicar "Copiar Markdown" no comparador.
   - Colar em editor de texto: vê `# Título`, `[texto](url)`, parágrafos crus.

6. **Copiar HTML:**
   - Clicar "Copiar HTML".
   - Colar em editor de texto: vê `<h1>`, `<p>`, `<a href="...">…</a>`.
   - Colar em editor visual (WordPress, Notion, Google Docs com paste-as-HTML): conteúdo aparece renderizado.

### Smoke test combinado

Executar uma nova vez o E2E completo com 3 URLs novas (não cacheadas) — válida cold path + densidade + conector limpo + formatação + cópia, tudo num único fluxo.

## 7. Fora de escopo (próxima SPEC)

- `histórico_performance` somando ao score do reranker — função `calcular_ajuste_score` já existe em `backend/app/services/inlink_performance_service.py:86-97`, só falta integrar no `node_match_rerank`.
- `penalização_por_rejeição` baixando score de URLs com muitas rejeições humanas — mesma função acima já calcula bonus/penalização.
- Botão "Refazer este inlink" quando humano rejeita.
- Telemetria de CTR real (UTM/pixel) para alimentar evento `click`.
- Persistir HTML pronto em CDN para deep link compartilhável.

## 8. Riscos e mitigações

- **Formatador pode quebrar links:** mitigado por `_count_links` antes/depois e fallback ao markdown original se diferir.
- **Densidade alta em pilar curto:** clamp inferior é 2; mínimo aceitável. Se pilar é tão curto que 2 inlinks não cabem, o inseridor IA pode propor menos (regra "vazio é aceitável" continua válida).
- **`remark-html` infla bundle inicial:** mitigado pelo `await import` lazy — só baixa quando usuário clica "Copiar HTML".
- **Conector redundante escapar do prompt:** a heurística regex de `_ha_conector_no_entorno` zera o conector como defesa final. Defesa em profundidade.
- **LLM exagera no H3:** prompt limita "máximo 1 H3 a cada ~400 palavras"; se exceder, QA visual detecta. Não é bloqueador funcional.
- **`sanitize: false`:** sem risco prático porque markdown vem do pipeline IA, não de input externo. Trocar para `sanitize: true` se for usar markdown vindo de usuário final.

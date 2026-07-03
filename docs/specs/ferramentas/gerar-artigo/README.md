# Gerar Artigo SEO

**Estado:** ✅ implementado · **Rota:** `/ferramentas/gerar-artigo` · **Slug:** `gerar_artigo`
**Créditos:** `15` base `+ 3`/revisão (acima da 1ª versão) `+ 5` se gerar imagem — `calcular_custo_final()`
**Código:** `backend/app/agents/workflow.py` (+ agentes) · `routers/ferramentas.py` · `models/versao_artigo.py`

Primeira ferramenta do SaaS. Gera um artigo otimizado para SEO por um **pipeline de agentes**
(pesquisa → análise → brief → redação → revisão), com **aprovação humana** no meio (o usuário revisa,
dá feedback ou aprova) e, ao final, indexação vetorial + geração de imagem de capa. Persona, tom e
palavras proibidas vêm da config do **cliente** selecionado (multi-tenant).

## Arquitetura (mapa → código)

Workflow LangGraph com checkpointer Postgres (`agents/checkpointer.py`), executado no worker ARQ
(`app/worker.py`) e progresso via SSE (`core/workflow_events.py`). Nós em `agents/workflow.py`:

```
pesquisar → analisar → criar_brief → redigir → revisar
   → [revisão aprovada?]  não → (re-redige, máx. revisões)   sim ↓
   marcar_aguardando → aguardar_aprovacao   (interrupt: feedback humano, máx. rodadas)
   → salvar_vetorial → gerar_imagem → END
```

| Nó | Agente | Arquivo |
|---|---|---|
| pesquisar | Pesquisador (SerpAPI/Trends + cache) | `agents/pesquisador.py`, `models/pesquisa_cache.py` |
| analisar | Analisador | `agents/analisador.py` |
| criar_brief | Criador de brief | `agents/criador_brief.py` |
| redigir | Redator | `agents/redator.py` |
| revisar | Revisor (determinístico) | `agents/revisor.py` |
| salvar_vetorial | Embeddings → pgvector | `core/embeddings.py`, `models/conteudo_vetor.py` |
| gerar_imagem | Geração + storage | `agents/gerador_imagem.py`, `agents/imagem_storage.py` |

Cada versão revisada vira um registro em `versao_artigo`; a **cobrança é por versão final** (não por
tentativa) — ver `SPEC_Billing_Gerar_Artigo.md`.

## Decisões travadas

| Tema | Decisão |
|---|---|
| Loop redator↔revisor | Teto de revisões automáticas + teto de rodadas de feedback humano (anti-loop infinito) |
| Aprovação | **Humana no meio do grafo** via interrupt do LangGraph (não autônomo, ao contrário dos inlinks) |
| Cobrança | Por versão: `15 + (versão−1)·3 + (imagem? 5)`; falha não cobra; reserva = custo máximo estimado |
| Pesquisa externa | Sempre via cache antes de chamar API paga; pesquisador **não-bloqueante** |
| Segurança | Conteúdo do LLM nunca em `innerHTML`; prompts de sistema nunca expostos; só conteúdo aprovado vai ao vetorial |

## Não-objetivos

- Publicação automática em CMS · Geração 100% autônoma sem aprovação · Mais de 1 imagem por artigo.

## Specs

### Base
| Spec | Conteúdo | Status |
|---|---|---|
| [SPEC_Ferramenta_Agente_Redacao](SPEC_Ferramenta_Agente_Redacao.md) | Spec-mãe: regras absolutas, pipeline de agentes, estados, segurança | ✅ implementado |

### Evolução / correções (aplicadas)
| Spec | Conteúdo | Commit |
|---|---|---|
| [SPEC_Billing_Gerar_Artigo](SPEC_Billing_Gerar_Artigo.md) | Cobrança correta por versão (base+revisão+imagem) | `ddbeb88` |
| [SPEC_Pesquisador_Nao_Bloqueante](SPEC_Pesquisador_Nao_Bloqueante.md) | Pesquisador não bloqueia o event loop | `ddbeb88` |
| [SPEC_Robustez_Workflow_SSE](SPEC_Robustez_Workflow_SSE.md) | Guarda anti-loop + SSE reconecta e segue até status terminal | `ddbeb88`, `1dec212` |
| [SPEC_Revisor_Determinismo](SPEC_Revisor_Determinismo.md) | Revisor determinístico (temperatura/modelo dedicado) | aplicado |
| [SPEC_Download_Imagem_Artigo](SPEC_Download_Imagem_Artigo.md) | Download da imagem de capa gerada | aplicado |

### Histórico
- [`_historico/PLANO_Correcoes_Gerar_Artigo.md`](_historico/PLANO_Correcoes_Gerar_Artigo.md) — 🗄️ plano de correções (aplicado).

# Ferramenta "Parecer Técnico com IA" — Índice das SPECs

Geração assistida por IA de **documentos de correção de problemas de SEO** ("Parecer Técnico")
no padrão do `Parecer-Tecnico-Performance-Imecap.docx`, para o usuário enviar à agência aplicar.

O usuário **cola prints/gifs e escreve descrições curtas** num editor rico (o "bloco branco"),
clica em **Gerar**, e a IA **analisa as imagens + a descrição (visão multimodal)**, identifica os
problemas e **redige o parecer no padrão do documento**. O resultado volta para o **mesmo editor
(preview editável)** para ajustes finos e é **exportado em `.docx`**.

- Entrada: **canvas livre** (editor WYSIWYG, colar imagem inline)
- Saída: **preview editável** + **baixar `.docx`**
- Cabeçalho: usuário só escolhe o **cliente**; a IA infere plataforma/escopo/objetivo/URLs

> Plano aprovado: `/.claude/plans/task-notification-task-id-b3mvx3dbi-tas-bubbly-deer.md`
> Documento de referência (formato-alvo): `/Parecer-Tecnico-Performance-Imecap.docx`

---

## 📦 SPECs (V1)

| # | SPEC | Escopo | Status |
|---|---|---|---|
| 1 | [SPEC principal — Ferramenta Parecer Técnico](SPEC_Parecer_Ferramenta.md) | Backend: rota + worker + `ExecucaoFerramenta` (lifecycle/créditos) + service de custo + cobrança. Orquestra os demais. | a aplicar |
| 2 | [SPEC Dados e Persistência](SPEC_Parecer_Dados_e_Persistencia.md) | **Tabela `parecer` dedicada** + model + migration + `parecer_persistencia` (habilita histórico). Refina o §2 da #1. | a aplicar |
| 3 | [SPEC IA de Visão Multimodal](SPEC_Parecer_IA_Visao_Multimodal.md) | Agentes `analisador` (visão/imagem) + `documentador` (síntese) + schemas + prompts + **2 modelos dedicados** | a aplicar |
| 4 | [SPEC Geração do `.docx`](SPEC_Parecer_Geracao_Docx.md) | Renderer `estrutura → HTML` e `HTML → .docx` no padrão da casa (template, tabelas, imagens) | a aplicar |
| 5 | [SPEC Editor + Frontend](SPEC_Parecer_Editor_Frontend.md) | Editor Tiptap (entrada + preview editável), paste/compressão de imagem, página, hook, api client, sidebar | a aplicar |
| 6 | [SPEC Histórico "Meus Pareceres"](SPEC_Parecer_Historico_UI.md) | Endpoint `historico`/`{id}` + lista + tela de reabrir/editar/re-baixar parecer salvo | a aplicar |
| 7 | [SPEC Erros, Estados e Observabilidade](SPEC_Parecer_Cenarios_Erro_Estados_e_Observabilidade.md) | Falhas/parciais/validação + estados de UI + logs/métricas/tracing (production-readiness) | a aplicar |
| 8 | [SPEC Testes e Verificação](SPEC_Parecer_Testes_e_Verificacao.md) | Pytest (renderer, agentes, rota, workflow) + E2E local + browser MCP | a aplicar |

---

## 🧩 Decisões-chave (travadas com o usuário)

| Tema | Decisão | Por quê |
|---|---|---|
| Editor | **Tiptap** (MIT) | Gratuito, sem chave de licença, ótimo paste/drag de imagem; serve de entrada **e** de preview editável. CKEditor 5 ficaria idêntico ao print enviado, mas Import/Export Word/PDF são **pagos** e exportam estilo genérico. |
| Geração `.docx` | **Servidor** (`python-docx` + `selectolax`) | Fidelidade ao template da casa; puro-Python, ok no free-tier do Render. Export do editor sairia genérico. |
| Visão | **2 modelos OpenAI dedicados** — `gpt-4o` (visão/imagem) + `gpt-4.1` (redação/síntese) | Primeiro uso de visão no projeto; ZhipuAI/GLM não garante o formato multimodal. Modelo de redação melhor = parecer mais bem escrito (padrão de modelos dedicados do CWV). |
| Imagens | **base64 inline** (+ compressão client-side) | Sem rota de imagem nova, sem problema de FS efêmero, parecer autocontido no Postgres. Upgrade durável = Supabase Storage. |
| Persistência | **`ExecucaoFerramenta` (lifecycle/créditos) + tabela `parecer` dedicada** | _Decisão de melhor resultado:_ tabela dedicada habilita "Meus Pareceres" (reabrir/re-baixar/versionar), espelhando o padrão `cwv_analise` do CWV. Ver [[SPEC_Parecer_Dados_e_Persistencia]]. |
| Async/créditos | Padrão das ferramentas (ARQ + reserva/confirma/refund) | Visão sobre N imagens é lenta (>30s) e cobra LLM; consistente com CWV/Inlinks. |

**Reuso de infra existente:** auth/multi-tenant (`get_current_user`, `get_db`, `rate_limit_autenticado`),
`BaseAgent` (`app/agents/base.py`), worker ARQ (`app/worker.py`), `ferramenta_service` + `credito_service`,
padrão de UI (`PageHeader`, Sonner, `useClientes`). Espelha [[SPEC_Ferramenta_Core_Web_Vitals]].

**Net-new no projeto:** visão multimodal, editor com paste de imagem, geração de `.docx`.

---

## 🗺️ Ordem de execução recomendada

```
   ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
   │ 2. Dados/Persistência│   │ 3. IA Visão (agentes │   │ 4. Geração .docx     │
   │   (tabela + migration)│   │   + prompts, 2 modelos)│ │   (renderer HTML→docx)│
   └───────────┬──────────┘   └───────────┬──────────┘   └───────────┬──────────┘
               └──────────────────┬────────┴───────────────────────────┘
                                  ▼
                   ┌─────────────────────────────┐
                   │ 1. SPEC principal (rota +   │  ← amarra tudo (worker chama 3,
                   │    worker + cobrança)       │     persiste via 2, exporta via 4)
                   └──────────────┬──────────────┘
                                  ▼
                   ┌─────────────────────────────┐   ┌─────────────────────────────┐
                   │ 5. Editor + Frontend        │──▶│ 6. Histórico "Meus Pareceres"│
                   └──────────────┬──────────────┘   └──────────────┬──────────────┘
                                  ▼                                  │
                   ┌─────────────────────────────┐                  │
                   │ 7. Erros/Estados/Observ.    │◀─────────────────┘
                   └──────────────┬──────────────┘
                                  ▼
                   ┌─────────────────────────────┐
                   │ 8. Testes + E2E             │
                   └─────────────────────────────┘
```

**Caminho crítico:** 2 + 3 + 4 (paralelizáveis) → 1 (orquestra) → 5 (UI) → 6/7 → 8 (validação).

---

## 🎯 Critério de pronto (V1)

- [ ] Colar 1+ prints + descrições no editor e **Gerar** produz um parecer estruturado coerente
- [ ] Preview carrega no editor e é **editável**; edição preserva o vocabulário suportado
- [ ] **Baixar `.docx`** abre no Word no padrão do documento de referência (cabeçalho, sumário,
      seções `N.` → subseções `N.M.` com Problema/Evidência/Solução e prints embutidos, recomendações globais)
- [ ] Reserva/confirma/refund de créditos correto (refund em falha; degradação parcial não aborta)
- [ ] Parecer salvo na tabela `parecer`; **"Meus Pareceres"** lista, reabre e re-baixa; multi-tenant
- [ ] Estados de UI (idle/gerando/pronto/erro + empty/loading/error) e validações (413/422) ok
- [ ] Logs `event_type` + métricas Prometheus + runs nomeados no langsmith
- [ ] Pytest (renderer `.docx`, agentes, rota, workflow) passando; E2E local (colar→gerar→editar→baixar→reabrir) ok
- [ ] `ruff` + `mypy` (backend) e `eslint` + `next build` (frontend) limpos

---

## 🚀 Backlog V2 (fora do escopo inicial)

- Export **PDF** (além do `.docx`)
- **Versões** do parecer (editar mantendo histórico de revisões)
- Imagens em **Supabase Storage** (durabilidade/peso além do base64 inline)
- Reaproveitar a **base de conhecimento do CWV** para enriquecer soluções quando o problema for de performance
- Templates de parecer por tipo (performance, técnico on-page, indexação)

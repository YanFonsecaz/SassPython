# SPEC — Cenários de Erro, Estados de UI e Observabilidade

**Status:** a aplicar · **Data:** 2026-05-30
**Escopo:** robustez backend (falhas/parciais/validação) + estados de UI (loading/empty/error) + logs/métricas/tracing
**Reusos:** `app/core/excecoes.py` (`ErroTransitorio`/`ErroPermanente`), `_executar_job` do worker, Sonner, `EmptyState`/`ErrorState`, langsmith/sentry/prometheus já configurados
**Specs irmãs:** todas — este é o "production-readiness" da ferramenta

## 1. Cenários de erro (backend) e política

| Cenário | Quando | Tratamento | Crédito |
|---|---|---|---|
| Sem `OPENAI_API_KEY` | startup do workflow | `ErroPermanente` + `_marcar_falhou("Visão indisponível: configure OPENAI_API_KEY")` | **libera reserva** |
| Créditos insuficientes | `POST /gerar` | `HTTP 402` antes de criar execução | n/a |
| Payload acima do limite | `POST /gerar` | `HTTP 413` ("Imagens muito grandes — reduza a quantidade/qualidade") | n/a |
| Nenhum conteúdo útil | `POST /gerar` | `HTTP 422` se não há texto **nem** imagem em nenhum bloco | n/a |
| Falha de visão em **1** imagem | etapa analisador | **degradar, não abortar**: gerar `AchadoImagem` placeholder (`o_que_mostra="Evidência não analisada automaticamente"`, `confianca=0`) e seguir | confirma normal |
| Rate limit / 5xx do LLM | qualquer chamada | `ErroTransitorio` → retry com `defer` (guard/`_executar_job` já fazem) | confirma ao concluir |
| Timeout do workflow | > `parecer_workflow_timeout` | `_marcar_falhou("Tempo excedido")` | **libera reserva** |
| Falha ao enfileirar | `POST /gerar` | status `falhou` + `liberar_reserva` (já na rota) | **libera reserva** |
| HTML inválido no export | `POST /exportar` | `selectolax` tolera; nós desconhecidos ignorados (log warn); se vazio → `HTTP 422` | n/a |
| Imagem corrompida no export | embутir | pular a imagem com log warn (não quebrar o `.docx`) | n/a |

**Regra-mestra de crédito:** confirma (`confirmar_debito`) **somente** quando o parecer é persistido
com sucesso; qualquer falha terminal **libera a reserva** (`liberar_reserva`). Centralizar num helper
`_finalizar_falha_parecer(execucao_id, usuario_id, custo, msg)`.

## 2. Validação de entrada (segurança)

- `data URI` aceitos: `^data:image/(png|jpe?g|gif|webp);base64,` — rejeitar outros esquemas.
- Limite por imagem (ex.: 4 MB decodificado) e por requisição (ex.: 12 MB total) → `413`.
- **Sanitização do HTML editado** no `exportar`: o renderer só interpreta o vocabulário do contrato
  ([[SPEC_Parecer_Geracao_Docx]] §1.1) — `script`/`iframe`/`on*`/`style` externos são **ignorados**
  por construção (selectolax + whitelist de tags). Garantir que nenhum conteúdo do HTML é executado
  no servidor (só lido) e que o que volta ao editor é re-renderizado pelo Tiptap (que também filtra).
- Rate limit já aplicado (`gerar` 5/5min, `exportar` 20/5min).

## 3. Estados de UI

### 3.1 Geração (`/ferramentas/parecer`)
- **idle:** editor com placeholder + dica "Cole prints (Ctrl/Cmd+V) e descreva o problema".
- **gerando:** botão desabilitado + spinner; mostrar **etapa** legível mapeada de `etapa_atual`:
  `analisando_imagens → "Analisando evidências…"`, `redigindo_parecer → "Redigindo o parecer…"`.
- **pronto:** troca para preview editável + botão **Baixar .docx**; toast `success`.
- **erro:** toast `error` (`mensagemErroAmigavel`) + botão "Tentar novamente" (re-`gerar` mantém o conteúdo).

### 3.2 Histórico / detalhe
- **empty:** `EmptyState` ("Nenhum parecer ainda" + CTA).
- **loading:** skeleton/spinner padrão.
- **error:** `ErrorState` + retry.

### 3.3 Microcopy
- pt-BR com acentuação correta (alinhado à Auditoria UX do projeto). Mensagens de erro orientam ação
  (ex.: "Saldo insuficiente de créditos." vem do `mensagemErroAmigavel` por status 402).

## 4. Observabilidade

### 4.1 Logs estruturados (padrão `event_type` do projeto)
| Evento | Onde | Campos |
|---|---|---|
| `parecer.gerar.enfileirado` | rota | execucao_id, usuario_id, n_imagens, custo |
| `parecer.workflow.start` / `.done` / `.failed` | workflow | execucao_id, n_imagens, modelo, dur_ms |
| `parecer.imagem.analisada` | analisador | execucao_id, indice, confianca, ok |
| `parecer.imagem.degradada` | analisador (falha parcial) | execucao_id, indice, erro |
| `parecer.exportar` | rota export | parecer_id, bytes, n_imgs |

### 4.2 Tracing
- LLM via langsmith já liga por env (`LANGSMITH_API_KEY`) — as chamadas de visão/síntese aparecem
  automaticamente (usam o mesmo `chamada_llm_com_retry`). Nomear os runs (`analisador_parecer`,
  `documentador_parecer`) para facilitar análise.

### 4.3 Métricas Prometheus (`prometheus-client` já é dep)
- `parecer_geracoes_total{status}` (counter)
- `parecer_imagens_total` / `parecer_imagens_degradadas_total` (counter)
- `parecer_geracao_duracao_segundos` (histogram)
- `parecer_export_total` (counter)

### 4.4 Sentry
- Erros inesperados no workflow/export já são capturados pelo `sentry_sdk` inicializado no worker/app;
  adicionar `tags={"ferramenta": "parecer_tecnico", "execucao_id": ...}` no contexto.

## 5. Critérios de aceite

- [ ] Falha de visão em 1 de N imagens **não** aborta o parecer (degrada com placeholder + log)
- [ ] Todo caminho terminal de falha **libera a reserva** de créditos; sucesso confirma
- [ ] `413`/`422` com mensagens claras para payload grande / sem conteúdo / esquema de imagem inválido
- [ ] HTML de export é tratado como dado (não executado); só o vocabulário do contrato é renderizado
- [ ] Estados idle/gerando(etapas)/pronto/erro e empty/loading/error do histórico implementados
- [ ] Logs `event_type`, métricas Prometheus e runs nomeados no langsmith presentes

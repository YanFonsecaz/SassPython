# Parecer Técnico com IA

**Estado:** ✅ implementado · **Rota:** `/ferramentas/parecer` · **Slug:** `parecer_tecnico`
**Créditos:** `10 + 3·N_imagens` (teto 90) — `calcular_custo_parecer()`
**Código:** `backend/app/agents/parecer/*` · `routers/ferramentas_parecer.py` · `services/parecer_*` · `models/parecer.py` (migrations `0020`/`0021`)

Geração assistida por IA de **documentos de correção de problemas de SEO** ("Parecer Técnico") no
padrão do `Parecer-Tecnico-Performance-Imecap.docx`, para o usuário enviar à agência aplicar. O usuário
**cola prints/gifs e escreve descrições curtas** num editor rico, clica em **Gerar**, e a IA **analisa
as imagens + a descrição (visão multimodal)**, identifica os problemas e **redige o parecer no padrão
do documento**. O resultado volta para o **mesmo editor (preview editável)** e é **exportado em `.docx`**.
Primeiro uso de **visão multimodal** no projeto.

- Entrada: canvas livre (editor WYSIWYG, colar imagem inline) · Saída: preview editável + baixar `.docx`
- Cabeçalho: o usuário só escolhe o **cliente**; a IA infere plataforma/escopo/objetivo/URLs

## Arquitetura (mapa → código)

Padrão das ferramentas async (worker ARQ + reserva/confirma/refund + estados de UI). Agentes em
`agents/parecer/`:

| Etapa | Função | Arquivo |
|---|---|---|
| analisar | Visão multimodal sobre as imagens + descrição | `agents/parecer/analisador.py`, `modelos.py` |
| documentar | Síntese do parecer no padrão da casa | `agents/parecer/documentador.py`, `workflow.py` |
| gerar `.docx` | `estrutura → HTML → .docx` (python-docx + selectolax) | `services/parecer_service.py` |
| persistir / histórico | Tabela `parecer` dedicada | `services/parecer_persistencia.py`, `models/parecer.py` |

Frontend: editor **Tiptap** (entrada + preview editável, paste/compressão de imagem), página da
ferramenta, histórico "Meus Pareceres" (reabrir/editar/re-baixar). Imagens em **base64 inline**.

## Decisões-chave (travadas com o usuário)

| Tema | Decisão | Por quê |
|---|---|---|
| Editor | **Tiptap** (MIT) | Gratuito, ótimo paste/drag de imagem; serve de entrada **e** preview editável |
| Geração `.docx` | **Servidor** (`python-docx` + `selectolax`) | Fidelidade ao template da casa; puro-Python, ok no free-tier do Render |
| Visão | **2 modelos OpenAI dedicados**: `gpt-4o` (visão) + `gpt-4.1` (redação) | ZhipuAI/GLM não garante o formato multimodal; redação melhor = parecer melhor escrito |
| Imagens | **base64 inline** (+ compressão client-side) | Sem rota de imagem nova, sem FS efêmero, parecer autocontido no Postgres |
| Persistência | `ExecucaoFerramenta` + **tabela `parecer` dedicada** | Habilita "Meus Pareceres" (reabrir/re-baixar), espelhando `cwv_analise` |

**Reuso de infra:** auth/multi-tenant, `BaseAgent` (`agents/base.py`), worker ARQ, `ferramenta_service`
+ `credito_service`, padrão de UI. Espelha o [[../core-web-vitals]].

## Não-objetivos

Export PDF · versões/histórico de revisões do parecer · imagens em storage externo (Supabase) ·
templates de parecer por tipo · reuso da KB do CWV para enriquecer soluções. (Backlog V2.)

## Specs

### Base
| Spec | Conteúdo |
|---|---|
| [SPEC_Parecer_Ferramenta](SPEC_Parecer_Ferramenta.md) | Spec-mãe: rota + worker + lifecycle/créditos; orquestra as demais |
| [SPEC_Parecer_Dados_e_Persistencia](SPEC_Parecer_Dados_e_Persistencia.md) | Tabela `parecer` + model + migration + persistência |
| [SPEC_Parecer_IA_Visao_Multimodal](SPEC_Parecer_IA_Visao_Multimodal.md) | Agentes analisador (visão) + documentador + 2 modelos |
| [SPEC_Parecer_Geracao_Docx](SPEC_Parecer_Geracao_Docx.md) | Renderer `estrutura → HTML → .docx` no padrão da casa |
| [SPEC_Parecer_Editor_Frontend](SPEC_Parecer_Editor_Frontend.md) | Editor Tiptap, paste/compressão de imagem, página, hook, api client |
| [SPEC_Parecer_Historico_UI](SPEC_Parecer_Historico_UI.md) | "Meus Pareceres": listar/reabrir/editar/re-baixar |

### Robustez e verificação
| Spec | Conteúdo |
|---|---|
| [SPEC_Parecer_Cenarios_Erro_Estados_e_Observabilidade](SPEC_Parecer_Cenarios_Erro_Estados_e_Observabilidade.md) | Falhas/parciais/validação + estados de UI + logs/métricas/tracing |
| [SPEC_Parecer_Testes_e_Verificacao](SPEC_Parecer_Testes_e_Verificacao.md) | Pytest (renderer, agentes, rota, workflow) + E2E |
| [SPEC_Parecer_Correcoes_Revisao](SPEC_Parecer_Correcoes_Revisao.md) | Correções pós code-review (créditos em falha, retry, `.docx`, polling) |

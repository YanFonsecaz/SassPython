# SPEC 04 — Microcopy, Acentuação e Jargão

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** frontend (texto/UI) + nota pontual de backend · **Severidade:** 🟡 Média · **Esforço:** ~4h
**Índice:** [Auditoria UX 2026-05](README.md)

## 1. Problema

### 1.1 Acentuação ausente disseminada
Boa parte da UI está **sem acento** ("creditos", "voce", "acao", "analise", "topico", "execucao", "introdutorio", "nao"…), enquanto outros componentes estão corretamente acentuados — inconsistência que passa impressão de descuido e atrapalha leitura. Contagem por arquivo (palavras-amostra):

| Arquivo | Ocorrências |
|---|---|
| `components/ferramentas/execucao-detalhe-conteudo.tsx` | ~50 |
| `components/ferramentas/formulario-gerar-artigo.tsx` | ~18 |
| `components/cwv/cwv-form.tsx` | ~15 |
| `components/ferramentas/formulario-distribuir-inlinks.tsx` | ~14 |
| `components/ferramentas/formulario-inlinks.tsx` | ~12 |
| `components/cwv/cwv-execucao-client.tsx` | ~10 |
| `components/cwv/comparador-component.tsx` | ~7 |
| `app/(publico)/recuperar-senha/page.tsx`, `modal-creditos-insuficientes.tsx`, `cwv-metricas-resumo.tsx`, `cwv-dashboard-client.tsx`, `cwv-url-client.tsx`, `formulario-alterar-senha.tsx`, `creditos/page.tsx`, demais | 2–5 cada |

~20 arquivos no total.

### 1.2 Jargão sem explicação para leigo
Termos exibidos sem contexto: **LCP / CLS / INP / TBT** (o CWV tem tooltips via `tooltipThresholds`, mas inconsistente entre telas), **"template"**, **"URL canônica"**, **"estratégia mobile/desktop"**, **"plataforma detectada"**, **"persona"**, **"MFA"**. O usuário não técnico não sabe o que significam nem o que fazer.

**Padrão-ouro a replicar:** `src/components/ferramentas/inlinks-seletor-modo.tsx` ("O que são inlinks?" + "Use quando" + exemplo).

### 1.3 Mensagens de erro com `detalhe` cru do backend
Forms exibem `err.detalhe` diretamente (`formulario-gerar-artigo.tsx:113-118`, `formulario-cliente.tsx:65-71`), podendo mostrar texto técnico/em inglês ao usuário.

## 2. Objetivos
1. **Acentuação correta** em toda a UI visível.
2. **Explicar jargão** no ponto de uso (tooltip/hint curto), com glossário central reutilizável.
3. **Humanizar** mensagens de erro (fallback amigável; nunca stack/inglês cru).

## 3. Mudanças propostas

### 3.1 Passada de acentuação
- Revisar os ~20 arquivos acima e corrigir strings visíveis (PT-BR correto). **Só texto exibido** — não mexer em chaves de API, `value` de enums, nem identificadores.
- Conferir telas de auth/recuperação/reset, créditos e CWV.
- Recomendado adicionar lint/checagem leve (script ou revisão) para evitar regressão — opcional.

### 3.2 Glossário + tooltips de jargão
- Criar `src/lib/glossario.ts` com definições curtas em PT-BR: `lcp`, `cls`, `inp`, `tbt`, `score`, `template`, `url_canonica`, `estrategia`, `plataforma`, `persona`, `mfa`.
- Componente leve `TermoComAjuda` (usa `ui/tooltip.tsx`, já existe) para renderizar o termo com ícone de ajuda + definição.
- Aplicar nos pontos de maior confusão: tiles de métricas do CWV (`cwv-metricas-resumo.tsx`), seleção de template/estratégia no `cwv-form.tsx`, "persona" no `formulario-gerar-artigo.tsx`, "MFA" no Perfil.
- Onde fizer sentido, replicar o bloco explicativo do `inlinks-seletor-modo` (1–2 linhas antes da decisão).

### 3.3 Humanizar erros
- Helper `mensagemErroAmigavel(err)` em `src/lib/api.ts` (ou util) que mapeia status → texto PT-BR ("Sessão expirada", "Sem conexão", "Você não tem acesso a isso") e só usa `detalhe` se for claramente legível; fallback "Algo deu errado. Tente novamente.".
- Aplicar nos forms (gerar-artigo, cliente, inlinks). (CWV form já mapeia 402/429/404 — usar como referência.)
- **Nota backend (não implementar agora):** garantir que `detalhe` das exceções voltadas ao usuário esteja em PT-BR. Registrar para revisão dos `HTTPException(detail=...)`.

## 4. Critérios de aceite
- [ ] Nenhuma string visível sem acento nos arquivos listados (revisão/screenshot das telas principais).
- [ ] LCP/CLS/INP/template/persona têm ajuda acessível (tooltip/hint) no ponto de uso.
- [ ] Erros de formulário mostram texto PT-BR amigável, sem termos técnicos crus.

## 5. Verificação E2E
Percorrer as telas principais logado e ler a copy (screenshots): hub, histórico, Gerar Artigo (4 passos), CWV (form + dashboard), Créditos, Perfil. Forçar um erro (ex.: enviar form com backend off) → confirmar mensagem amigável.

## 6. Notas
- Esta SPEC é em grande parte **mecânica + glossário**; pode ser fatiada por área (CWV / ferramentas / auth) em PRs menores.
- Relacionado: [[SPEC_02_Error_Empty_Loading_Boundaries]] (texto dos boundaries), [[SPEC_03_Onboarding_Primeiros_Passos]].

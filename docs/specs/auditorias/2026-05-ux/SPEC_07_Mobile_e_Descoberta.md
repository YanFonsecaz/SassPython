# SPEC 07 — Mobile e Descoberta

**Status:** parcialmente feito · **Escopo:** frontend (responsivo + descoberta) · **Severidade:** 🟢 Baixa · **Esforço:** ~2h
**Índice:** [Auditoria UX 2026-05](README.md)

## 1. Contexto

### 1.1 Descoberta — JÁ CORRIGIDO nesta sessão (pendente de commit)
As principais lacunas de descoberta do CWV/histórico foram resolvidas durante a sessão de 2026-05-29 e estão no working tree (**ainda não commitadas**). Esta seção serve para **registrar/commitar**, não re-implementar:
- **CWV no hub** `(app)/ferramentas/page.tsx`: card "Core Web Vitals" + contador "Ferramentas ativas" 2→3.
- **Histórico legível + filtro** `(app)/ferramentas/historico/page.tsx`: rótulos amigáveis (`labelFerramenta`), chips de filtro por ferramenta, CTA neutro "Ver ferramentas".
- **Entrada para URLs auditadas** `cwv-form.tsx`: botão "Ver análises anteriores deste cliente" → histórico por cliente.
- **Redirect inteligente** `execucao-detalhe-conteudo.tsx`: execução CWV de 1 URL → dashboard; de várias → lista por cliente.
- **Helper compartilhado** `src/lib/ferramentas.ts` (`labelFerramenta`/`iconeFerramenta`).
- Validado E2E logado (27 análises reais). **Ação:** commitar separadamente (não é parte da implementação desta auditoria).

### 1.2 Mobile / responsividade — a verificar
- **Tabelas largas** podem estourar horizontalmente no celular: `src/components/ferramentas/tabela-execucoes.tsx` e a tabela de recursos/problemas do CWV (`cwv-problema-detalhes.tsx` — colunas "Recurso | Detalhe | Desperdiçado | Total").
- Confirmar a sidebar mobile (drawer) e os wizards (Gerar Artigo / CWV) em larguras pequenas.
- O painel de evolução do CWV (`cwv-evolucao-chart.tsx`) usa grid `sm:grid-cols-2` (já responsivo) — confirmar sparklines/labels em telas estreitas.

## 2. Objetivos
1. Garantir que nenhuma tela quebre o layout no mobile (sem scroll horizontal indevido).
2. Deixar registrada/commitada a melhoria de descoberta já feita.

## 3. Mudanças propostas
- **Tabelas:** envolver em container com `overflow-x-auto` e, onde fizer sentido para leigo, oferecer layout de **cards empilhados** no mobile (especialmente a tabela de problemas do CWV, que é a mais larga).
- **Revisão responsiva** das telas principais em viewport ~375px: hub, histórico, Gerar Artigo, CWV (form + dashboard), Clientes, Créditos, Perfil (após [[SPEC_01_App_Shell_Navegacao]]).
- **Commit** das correções de descoberta da §1.1 (mensagem sugerida: `feat(nav): integrar CWV ao hub/histórico e facilitar achar URLs auditadas`).

## 4. Critérios de aceite
- [ ] Nenhuma tela principal apresenta scroll horizontal indevido em 375px.
- [ ] Tabela de problemas do CWV legível no mobile (scroll contido ou cards).
- [ ] Correções de descoberta da §1.1 commitadas.

## 5. Verificação E2E
`mcp__playwright__browser_resize` para 375×812 e percorrer as telas principais logado (screenshots), conferindo ausência de overflow.

## 6. Notas
- Severidade baixa: a descoberta (maior risco) já foi tratada; aqui é polish responsivo + housekeeping de commit.
- Relacionado: [[SPEC_01_App_Shell_Navegacao]] (Perfil entra no shell e precisa de checagem mobile).

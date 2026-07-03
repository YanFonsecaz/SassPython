# Auditorias — campanhas pontuais (histórico)

Revisões de qualidade feitas num **momento específico**, agrupadas em SPECs numeradas. São **🗄️
histórico**: o produto já evoluiu além delas (21 migrations, 5 ferramentas no ar). Servem como registro
do que foi diagnosticado/corrigido e do raciocínio — **não** como spec viva. Para o estado atual, use os
READMEs em [`../ferramentas/`](../ferramentas/) e [`../plataforma/`](../plataforma/).

## Campanhas

| Campanha | Foco | SPECs | Estado |
|---|---|---|---|
| [2026-05-16 — codebase](2026-05-16-codebase/README.md) | Auditoria crítica de ~10k LOC: 48 issues por severidade (P0, créditos transacional, multi-tenant/concorrência, robustez do worker ARQ, LangGraph produção, auth hardening, observabilidade/testes, limpeza) | 11 | 🗄️ aplicada |
| [2026-05 — UX](2026-05-ux/README.md) | Front para usuário **não técnico**: app shell/navegação, estados de erro/vazio/carregamento, onboarding, microcopy/acentos/jargão, design-system, acessibilidade, mobile, UI visual | 8 | 🗄️ aplicada |

## Como usar

- **Entender uma decisão de arquitetura/segurança** tomada em maio/2026 → leia a SPEC correspondente
  (cada campanha tem README com mapa issue→SPEC).
- **Padrão de UX para público leigo** → a auditoria de UX aponta o "padrão-ouro"
  (`inlinks-seletor-modo.tsx`: explicar antes de exigir), referência ainda válida para novas telas.
- **Nova auditoria** → crie `auditorias/AAAA-MM-<tema>/` com seu próprio README (índice + mapa
  issue→SPEC), seguindo [`../_template/CONVENCOES.md`](../_template/CONVENCOES.md).

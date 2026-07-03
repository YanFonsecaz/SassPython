# Convenções das specs (SDD)

Regras para manter `docs/specs/` navegável e fiel ao código. Porta de entrada: [`../README.md`](../README.md).

## Organização

- **1 capacidade = 1 pasta.** Ferramentas em `ferramentas/<slug>/`; temas transversais em
  `plataforma/<tema>/`. O `<slug>` casa com a **rota do frontend** (`gerar-artigo`,
  `inlinks-automaticos`, `inlinks-reversos`, `core-web-vitals`, `parecer-tecnico`).
- **`README.md` da pasta = spec viva** (fonte da verdade, no presente). As `SPEC_*.md` = registro de
  design/decisões.
- **Histórico separado:** PLANOs de correção aplicados vão em `<capacidade>/_historico/`; campanhas de
  auditoria/postmortems ficam em `auditorias/` ou marcados `🗄️ histórico`.

## Nomes de arquivo

- Pastas: `kebab-case` em PT, alinhadas à rota.
- Specs: `SPEC_<Tema_Em_Snake>.md`. Planos: `PLANO_<Tema>.md`. Postmortems: `POSTMORTEM_<...>.md`.
- Evite renomear specs existentes sem motivo (preserva histórico de git e links). Prefira mover a pasta.

## Vocabulário de status (header de toda spec)

| Marca | Quando usar |
|---|---|
| ✅ implementado | Está no código e em uso. A spec descreve o que **existe**. |
| 🚧 parcial | Parte implementada; o resto é backlog descrito na própria spec. |
| 📋 planejado | Proposta ainda não implementada. |
| 🗄️ histórico | Pontual e encerrado (correção aplicada, auditoria, postmortem). Cite o commit. |

Header padrão: ver [`TEMPLATE_SPEC.md`](TEMPLATE_SPEC.md). Sempre inclua **Status**, **Capacidade**,
**Código** e (quando aplicável) **Commit/Data**.

## Ciclo de vida

```
📋 planejado  →  🚧 parcial  →  ✅ implementado  →  (correção aplicada)  🗄️ histórico
```

1. Antes de codar uma feature não-trivial: escreva a spec (📋) a partir do template.
2. Ao implementar: atualize o `README.md` da capacidade (estado atual + mapa→código) e mova a spec
   para ✅.
3. Ao corrigir algo já entregue: **não reescreva o corpo** — registre na seção *Histórico* da spec e
   marque o item como aplicado. Se houve um PLANO dedicado, arquive-o em `_historico/`.

## Quando criar uma spec (vs. só commit)

- **Crie spec:** nova ferramenta, mudança de arquitetura, alteração de cobrança/créditos, novo agente,
  decisão que outra pessoa/IA precisaria entender depois.
- **Dispensa spec:** typo, ajuste de cópia, refactor local sem mudança de comportamento, correção óbvia
  (registre no *Histórico* da spec relacionada, se houver).

## Rastreabilidade ao código

Toda spec viva deve apontar para **arquivos e símbolos reais** do `backend/app/` e `frontend/src/`.
Se um caminho citado deixar de existir, atualize a spec — specs que mentem sobre o código são pior que
nenhuma spec.

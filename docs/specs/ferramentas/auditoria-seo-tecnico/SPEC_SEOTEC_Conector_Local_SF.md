# SPEC — Conector local do Screaming Frog + contrato de ingestão

**Status:** 📋 planejado
**Capacidade:** `auditoria-seo-tecnico`
**Escopo:** conector CLI (pacote separado) + rotas de dispositivo/ingestão no backend
**Código:** pacote `sf-connector` em `tools/sf-connector/` neste repo (monorepo: versiona junto do contrato de ingestão) · `backend/app/routers/ferramentas_seo_tecnico.py` (rotas `…/conector/*`) · `backend/app/services/seotec_ingestao.py`
**Créditos:** não cobra (cobrança acontece na ingestão da auditoria — spec-mãe §3.5)
**Depende de:** [SPEC_Ferramenta_Auditoria_SEO_Tecnico](SPEC_Ferramenta_Auditoria_SEO_Tecnico.md)

---

## 1. Contexto (por quê)

O Screaming Frog roda **na máquina de cada usuário** (licença própria; decisão travada). O SaaS
precisa dos dados do crawl de forma confiável e sem exigir conhecimento técnico: um conector CLI
instalável executa o SF headless via **MCP nativo do v24**, roda a receita de exports que o backend
define, normaliza e sobe. Quem não puder instalar usa o **fallback de upload manual** do mesmo
pacote.

Referências externas (verificadas 2026-07-17):
- SF v24.0 (mai/2026) tem servidor MCP nativo (~29 tools; crawl control, reports, bulk exports,
  URL inspection) em 2 modos: Streamable HTTP no app aberto **ou stdio, onde o cliente MCP lança o
  Spider headless**. Licença paga necessária para headless/save-load.
- Community server locked-down (9 tools, CLI headless): `github.com/bzsasson/screaming-frog-mcp` —
  referência de desenho, não dependência.

## 2. Requisitos / Critérios de aceite

- [ ] `sf-connector pair <código>` troca código de pareamento (validade ≤10 min, uso único) por
      **token de dispositivo** persistido no keychain/arquivo local com escopo mínimo
      (ingestão da própria conta).
- [ ] `sf-connector run` sem argumentos: busca no SaaS a próxima auditoria pendente do usuário
      (ou `--auditoria <id>`), executa crawl + exports + normalização + upload, imprime progresso.
- [ ] `sf-connector doctor`: verifica SF instalado, versão, licença, MCP disponível, conectividade.
- [ ] Interface primária com o SF: **cliente MCP stdio** (SDK `mcp` Python) lançando o Spider
      headless; se SF < v24 ou MCP falhar → **fallback automático** para CLI clássico
      (`screamingfrogseospider --headless --crawl <url> --export-tabs ... --save-crawl`).
- [ ] Pacote final `.zip`: JSONs normalizados + `manifest.json` (`schema_version`, versão SF,
      versão do conector, contadores por export, hashes). Upload em chunks com retry; conexões
      **outbound-only** HTTPS.
- [ ] Fallback B: a UI aceita o mesmo `.zip` por upload manual; página do conector traz o guia de
      exports manuais (GUI do SF) que produz pacote equivalente.
- [ ] Backend valida `schema_version` e completude; pacote incompleto → ingestão `parcial` com
      lista do que faltou (itens sem dados viram "Sem dados", nunca "Reprovado").
- [ ] Evidências limitadas na origem: o conector agrega e **corta amostras por item (≤500 URLs)** +
      contadores totais; o crawl completo nunca sobe.

## 3. Design (mapeado ao código)

### 3.1 Conector (Python 3.12, empacotado com PyInstaller p/ mac/win/linux)

```
sf_connector/
  cli.py          # pair · run · doctor (typer)
  auth.py         # código→token de dispositivo; storage seguro
  receita.py      # busca receita da auditoria no backend (JSON)
  sf_mcp.py       # cliente MCP stdio do SF v24 (SDK mcp): start crawl, progresso, exports
  sf_cli.py       # fallback: subprocess screamingfrogseospider --headless
  normalizador.py # CSVs/exports → JSONs do contrato (schema_version)
  upload.py       # zip + chunks + retry + finalizar
```

**Receita** (definida pelo backend, versionada junto do `schema_version`): lista de exports
requeridos + configuração de crawl (user-agent, respeitar robots, limites) + **custom search /
custom extraction** exigidos pelos itens do checklist (ex.: presença de tag GA, `<meta viewport>`,
doctype, meta-refresh, lorem ipsum, atributo `lang`) — ver
[SPEC_SEOTEC_Checklist_Motor_Regras](SPEC_SEOTEC_Checklist_Motor_Regras.md) §3.3.

Exports mínimos da receita v1 (tabs/bulk do SF):

`Internal:All` · `Page Titles:*` · `Meta Description:*` · `H1:*`/`H2:*` · `Response Codes:*` ·
`Redirects (chains report)` · `Canonicals:*` · `Directives:*` · `Hreflang:*` ·
`Structured Data:*` (validation errors/warnings + types) · `Images:*` · `Links:All Inlinks (órfãs)` ·
`Sitemaps:*` · `Security:*` · `Content:*` (word count, duplicates) · `Custom Search/Extraction:*` ·
`Crawl Overview report`

### 3.2 Rotas de dispositivo (backend)

| Rota | Papel |
|---|---|
| `POST /conector/parear` | código → `{device_token}` (hash no DB, tabela `seo_conector_dispositivo`: `usuario_id`, `nome_maquina`, `criado_em`, `ultimo_uso`) |
| `GET /conector/receita?auditoria_id=` | receita + `schema_version` correntes |
| `POST /conector/ingestao/iniciar` | abre `seo_crawl` (`origem=conector`) → `{upload_id}` |
| `PUT /conector/ingestao/{upload_id}/chunk/{n}` | chunk do zip (limite de tamanho por chunk e total) |
| `POST /conector/ingestao/{upload_id}/finalizar` | valida hashes → enfileira worker |

Autenticação: header com token de dispositivo (não é sessão de usuário); rate-limit por dispositivo;
tenant resolvido pelo dono do dispositivo. Revogação na página do conector.

### 3.3 Contrato de ingestão (`schema_version: 1`)

```jsonc
// manifest.json
{ "schema_version": 1, "conector_versao": "x.y.z", "sf_versao": "24.x",
  "dominio": "https://…", "auditoria_id": "…", "gerado_em": "ISO",
  "exports": { "page_titles": {"linhas": 1234, "hash": "sha256:…"}, … } }
// exports/<nome>.json — por export: colunas normalizadas (nomes canônicos em snake_case),
// linhas cortadas conforme política de amostra, contadores totais antes do corte.
```

Regras: encoding UTF-8; colunas ausentes numa versão do SF → `null` + flag no manifest; o
normalizador conhece o mapeamento de cabeçalhos por versão do SF (en/pt).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Transporte MCP | stdio headless (conector lança o Spider) | HTTP no app aberto (exige GUI; DB lock com CLI) |
| Linguagem do conector | Python + PyInstaller (reusa stack do time) | Go/Rust (novo toolchain); Electron (peso) |
| Direção de rede | Outbound-only (conector → SaaS) | Backend acessar máquina do usuário (NAT/segurança) |
| Dados que sobem | Amostras agregadas por item + contadores | Crawl inteiro (DB incha; LGPD do cliente final) |
| Guia manual | Pacote equivalente via GUI documentado | Formato próprio para upload manual (2 parsers) |

## 5. Verificação

```bash
# unit do normalizador com fixtures de CSVs reais (en + pt, v23 e v24)
rtk pytest backend/tests/unit/test_seotec_normalizador.py
# contrato: pacote válido/incompleto/versão errada
rtk pytest backend/tests/unit/test_seotec_ingestao.py
# manual: sf-connector doctor && sf-connector run --auditoria <id> num site pequeno
```

## 6. Não-objetivos

Modo daemon/agendado do conector (V2) · auto-update do conector (V2) · suporte a proxies
corporativos exóticos · rodar crawl de URLs autenticadas.

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-17 | Spec inicial | — |

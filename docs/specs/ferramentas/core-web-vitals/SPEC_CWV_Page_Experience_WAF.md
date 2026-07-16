# SPEC — Page Experience: veredito `na` para bloqueio WAF/anti-bot (401/403/429)

**Status:** ✅ implementado
**Capacidade:** `core-web-vitals`
**Escopo:** `backend` — checks de page experience
**Código:** `backend/app/services/cwv_page_experience.py`
**Créditos:** não cobra (correção de veredito)
**Depende de:** [[SPEC_CWV_Page_Experience]] (S6)
**Commit/Data:** — · 2026-07-15

---

## 1. Contexto (por quê)

**Falso "fail" encontrado no teste E2E de produção (auditoria Kumon, 2026-07-15).** O site
`kumon.com.br` fica atrás de WAF que responde **403** a requests de datacenter. Resultado gravado
em `cwv_page_experience` (execução `6748472d`): `https = fail` com detalhe `{"status_code": 403}`
e `redirect_301 = fail` com motivo `"termino em https://www.kumon.com.br/ status 403"` — **num site
que comprovadamente serve HTTPS com certificado válido** (o check de SSL passou e o Lighthouse/PSI
auditou a página normalmente).

Um 403 recebido via `https://` **prova** que o TLS funciona e que a resposta HTTP chegou — ele é
inconclusivo sobre o item auditado, não uma reprovação. A gap analysis já previa esse risco
("falsos positivos SSL; sites atrás de WAF", V1.2). O contrato de vereditos do S6 tem o valor
certo para isso: `VEREDITOS = ("pass", "fail", "erro", "na")` (`cwv_page_experience.py:24`), e o
`na` já é usado pelo Safe Browsing sem key.

**Impacto (preciso):** o health score numérico da execução (S2) **não** é afetado — ele conta
apenas audits PSI (`cwv_health.py::calcular_health_score`). O que distorce: o checklist da
auditoria S5 (`n_fail_before` e itens `pe_https`/`pe_redirect_301` como fail com prioridade), o
relatório S9 (tabela Page Experience e o plano faseado — o redator LLM recebe esses itens na lista
de fails e os inclui nas fases) e o `status_after` da re-auditoria S10
(`cwv_auditoria_service.aplicar_resultado_after`, ramo `page_experience`).

## 2. Requisitos / Critérios de aceite

- [ ] Dado `check_https` recebendo resposta HTTP **401, 403 ou 429**, então o veredito é `na` com
      detalhe `{"status_code": <n>, "motivo": "bloqueio WAF/anti-bot — inconclusivo"}` (hoje: `fail`).
- [ ] Dado `check_redirect_301` cuja cadeia termina em `https://` com status **401/403/429**, então
      `na` com a cadeia registrada (hoje: `fail`). O caso "primeiro salto não é 301" continua `fail`.
- [ ] Dado `check_redirect_301` cuja **primeira** resposta (em `http://`) já é 401/403/429 sem
      redirect, então `na` (o WAF interceptou antes do redirect — inconclusivo).
- [ ] Dado `check_security_headers` sobre uma resposta 401/403/429, então `na` (os headers de uma
      página de bloqueio do WAF não representam a aplicação real).
- [ ] Dado um site sem WAF que responde 2xx/3xx ou erro real de TLS/conexão, então os vereditos
      atuais não mudam (pass/fail como hoje).
- [ ] Dado o checklist S5 gerado após a correção, então `pe_https`/`pe_redirect_301` com veredito
      `na` **não** entram em `n_fail_before` (a agregação `pior_veredito` em
      `cwv_auditoria_service._itens_page_experience:202-208` já trata `na` — não mexer nela).

## 3. Design (mapeado ao código)

Tudo em `backend/app/services/cwv_page_experience.py`:

```python
# Status que indicam bloqueio anti-bot, não reprovação do item auditado.
_STATUS_BLOQUEIO = (401, 403, 429)
```

1. **`check_https` (linha 60-69):** hoje `return "fail", {"status_code": resp.status_code}` para
   qualquer status fora de 2xx/3xx (linha 66). Inserir antes:
   `if resp.status_code in _STATUS_BLOQUEIO: return "na", {...}`. Exceções (TLS/conexão) continuam
   `fail` — aí sim o HTTPS não funciona.
2. **`check_redirect_301` (linha 110-144):** no término da cadeia (linhas 135-140), antes do
   `return "fail"` final: se `terminou_https and resp.status_code in _STATUS_BLOQUEIO` → `na` com
   `{"cadeia": cadeia, "motivo": f"bloqueio WAF (status {resp.status_code}) — inconclusivo"}`.
   Cobre também o caso da primeira resposta ser 401/403/429 (mesma linha de código — a cadeia terá
   0 saltos e `url` ainda é `http://...`; nesse caso `terminou_https` é False → adicionar a
   condição `or not cadeia` para o veredito `na`).
3. **`check_security_headers` (linha 147+):** após obter a resposta, se
   `resp.status_code in _STATUS_BLOQUEIO` → `na` (não avaliar headers de página de bloqueio).

**Não tocar:** agregação `pior_veredito` (S5), colunas da tabela, front (a UI já renderiza `na`
para `safe_browsing`/`mobile_friendly`), e os demais checks (`check_ssl` faz handshake TLS próprio
e não passa pelo WAF de camada HTTP; `check_mixed_content`/`check_mobile_friendly` não fazem rede).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Veredito para 401/403/429 | `na` (inconclusivo) | `pass` em `check_https` — um 403 até prova HTTPS, mas generalizar "bloqueio = aprovado" mascara outros itens; `na` é honesto e já existe no contrato |
| Lista de status | Constante `_STATUS_BLOQUEIO = (401, 403, 429)` | Detectar WAF por fingerprint (headers `server: cloudflare` etc.) — frágil e desnecessário |
| `check_security_headers` | Incluído (mesma causa raiz, mesma evidência do E2E) | Deixar de fora por não estar na lista original do bug — deixaria o falso fail vivo |
| Retry com User-Agent de navegador | Não fazer | Contornar WAF é frágil, pode violar ToS do site e o resultado continuaria não confiável |
| 5xx | Continua `fail` | Tratar como `na` — 5xx é indisponibilidade real do site, informação legítima |

## 5. Verificação

```bash
cd backend && uv run pytest tests/unit/test_cwv_page_experience.py -q
```

Novos testes (padrão AsyncMock/monkeypatch do arquivo, sem rede real):

- `check_https` com mock respondendo 403 → `("na", {...})`; com 500 → `("fail", ...)`; com 200 →
  `("pass", ...)` (regressão).
- `check_redirect_301` com cadeia `301 → https 403` → `na`; com primeira resposta 403 → `na`;
  com primeiro salto 302 → `fail` (regressão).
- `check_security_headers` com resposta 403 → `na`.
- Integração leve: `_itens_page_experience` com vereditos `na` → item fora de `n_fail_before`.

E2E real (opcional): reexecutar a análise da Kumon e conferir na tabela `cwv_page_experience`
que `https/redirect_301/security_headers` viram `na` com o motivo de bloqueio.

## 6. Não-objetivos

- Detectar/contornar WAF (UA spoofing, proxy residencial).
- Mudar a agregação do checklist ou o cálculo do health score.
- Reprocessar vereditos históricos já gravados (correção vale para execuções novas).
- Check de pop-ups/interstitiais (roadmap V3).

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-15 | Spec criada a partir do falso fail encontrado no E2E de produção (auditoria Kumon, execução `6748472d`) | — |

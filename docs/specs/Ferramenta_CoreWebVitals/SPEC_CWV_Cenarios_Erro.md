# SPEC — CWV Cenários de Erro

**Status:** a aplicar · **Escopo:** backend (validação de branches existentes + 1 fix de regressão) + frontend (UX clara para cada erro)
**Dependências:** [[SPEC_Ferramenta_Core_Web_Vitals]] (§5 risks, §6 mitigations)
**Esforço estimado:** ~1.5 dias

## 1. Problema

O workflow CWV (`app/agents/cwv/workflow.py:executar_workflow_cwv`) tem branches `except` para:

- **`asyncio.CancelledError`** — cancelamento
- **`TimeoutError`** — timeout do `asyncio.wait_for`
- **`Exception` genérica** — qualquer outro erro
- **`ValueError` em confirmar_debito** — saldo insuficiente
- **Falha PSI em todas as URLs** — não está no try/except, mas `n_sucesso=0`

**Nenhum desses branches foi exercitado no e2e.** Após o fix do Bug #7 (commit ausente), todas as branches que faziam `flush()` em vez de `commit()` também foram corrigidas — mas precisamos validar que cada caminho:

1. Atualiza `execucao.status` corretamente
2. Libera os créditos reservados (não cobrar quando não houve trabalho)
3. Renderiza UX adequada no frontend (em vez de polling infinito)

Adicionalmente, alguns cenários não têm tratamento explícito hoje:

- **Saldo insuficiente NO MOMENTO DO POST `/analisar`** (não na confirmação pós-workflow): hoje retorna HTTP 402, mas frontend não tem UX específica
- **Rate limit hit** (3 req/5min): retorna HTTP 429, sem UX específica
- **Cliente inativo / deletado durante execução** (caso raro): hoje quebra silenciosamente

## 2. Matriz de cenários

| # | Cenário | Onde acontece | Status esperado | UX frontend hoje | UX desejada |
|---|---|---|---|---|---|
| 1 | Saldo insuficiente no POST | Router `/analisar` | HTTP 402 | Erro genérico | "Saldo: X · Necessário: 16 · [Comprar créditos]" |
| 2 | Rate limit (>3/5min) | Router `/analisar` middleware | HTTP 429 | Erro genérico | "Aguarde 3 min · Reduz spam" |
| 3 | Cliente de outro usuário | Router `/analisar` | HTTP 404 | "Erro ao criar" | "Cliente inválido" |
| 4 | Cliente OK no POST, deletado durante workflow | Worker | execução `falhou` com `erro_msg='cliente removido'` | polling infinito | Notif + estado terminal |
| 5 | PSI 429 em uma URL (n>1 URLs) | Workflow | URLs OK persistem, falhadas com `status='falhou_psi'` | Hoje mostra UI parcial | OK como está |
| 6 | PSI 429 em todas as URLs | Workflow | execução marcada `concluida`, mas `n_urls_analisadas=0` | Mostra "0 analisadas" + créditos cobrados (base) | "PSI sem cota · [Tentar novamente em 24h]" + não cobrar |
| 7 | Workflow `asyncio.CancelledError` | Worker | execução `cancelada` | polling infinito | "Análise cancelada" |
| 8 | Workflow timeout | Worker | execução `falhou` com erro_msg | polling infinito | "Análise demorou demais — tente menos URLs" |
| 9 | Workflow exception genérica | Worker | execução `falhou` com erro_msg sanitizado | polling infinito | "Erro interno · Suporte foi notificado" |
| 10 | Saldo insuficiente NO confirma_debito (race) | Worker | execução `falhou`, créditos liberados | polling infinito | Mesma de #1 |
| 11 | LLM down (provider) durante analisador | Worker (LLM fallback) | execução continua com fast-path (fail-soft, já implementado em [[SPEC_CWV_LLM_Fallback_Analisador]]) | OK | OK |
| 12 | DB down durante persistência | Worker | execução fica em `executando` (rollback automático) | polling infinito | Job re-tenta automaticamente (arq) |

## 3. Backend

### 3.1 Cenário #6 — PSI 429 em todas as URLs deve não cobrar nada

Atual: `_run_workflow_cwv` chama `calcular_custo_cwv(0)` que retorna `15 + 0*1 = 15` (custo base). Confirma débito de 15. Resultado: usuário paga 15 créditos por análise que retornou zero dados.

**Fix:**

```python
# em _run_workflow_cwv, após calcular n_sucesso
if n_sucesso == 0:
    # Libera reserva inteira; não cobra nada
    await credito_service.liberar_reserva(session, str(execucao.usuario_id), custo_base)
    execucao.status = "falhou"
    execucao.creditos_cobrados = 0
    execucao.erro_msg = "Nenhuma URL pôde ser analisada (PSI indisponível ou todas as URLs inválidas)"
    execucao.resultado_json = {
        "n_urls_analisadas": 0,
        "n_urls_falharam": len(estado_final.get("urls_por_template", [])),
        "analise_ids": [],
        "motivo_falha": "psi_total"
    }
    execucao.concluida_em = datetime.now(UTC)
    await session.commit()
    return
```

### 3.2 Cenário #4 — Cliente deletado durante workflow

No workflow.py, no node `persistir`, o `cliente_id` é passado como string. Não há check de existência. Se cliente foi deletado entre POST e worker pickup, INSERT em `cwv_analise` falha por FK violation.

**Fix:** no início do workflow, validar:

```python
async def executar_workflow_cwv(execucao_id: str, ctx: dict[str, Any] | None = None):
    ...
    async with async_session_factory() as session:
        ...
        execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
        
        # NOVO: validar cliente ainda existe
        from app.models.cliente import Cliente
        cliente = await session.get(Cliente, execucao.cliente_id)
        if not cliente or cliente.deletado_em is not None:
            logger.error("CWV: cliente %s não existe mais", execucao.cliente_id)
            await ferramenta_service.finalizar_falha(
                session, execucao_id,
                "Cliente foi removido após o início da análise",
                ferramenta="core_web_vitals"
            )
            await credito_service.liberar_reserva(session, str(execucao.usuario_id), CUSTO_BASE_CWV)
            await session.commit()
            return
```

### 3.3 Sanitizar `erro_msg` para usuário final

`Exception` genérica grava o stack trace? Não — olhando `_run_workflow_cwv` atual, grava `"Erro interno do workflow CWV"`. Bom.

Mas no router `/analisar` o handler exposto pode vazar info. Validar:

```python
except Exception as e:
    logger.exception("Falha ao enfileirar CWV")
    # NÃO retornar str(e) — sanitizar
    execucao.status = "falhou"
    execucao.erro_msg = "Falha ao enfileirar análise. Tente novamente."
    ...
```

### 3.4 Endpoint expõe `motivo_falha` estruturado

Atual: `erro_msg` é string livre. Frontend não consegue decidir UX baseado nisso.

**Adicionar enum**:

```python
# em app/schemas/cwv.py
MotivoFalha = Literal[
    "saldo_insuficiente",
    "rate_limit",
    "cliente_invalido",
    "cliente_removido",
    "psi_total",
    "timeout",
    "cancelada",
    "erro_interno",
]
```

E em `resultado_json` adicionar `motivo_falha` quando aplicável. Frontend usa pra decidir UX.

## 4. Frontend

### 4.1 Componente `CwvErroExecucao` (NOVO)

`frontend/src/components/cwv/cwv-erro-execucao.tsx`:

```tsx
import { AlertTriangleIcon, ClockIcon, BanIcon, CreditCardIcon, RefreshCwIcon, XCircleIcon } from "lucide-react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";

interface Props {
  motivo?: string;
  erroMsg?: string | null;
  saldoAtual?: number | null;
  saldoNecessario?: number;
  onTentarNovamente?: () => void;
}

const CONFIGS = {
  saldo_insuficiente: {
    icon: CreditCardIcon,
    title: "Saldo insuficiente",
    cta: (props: Props) => (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Saldo: <b>{props.saldoAtual ?? "—"}</b> · Necessário: <b>{props.saldoNecessario ?? "—"}</b>
        </p>
        <Link href="/creditos" className={buttonVariants()}>Comprar créditos</Link>
      </div>
    ),
  },
  rate_limit: {
    icon: ClockIcon,
    title: "Aguarde alguns minutos",
    description: "Você atingiu o limite temporário de análises (3 a cada 5 minutos).",
  },
  cliente_removido: {
    icon: BanIcon,
    title: "Cliente foi removido",
    description: "O cliente desta análise foi removido. Selecione outro cliente para nova análise.",
  },
  psi_total: {
    icon: AlertTriangleIcon,
    title: "PageSpeed Insights indisponível",
    description: "Não conseguimos analisar nenhuma URL — provavelmente a cota da Google PSI está esgotada hoje. Os créditos foram devolvidos.",
    cta: (props: Props) => (
      <Link href="/ferramentas/core-web-vitals" className={buttonVariants({ variant: "outline" })}>
        Tentar mais tarde
      </Link>
    ),
  },
  timeout: {
    icon: ClockIcon,
    title: "Análise demorou demais",
    description: "Tente com menos URLs por análise. Recomendamos no máximo 20 URLs por vez.",
  },
  cancelada: {
    icon: XCircleIcon,
    title: "Análise cancelada",
  },
  erro_interno: {
    icon: AlertTriangleIcon,
    title: "Erro ao processar análise",
    description: "Algo inesperado aconteceu. Nossa equipe foi notificada. Tente novamente em alguns minutos.",
    cta: (props: Props) => (
      <Button variant="outline" onClick={props.onTentarNovamente}>
        <RefreshCwIcon className="size-4 mr-1" /> Tentar novamente
      </Button>
    ),
  },
} as const;

export function CwvErroExecucao(props: Props) {
  const config = CONFIGS[props.motivo as keyof typeof CONFIGS] ?? CONFIGS.erro_interno;
  const Icon = config.icon;
  
  return (
    <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-6 sm:p-8">
      <div className="flex items-start gap-4">
        <div className="flex items-center justify-center size-12 rounded-full bg-destructive/10 shrink-0">
          <Icon className="size-6 text-destructive" />
        </div>
        <div className="space-y-3 flex-1">
          <h3 className="text-lg font-semibold">{config.title}</h3>
          {"description" in config && config.description && (
            <p className="text-sm text-muted-foreground">{config.description}</p>
          )}
          {props.erroMsg && !("description" in config) && (
            <p className="text-sm text-muted-foreground">{props.erroMsg}</p>
          )}
          {"cta" in config && config.cta && <div className="pt-2">{config.cta(props)}</div>}
        </div>
      </div>
    </div>
  );
}
```

### 4.2 Integração em `cwv-execucao-client.tsx`

Substituir o branch `statusFinal === "falhou"`:

```tsx
{statusFinal === "falhou" ? (
  <CwvErroExecucao
    motivo={(execucao?.resultado_json as { motivo_falha?: string })?.motivo_falha}
    erroMsg={erroMsg}
    saldoAtual={saldo?.saldo_total}
    saldoNecessario={execucao?.resultado_json?.custo_estimado as number}
    onTentarNovamente={() => router.push("/ferramentas/core-web-vitals")}
  />
) : ...}
```

### 4.3 Integração no form principal (cenários 1, 2, 3 no POST)

`cwv-form.tsx` — no `handleSubmit`, tratar HTTP status específicos:

```tsx
async function handleSubmit() {
  setErro("");
  setEnviando(true);
  try {
    const resultado = await analisarCwv({ cliente_id: clienteId, urls_por_template: urls, estrategia });
    router.push(`/ferramentas/core-web-vitals/execucao/${resultado.id}`);
  } catch (err: unknown) {
    const e = err as { status?: number; detalhe?: string };
    if (e.status === 402) {
      setErro(`Saldo insuficiente. Necessário ${custo} créditos.`);
      // Link no rodapé pra créditos já existe
    } else if (e.status === 429) {
      setErro("Aguarde alguns minutos antes de tentar de novo (limite: 3 análises a cada 5 minutos).");
    } else if (e.status === 404) {
      setErro("Cliente selecionado é inválido. Recarregue a página.");
    } else {
      setErro(e.detalhe || "Erro ao criar análise. Tente novamente.");
    }
  } finally {
    setEnviando(false);
  }
}
```

## 5. Testes

### 5.1 Backend

Adicionar em `backend/tests/cwv/test_router_analisar.py`:

```python
@pytest.mark.asyncio
async def test_analisar_saldo_insuficiente_retorna_402(client_autenticado_sem_creditos):
    resp = await client.post("/api/ferramentas/core-web-vitals/analisar", json={...})
    assert resp.status_code == 402

@pytest.mark.asyncio
async def test_analisar_4_chamadas_em_sequencia_dispara_rate_limit(client_autenticado):
    for i in range(4):
        resp = await client.post(...)
        if i < 3:
            assert resp.status_code == 202
        else:
            assert resp.status_code == 429
```

Em `backend/tests/cwv/test_workflow_integration.py`:

```python
@pytest.mark.asyncio
async def test_workflow_psi_429_em_todas_marca_falhou_e_libera_creditos(...):
    """REGRESSAO Cenário #6 — não cobrar nada quando ninguém analisou"""
    httpx_mock.add_response(status_code=429, json={"error": {"message": "Quota"}})
    saldo_antes = ...
    await executar_workflow_cwv(str(execucao.id))
    saldo_depois = ...
    assert saldo_depois == saldo_antes
    
    async with async_session_factory() as s:
        e = await s.get(ExecucaoFerramenta, execucao.id)
        assert e.status == "falhou"
        assert e.creditos_cobrados == 0
        assert e.resultado_json["motivo_falha"] == "psi_total"

@pytest.mark.asyncio
async def test_workflow_cliente_removido_durante_execucao(...):
    """REGRESSAO Cenário #4"""
    await execucao_criada(...)
    await deletar_cliente(...)  # antes do worker rodar
    await executar_workflow_cwv(...)
    assert execucao.status == "falhou"
    assert "removido" in execucao.erro_msg.lower()
```

## 6. Plano de execução

| Fase | O que | Esforço |
|---|---|---|
| E1 | Backend: fix Cenário #6 (não cobrar quando 0 URLs) + teste | 0.25 dia |
| E2 | Backend: fix Cenário #4 (cliente removido) + teste | 0.25 dia |
| E3 | Backend: adicionar `motivo_falha` ao resultado_json em cada caminho de falha | 0.25 dia |
| E4 | Frontend: componente `CwvErroExecucao` | 0.4 dia |
| E5 | Frontend: integrar em `cwv-execucao-client.tsx` e `cwv-form.tsx` | 0.25 dia |
| E6 | Testes de regressão (cenários 1, 2, 4, 6) | 0.1 dia |
| **Total** | | **~1.5 dias** |

## 7. Critério de pronto

- [ ] Cenário #6: PSI 429 em todas → execução `falhou`, créditos não cobrados, UX "PSI indisponível"
- [ ] Cenário #4: cliente deletado → execução `falhou` com `motivo_falha='cliente_removido'`
- [ ] Cenário #1: saldo insuficiente no POST → frontend mostra saldo atual + link comprar
- [ ] Cenário #2: rate limit → frontend mostra "aguarde X min"
- [ ] Cenário #7-9: branches `except` no workflow setam `motivo_falha` apropriado
- [ ] Frontend renderiza UX dedicada para cada `motivo_falha`
- [ ] Tests cobrem os 4 cenários novos

## 8. Não-objetivos

- Retry automático de PSI em backoff (V2 — depende de fila dedicada)
- Notificação por email quando análise falhou (V2)
- "Status page" pública mostrando se PSI Google está fora
- Webhooks pra integração externa

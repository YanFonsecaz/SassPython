# SPEC — CWV Testes Automatizados

**Status:** a aplicar · **Escopo:** backend (pytest) — código novo da ferramenta CWV ficou sem cobertura
**Dependências:** [[SPEC_CWV_Bugs_Postmortem]] (cada bug listado lá precisa ter pelo menos 1 teste correspondente aqui)
**Esforço estimado:** ~2 dias

## 1. Visão geral

### 1.1 Problema
Toda a ferramenta CWV foi implementada sem nenhum teste automatizado. O e2e de 2026-05-26 encontrou 9 bugs reais — todos teriam sido prevenidos com testes unitários ou de integração básicos. Esta SPEC define o conjunto mínimo de testes necessários antes de considerar a ferramenta produção-ready.

### 1.2 Princípios
- **Pirâmide invertida pra esta ferramenta**: foco em testes de **integração** (DB real em container ou em-memória, PSI mockado), porque os bugs encontrados foram majoritariamente em integração entre camadas, não em lógica isolada.
- **Cada bug do postmortem ⇒ 1 teste de regressão nomeado** (ex: `test_bug_n_problemas_count_correto`, `test_bug_workflow_commit_persiste_status`).
- **Tests rodam em CI sem cota PSI**: PSI é sempre mockado via `httpx_mock`.

## 2. Estrutura de arquivos

Criar diretório `backend/tests/cwv/`:

```
backend/tests/cwv/
├── __init__.py
├── conftest.py                          # fixtures comuns
├── fixtures/
│   ├── psi_payload_sucesso.json         # payload PSI real anonimizado
│   ├── psi_payload_lcp_alto.json
│   ├── psi_payload_wordpress.json       # com stackPacks=[{id: 'wordpress'}]
│   ├── psi_payload_nextjs.json
│   ├── psi_payload_vtex.json            # network-requests com vtexassets
│   └── psi_payload_quota_429.json
├── test_kb_loader.py
├── test_plataforma_detector.py
├── test_psi_client.py
├── test_psi_parser.py
├── test_priorizador.py
├── test_documentador.py
├── test_persistencia.py
├── test_workflow_integration.py
├── test_router_analisar.py
├── test_router_historico.py
└── test_router_reanalisar.py
```

Reuso de `backend/conftest.py` para fixtures de DB (já existem para outras ferramentas).

## 3. Conteúdo dos testes

### 3.1 `test_kb_loader.py` — Validação da Base de Conhecimento

```python
def test_kb_carrega_sem_erros():
    """KB YAML carrega e valida via Pydantic"""
    from app.services.cwv_kb import carregar_kb
    kb = carregar_kb()
    assert len(kb.entradas) >= 30

def test_kb_codigos_unicos():
    """Nenhum kb_codigo duplicado"""
    from app.services.cwv_kb import carregar_kb
    kb = carregar_kb()
    codigos = [e.codigo for e in kb.entradas]
    assert len(codigos) == len(set(codigos))

def test_kb_solucao_geral_obrigatoria():
    """Toda entrada tem solução 'geral'"""
    from app.services.cwv_kb import carregar_kb
    kb = carregar_kb()
    for e in kb.entradas:
        assert "geral" in e.solucoes

def test_kb_mapeamento_audit_kb_cobre_audits_principais():
    """Audits Lighthouse críticos têm mapeamento"""
    from app.services.cwv_kb import mapeamento_audit_kb
    mapa = mapeamento_audit_kb()
    obrigatorios = [
        "largest-contentful-paint-element",
        "unsized-images",
        "lcp-lazy-loaded",
        "cumulative-layout-shift",
        "total-blocking-time",
    ]
    for audit in obrigatorios:
        assert audit in mapa, f"Audit {audit} sem mapeamento na KB"

def test_kb_buscar_entrada_inexistente_retorna_none():
    from app.services.cwv_kb import buscar_entrada
    assert buscar_entrada("codigo-que-nao-existe") is None
```

### 3.2 `test_plataforma_detector.py`

```python
import json
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.mark.parametrize("fixture,esperado", [
    ("psi_payload_wordpress.json", "wordpress"),
    ("psi_payload_nextjs.json", "nextjs"),
    ("psi_payload_vtex.json", "vtex"),
])
def test_detecta_plataforma_via_stackpacks(fixture, esperado):
    from app.services.cwv_plataforma import detectar_plataforma
    payload = json.loads((FIXTURES / fixture).read_text())
    assert detectar_plataforma(payload) == esperado

def test_detecta_vtex_via_network_quando_stackpacks_vazio():
    """Fallback regex em network-requests"""
    payload = {
        "lighthouseResult": {
            "stackPacks": [],
            "audits": {"network-requests": {"details": {"items": [
                {"url": "https://lojax.vtexassets.com/img/a.png"},
            ]}}},
        }
    }
    from app.services.cwv_plataforma import detectar_plataforma
    assert detectar_plataforma(payload) == "vtex"

def test_payload_vazio_retorna_desconhecida():
    from app.services.cwv_plataforma import detectar_plataforma
    assert detectar_plataforma({}) == "desconhecida"
    assert detectar_plataforma({"lighthouseResult": {}}) == "desconhecida"
```

### 3.3 `test_psi_client.py` — **Cobre Bug #5 (fallback de key)**

```python
import pytest
from app.services.cwv_psi_client import fetch_psi, PSIError

@pytest.mark.asyncio
async def test_fetch_psi_sucesso_com_key1(httpx_mock, monkeypatch):
    monkeypatch.setattr("app.config.settings.api_psi_key", "KEY1")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "KEY2")
    httpx_mock.add_response(
        url=lambda url: "key=KEY1" in url,
        json={"lighthouseResult": {"finalUrl": "https://x.com"}},
    )
    data = await fetch_psi("https://x.com")
    assert "lighthouseResult" in data

@pytest.mark.asyncio
async def test_fetch_psi_429_em_key1_tenta_key2(httpx_mock, monkeypatch):
    """REGRESSAO Bug #5"""
    monkeypatch.setattr("app.config.settings.api_psi_key", "KEY1")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "KEY2")
    httpx_mock.add_response(
        url=lambda url: "key=KEY1" in url,
        status_code=429,
        json={"error": {"message": "Quota exceeded"}},
    )
    httpx_mock.add_response(
        url=lambda url: "key=KEY2" in url,
        json={"lighthouseResult": {"finalUrl": "https://x.com"}},
    )
    data = await fetch_psi("https://x.com")
    assert "lighthouseResult" in data

@pytest.mark.asyncio
async def test_fetch_psi_429_em_todas_keys_levanta_erro(httpx_mock, monkeypatch):
    monkeypatch.setattr("app.config.settings.api_psi_key", "KEY1")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "KEY2")
    httpx_mock.add_response(status_code=429, json={"error": {"message": "Quota"}})
    httpx_mock.add_response(status_code=429, json={"error": {"message": "Quota"}})
    with pytest.raises(PSIError, match="429"):
        await fetch_psi("https://x.com")

@pytest.mark.asyncio
async def test_fetch_psi_sem_keys_usa_anonimo(httpx_mock, monkeypatch):
    monkeypatch.setattr("app.config.settings.api_psi_key", "")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "")
    httpx_mock.add_response(json={"lighthouseResult": {"finalUrl": "x"}})
    data = await fetch_psi("https://x.com")
    assert data["lighthouseResult"]["finalUrl"] == "x"
```

### 3.4 `test_psi_parser.py`

```python
def test_parse_psi_extrai_metricas():
    from app.services.cwv_psi_client import parse_psi
    payload = {"lighthouseResult": {
        "categories": {"performance": {"score": 0.62}},
        "audits": {
            "largest-contentful-paint": {"score": 0.5, "numericValue": 4200.0, "scoreDisplayMode": "numeric"},
            "cumulative-layout-shift": {"score": 0.4, "numericValue": 0.18, "scoreDisplayMode": "numeric"},
        },
    }}
    parsed = parse_psi(payload)
    assert parsed["score_performance"] == 62
    assert parsed["lcp_ms"] == 4200.0
    assert parsed["cls"] == 0.18

def test_parse_psi_audits_informativos_excluidos():
    """Audits com scoreDisplayMode='informative' não entram em audits_falhos"""
    from app.services.cwv_psi_client import parse_psi
    payload = {"lighthouseResult": {
        "categories": {"performance": {"score": 0.5}},
        "audits": {
            "audit-info": {"score": 0.5, "scoreDisplayMode": "informative"},
        },
    }}
    parsed = parse_psi(payload)
    assert all(a["id"] != "audit-info" for a in parsed["audits_falhos"])

def test_normalizar_url():
    from app.services.cwv_psi_client import normalizar_url
    assert normalizar_url("https://x.com/produto/") == "https://x.com/produto"
    assert normalizar_url("http://EXEMPLO.com/Foo#bar") == "http://exemplo.com/Foo"
    assert normalizar_url("https://x.com") == "https://x.com/"
```

### 3.5 `test_priorizador.py`

```python
def test_prioriza_por_severidade_e_metrica():
    """LCP (peso 5) × severidade 5 = 25; CLS (peso 4) × severidade 4 = 16"""
    from app.agents.cwv.priorizador import priorizar_problemas
    problemas = [
        {"kb_codigo": "a", "severidade": 4, "metricas_afetadas": ["CLS"]},  # 4*4=16
        {"kb_codigo": "b", "severidade": 5, "metricas_afetadas": ["LCP"]},  # 5*5=25
        {"kb_codigo": "c", "severidade": 3, "metricas_afetadas": ["FCP"]},  # 3*2=6
    ]
    ordenados = priorizar_problemas(problemas)
    assert ordenados[0]["kb_codigo"] == "b"
    assert ordenados[1]["kb_codigo"] == "a"
    assert ordenados[2]["kb_codigo"] == "c"
    assert ordenados[0]["prioridade_ordem"] == 1
```

### 3.6 `test_documentador.py`

```python
@pytest.mark.asyncio
async def test_documentador_gera_markdown_com_secoes():
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    problemas = [{"kb_codigo": "lcp-imagem-grande", "contexto_especifico": {"display_value": "4.2s", "items": []}}]
    docs = await CWVDocumentadorAgent().documentar(problemas=problemas, plataforma="vtex")
    assert len(docs) == 1
    md = docs[0]["documentacao_md"]
    assert "## Problema" in md
    assert "## Solu" in md  # Solucao ou Solução
    assert "VTEX" in md or "vtex" in md  # adaptado p/ plataforma

@pytest.mark.asyncio
async def test_documentador_ignora_kb_codigo_invalido():
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    problemas = [{"kb_codigo": "codigo-inventado", "contexto_especifico": {}}]
    docs = await CWVDocumentadorAgent().documentar(problemas=problemas, plataforma="geral")
    assert docs == []
```

### 3.7 `test_persistencia.py` — **Cobre Bug #1, #2**

```python
@pytest.mark.asyncio
async def test_persistir_analise_sucesso(db_session, usuario_fixture, cliente_fixture, execucao_fixture):
    from app.services.cwv_persistencia import persistir_analise
    analise_id = await persistir_analise(
        db_session,
        execucao_id=str(execucao_fixture.id),
        cliente_id=str(cliente_fixture.id),
        usuario_id=str(usuario_fixture.id),
        url="https://x.com/",
        template="home",
        estrategia="mobile",
        plataforma="vtex",
        psi_resultado={"ok": True, "payload": {}, "parsed": {"score_performance": 80, "lcp_ms": 1500.0, "cls": 0.05, "inp_ms": 100, "fcp_ms": 1000, "ttfb_ms": 200, "tbt_ms": 100, "audits_falhos": []}},
        problemas=[{"kb_codigo": "x", "titulo": "T", "severidade": 4, "prioridade_ordem": 1, "metricas_afetadas": ["LCP"], "contexto_especifico": {}, "documentacao_md": "## P"}],
    )
    assert analise_id

@pytest.mark.asyncio
async def test_persistir_analise_falha_psi(db_session, ...):
    """Análise com PSI falho gera linha com status='falhou_psi'"""
    analise_id = await persistir_analise(..., psi_resultado={"ok": False, "erro": "PSI 429"}, problemas=[])
    # Validar via select que status='falhou_psi' e erro_msg='PSI 429'

@pytest.mark.asyncio
async def test_buscar_historico_url_retorna_contagens_corretas(db_session, ...):
    """REGRESSAO Bug #1: n_problemas e n_problemas_alta_severidade vêm do banco"""
    # Cria 1 análise com 5 problemas (3 severidade>=4, 2 severidade=2)
    # ...
    historico = await buscar_historico_url(db_session, str(cliente.id), "https://x.com/")
    assert historico[0]["n_problemas"] == 5
    assert historico[0]["n_problemas_alta_severidade"] == 3

@pytest.mark.asyncio
async def test_buscar_ultima_analise_url_retorna_mais_recente(db_session, ...):
    """REGRESSAO Bug #2"""
    # Cria 2 análises da mesma URL com plataformas diferentes
    ultima = await buscar_ultima_analise_url(db_session, cliente_id, url)
    assert ultima.plataforma_detectada == "wordpress"  # a mais recente
```

### 3.8 `test_workflow_integration.py` — **Cobre Bug #6, #7**

```python
@pytest.mark.asyncio
async def test_workflow_completo_persiste_e_atualiza_execucao(db_session, httpx_mock, execucao_fixture):
    """REGRESSAO Bugs #6 e #7"""
    httpx_mock.add_response(json={"lighthouseResult": {
        "finalUrl": "https://x.com/",
        "categories": {"performance": {"score": 0.62}},
        "audits": {
            "largest-contentful-paint": {"score": 0.4, "numericValue": 4200, "scoreDisplayMode": "numeric"},
            "cumulative-layout-shift": {"score": 0.5, "numericValue": 0.18, "scoreDisplayMode": "numeric"},
        },
        "stackPacks": [{"id": "wordpress"}],
    }})

    from app.agents.cwv.workflow import executar_workflow_cwv
    await executar_workflow_cwv(str(execucao_fixture.id))

    # Re-lê em sessão nova (importante: garante que commit aconteceu)
    async with async_session_factory() as session_new:
        execucao = await session_new.get(ExecucaoFerramenta, execucao_fixture.id)
        assert execucao.status == "concluida"           # Bug #7
        assert execucao.resultado_json is not None       # Bug #6
        analise_ids = execucao.resultado_json["analise_ids"]
        assert len(analise_ids) == 1                     # Bug #6
        analise = await session_new.get(CwvAnalise, UUID(analise_ids[0]))
        assert analise.status == "sucesso"
        assert analise.plataforma_detectada == "wordpress"
```

### 3.9 `test_router_analisar.py` — **Cobre Bug #3**

```python
@pytest.mark.asyncio
async def test_analisar_aceita_request_valida(client_autenticado, cliente_do_usuario):
    """REGRESSAO Bug #3 (HttpUrl não serializável)"""
    resp = await client_autenticado.post("/api/ferramentas/core-web-vitals/analisar", json={
        "cliente_id": str(cliente_do_usuario.id),
        "urls_por_template": {"home": ["https://example.com/"]},
        "estrategia": "mobile",
    })
    assert resp.status_code == 202   # antes do fix: 500
    body = resp.json()
    assert "id" in body
    assert body["custo_estimado"] == 16  # base 15 + 1 url

@pytest.mark.asyncio
async def test_analisar_sem_urls_retorna_422(client_autenticado, cliente_do_usuario):
    resp = await client_autenticado.post("/api/ferramentas/core-web-vitals/analisar", json={
        "cliente_id": str(cliente_do_usuario.id),
        "urls_por_template": {},
        "estrategia": "mobile",
    })
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_analisar_cliente_de_outro_usuario_retorna_404(client_autenticado, cliente_de_outro_usuario):
    resp = await client_autenticado.post("/api/ferramentas/core-web-vitals/analisar", json={
        "cliente_id": str(cliente_de_outro_usuario.id),
        "urls_por_template": {"home": ["https://example.com/"]},
        "estrategia": "mobile",
    })
    assert resp.status_code == 404
```

### 3.10 `test_router_historico.py` — **Cobre Bug #2**

```python
@pytest.mark.asyncio
async def test_historico_url_retorna_plataforma_e_template_da_ultima(client_autenticado, ...):
    """REGRESSAO Bug #2"""
    # Setup: cria 2 analises da mesma URL com plataformas diferentes
    resp = await client_autenticado.get(f"/api/ferramentas/core-web-vitals/historico-url?cliente_id={cliente_id}&url=https://x.com/")
    body = resp.json()
    assert body["plataforma_detectada"] != ""
    assert body["template_tipo"] != ""

@pytest.mark.asyncio
async def test_historico_url_cliente_de_outro_usuario_retorna_404(...):
    """REGRESSAO Bug #2 (security)"""
    resp = await client_autenticado.get(f"/api/ferramentas/core-web-vitals/historico-url?cliente_id={cliente_de_outro_usuario}&url=...")
    assert resp.status_code == 404
```

### 3.11 `test_router_reanalisar.py`

```python
@pytest.mark.asyncio
async def test_reanalisar_cria_nova_execucao_com_mesma_url(client_autenticado, analise_fixture):
    resp = await client_autenticado.post(f"/api/ferramentas/core-web-vitals/reanalisar/{analise_fixture.id}")
    assert resp.status_code == 202
    body = resp.json()
    assert body["n_urls"] == 1

@pytest.mark.asyncio
async def test_reanalisar_analise_de_outro_usuario_retorna_404(...):
    resp = await client_autenticado.post(f"/api/ferramentas/core-web-vitals/reanalisar/{analise_outro_usuario.id}")
    assert resp.status_code == 404
```

## 4. Fixtures de conftest.py

```python
# backend/tests/cwv/conftest.py
import json
from pathlib import Path
import pytest
import pytest_asyncio

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def psi_payload_sucesso():
    return json.loads((FIXTURES_DIR / "psi_payload_sucesso.json").read_text())

@pytest_asyncio.fixture
async def usuario_fixture(db_session):
    # cria usuário de teste
    ...

@pytest_asyncio.fixture
async def cliente_fixture(db_session, usuario_fixture):
    ...

@pytest_asyncio.fixture
async def execucao_fixture(db_session, usuario_fixture, cliente_fixture):
    """Cria ExecucaoFerramenta de tipo core_web_vitals, status='executando'"""
    ...

@pytest_asyncio.fixture
async def client_autenticado(usuario_fixture):
    """AsyncClient com cookie/token JWT já populado"""
    ...
```

## 5. CI

- Pytest deve rodar todos os testes de `backend/tests/cwv/` em PR contra `main`
- Cobertura mínima: 70% de linhas em `app/services/cwv_*.py`, `app/agents/cwv/*.py`, `app/routers/ferramentas_cwv.py`
- `pytest --cov-report=term-missing` no make `test`
- Verificar que `httpx_mock` está em `pyproject.toml` dev deps

## 6. Não-objetivos

- Testes E2E com Playwright (estão fora de pytest — ver SPECs 3-7 que definem cenários manuais)
- Testes de carga / performance
- Testes do frontend (Vitest/Jest) — fora do escopo desta SPEC
- Testes de chamada PSI real contra a API do Google — usa-se sempre mocks

## 7. Plano de execução

| Fase | O que | Esforço |
|---|---|---|
| 1 | Setup conftest + fixtures + 3 payloads PSI reais (anonimizados) | 0.5 dia |
| 2 | Testes KB + parser + plataforma + priorizador + documentador | 0.5 dia |
| 3 | Testes persistencia + workflow integration (com DB real) | 0.5 dia |
| 4 | Testes router (com auth client) | 0.5 dia |
| **Total** | | **~2 dias** |

## 8. Critério de pronto

- [ ] Todos os 9 bugs do [[SPEC_CWV_Bugs_Postmortem]] têm pelo menos 1 teste de regressão com docstring `"REGRESSAO Bug #X"`
- [ ] `pytest backend/tests/cwv/` passa local sem flaky
- [ ] Cobertura ≥70% nos módulos novos
- [ ] CI executa testes em PR e bloqueia merge se falhar
- [ ] README de testes adicionado em `backend/tests/cwv/README.md` explicando como rodar

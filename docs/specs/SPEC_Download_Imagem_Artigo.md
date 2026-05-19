# SPEC — Download de imagem do artigo

**Status:** pendente
**Escopo:** backend (persistência + endpoint) + frontend (botão de download)
**Crédito:** não muda (custo já está em `CUSTO_IMAGEM`)
**Esforço:** ~2h

## 1. Resumo

Hoje a ferramenta `gerar_artigo` produz uma imagem via OpenAI (`gpt-image-1*`) e armazena uma string em `resultado_json.imagem_url`. Essa string pode ser:

- uma URL temporária da OpenAI (expira em ~1h) — caminho mais comum;
- um data URL base64 (fallback de `b64_json`).

A UI renderiza `<img src={imagemUrl}>` em `frontend/src/components/ferramentas/preview-artigo.tsx:39-47` mas **não oferece download**. O usuário precisa usar "clicar com botão direito → salvar". Pior: depois de ~1h a URL da OpenAI expira e a imagem some do histórico.

Esta SPEC entrega: imagem persistida no servidor, endpoint protegido para download, botão "Baixar imagem" na UI com nome de arquivo derivado do título do artigo.

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | Imagem some do histórico depois de ~1h | `resultado_json.imagem_url` aponta para `oaidalleapiprodscus.blob.core.windows.net/...` que expira | Backend não baixa nem persiste o binário |
| 2 | Não há botão de download na UI | `preview-artigo.tsx` só renderiza `<img>` | Funcionalidade nunca foi implementada |
| 3 | Nome do arquivo salvo pelo browser é aleatório (UUID OpenAI) | Sem `Content-Disposition` no servidor da OpenAI | — |
| 4 | Quando o fallback retorna data URL, a string em `imagem_url` fica com ~3 MB e infla `resultado_json` no Postgres | `graceful_degradation.py:82` retorna `data:image/png;base64,...` | Sem persistência separada |

## 3. Decisão de arquitetura

**Persistir o binário em filesystem local (`backend/uploads/imagens/{execucao_id}.png`)** e guardar em `imagem_url` apenas o path relativo (`/uploads/imagens/{execucao_id}.png`). Endpoint serve via `FileResponse` com autenticação.

Alternativas consideradas e descartadas:

- **S3/cloud storage**: prematuro pro estágio do projeto. Filesystem local resolve até 1000+ usuários. Migração depois é trivial (mesma interface).
- **Manter base64 inline no `resultado_json`**: infla o banco rapidamente (3 MB × N artigos). Postgres TOAST funciona mas backups e replicação ficam pesados.
- **Reproxy on demand (rebaixar de openai a cada request)**: URLs expiram, não tem como rebaixar depois.

## 4. Mudanças

### 4.1 Backend — persistir imagem

`backend/app/core/graceful_degradation.py` — `gerar_imagem_com_fallback` continua retornando `(str | None, bool)`, mas o caller no agente passa a baixar e salvar.

`backend/app/agents/gerador_imagem.py` — depois de `gerar_imagem_com_fallback`, baixar o binário e gravar em disco:

```python
import httpx
from pathlib import Path
from app.config import settings

IMAGENS_DIR = Path(settings.uploads_dir) / "imagens"
IMAGENS_DIR.mkdir(parents=True, exist_ok=True)

async def _persistir_imagem(imagem_url: str, execucao_id: str) -> str | None:
    if not imagem_url:
        return None
    destino = IMAGENS_DIR / f"{execucao_id}.png"
    try:
        if imagem_url.startswith("data:image/"):
            import base64
            header, b64 = imagem_url.split(",", 1)
            destino.write_bytes(base64.b64decode(b64))
        else:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(imagem_url)
                resp.raise_for_status()
                destino.write_bytes(resp.content)
        return f"/api/execucoes/{execucao_id}/imagem"
    except Exception as e:
        logger.warning("Falha ao persistir imagem para %s: %s", execucao_id, e)
        return imagem_url  # fallback: usa URL original mesmo que expire
```

E em `gerador_imagem.py:48` chamar `_persistir_imagem(imagem_url, estado.execucao_id)` antes do return. Para receber `execucao_id`, propagar via `EstadoWorkflow` (já existe `id` em `execucao` do estado — checar o tipo).

`backend/app/config.py` — adicionar:

```python
uploads_dir: str = "uploads"  # relativo a backend/ ou path absoluto
```

E criar diretório `backend/uploads/imagens/` (gitignored) — adicionar `uploads/` ao `.gitignore` do backend.

### 4.2 Backend — endpoint de download

`backend/app/routers/ferramentas.py` (ou novo `imagens.py`):

```python
@router.get("/execucoes/{execucao_id}/imagem")
async def baixar_imagem(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> FileResponse:
    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao or str(execucao.usuario_id) != str(usuario.id):
        raise HTTPException(404, "Execucao nao encontrada")
    caminho = Path(settings.uploads_dir) / "imagens" / f"{execucao_id}.png"
    if not caminho.exists():
        raise HTTPException(404, "Imagem nao disponivel")
    titulo = (execucao.resultado_json or {}).get("artigo_titulo", "imagem")
    filename = _slugify(titulo)[:80] + ".png"
    return FileResponse(
        caminho,
        media_type="image/png",
        filename=filename,
        headers={"Cache-Control": "private, max-age=3600"},
    )
```

Helper `_slugify`:

```python
import re, unicodedata
def _slugify(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9\-_ ]", "", s).strip().replace(" ", "-").lower()
    return s or "imagem"
```

Autorização: a verificação `execucao.usuario_id == usuario.id` é estrita (não permite admin override por enquanto). Multi-tenant fica isolado.

### 4.3 Backend — registrar router

`backend/app/main.py` — incluir o router de imagens depois de `ferramentas`.

### 4.4 Frontend — botão de download

`frontend/src/components/ferramentas/preview-artigo.tsx`:

Acima da imagem (ou sobreposto no canto), adicionar botão:

```tsx
{imagemUrl && (
  <div className="relative w-full aspect-[16/7] overflow-hidden bg-surface-light group">
    <img src={imagemUrl} alt={titulo} className="w-full h-full object-cover" />
    <Button
      variant="outline"
      size="sm"
      onClick={() => baixarImagem(imagemUrl, titulo)}
      className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity bg-background/90 backdrop-blur"
    >
      <DownloadIcon className="size-3.5" />
      Baixar imagem
    </Button>
  </div>
)}
```

Helper `baixarImagem`:

```tsx
async function baixarImagem(url: string, titulo: string) {
  const resp = await fetch(url, { credentials: "include" });
  if (!resp.ok) {
    toast.error("Imagem indisponivel");
    return;
  }
  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = slugify(titulo).slice(0, 80) + ".png";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
```

Importar `DownloadIcon` de `lucide-react`. Slugify client-side mesmo padrão que backend (consistência no nome).

**Acessibilidade:** botão sempre acessível via tab, não apenas hover (`opacity-0 group-hover:opacity-100 focus-visible:opacity-100`).

### 4.5 Migração de execuções antigas

Execuções já no banco têm URL OpenAI expirada — não há como recuperar. **Sem migração**: para artigos antigos, o botão tenta o download, falha (URL expirada → CORS ou 403) e exibe toast "Imagem indisponivel". UI degrada graciosamente.

Opcionalmente, um script `backend/scripts/migrar_imagens.py` pode varrer execuções com `imagem_url` ainda começando com `https://oaidalleapi...` e baixar as que ainda estão no ar. Fora do escopo desta SPEC.

## 5. Verificação

### 5.1 Caso feliz (artigo novo)

1. Restart backend + worker.
2. Rodar uma execução de `gerar_artigo` via UI.
3. Aguardar conclusão.
4. Verificar:
   - Arquivo existe em `backend/uploads/imagens/{execucao_id}.png`
   - `resultado_json.imagem_url` é `/api/execucoes/{id}/imagem`
   - UI mostra imagem
   - Clicar "Baixar imagem" → arquivo `como-escolher-o-cnae-certo.png` baixa
5. Reabrir o histórico no dia seguinte → imagem ainda renderiza.

### 5.2 Permissão

```bash
# Usuário A faz uma execução
EID=$(curl -s ... | jq -r .id)

# Usuário B tenta baixar
curl -i -H "Authorization: Bearer $TOKEN_B" /api/execucoes/$EID/imagem
# Esperado: 404
```

### 5.3 Imagem ausente

Endpoint para execução sem imagem (falha do modelo) → 404 com detail `"Imagem nao disponivel"`. Frontend mostra toast, não quebra.

### 5.4 Tamanho do `resultado_json`

```sql
SELECT pg_column_size(resultado_json) FROM execucoes_ferramentas WHERE ferramenta='gerar_artigo' ORDER BY criado_em DESC LIMIT 5;
```

Esperado: < 50 KB (sem base64 inline).

## 6. Riscos

- **Disco enche**: cada PNG ~1-3 MB. 10k artigos = ~30 GB. Não bloqueante hoje, mas adicionar alerta de disco no `/health` num PR futuro. Quando passar de ~50 GB, migrar pra S3.
- **httpx timeout no download**: 60s deve ser suficiente. Se a OpenAI demorar mais, persiste como `None` e UI degrada.
- **Concorrência no `mkdir`**: `mkdir(parents=True, exist_ok=True)` é safe. Sem race.
- **CORS no fetch do data URL**: data URLs não passam por fetch HTTP. O caso "imagem antiga ainda é data URL" só ocorre em execuções pré-spec; após esta SPEC, todas viram `/api/...`.

## 7. Fora de escopo

- Migração de imagens antigas (URLs OpenAI expiradas).
- Múltiplas imagens por artigo.
- Edição/regeneração da imagem.
- Watermark.
- Variações de tamanho (thumbnail, banner). Hoje é só 1024×1024 ou 1024×1536.
- S3 / CDN.

## 8. Arquivos alterados

- `backend/app/agents/gerador_imagem.py` — chama `_persistir_imagem` antes do return.
- `backend/app/agents/imagem_storage.py` (NOVO) — helper `_persistir_imagem`, `IMAGENS_DIR`.
- `backend/app/routers/imagens.py` (NOVO) — endpoint `GET /api/execucoes/{id}/imagem`.
- `backend/app/main.py` — registra router.
- `backend/app/config.py` — `uploads_dir`.
- `backend/.gitignore` — adicionar `uploads/`.
- `frontend/src/components/ferramentas/preview-artigo.tsx` — botão + helper `baixarImagem`.

# SPEC — Histórico "Meus Pareceres" (endpoint + UI)

**Status:** ✅ implementado · **Data:** 2026-05-30
**Escopo:** backend — `GET /parecer/historico` + `GET /parecer/{id}` · frontend — lista + tela de visualização/edição de parecer salvo
**Reusos:** `parecer_persistencia.listar_pareceres/buscar_parecer`, `EditorParecer`, `EmptyState`, `PageHeader`, `useClientes`
**Specs irmãs:** [[SPEC_Parecer_Dados_e_Persistencia]] (dados) · [[SPEC_Parecer_Editor_Frontend]] (editor reutilizado)

## 1. Por que existe

Um parecer é um **artefato que o usuário quer revisitar**: reabrir, ajustar e **re-baixar o `.docx`**
depois (ex.: o cliente pediu correção). A tabela `parecer` dedicada ([[SPEC_Parecer_Dados_e_Persistencia]])
habilita isso. Sem essa tela, o valor do documento "se perde" após o download.

## 2. Backend

### 2.1 `GET /parecer/historico`

```python
@router.get("/parecer/historico")
async def historico_parecer(
    cliente_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    if cliente_id:
        await _validar_cliente(db, str(usuario.id), str(cliente_id))
    from app.services import parecer_persistencia
    itens = await parecer_persistencia.listar_pareceres(db, str(usuario.id), str(cliente_id) if cliente_id else None)
    return {"pareceres": [
        {"id": str(p.id), "titulo": p.titulo, "cliente_nome": p.cliente_nome, "site": p.site,
         "plataforma": p.plataforma, "n_imagens": p.n_imagens, "status": p.status,
         "criado_em": str(p.criado_em)} for p in itens
    ]}
```

### 2.2 `GET /parecer/{parecer_id}` — documento completo

Definido em [[SPEC_Parecer_Dados_e_Persistencia]] §4.2: retorna `parecer_html`, `estrutura`,
`meta`, `cliente_nome`, datas. Filtra por `usuario_id` → `404` se não for do usuário.

## 3. Frontend

### 3.1 API client (`src/lib/api/parecer.ts`, estender)

```ts
export interface ParecerResumo { id: string; titulo: string; cliente_nome: string; site?: string;
  plataforma?: string; n_imagens: number; status: string; criado_em: string; }
export interface ParecerDoc { id: string; titulo: string; parecer_html: string; estrutura: unknown;
  meta: Record<string, string>; cliente_nome: string; criado_em: string; }

export const listarPareceres = (clienteId?: string) =>
  api.get<{ pareceres: ParecerResumo[] }>(`/ferramentas/parecer/historico${clienteId ? `?cliente_id=${clienteId}` : ""}`);
export const buscarParecerDoc = (id: string) => api.get<ParecerDoc>(`/ferramentas/parecer/${id}`);
```

### 3.2 Rotas / páginas

| Rota | Arquivo | Função |
|---|---|---|
| `/ferramentas/parecer` | `parecer/page.tsx` | criar novo (editor + gerar) — [[SPEC_Parecer_Editor_Frontend]] |
| `/ferramentas/parecer/historico` | `parecer/historico/page.tsx` | **lista** "Meus Pareceres" (filtro por cliente) |
| `/ferramentas/parecer/[id]` | `parecer/[id]/page.tsx` | **abrir/editar** parecer salvo + **Baixar .docx** |

> Next 16 / static export: `[id]` é rota dinâmica. Como o app usa `output:"export"`, usar a
> abordagem de rota client-side já adotada no projeto para detalhes de execução (ex.: o CWV tem
> `core-web-vitals/execucao/` e `url/`). **Conferir em `node_modules/next/dist/docs/`** como o repo
> trata dynamic routes em export (provável render client-side lendo o `id` da URL via hook). Seguir o
> mesmo padrão das telas de detalhe existentes.

### 3.3 Lista (`historico/page.tsx`)

- `PageHeader title="Meus Pareceres" action={<Link href="/ferramentas/parecer">Novo parecer</Link>}`.
- Filtro por cliente (`useClientes`).
- Tabela/cards: título, cliente, site, plataforma, nº de imagens, data; clique → `/ferramentas/parecer/[id]`.
- **EmptyState** quando vazio ("Você ainda não gerou nenhum parecer" + CTA "Novo parecer").
- **ErrorState** + retry no padrão do projeto.

### 3.4 Visualização/edição (`[id]/page.tsx`)

- Carrega `buscarParecerDoc(id)` → `EditorParecer content={parecer_html} editable`.
- Botão **Baixar .docx** (`exportarParecer(id, htmlEditado)` — persiste a edição).
- Botão **Voltar** para a lista.
- Estado de loading/erro padrão.

### 3.5 Navegação

- Item principal "Parecer Técnico" já entra no sidebar ([[SPEC_Parecer_Editor_Frontend]] §8).
- Dentro da página da ferramenta, um link/tab **"Meus Pareceres"** → `/ferramentas/parecer/historico`
  (padrão do CWV, que separa ferramenta × histórico). Opcional: também acessível pelo Histórico genérico.

## 4. Critérios de aceite

- [ ] `GET /parecer/historico` lista só os pareceres do usuário (e filtra por cliente quando informado)
- [ ] Lista mostra título/cliente/data e abre o parecer ao clicar
- [ ] Tela `[id]` carrega o HTML salvo no editor, permite editar e **re-baixar** o `.docx` com a edição
- [ ] EmptyState/ErrorState corretos
- [ ] `next build` (static export) ok com a rota dinâmica `[id]`

# SPEC — Editor (Tiptap) + Frontend

**Status:** ✅ implementado · **Data:** 2026-05-30
**Escopo:** frontend — editor Tiptap (entrada + preview editável), paste/compressão de imagem, página, hook de polling, api client, item no sidebar
**Reusos:** `@/lib/api` (`api`, `mensagemErroAmigavel`), `useClientes`, `PageHeader`, Sonner, padrões de `formulario-gerar-artigo.tsx` e `lib/api/cwv.ts`
**Specs irmãs:** [[SPEC_Parecer_Ferramenta]] (rota consumida) · [[SPEC_Parecer_Geracao_Docx]] (contrato de HTML)

> ⚠️ **Next.js 16 é não-padrão neste repo** (`frontend/AGENTS.md`). **Antes de codar**, ler os guias
> em `node_modules/next/dist/docs/` e respeitar avisos de deprecação. O app é **static export**
> (`output:"export"`), então o editor (usa `window`) precisa ser **client-only**.

## 1. Dependências (`frontend/package.json`, editar)

```json
"@tiptap/react": "^2",
"@tiptap/starter-kit": "^2",
"@tiptap/extension-image": "^2",
"@tiptap/extension-table": "^2",
"@tiptap/extension-table-row": "^2",
"@tiptap/extension-table-cell": "^2",
"@tiptap/extension-table-header": "^2"
```

Tiptap é **MIT** (sem chave de licença), React 19-compatível, com excelente paste/drag de imagem.
Confirmar a major compatível com React 19.2 / Next 16 no momento da instalação.

## 2. Arquivos novos / editados

| Arquivo | Tipo | Função |
|---|---|---|
| `src/components/ferramentas/editor-parecer.tsx` | novo | Wrapper Tiptap reutilizável (entrada **e** preview editável) |
| `src/components/ferramentas/formulario-parecer.tsx` | novo | Seletor de cliente + editor + botões Gerar/Baixar + estados |
| `src/lib/api/parecer.ts` | novo | Wrappers da API (`custo`, `gerar`, `execucao`, `exportar`→blob) |
| `src/hooks/use-parecer.ts` | novo | Orquestra gerar + **polling** do status |
| `src/lib/image-compress.ts` | novo | Downscale/compressão client-side antes do base64 |
| `src/app/(app)/ferramentas/parecer/page.tsx` | novo | Página (PageHeader + formulário) |
| `src/components/layout/sidebar.tsx` | editar | Item de navegação |

## 3. `editor-parecer.tsx` — Tiptap client-only

- `"use client"`; importar no formulário via `next/dynamic` com `{ ssr: false }` (static export).
- Extensões: `StarterKit` (headings h1–h3, bold, italic, listas, parágrafo, hr) + `Image` + `Table*`.
  **Restringir** o schema ao [vocabulário do contrato](SPEC_Parecer_Geracao_Docx.md#11-vocabulário-html-suportado-contrato-editor--docx)
  (não habilitar link/code-block/etc. que o renderer não converte).
- **Paste/drop de imagem:** handler que intercepta `ClipboardEvent`/`DropEvent`, pega os arquivos de
  imagem, passa por `comprimirImagem()` (§4) e insere como nó `image` com `src` = data URI.
- Toolbar mínima (botões Base UI / lucide): Parágrafo·H2·H3, **B**, *I*, lista, tabela, desfazer/refazer.
  (No print enviado o usuário queria uma barra assim — replicar o essencial.)
- Props: `content: string` (HTML), `editable: boolean`, `onChange(html)`, `placeholder`.
- Reutilização: na **entrada** começa vazio (`placeholder: "Cole prints e descreva o problema…"`);
  no **preview** recebe `content = parecer_html` e continua editável.

```tsx
"use client";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
// + Table, TableRow, TableHeader, TableCell

export function EditorParecer({ content, editable = true, onChange, placeholder }: Props) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] }, codeBlock: false }),
      Image.configure({ inline: false, allowBase64: true }),
      // Table, TableRow, TableHeader, TableCell
    ],
    content,
    editable,
    editorProps: {
      handlePaste: (_v, event) => inserirImagensDoEvento(event, editor, onChange),
      handleDrop: (_v, event) => inserirImagensDoEvento(event, editor, onChange),
      attributes: { class: "prose max-w-none min-h-[420px] p-4 focus:outline-none" },
    },
    onUpdate: ({ editor }) => onChange?.(editor.getHTML()),
    immediatelyRender: false, // SSR/static export safety
  });
  return <EditorContent editor={editor} />;
}
```

> Estilo: o app já tem `@tailwindcss/typography` (classe `prose`) e `react-markdown` com
> `.markdown-content` — reaproveitar a tipografia para o editor parecer com o visual do app.

## 4. Compressão de imagem client-side (`src/lib/image-compress.ts`, novo)

Evita payloads enormes (base64 no Postgres) — ver limite em [[SPEC_Parecer_Ferramenta]] §6.

```ts
export async function comprimirImagem(file: File, maxLado = 1600, quality = 0.8): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const escala = Math.min(1, maxLado / Math.max(bitmap.width, bitmap.height));
  const w = Math.round(bitmap.width * escala), h = Math.round(bitmap.height * escala);
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, w, h);
  // GIF animado perde animação (vira 1º frame) — aceitável: a evidência é estática.
  return canvas.toDataURL("image/webp", quality); // ou image/jpeg p/ máxima compat
}
```

> Nota: GIF animado é rasterizado para 1 frame aqui; o backend também trata GIF (1º frame). Para o
> parecer (evidência estática) isso é o comportamento desejado.

## 5. API client (`src/lib/api/parecer.ts`, novo)

Espelha `lib/api/cwv.ts`. O `exportar` baixa **blob** (não JSON):

```ts
import { api } from "@/lib/api";

export interface BlocoEntrada { texto: string; imagens: string[]; }
export interface GerarParecerReq { cliente_id: string; titulo_sugerido?: string; blocos: BlocoEntrada[]; }
export interface ParecerExecucao {
  id: string; status: string; etapa_atual?: string | null;
  parecer_html?: string | null; estrutura?: unknown; erro_msg?: string | null;
}

export const custoParecer = (b: GerarParecerReq) => api.post<{ custo: number; n_imagens: number }>("/ferramentas/parecer/custo", b);
export const gerarParecer = (b: GerarParecerReq) => api.post<{ id: string; status: string }>("/ferramentas/parecer/gerar", b);
export const buscarExecucaoParecer = (id: string) => api.get<ParecerExecucao>(`/ferramentas/parecer/execucao/${id}`);

export async function exportarParecer(id: string, html: string, nome?: string): Promise<Blob> {
  // usar o token/CSRF do mesmo jeito que `api`; aqui via fetch direto para receber blob
  const resp = await fetch(`/api/ferramentas/parecer/${id}/exportar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ html, nome_arquivo: nome }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.blob();
}
```

> Conferir como `@/lib/api` injeta Bearer/CSRF e replicar em `authHeaders()` para o `fetch` do blob
> (ou estender `api` para suportar `responseType: "blob"`).

## 6. Hook (`src/hooks/use-parecer.ts`, novo)

Gera e faz **polling** do status (padrão dos hooks existentes; intervalo ~2s, timeout ~10min):

```ts
export function useParecer() {
  const [estado, setEstado] = useState<"idle"|"gerando"|"pronto"|"erro">("idle");
  const [execucaoId, setExecucaoId] = useState<string | null>(null);
  const [html, setHtml] = useState<string>("");

  async function gerar(req: GerarParecerReq) {
    setEstado("gerando");
    try {
      const { id } = await gerarParecer(req);
      setExecucaoId(id);
      const final = await aguardarConclusao(id);     // polling de buscarExecucaoParecer
      if (final.status === "concluida" && final.parecer_html) {
        setHtml(final.parecer_html); setEstado("pronto");
      } else {
        toast.error(final.erro_msg || "Falha ao gerar o parecer"); setEstado("erro");
      }
    } catch (e) { toast.error(mensagemErroAmigavel(e)); setEstado("erro"); }
  }

  async function baixar(nome?: string) {
    if (!execucaoId) return;
    const blob = await exportarParecer(execucaoId, html, nome);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `${nome ?? "parecer-tecnico"}.docx`; a.click();
    URL.revokeObjectURL(url);
  }

  return { estado, html, setHtml, gerar, baixar };
}
```

## 7. Página + formulário

- `src/app/(app)/ferramentas/parecer/page.tsx`: `PageHeader title="Parecer Técnico"` + `<FormularioParecer/>`.
- `formulario-parecer.tsx`:
  - seletor de **cliente** (`useClientes`);
  - `EditorParecer` (entrada) — extrair `blocos` do HTML do editor para o request (texto + imagens em
    ordem). Estratégia simples: percorrer os nós do conteúdo (parágrafos viram `texto`, `img` viram
    `imagens`), agrupando texto+imagens contíguos em blocos;
  - botão **Gerar** (desabilitado sem cliente/sem conteúdo; mostra custo estimado via `custoParecer`);
  - estados loading/erro no padrão de `formulario-gerar-artigo.tsx` (+ Sonner);
  - ao ficar **pronto**, troca para o `EditorParecer` com `content=html` (preview editável) +
    botão **Baixar .docx**.

## 8. Navegação (`src/components/layout/sidebar.tsx`, editar)

```tsx
import { FileTextIcon } from "lucide-react";
// dentro de NAV_ITEMS, junto das ferramentas:
{ href: "/ferramentas/parecer", label: "Parecer Técnico", icon: FileTextIcon },
```

## 9. Acessibilidade / UX (padrão do projeto)

- Botões com `aria-label`; estado de erro com `role="alert"` (igual aos formulários atuais).
- Empty state no editor (`placeholder`) e dica "cole prints (Ctrl/Cmd+V) e descreva o problema".
- Microcopy em pt-BR com acentuação (ver auditoria UX do projeto).

## 10. Critérios de aceite

- [ ] Editor carrega client-only (sem erro de SSR no `next build`/static export)
- [ ] Colar print (Ctrl/Cmd+V) insere a imagem **comprimida** inline; drag-drop idem
- [ ] **Gerar** envia `blocos` (texto+imagens em ordem), mostra loading e faz polling até concluir
- [ ] Preview carrega o `parecer_html` no editor e permanece **editável**
- [ ] **Baixar .docx** baixa o arquivo; edições no editor refletem no arquivo
- [ ] Item "Parecer Técnico" aparece no sidebar e roteia para a página
- [ ] `eslint` + `next build` limpos

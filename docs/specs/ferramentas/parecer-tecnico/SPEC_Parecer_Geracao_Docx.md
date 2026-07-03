# SPEC — Geração do `.docx` (renderer no padrão da casa)

**Status:** ✅ implementado · **Data:** 2026-05-30
**Escopo:** backend — `app/services/parecer_service.py` (`estrutura_para_html`, `html_para_docx_bytes`) + asset `parecer_template.docx` + deps
**Reusos:** `selectolax` (já é dependência), Pillow (usado em `imagem_storage.py`)
**Specs irmãs:** [[SPEC_Parecer_IA_Visao_Multimodal]] (produz a `estrutura`) · [[SPEC_Parecer_Ferramenta]] (chama `html_para_docx_bytes` no `exportar`) · [[SPEC_Parecer_Editor_Frontend]] (edita o HTML)

## 0. Dependências (`backend/pyproject.toml`, editar)

```toml
"python-docx>=1.1.0",
"pillow>=10.0.0",   # fixar explícito (hoje PIL é usado só transitivamente em imagem_storage.py)
```

Ambas são puro-Python / sem libs nativas pesadas → ok no free-tier do Render. **Não** usar
weasyprint/reportlab (libs nativas + memória).

## 1. `estrutura_para_html(estrutura, imagens_por_indice) -> str`

Converte `ParecerEstruturado` para o **HTML de vocabulário controlado** que: (a) é carregado no
editor Tiptap como preview editável e (b) é a entrada do `html_para_docx_bytes`. As imagens entram
como `<img src="data:...">` (base64 original), pelo índice referenciado em `imagens_indices`.

### 1.1 Vocabulário HTML suportado (contrato editor ⇄ docx)

| Elemento | Uso no parecer | Vira no `.docx` |
|---|---|---|
| `<h1>` | Título do parecer | estilo **Title** |
| `<h2>` | "1. Página …", "N. Recomendações globais" | **Heading 1** |
| `<h3>` | Subproblema (ex.: "2.1 LCP atrasado…") | **Heading 2** |
| `<p>` | Parágrafos; rótulos **Problema/Evidência/Solução** em `<strong>` | **Normal** |
| `<table data-meta>` | Tabela de metadados (Cliente, Escopo, …) 2 colunas | tabela estilo "Tabela Parecer" |
| `<table data-causas>` | Causas-raiz (Problema \| Impacto \| Onde ocorre) 3 colunas | tabela estilo "Tabela Parecer" |
| `<ul>/<ol><li>` | Itens das recomendações | List Bullet / List Number |
| `<strong>`, `<em>` | Ênfase inline | bold / italic runs |
| `<img src="data:…">` | Evidência (print) | `add_picture` (convertido p/ PNG) |
| `<hr>` | Separador (rodapé) | parágrafo vazio / regra |

> O editor Tiptap é **configurado para permitir apenas** esses nós/marcas (ver
> [[SPEC_Parecer_Editor_Frontend]] §3), de modo que a edição livre não introduza HTML que o renderer
> não saiba converter.

### 1.2 Estrutura do HTML gerado (ordem)

Espelha o `[Imecap] Parecer Tecnico Performance (1).docx`: cabeçalho de 3 linhas → seções por
página (`N.`) → subseções (`N.M.`) com Problema/Evidência(s)/Solução → "Recomendações globais" por
último. **Sem tabela de metadados e sem sumário executivo.**

```html
<h1>PARECER TÉCNICO — SEO / PERFORMANCE</h1>
<p><em>{subtitulo}</em></p>            <!-- ex.: Otimização de Core Web Vitals -->
<p>{escopo_linha}</p>                  <!-- ex.: LCP e CLS — dominio.com.br (Cliente) -->

<!-- por seção (i começa em 1) -->
<h2>{i}. {secao.titulo}</h2>
<p>URL: {secao.url}</p>                <!-- se houver -->
<p><em>{secao.observacao}</em></p>     <!-- se houver -->
<!-- por subseção (j) -->
<h3>{i}.{j}. {subsecao.titulo}</h3>
<!-- por problema (k): rótulo "Problema" se 1 só, "Problema 1/2/…" se vários -->
<p><strong>Problema[ k]</strong> {problema.descricao}</p>
<!-- por evidência -->
<p><strong>Evidência:</strong> {evidencia.legenda}</p>
<img src="{imagens_por_indice[idx]}" />   <!-- para cada idx em evidencia.imagens_indices -->
<p><strong>Solução[ ({solucao_escopo})]</strong> {problema.solucao}</p>

<h2>{N}. Recomendações globais (aplicáveis a toda a loja)</h2>   <!-- N = nº seções + 1 -->
<!-- por prioridade -->
<p><strong>{prioridade.titulo}</strong></p>
<ul><li>{item}</li>…</ul>
```

Implementar com montagem de string segura (escapar texto com `html.escape`; **não** escapar os
`data:` das imagens). Numerar seções/subseções e os rótulos "Problema N" no servidor (determinístico).

> Tabelas (`<table>`) **não** aparecem no documento gerado, mas o renderer (`_render_table`) continua
> suportando-as para o caso de o usuário inserir uma tabela manualmente no editor.

## 2. `html_para_docx_bytes(html: str) -> bytes`

Recebe o HTML **final editado** (Tiptap) e produz o `.docx`. Usa `selectolax` para parsear e
`python-docx` para escrever sobre o **template de estilos**.

```python
import io, base64, re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from selectolax.parser import HTMLParser
from PIL import Image
from pathlib import Path

TEMPLATE = Path(__file__).parent / "templates" / "parecer_template.docx"
LARGURA_UTIL = Inches(6.3)  # largura de imagem dentro das margens

def html_para_docx_bytes(html: str) -> bytes:
    doc = Document(str(TEMPLATE)) if TEMPLATE.exists() else Document()
    _garantir_estilos(doc)              # cria estilos se o template não existir
    tree = HTMLParser(html)
    body = tree.body or tree.root
    for node in body.iter(include_text=False):
        _render_node(doc, node)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

### 2.1 Mapeamento de nós (`_render_node`)

- `h1` → `doc.add_paragraph(texto, style="Title")`
- `h2` → `Heading 1`; `h3` → `Heading 2`
- `p` → `Normal`; percorrer filhos para aplicar **bold** (`strong`/`b`) e *italic* (`em`/`i`) em runs
- `table[data-meta]` → tabela 2 colunas; 1ª coluna em **bold** (rótulo), estilo de tabela leve
- `table[data-causas]` → tabela 3 colunas; 1ª linha = cabeçalho em **bold**
- `ul`/`ol` → cada `li` vira parágrafo `List Bullet` / `List Number`
- `img[src^="data:"]` → ver §2.2
- `hr` → parágrafo separador

### 2.2 Imagens (Evidência)

```python
def _add_imagem(doc, data_uri: str):
    header, b64 = data_uri.split(",", 1)
    raw = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw))
    if getattr(img, "is_animated", False):     # GIF animado → 1º frame
        img.seek(0)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    png = io.BytesIO()
    img.save(png, "PNG")                         # python-docx NÃO embute WebP; normalizar p/ PNG
    png.seek(0)
    # largura: não ultrapassar a largura útil mantendo proporção
    largura = min(LARGURA_UTIL, Inches(img.width / 96))
    doc.add_picture(png, width=largura)
```

> **Por que normalizar p/ PNG:** `python-docx.add_picture` aceita PNG/JPEG/GIF/BMP/TIFF, **não WebP**.
> Como o editor pode ter imagens WebP (e GIFs animados), converter sempre via Pillow antes de embutir.

## 3. Template de estilos (`app/services/templates/parecer_template.docx`, novo)

Arquivo `.docx` "vazio" carregando os **estilos nomeados** usados pelo renderer (Title, Heading 1/2,
Normal, List Bullet/Number e um estilo de tabela). Duas formas de produzir (escolher uma):

- **(Recomendado)** Derivar do documento de referência: abrir `Parecer-Tecnico-Performance-Imecap.docx`,
  remover o conteúdo do corpo mantendo os estilos/seção/margens, salvar como `parecer_template.docx`.
  Garante fontes/cores/espaçamentos idênticos ao padrão.
- **Fallback em código** (`_garantir_estilos`): se o template não existir, criar/ajustar estilos
  programaticamente (fonte base, tamanhos de heading, cor de destaque da marca `#5C5249`). Mantém o
  renderer funcional sem o asset (útil em testes).

```python
def _garantir_estilos(doc):
    # Ajusta Normal e cria estilo de tabela se faltarem (idempotente).
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"; normal.font.size = Pt(11)
    # … Heading 1/2 cores/tamanhos; estilo "Tabela Parecer" com bordas leves …
```

## 4. Considerações

- **Determinismo:** a numeração de seções e a ordem das imagens são definidas no servidor (não
  dependem do LLM), garantindo consistência entre o preview (HTML) e o `.docx`.
- **Robustez:** nós desconhecidos (fora do vocabulário) são ignorados com log `warning` (a edição
  livre não deveria gerá-los, mas o renderer não quebra).
- **Tamanho:** imagens já chegam comprimidas do cliente; ainda assim, limitar a largura embutida
  evita `.docx` gigante.
- **Memória:** processar imagem a imagem (stream) — não acumular todos os bitmaps.

## 5. Critérios de aceite

- [ ] `estrutura_para_html` produz o HTML na ordem da §1.2, com `data-meta`/`data-causas` e imagens por índice
- [ ] `html_para_docx_bytes` gera `.docx` que **abre no Word** com: Title, headings, 2 tabelas, listas e imagens embutidas
- [ ] Imagem WebP e GIF animado embutem corretamente (convertidas p/ PNG)
- [ ] Funciona com e sem `parecer_template.docx` (fallback de estilos)
- [ ] HTML editado (texto alterado, parágrafo removido) ainda exporta sem erro

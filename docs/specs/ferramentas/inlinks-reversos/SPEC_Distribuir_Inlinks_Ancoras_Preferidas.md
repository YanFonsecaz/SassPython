# SPEC — Distribuir Inlinks: campo "Âncoras preferidas"

**Status:** ✅ implementado
**Escopo:** backend (schema + workflow + inseridor) + frontend (formulário + types)
**Crédito:** não muda
**Esforço estimado:** ~90 min
**Depende de:** nenhuma (encadeia naturalmente em cima do estado atual do Inseridor)

## 1. Resumo

Hoje no Distribuir Inlinks o Inseridor (gpt-4.1) escolhe a âncora olhando apenas para o contexto do parágrafo da candidata e a lista de `palavras_chave` que o Enriquecedor extraiu do alvo. Resultado: em pilares com tema bem definido, ele pega palavras curtas e genéricas ("cálcio", "deficiência") em vez dos bigramas estratégicos que o cliente quer rankear ("reposição de cálcio", "repor cálcio").

Esta SPEC adiciona um campo opcional **"Âncoras preferidas"** no formulário, lista de termos que o usuário quer ver como âncora dos links que serão inseridos nas candidatas. Lista vazia mantém comportamento atual; lista preenchida prioriza essas âncoras quando o Inseridor encontra parágrafo onde encaixam naturalmente.

## 2. Caso real

URL alvo: `https://calcitran.com.br/blog/repor-calcio-sinais`
Candidatas: artigos do mesmo blog que mencionam "reposição".
Resultado atual: âncoras escolhidas foram "cálcio", "deficiência", "deficiência de cálcio".
Resultado desejado: prioridade para "reposição de cálcio" / "repor cálcio" quando o trecho permitir.

Motivação SEO: âncora descritiva passa sinal de relevância muito mais forte que âncora genérica. "Cálcio" é ambíguo; "reposição de cálcio" diz ao Google exatamente o que a página de destino aborda.

## 3. Estado atual

Fluxo do Distribuir Inlinks (em ordem):

1. `routers/ferramentas_inlinks_reversos.py` recebe `DistribuirInlinksRequest` (`url_alvo`, `candidatas_urls`, `threshold_score`, `max_inlinks_por_candidata`, `rel_attr`) → persiste em `entrada_json`.
2. `workflow_inlinks_reversos.executar_workflow_distribuir_inlinks` hidrata `EstadoDistribuir` a partir de `entrada_json` e roda os nós.
3. `node_inserir_em_cada` monta `alvo_base` (url, titulo, resumo, palavras_chave, categoria do alvo) e chama `inserir_inlinks(conteudo_md_da_candidata, [alvo_base], usuario_id, max_inlinks=max_inlinks_por_candidata)` para cada candidata viável.
4. `inlinks/inseridor.inserir_inlinks` → `_propor_insercao_para_candidato` monta prompt e chama o LLM.
5. `_build_prompt_focado` injeta `URL DESTINO` + `Título` + `Palavras-chave do destino` (= `palavras_chave` do alvo) + parágrafos da candidata. LLM devolve `paragrafo_idx`, `trecho_original`, `anchor_text`, `palavra_chave_destino`.
6. `_validar_palavra_chave_destino` confere se `palavra_chave_destino` retornado está em `palavras_chave` do alvo. Se não, vira `sugestao_manual`.

Onde a âncora nasce: passo 5. O LLM otimiza naturalidade no parágrafo da candidata, não estratégia SEO do destino.

## 4. Comportamento novo

### 4.1 Princípios

- **Prioridade, não obrigação.** Se nenhuma âncora preferida encaixa, cai pro comportamento atual (escolhe da lista de `palavras_chave` do destino). Forçar âncora desconectada é pior que escolher âncora genérica.
- **Match flexível.** Aceitar variações morfológicas comuns PT-BR: singular↔plural, gênero, com/sem artigo, ordem invertida em bigramas. Já existe `_variacoes_morfologicas` em `workflow_inlinks_reversos.py:134` que pode ser reusado/movido.
- **Transparência.** O resultado por candidata indica se a âncora aplicada veio da lista de preferidas ou do fallback, pra o usuário entender o que aconteceu.

### 4.2 Algoritmo

1. Frontend coleta lista de strings em `ancoras_preferidas` (0–10 itens, 2–50 chars cada).
2. Backend propaga até `inserir_inlinks(..., ancoras_preferidas: list[str] | None = None)`.
3. `_selecionar_paragrafos_relevantes`: se `ancoras_preferidas` preenchido, somar boost adicional aos parágrafos que contêm qualquer âncora preferida (literal ou variação morfológica). Boost ≥ que o `_keyword_boost` atual para que parágrafos com âncora preferida subam no top-N.
4. `_build_prompt_focado`: se `ancoras_preferidas` preenchido, adicionar bloco no prompt:

   ```
   ÂNCORAS PREFERIDAS (use uma destas quando o parágrafo permitir naturalmente):
   - "reposição de cálcio"
   - "repor cálcio"

   REGRA: se algum parágrafo contém uma destas âncoras (literal ou flexionada), USE-A como `anchor_text`. Mantenha `trecho_original` copiado literalmente do parágrafo. Se NENHUM parágrafo contém variação de uma âncora preferida, escolha normalmente das palavras-chave do destino.
   ```

5. `_validar_palavra_chave_destino`: estender a lista de termos válidos com `ancoras_preferidas` quando preenchida. Hoje a validação só aceita palavra-chave que está em `palavras_chave` do destino — passa a aceitar também qualquer âncora preferida (ou variação dela).
6. Resultado por candidata ganha campo `ancora_preferida_usada: bool` indicando se a âncora final pertence ao conjunto preferido.

### 4.3 Sem âncoras preferidas

Quando `ancoras_preferidas` é `None` ou `[]`, NENHUM código novo é executado: prompt, seleção de parágrafos, validação e resultado ficam idênticos ao comportamento atual. Backward compat total.

## 5. Mudanças por arquivo

### 5.1 Backend

#### `backend/app/schemas/inlinks_reversos.py`

Adicionar campo + validador em `DistribuirInlinksRequest`:

```python
class DistribuirInlinksRequest(BaseModel):
    url_alvo: str = Field(..., max_length=2048)
    candidatas_urls: list[str] = Field(..., min_length=1, max_length=100)
    threshold_score: float = Field(default=0.6, ge=0.0, le=1.0)
    max_inlinks_por_candidata: int = Field(default=1, ge=1, le=3)
    rel_attr: str = Field(default="noopener")
    ancoras_preferidas: list[str] = Field(default_factory=list, max_length=10)

    # ... validadores existentes ...

    @field_validator("ancoras_preferidas")
    @classmethod
    def validar_ancoras(cls, v: list[str]) -> list[str]:
        normalizadas: list[str] = []
        vistos: set[str] = set()
        for raw in v:
            s = (raw or "").strip()
            if not s:
                continue
            if len(s) < 2 or len(s) > 50:
                raise ValueError("Cada ancora deve ter entre 2 e 50 caracteres")
            chave = s.lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            normalizadas.append(s)
        return normalizadas
```

#### `backend/app/agents/workflow_inlinks_reversos.py`

1. Adicionar `ancoras_preferidas: list[str]` em `EstadoDistribuir`.
2. Em `executar_workflow_distribuir_inlinks`, ler do `entrada_json`:

   ```python
   "ancoras_preferidas": entrada.get("ancoras_preferidas", []),
   ```

3. Em `node_inserir_em_cada`, ler do estado e passar para o `inserir_inlinks`:

   ```python
   ancoras_pref = estado.get("ancoras_preferidas", [])
   # ... no _inserir_candidata:
   markdown_modificado, inseridos = await inserir_inlinks(
       conteudo_md, [candidato_alvo], uid,
       max_inlinks=max_inlinks,
       ancoras_preferidas=ancoras_pref,
   )
   ```

4. Em `node_persistir`, persistir `ancora_preferida_usada` no `resultado_final.candidatas[*]` para o frontend exibir.

#### `backend/app/agents/inlinks/inseridor.py`

1. Mover (ou reusar) `_variacoes_morfologicas` para um helper compartilhado. Hoje vive em `workflow_inlinks_reversos.py:134`. Pode ficar em `app/core/text_utils.py` (criar) ou ser duplicado por enquanto.

2. Novo helper para detectar âncora preferida em texto:

   ```python
   def _ancora_preferida_match(texto: str, ancoras: list[str]) -> str | None:
       """Retorna a âncora preferida (forma original) que casa com o texto.
       Aceita match literal (insensível a acentos/caixa), ou todas as palavras
       da âncora presentes próximas (janela de ~10 palavras) para bigramas.
       """
       if not texto or not ancoras:
           return None
       texto_norm = _strip_accents(texto.lower())
       for ancora in ancoras:
           ancora_norm = _strip_accents(ancora.lower())
           if ancora_norm in texto_norm:
               return ancora
           palavras = ancora_norm.split()
           if len(palavras) > 1:
               # Todas as palavras presentes? Match aproximado.
               if all(p in texto_norm for p in palavras):
                   return ancora
       return None
   ```

3. `_keyword_boost` permanece; adicionar boost separado para âncora preferida em `_selecionar_paragrafos_relevantes`:

   ```python
   def _ancora_preferida_boost(paragrafo: str, ancoras: list[str]) -> float:
       if not ancoras or not paragrafo:
           return 0.0
       return 0.30 if _ancora_preferida_match(paragrafo, ancoras) else 0.0
   ```

   Boost 0.30 (vs 0.08–0.25 do `_keyword_boost`) garante que parágrafo com âncora preferida sobe no top-N mesmo com cosine semântico menor.

4. Estender assinatura:

   ```python
   async def inserir_inlinks(
       pilar_markdown: str,
       candidatos: list[dict[str, Any]],
       usuario_id: str,
       max_inlinks: int = 8,
       ancoras_preferidas: list[str] | None = None,
   ) -> tuple[str, list[InlinkInserido]]:
   ```

   Passar `ancoras_preferidas` por toda cadeia: `_selecionar_paragrafos_relevantes` (para boost), `_propor_insercao_para_candidato` (para prompt e validação).

5. `_build_prompt_focado` recebe `ancoras_preferidas` e, se não vazio, injeta o bloco descrito em 4.2 logo após `Palavras-chave do destino`.

6. `_validar_palavra_chave_destino` ganha parâmetro `ancoras_preferidas`. Antes da rejeição final, conferir se `palavra_chave_destino` (ou âncora retornada) casa com alguma âncora preferida; se sim, aceita.

7. Após `_aplicar_insercoes`, marcar em cada `InlinkInserido` aplicado o campo `ancora_preferida_usada` (bool): true quando `_ancora_preferida_match(anchor_text, ancoras_preferidas)` retorna não-nulo.

8. Adicionar campo no dataclass `InlinkInserido`:

   ```python
   ancora_preferida_usada: bool = False
   ```

#### `backend/app/services/ferramenta_service.py` (verificar)

Se houver função `salvar_versao` ou similar que serializa o resultado, garantir que `ancora_preferida_usada` chega no `resultado_json` da execução.

### 5.2 Frontend

#### `frontend/src/types/ferramenta.ts`

```typescript
export interface DistribuirInlinksRequest {
  url_alvo: string;
  candidatas_urls: string[];
  threshold_score?: number;
  max_inlinks_por_candidata?: number;
  rel_attr?: string;
  ancoras_preferidas?: string[];
}

export interface CandidataResultado {
  // ... campos existentes ...
  ancora_preferida_usada?: boolean | null;
}
```

#### `frontend/src/components/ferramentas/formulario-distribuir-inlinks.tsx`

Adicionar bloco no **Step 0** (junto com URL alvo, antes do botão "Próximo"):

```tsx
// estado
const [ancorasPreferidas, setAncorasPreferidas] = useState<string[]>([]);
const [novaAncora, setNovaAncora] = useState("");

function addAncora() {
  const a = novaAncora.trim();
  if (!a || a.length < 2 || a.length > 50) {
    setErro("Ancora deve ter entre 2 e 50 caracteres");
    return;
  }
  if (ancorasPreferidas.some((x) => x.toLowerCase() === a.toLowerCase())) {
    setErro("Ancora ja adicionada");
    return;
  }
  if (ancorasPreferidas.length >= 10) {
    setErro("Maximo 10 ancoras preferidas");
    return;
  }
  setAncorasPreferidas((prev) => [...prev, a]);
  setNovaAncora("");
  setErro("");
}

function removeAncora(idx: number) {
  setAncorasPreferidas((prev) => prev.filter((_, i) => i !== idx));
}
```

UI (chip input baseado em `Badge` + `Input`):

```tsx
<div className="space-y-2 pt-2">
  <div className="flex items-center gap-1.5">
    <Label htmlFor="ancora" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
      Ancoras preferidas (opcional)
    </Label>
    <span title="Termos que voce quer ver como ancora dos links. A ferramenta usa quando o paragrafo permite naturalmente; se nao couber, cai pro comportamento padrao. Maximo 10.">
      <InfoIcon className="size-3 text-muted-foreground/60" />
    </span>
  </div>
  <div className="flex gap-2">
    <Input
      id="ancora"
      placeholder="ex.: reposicao de calcio"
      maxLength={50}
      value={novaAncora}
      onChange={(e) => { setNovaAncora(e.target.value); setErro(""); }}
      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addAncora(); } }}
      disabled={enviando}
    />
    <Button
      type="button"
      variant="outline"
      onClick={addAncora}
      disabled={enviando || !novaAncora.trim()}
    >
      Adicionar
    </Button>
  </div>
  {ancorasPreferidas.length > 0 && (
    <div className="flex flex-wrap gap-1.5 pt-1">
      {ancorasPreferidas.map((a, i) => (
        <Badge
          key={`${a}-${i}`}
          className="bg-brand/10 text-brand-dark border border-brand/30 gap-1.5"
        >
          {a}
          <button
            type="button"
            onClick={() => removeAncora(i)}
            className="hover:text-destructive"
            disabled={enviando}
            aria-label={`Remover ${a}`}
          >
            ×
          </button>
        </Badge>
      ))}
    </div>
  )}
  <p className="text-xs text-muted-foreground">
    Se nenhuma ancora preferida couber naturalmente no texto, a ferramenta escolhe sozinha.
  </p>
</div>
```

Inclusão no payload do `handleSubmit`:

```tsx
const body: DistribuirInlinksRequest = {
  url_alvo: urlAlvo.trim(),
  candidatas_urls: candidatasUrls,
  max_inlinks_por_candidata: maxInlinksPorCandidata,
  threshold_score: thresholdScore,
  rel_attr: relAttr,
  ancoras_preferidas: ancorasPreferidas,
};
```

Incluir no **Step 2 (Resumo)**:

```tsx
["Ancoras preferidas", ancorasPreferidas.length
  ? ancorasPreferidas.join(", ")
  : "—"],
```

#### `frontend/src/components/ferramentas/distribuir-inlinks-resultado.tsx`

Em `CandidataAccordion`, quando `candidata.ancora_preferida_usada === true`, exibir badge ao lado da âncora:

```tsx
{candidata.ancora_preferida_usada && (
  <Badge className="bg-success/10 text-success border-success/30">
    Ancora preferida
  </Badge>
)}
```

## 6. Edge cases

- **Lista vazia / `null`**: comportamento idêntico ao atual. Nenhum boost, nenhum bloco no prompt, nenhum campo no resultado.
- **Âncora não cabe em parágrafo nenhum**: Inseridor cai pro comportamento padrão. Resultado fica `ancora_preferida_usada: false`. Não vira `sugestao_manual` por causa disso.
- **Múltiplas âncoras preferidas + `max_inlinks_por_candidata = 1`**: Inseridor escolhe a melhor que cabe (decisão do LLM, com regra explícita no prompt).
- **Âncora preferida em variação flexionada**: `_ancora_preferida_match` aceita. Ex.: usuário escreveu "reposição de cálcio", parágrafo tem "repor cálcio" → match (todas as palavras do bigrama presentes).
- **Âncora preferida igual a uma genérica do destino**: sem conflito. Validação aceita por estar em `ancoras_preferidas` E em `palavras_chave`.
- **Candidata filtrada por `threshold_score` antes do Inseridor**: âncora preferida não muda o filtro de similaridade alvo×candidata. Se a candidata não passa, não chega ao Inseridor. Usuário precisa baixar threshold OU escolher candidatas mais alinhadas. Documentar no tooltip do campo se aparecerem dúvidas.
- **Âncora muito genérica passada pelo usuário ("texto", "link")**: validador do schema rejeita por tamanho mínimo (2 chars passa), mas `_validar_palavra_chave_destino` continua rejeitando se for um termo das `_STOPWORDS_GENERICAS`. Mantém o piso de qualidade.

## 7. Verificação E2E

1. **Restart backend + worker**:
   ```bash
   pkill -f "uvicorn app.main" || true
   pkill -f "arq app.worker" || true
   cd backend && nohup python3 -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
   cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
   sleep 3
   curl -sf -o /dev/null -w "Backend: %{http_code}\n" http://localhost:8000/health
   ```

2. **Frontend rebuild**:
   ```bash
   cd frontend && npm run build
   ```

3. **Caso real (cliente Calcitran)**:
   - Alvo: `https://calcitran.com.br/blog/repor-calcio-sinais`
   - Candidatas: 3–5 artigos do mesmo blog que mencionem "reposição" / "repor"
   - Âncoras preferidas: `["reposição de cálcio", "repor cálcio"]`
   - Threshold: 0.6
   - Esperado: pelo menos 1 candidata com `anchor_text` = "reposição de cálcio" ou "repor cálcio" (ou variação flexionada do parágrafo) e badge "Âncora preferida".

4. **Regressão sem âncoras preferidas**:
   - Mesmo alvo + candidatas, lista de âncoras VAZIA.
   - Esperado: comportamento idêntico ao da execução anterior já validada — nenhuma diferença em scores/decisões.

5. **Sanidade de logs**:
   ```bash
   grep -E "ancoras_preferidas|ancora_preferida_match|ancora_preferida_usada" /tmp/worker.log | tail -20
   ```
   Deve mostrar quantas âncoras foram passadas, quais paragrafos casaram, qual foi escolhida.

6. **Backward compat de execuções antigas**: abrir uma execução de Distribuir Inlinks anterior à mudança no histórico — `ancora_preferida_usada` deve aparecer como `false`/`null` sem quebrar a renderização.

## 8. Fora de escopo

- **Auto-derivação de âncoras a partir do slug/título do alvo**. Pode ser v2 (pré-preencher o campo com sugestões `["repor cálcio", "reposição cálcio"]` extraídas de `repor-calcio-sinais`). Mantém controle manual primeiro.
- **Aplicar a mesma ideia no Inlinks (Pilar)**. A ferramenta de Inlinks recebe pilar único + várias candidatas (inverso do Distribuir). O caso de uso é diferente: lá o usuário não controla âncora por candidata. Avaliar separadamente.
- **Permitir âncora preferida POR candidata** (mapa URL → âncoras). Complica UI desnecessariamente; uma lista global cobre o caso da Calcitran.
- **Suporte multi-idioma de variações morfológicas**. Variações ficam em PT-BR.

## 9. Riscos

- **Inseridor (LLM) ignora a regra do prompt**: gpt-4.1 pode ainda escolher palavra mais "natural" no parágrafo. Mitigação: boost de 0.30 em `_selecionar_paragrafos_relevantes` aumenta chance do top-N conter parágrafo onde a âncora preferida cabe; few-shot no prompt reforça a preferência. Se reincidir, endurecer regra ("OBRIGATÓRIO usar a âncora preferida X quando presente").
- **`_ancora_preferida_match` falsamente positivo em bigramas (todas as palavras presentes em qualquer ordem/distância)**: parágrafo com "cálcio é importante para a saúde óssea, faça reposição" casa com "reposição de cálcio". Aceitável para boost de seleção; o Inseridor depois decide o trecho exato. Se virar problema, refinar para "todas as palavras presentes dentro de janela de N tokens".
- **Usuário lista âncoras que nenhuma candidata contém**: usuário pode ficar frustrado por não ver a âncora preferida no resultado. Mitigação: badge no resultado + tooltip explicando "cai pro padrão quando não cabe". Logs informam exatamente quais matches foram tentados.
- **Conflito com `_validar_palavra_chave_destino`**: precisa garantir que âncora preferida não-listada em `palavras_chave` do destino seja aceita. Testar com âncora que sabidamente não está nos `palavras_chave` do alvo Calcitran (ex.: usuário pede "repor calcio agora").

## 10. Decisões deixadas explícitas

- Lista é **global por execução**, não por candidata.
- Limite de **10 âncoras**, 2–50 chars cada.
- Boost de **0.30** na seleção de parágrafos (acima do `_keyword_boost` máximo de 0.25 atual).
- Match aceita **variação morfológica simples** + **bigrama com palavras em qualquer ordem dentro do parágrafo**.
- Sem âncora preferida que caiba **não bloqueia** — fallback para comportamento atual.
- **Backward compat** garantido por `ancoras_preferidas: list[str] = Field(default_factory=list)` no schema.

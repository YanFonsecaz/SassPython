"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, mensagemErroAmigavel } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CheckIcon, LinkIcon, FileTextIcon, SparklesIcon, Trash2Icon, ClipboardPasteIcon, InfoIcon } from "lucide-react";
import type { InlinksRequest, ExecucaoCriada, CustoInlinksResponse } from "@/types";

const STEPS = [
  { label: "Pilar", icon: FileTextIcon },
  { label: "URLs", icon: LinkIcon },
  { label: "Confirmar", icon: SparklesIcon },
] as const;

export function FormularioInlinks() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [saldo, setSaldo] = useState<number | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  const [pilarUrl, setPilarUrl] = useState("");
  const [pilarMarkdown, setPilarMarkdown] = useState("");
  const [candidatasUrls, setCandidatasUrls] = useState<string[]>([]);
  const [novaUrl, setNovaUrl] = useState("");
  const [urlsEmLote, setUrlsEmLote] = useState("");
  const [modoLote, setModoLote] = useState(false);
  const [maxInlinks, setMaxInlinks] = useState(8);
  const [thresholdScore, setThresholdScore] = useState(0.6);
  const [relAttr, setRelAttr] = useState("noopener");
  const [custoEstimado, setCustoEstimado] = useState<CustoInlinksResponse | null>(null);

  useEffect(() => {
    async function loadSaldo() {
      try {
        const dados = await api.get<{ saldo_total: number }>("/creditos/saldo");
        setSaldo(dados.saldo_total);
      } catch {
        // silent
      }
    }
    loadSaldo();
  }, []);

  useEffect(() => {
    async function loadCusto() {
      try {
        const dados = await api.get<CustoInlinksResponse>(
          `/ferramentas/inlinks-automaticos/custo?n_urls=${candidatasUrls.length}`
        );
        setCustoEstimado(dados);
      } catch {
        // silent
      }
    }
    loadCusto();
  }, [candidatasUrls.length]);

  const canAdvance = useCallback(() => {
    switch (step) {
      case 0: return !!(pilarUrl.trim() || pilarMarkdown.trim());
      case 1: return candidatasUrls.length >= 1;
      case 2: return true;
      default: return false;
    }
  }, [step, pilarUrl, pilarMarkdown, candidatasUrls]);

  function parseUrl(text: string): string | null {
    const trimmed = text.trim();
    if (!trimmed) return null;
    if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) return null;
    return trimmed;
  }

  function addUrl() {
    const url = novaUrl.trim();
    if (!url) return;
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      setErro("URL deve começar com http:// ou https://");
      return;
    }
    if (candidatasUrls.includes(url)) {
      setErro("URL já adicionada");
      return;
    }
    setCandidatasUrls((prev) => [...prev, url]);
    setNovaUrl("");
    setErro("");
  }

  function addUrlsEmLote() {
    const linhas = urlsEmLote.split(/[\n,]/).map((l) => parseUrl(l)).filter((u): u is string => u !== null);
    if (linhas.length === 0) {
      setErro("Nenhuma URL válida encontrada. Cada URL deve começar com http:// ou https://");
      return;
    }
    const novas = linhas.filter((u) => !candidatasUrls.includes(u));
    const duplicadas = linhas.length - novas.length;
    setCandidatasUrls((prev) => [...prev, ...novas]);
    setUrlsEmLote("");
    if (duplicadas > 0) {
      setErro(`${novas.length} adicionada${novas.length !== 1 ? "s" : ""}, ${duplicadas} duplicada${duplicadas !== 1 ? "s" : ""} ignorada${duplicadas !== 1 ? "s" : ""}`);
    } else {
      setErro("");
    }
    if (novas.length + candidatasUrls.length > 100) {
      setErro("Máximo de 100 URLs por execução");
    }
  }

  function removeUrl(index: number) {
    setCandidatasUrls((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit() {
    setErro("");
    setEnviando(true);

    try {
      const body: InlinksRequest = {
        pilar_url: pilarUrl.trim() || undefined,
        pilar_markdown: pilarMarkdown.trim() || undefined,
        candidatas_urls: candidatasUrls,
        max_inlinks: maxInlinks,
        threshold_score: thresholdScore,
        rel_attr: relAttr,
      };

      const resultado = await api.post<ExecucaoCriada>(
        "/ferramentas/inlinks-automaticos",
        body
      );

      router.push(`/ferramentas/historico/${resultado.id}`);
    } catch (err) {
      setErro(mensagemErroAmigavel(err));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="max-w-2xl animate-slide-up">
      <div className="flex items-center gap-0 mb-8">
        {STEPS.map((s, i) => {
          const StepIcon = s.icon;
          const isCompleted = i < step;
          const isCurrent = i === step;
          return (
            <div key={s.label} className="flex items-center flex-1 last:flex-none">
              <button
                type="button"
                onClick={() => i < step && setStep(i)}
                className="flex flex-col items-center gap-1.5 group"
                disabled={i > step}
              >
                <div
                  className={cn(
                    "flex items-center justify-center size-9 rounded-full border-2 transition-all duration-200",
                    isCompleted && "bg-brand border-brand text-white",
                    isCurrent && "border-brand text-brand",
                    !isCompleted && !isCurrent && "border-border text-muted-foreground"
                  )}
                >
                  {isCompleted ? <CheckIcon className="size-4" /> : <StepIcon className="size-4" />}
                </div>
                <span
                  className={cn(
                    "text-xs font-medium transition-colors",
                    isCurrent && "text-brand-dark",
                    isCompleted && "text-foreground",
                    !isCompleted && !isCurrent && "text-muted-foreground"
                  )}
                >
                  {s.label}
                </span>
              </button>
              {i < STEPS.length - 1 && (
                <div className={cn("flex-1 h-0.5 mx-2 mb-5 transition-colors", i < step ? "bg-brand" : "bg-border")} />
              )}
            </div>
          );
        })}
      </div>

      <div className="glass-card rounded-2xl p-6 sm:p-8">
        {erro && (
          <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2 mb-6">
            <p className="text-sm text-destructive" role="alert">{erro}</p>
          </div>
        )}

        {step === 0 && (
          <div className="space-y-5 animate-fade-in">
            <p className="text-sm font-medium text-muted-foreground">
              Forneça o conteúdo pilar — pode ser uma URL ou texto markdown
            </p>
            <div className="space-y-2">
              <Label htmlFor="pilar-url" className="text-sm font-medium text-muted-foreground">
                URL do artigo pilar
              </Label>
              <Input
                id="pilar-url"
                placeholder="https://seublog.com/artigo-pilar"
                maxLength={2048}
                value={pilarUrl}
                onChange={(e) => setPilarUrl(e.target.value)}
                disabled={enviando}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="pilar-md" className="text-sm font-medium text-muted-foreground">
                Ou cole o markdown do artigo
              </Label>
              <Textarea
                id="pilar-md"
                placeholder="Cole aqui o conteúdo markdown do artigo pilar..."
                maxLength={100000}
                value={pilarMarkdown}
                onChange={(e) => setPilarMarkdown(e.target.value)}
                disabled={enviando}
                rows={8}
              />
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5 animate-fade-in">
            <p className="text-sm font-medium text-muted-foreground">
              Adicione as URLs candidatas para receber inlinks do artigo pilar
            </p>

            <div className="flex gap-2">
              <Button
                type="button"
                variant={modoLote ? "outline" : "default"}
                size="sm"
                onClick={() => setModoLote(false)}
                className="text-xs"
              >
                <LinkIcon className="size-3 mr-1" /> Uma por uma
              </Button>
              <Button
                type="button"
                variant={modoLote ? "default" : "outline"}
                size="sm"
                onClick={() => setModoLote(true)}
                className="text-xs"
              >
                <ClipboardPasteIcon className="size-3 mr-1" /> Colar em lote
              </Button>
            </div>

            {!modoLote ? (
              <div className="space-y-2">
                <Label htmlFor="nova-url" className="text-sm font-medium text-muted-foreground">
                  URL candidata
                </Label>
                <div className="flex gap-2">
                  <Input
                    id="nova-url"
                    placeholder="https://seublog.com/outro-artigo"
                    maxLength={2048}
                    value={novaUrl}
                    onChange={(e) => { setNovaUrl(e.target.value); setErro(""); }}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addUrl(); } }}
                    disabled={enviando}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={addUrl}
                    disabled={enviando || !novaUrl.trim()}
                  >
                    Adicionar
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="urls-lote" className="text-sm font-medium text-muted-foreground">
                  URLs candidatas (uma por linha)
                </Label>
                <Textarea
                  id="urls-lote"
                  placeholder={`https://seublog.com/artigo-1\nhttps://seublog.com/artigo-2\nhttps://seublog.com/artigo-3`}
                  maxLength={50000}
                  value={urlsEmLote}
                  onChange={(e) => { setUrlsEmLote(e.target.value); setErro(""); }}
                  disabled={enviando}
                  rows={6}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={addUrlsEmLote}
                  disabled={enviando || !urlsEmLote.trim()}
                  className="text-xs"
                >
                  <ClipboardPasteIcon className="size-3 mr-1" />
                  Adicionar todas
                </Button>
                <p className="text-xs text-muted-foreground">
                  Cole uma URL por linha ou separadas por vírgula. Máximo de 100 URLs por execução.
                </p>
              </div>
            )}

            {candidatasUrls.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">
                  {candidatasUrls.length} URL{candidatasUrls.length !== 1 ? "s" : ""} adicionada{candidatasUrls.length !== 1 ? "s" : ""}
                </p>
                <div className="space-y-1.5 max-h-60 overflow-y-auto">
                  {candidatasUrls.map((url, i) => (
                    <div key={i} className="flex items-center gap-2 rounded-lg border bg-surface-light px-3 py-2">
                      <LinkIcon className="size-3.5 text-muted-foreground shrink-0" />
                      <span className="text-sm truncate flex-1 min-w-0">{url}</span>
                      <button
                        type="button"
                        onClick={() => removeUrl(i)}
                        className="text-muted-foreground hover:text-destructive transition-colors shrink-0"
                        disabled={enviando}
                      >
                        <Trash2Icon className="size-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-3 pt-2">
              <div className="space-y-2">
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="max-inlinks" className="text-sm font-medium text-muted-foreground">
                    Teto de inlinks
                  </Label>
                  <span title="Calculamos automaticamente 4-5 inlinks por mil palavras. Este valor é apenas um limite superior para evitar excesso.">
                    <InfoIcon className="size-3 text-muted-foreground/60" />
                  </span>
                </div>
                <Input
                  id="max-inlinks"
                  type="number"
                  min={1}
                  max={20}
                  value={maxInlinks}
                  onChange={(e) => setMaxInlinks(Number(e.target.value))}
                  disabled={enviando}
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="threshold" className="text-sm font-medium text-muted-foreground">
                    Score mínimo
                  </Label>
                  <span title="Quanto mais alto, mais rigoroso. Valores entre 0.5 e 0.7 funcionam para a maioria. Abaixo de 0.4 = links pouco relacionados.">
                    <InfoIcon className="size-3 text-muted-foreground/60" />
                  </span>
                </div>
                <Input
                  id="threshold"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={thresholdScore}
                  onChange={(e) => setThresholdScore(Number(e.target.value))}
                  disabled={enviando}
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="rel-attr" className="text-sm font-medium text-muted-foreground">
                    Rel attribute
                  </Label>
                  <span title="Atributo HTML do link. noopener = recomendado para SEO; nofollow = diz ao Google para não seguir o link.">
                    <InfoIcon className="size-3 text-muted-foreground/60" />
                  </span>
                </div>
                <select
                  id="rel-attr"
                  className="flex h-10 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm transition-colors focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  value={relAttr}
                  onChange={(e) => setRelAttr(e.target.value)}
                  disabled={enviando}
                >
                  <option value="noopener">noopener</option>
                  <option value="nofollow">nofollow</option>
                  <option value="sponsored">sponsored</option>
                  <option value="ugc">ugc</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5 animate-fade-in">
            <div className="rounded-xl border bg-surface-light p-5 space-y-3">
              <h4 className="text-sm font-semibold text-muted-foreground">Resumo</h4>
              <div className="grid gap-3 text-sm">
                {[
                  ["Pilar URL", pilarUrl || "Texto markdown fornecido"],
                  ["URLs candidatas", `${candidatasUrls.length} URLs`],
                  ["Teto de inlinks", String(maxInlinks)],
                  ["Score mínimo", String(thresholdScore)],
                  ["Rel", relAttr],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4">
                    <span className="text-muted-foreground shrink-0">{label}</span>
                    <span className="text-right truncate font-medium">{value || "—"}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-brand/20 bg-brand/5 p-5 space-y-3">
              <h4 className="text-sm font-semibold text-muted-foreground">Custo estimado</h4>
              <div className="text-sm space-y-1.5 text-muted-foreground">
                <p className="font-semibold text-foreground">
                  {custoEstimado ? `${custoEstimado.custo_estimado} créditos` : "... créditos"}
                </p>
                <p className="pl-3">Base: 15 créditos (fixo)</p>
                <p className="pl-3">Por URL: 1 crédito cada</p>
                <p className="pl-3">Máximo: 60 créditos</p>
              </div>
              <div className="pt-2 border-t border-brand/20">
                <p className="text-sm">
                  Seu saldo atual:{" "}
                  <span className={cn("font-bold", saldo !== null && saldo < 20 ? "text-destructive" : "text-brand-dark")}>
                    {saldo ?? "..."}
                  </span>{" "}
                  créditos
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between mt-8 pt-6 border-t border-border">
          <div>
            {step > 0 && (
              <Button type="button" variant="ghost" onClick={() => setStep((s) => s - 1)} disabled={enviando}>
                Voltar
              </Button>
            )}
          </div>
          <div>
            {step < STEPS.length - 1 ? (
              <Button
                type="button"
                className="gradient-bg border-0 hover:opacity-90 transition-opacity"
                onClick={() => setStep((s) => s + 1)}
                disabled={!canAdvance() || enviando}
              >
                Próximo
              </Button>
            ) : (
              <Button
                type="button"
                className="gradient-bg border-0 hover:opacity-90 transition-opacity"
                onClick={handleSubmit}
                disabled={enviando || (saldo !== null && saldo < 15)}
              >
                {enviando ? "Processando..." : "Gerar Inlinks"}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

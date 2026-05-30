"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { useClientes } from "@/hooks/use-clientes";
import { useCreditos } from "@/hooks/use-creditos";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ArrowLeftIcon,
  CheckIcon,
  GaugeIcon,
  LinkIcon,
  PlusIcon,
  SparklesIcon,
  Trash2Icon,
  ClipboardPasteIcon,
  GlobeIcon,
  SmartphoneIcon,
  MonitorIcon,
} from "lucide-react";
import type { TemplateTipo } from "@/lib/api/cwv";
import { analisarCwv, buscarCustoCwv } from "@/lib/api/cwv";
import Link from "next/link";
import { TermoComAjuda } from "@/components/ui/termo-com-ajuda";

const STEPS = [
  { label: "Cliente", icon: GlobeIcon },
  { label: "URLs", icon: LinkIcon },
  { label: "Confirmar", icon: SparklesIcon },
] as const;

const TEMPLATES: { key: TemplateTipo; label: string; placeholder: string; icon: React.ElementType }[] = [
  { key: "home", label: "Home", placeholder: "https://loja.com.br/", icon: GlobeIcon },
  { key: "categoria", label: "Categoria", placeholder: "https://loja.com.br/categoria/tenis", icon: GlobeIcon },
  { key: "produto", label: "Produto", placeholder: "https://loja.com.br/produto/tenis-x", icon: GlobeIcon },
  { key: "blog", label: "Blog (listagem)", placeholder: "https://loja.com.br/blog", icon: GlobeIcon },
  { key: "blogpost", label: "Blog Post", placeholder: "https://loja.com.br/blog/como-escolher-tenis", icon: GlobeIcon },
  { key: "outros", label: "Outros", placeholder: "https://loja.com.br/outra-pagina", icon: GlobeIcon },
];

export function CwvFormPage() {
  const router = useRouter();
  const { clientes, carregando: carregandoClientes } = useClientes();
  const { saldo } = useCreditos();

  const [step, setStep] = useState(0);
  const [clienteId, setClienteId] = useState("");
  const [estrategia, setEstrategia] = useState<"mobile" | "desktop">("mobile");
  const [urls, setUrls] = useState<Record<TemplateTipo, string[]>>({
    home: [], categoria: [], produto: [], blog: [], blogpost: [], outros: [],
  });
  const [novaUrl, setNovaUrl] = useState("");
  const [urlsEmLote, setUrlsEmLote] = useState("");
  const [modoLote, setModoLote] = useState(false);
  const [templateAtivo, setTemplateAtivo] = useState<TemplateTipo>("home");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [custo, setCusto] = useState<number | null>(null);

  const totalUrls = useMemo(() => Object.values(urls).flat().length, [urls]);

  useEffect(() => {
    async function loadCusto() {
      if (totalUrls === 0) { setCusto(null); return; }
      try {
        const r = await buscarCustoCwv(totalUrls);
        setCusto(r.custo);
      } catch { /* silent */ }
    }
    loadCusto();
  }, [totalUrls]);

  function addUrl() {
    const u = novaUrl.trim();
    if (!u.startsWith("http://") && !u.startsWith("https://")) {
      setErro("URL deve começar com http:// ou https://");
      return;
    }
    if (urls[templateAtivo].includes(u)) {
      setErro("URL já adicionada neste template");
      return;
    }
    if (totalUrls >= 50) {
      setErro("Máximo de 50 URLs por execução");
      return;
    }
    setUrls((prev) => ({ ...prev, [templateAtivo]: [...prev[templateAtivo], u] }));
    setNovaUrl("");
    setErro("");
  }

  function addUrlsEmLote() {
    const linhas = urlsEmLote.split(/[\n,]/).map((l) => l.trim()).filter((l) => l.startsWith("http://") || l.startsWith("https://"));
    if (linhas.length === 0) { setErro("Nenhuma URL válida encontrada"); return; }
    const novas = linhas.filter((u) => !urls[templateAtivo].includes(u));
    const totalNovo = totalUrls + novas.length;
    if (totalNovo > 50) { setErro("Máximo de 50 URLs por execução"); return; }
    setUrls((prev) => ({ ...prev, [templateAtivo]: [...prev[templateAtivo], ...novas] }));
    setUrlsEmLote("");
    setErro("");
  }

  function removeUrl(template: TemplateTipo, index: number) {
    setUrls((prev) => ({ ...prev, [template]: prev[template].filter((_, i) => i !== index) }));
  }

  const canAdvance = useCallback(() => {
    if (step === 0) return !!clienteId;
    if (step === 1) return totalUrls >= 1;
    return true;
  }, [step, clienteId, totalUrls]);

  async function handleSubmit() {
    setErro("");
    setEnviando(true);
    try {
      const resultado = await analisarCwv({
        cliente_id: clienteId,
        urls_por_template: urls,
        estrategia,
      });
      router.push(`/ferramentas/core-web-vitals/execucao/${resultado.id}`);
    } catch (err) {
      const e = err as { status?: number; detalhe?: string };
      if (e.status === 402) {
        setErro(`Saldo insuficiente. Necessário ${custo ?? "—"} créditos. Compre créditos em /créditos.`);
      } else if (e.status === 429) {
        setErro("Aguarde alguns minutos. Limite: 3 análises a cada 5 minutos.");
      } else if (e.status === 404) {
        setErro("Cliente selecionado é inválido. Recarregue a página.");
      } else {
        setErro(e.detalhe || "Erro ao criar análise. Tente novamente.");
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Core Web Vitals"
        description="Análise métricas de performance e receba um plano de ação por URL"
        action={
          <Link href="/ferramentas" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" /> Voltar
          </Link>
        }
      />

      <div className="max-w-2xl animate-slide-up">
        <div className="flex items-center gap-0 mb-8">
          {STEPS.map((s, i) => {
            const StepIcon = s.icon;
            const isCompleted = i < step;
            const isCurrent = i === step;
            return (
              <div key={s.label} className="flex items-center flex-1 last:flex-none">
                <button type="button" onClick={() => i < step && setStep(i)} className="flex flex-col items-center gap-1.5 group" disabled={i > step}>
                  <div className={cn("flex items-center justify-center size-9 rounded-full border-2 transition-all duration-200",
                    isCompleted && "bg-brand border-brand text-white",
                    isCurrent && "border-brand text-brand",
                    !isCompleted && !isCurrent && "border-border text-muted-foreground"
                  )}>
                    {isCompleted ? <CheckIcon className="size-4" /> : <StepIcon className="size-4" />}
                  </div>
                  <span className={cn("text-xs font-medium transition-colors",
                    isCurrent && "text-brand-dark", isCompleted && "text-foreground",
                    !isCompleted && !isCurrent && "text-muted-foreground"
                  )}>{s.label}</span>
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
                Selecione o cliente para a análise
              </p>
              {carregandoClientes ? (
                <div className="h-10 rounded-lg bg-muted/50 animate-pulse" />
              ) : clientes.length === 0 ? (
                <div className="rounded-lg border bg-surface-light p-4 text-center">
                  <p className="text-sm text-muted-foreground">Nenhum cliente cadastrado.</p>
                  <Link href="/clientes" className="text-sm text-brand-dark font-medium hover:underline mt-1 inline-block">
                    Cadastrar cliente
                  </Link>
                </div>
              ) : (
                <div className="grid gap-2 max-h-60 overflow-y-auto">
                  {clientes.map((c) => (
                    <button key={c.id} type="button" onClick={() => setClienteId(c.id)}
                      className={cn("flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                        clienteId === c.id ? "border-brand bg-brand/5" : "hover:bg-surface-light"
                      )}>
                      <div className={cn("size-2 rounded-full shrink-0",
                        clienteId === c.id ? "bg-brand" : "bg-muted-foreground/30"
                      )} />
                      <span className="text-sm font-medium truncate">{c.nome}</span>
                      {c.site_url && <span className="text-xs text-muted-foreground truncate ml-auto">{c.site_url}</span>}
                    </button>
                  ))}
                </div>
              )}

              {clienteId && (
                <Link
                  href={`/ferramentas/core-web-vitals/historico/${clienteId}`}
                  className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-brand/40 px-3 py-2.5 text-sm font-medium text-brand-dark hover:bg-brand/5 transition-colors"
                >
                  <GaugeIcon className="size-4" />
                  Ver análises anteriores deste cliente
                </Link>
              )}
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5 animate-fade-in">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">
                  Adicione URLs agrupadas por <TermoComAjuda termo="template" />
                </p>
                <div className="flex gap-1">
                  <span className="text-xs text-muted-foreground mr-1 self-center">
                    <TermoComAjuda termo="estratégia" texto="Dispositivo de teste: Mobile testa como o site funciona em celulares; Desktop testa em computadores." />
                  </span>
                  <button type="button" onClick={() => setEstrategia("mobile")}
                    className={cn("flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                      estrategia === "mobile" ? "border-brand bg-brand/5 text-brand-dark" : "text-muted-foreground hover:bg-surface-light"
                    )}>
                    <SmartphoneIcon className="size-3.5" /> Mobile
                  </button>
                  <button type="button" onClick={() => setEstrategia("desktop")}
                    className={cn("flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                      estrategia === "desktop" ? "border-brand bg-brand/5 text-brand-dark" : "text-muted-foreground hover:bg-surface-light"
                    )}>
                    <MonitorIcon className="size-3.5" /> Desktop
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {TEMPLATES.map((t) => {
                  const count = urls[t.key].length;
                  return (
                    <button key={t.key} type="button" onClick={() => setTemplateAtivo(t.key)}
                      className={cn("flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors",
                        templateAtivo === t.key ? "border-brand bg-brand/5 text-brand-dark" : "text-muted-foreground hover:bg-surface-light"
                      )}>
                      {t.label}
                      {count > 0 && <span className="bg-brand/10 text-brand-dark rounded-full px-1.5 text-[10px] font-bold">{count}</span>}
                    </button>
                  );
                })}
              </div>

              {TEMPLATES.filter((t) => t.key === templateAtivo).map((t) => (
                <div key={t.key} className="space-y-3">
                  <Label className="text-sm font-medium text-muted-foreground">
                    URLs — {t.label}
                  </Label>
                  <div className="flex gap-2">
                    <Button type="button" variant={modoLote ? "outline" : "default"} size="sm" onClick={() => setModoLote(false)} className="text-xs">
                      <PlusIcon className="size-3 mr-1" /> Uma por uma
                    </Button>
                    <Button type="button" variant={modoLote ? "default" : "outline"} size="sm" onClick={() => setModoLote(true)} className="text-xs">
                      <ClipboardPasteIcon className="size-3 mr-1" /> Colar em lote
                    </Button>
                  </div>

                  {!modoLote ? (
                    <div className="flex gap-2">
                      <Input placeholder={t.placeholder} value={novaUrl}
                        onChange={(e) => { setNovaUrl(e.target.value); setErro(""); }}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addUrl(); } }}
                        disabled={enviando} maxLength={2048}
                      />
                      <Button type="button" variant="outline" onClick={addUrl} disabled={enviando || !novaUrl.trim()}>Adicionar</Button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <textarea placeholder={"Uma URL por linha\n" + t.placeholder} value={urlsEmLote}
                        onChange={(e) => { setUrlsEmLote(e.target.value); setErro(""); }}
                        disabled={enviando} rows={4}
                        className="flex w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand resize-none"
                      />
                      <Button type="button" variant="outline" size="sm" onClick={addUrlsEmLote} disabled={enviando || !urlsEmLote.trim()} className="text-xs">
                        <ClipboardPasteIcon className="size-3 mr-1" /> Adicionar todas
                      </Button>
                    </div>
                  )}

                  {urls[t.key].length > 0 && (
                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                      {urls[t.key].map((url, i) => (
                        <div key={i} className="flex items-center gap-2 rounded-lg border bg-surface-light px-3 py-2">
                          <LinkIcon className="size-3.5 text-muted-foreground shrink-0" />
                          <span className="text-sm truncate flex-1 min-w-0">{url}</span>
                          <button type="button" onClick={() => removeUrl(t.key, i)}
                            aria-label="Remover URL"
                            className="text-muted-foreground hover:text-destructive transition-colors shrink-0" disabled={enviando}>
                            <Trash2Icon className="size-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              <div className="pt-2 border-t border-border">
                <p className="text-sm font-medium">{totalUrls} URL{totalUrls !== 1 ? "s" : ""} no total</p>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5 animate-fade-in">
              <div className="rounded-xl border bg-surface-light p-5 space-y-3">
                <h4 className="text-sm font-semibold text-muted-foreground">Resumo</h4>
                <div className="grid gap-3 text-sm">
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground shrink-0">Cliente</span>
                    <span className="text-right truncate font-medium">{clientes.find((c) => c.id === clienteId)?.nome ?? "—"}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground shrink-0"><TermoComAjuda termo="Estratégia" texto="Dispositivo usado na análise: Mobile ou Desktop." /></span>
                    <span className="text-right font-medium">{estrategia === "mobile" ? "Mobile" : "Desktop"}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground shrink-0">Total de URLs</span>
                    <span className="text-right font-medium">{totalUrls}</span>
                  </div>
                  {TEMPLATES.filter((t) => urls[t.key].length > 0).map((t) => (
                    <div key={t.key} className="flex justify-between gap-4">
                      <span className="text-muted-foreground shrink-0">{t.label}</span>
                      <span className="text-right font-medium">{urls[t.key].length}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-brand/20 bg-brand/5 p-5 space-y-3">
                <h4 className="text-sm font-semibold text-muted-foreground">Custo estimado</h4>
                <div className="text-sm space-y-1.5 text-muted-foreground">
                  <p className="font-semibold text-foreground">{custo ?? "..."} créditos</p>
                  <p className="pl-3">Base: 15 créditos (fixo)</p>
                  <p className="pl-3">Por URL: 1 crédito cada</p>
                  <p className="pl-3">Máximo: 50 créditos</p>
                </div>
                <div className="pt-2 border-t border-brand/20">
                  <p className="text-sm">
                    Seu saldo atual:{" "}
                    <span className={cn("font-bold", saldo != null && saldo.saldo_total < 20 ? "text-destructive" : "text-brand-dark")}>
                      {saldo?.saldo_total ?? "..."}
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
                <Button type="button" className="gradient-bg border-0 hover:opacity-90 transition-opacity"
                  onClick={() => setStep((s) => s + 1)} disabled={!canAdvance() || enviando}>
                  Próximo
                </Button>
              ) : (
                <Button type="button" className="gradient-bg border-0 hover:opacity-90 transition-opacity"
                  onClick={handleSubmit} disabled={enviando || (saldo != null && saldo.saldo_total < 15)}>
                  {enviando ? "Processando..." : "Analisar CWV"}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

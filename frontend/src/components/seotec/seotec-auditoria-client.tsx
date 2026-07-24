"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowLeftIcon,
  ChevronDownIcon,
  Loader2Icon,
  UploadCloudIcon,
  SparklesIcon,
  CheckCircle2Icon,
  AlertTriangleIcon,
  XCircleIcon,
  MinusCircleIcon,
  HelpCircleIcon,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { cn } from "@/lib/utils";
import { mensagemErroAmigavel } from "@/lib/api";
import {
  buscarAuditoriaSeotec,
  editarItemSeotec,
  uploadPacoteSeotec,
  type AuditoriaDetalheSeotec,
  type ItemRespostaSeotec,
  type ItemPatchSeotec,
  type StatusItem,
} from "@/lib/api/seotec";

const FASE_LABELS: Record<string, string> = {
  before: "Before (auditoria inicial)",
  after: "After (re-auditoria)",
  concluida: "Concluída",
};

const FASE_CORES: Record<string, string> = {
  before: "border-blue-400 text-blue-700 bg-blue-50",
  after: "border-purple-400 text-purple-700 bg-purple-50",
  concluida: "border-success/30 text-success bg-success/10",
};

const STATUS_META: Record<StatusItem, { label: string; cor: string; icon: React.ElementType }> = {
  aprovado: { label: "Aprovado", cor: "border-success/30 text-success bg-success/10", icon: CheckCircle2Icon },
  atencao: { label: "Atenção", cor: "border-yellow-400 text-yellow-700 bg-yellow-50", icon: AlertTriangleIcon },
  reprovado: { label: "Reprovado", cor: "border-destructive/30 text-destructive bg-destructive/10", icon: XCircleIcon },
  na: { label: "N/A", cor: "border-border text-muted-foreground bg-muted/40", icon: MinusCircleIcon },
  sem_dados: { label: "Sem dados", cor: "border-border text-muted-foreground bg-muted/40", icon: HelpCircleIcon },
};

const PRIORIDADE_CORES: Record<string, string> = {
  alta: "border-destructive/30 text-destructive bg-destructive/10",
  media: "border-yellow-400 text-yellow-700 bg-yellow-50",
  baixa: "border-border text-muted-foreground bg-muted/40",
};

export function SeotecAuditoriaClient() {
  const pathname = usePathname();
  const id = pathname.split("/").filter(Boolean).pop() || "";

  const [auditoria, setAuditoria] = useState<AuditoriaDetalheSeotec | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [salvandoSlug, setSalvandoSlug] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const carregar = useCallback(async () => {
    try {
      const data = await buscarAuditoriaSeotec(id);
      setAuditoria(data);
      return data;
    } catch (e) {
      setErro(mensagemErroAmigavel(e));
      return null;
    }
  }, [id]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    buscarAuditoriaSeotec(id)
      .then((data) => { if (!cancelled) setAuditoria(data); })
      .catch((e) => { if (!cancelled) setErro(mensagemErroAmigavel(e)); });
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [id]);

  // Polling quando crawl está em processamento
  const crawlStatus = auditoria?.ultimo_crawl?.status;
  useEffect(() => {
    if (crawlStatus !== "enfileirado" && crawlStatus !== "processando") return;
    pollRef.current = setInterval(() => { carregar(); }, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [crawlStatus, carregar]);

  async function handleUpload(file: File) {
    if (enviando) return;
    if (!file.name.endsWith(".zip")) {
      toast.error("O arquivo deve ser um .zip (export do Screaming Frog)");
      return;
    }
    setEnviando(true);
    try {
      const resp = await uploadPacoteSeotec(id, file);
      toast.success(`Upload enviado (${resp.custo} créditos · ${resp.fase_destino})`);
      await carregar();
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setEnviando(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleEditarItem(slug: string, dados: ItemPatchSeotec) {
    setSalvandoSlug(slug);
    try {
      const atualizado = await editarItemSeotec(id, slug, dados);
      setAuditoria((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          itens: prev.itens.map((it) => (it.item_slug === slug ? atualizado : it)),
        };
      });
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setSalvandoSlug(null);
    }
  }

  if (erro) {
    return (
      <div className="space-y-6">
        <PageHeader title="Auditoria SEO Técnico" description="Erro ao carregar" />
        <div className="max-w-2xl mx-auto rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-center">
          <p className="text-sm text-destructive">{erro}</p>
        </div>
      </div>
    );
  }

  if (!auditoria) {
    return (
      <div className="space-y-6">
        <PageHeader title="Auditoria SEO Técnico" description="Carregando..." />
        <div className="max-w-2xl mx-auto space-y-4">
          <div className="h-8 rounded-lg bg-muted/50 animate-pulse" />
          <div className="h-24 rounded-xl bg-muted/50 animate-pulse" />
        </div>
      </div>
    );
  }

  // Agrupar itens por categoria
  const porCategoria: Record<string, ItemRespostaSeotec[]> = {};
  for (const item of auditoria.itens) {
    (porCategoria[item.categoria] ??= []).push(item);
  }
  const categorias = Object.keys(porCategoria).sort();

  const crawl = auditoria.ultimo_crawl;
  const crawlProcessando = crawl && (crawl.status === "enfileirado" || crawl.status === "processando");

  return (
    <div className="space-y-6">
      <PageHeader
        title={auditoria.dominio}
        description="Auditoria SEO Técnico"
        action={
          <Link href="/ferramentas/auditoria-seo-tecnico" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" /> Voltar
          </Link>
        }
      />

      <div className="max-w-3xl mx-auto space-y-4">
        {/* Header da auditoria */}
        <div className="glass-card rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <Badge variant="outline" className={FASE_CORES[auditoria.fase] || ""}>
              {FASE_LABELS[auditoria.fase] || auditoria.fase}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {new Date(auditoria.criado_em).toLocaleDateString("pt-BR")}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 text-center">
            <div className="rounded-lg border bg-surface-light p-3">
              <p className="text-xs text-muted-foreground">Score Before</p>
              <p className="text-xl font-bold">
                {auditoria.score_antes !== null ? `${auditoria.score_antes.toFixed(0)}%` : "—"}
              </p>
            </div>
            <div className="rounded-lg border bg-surface-light p-3">
              <p className="text-xs text-muted-foreground">Score After</p>
              <p className="text-xl font-bold">
                {auditoria.score_depois !== null ? `${auditoria.score_depois.toFixed(0)}%` : "—"}
              </p>
            </div>
          </div>
        </div>

        {/* Status do crawl */}
        {crawl && (
          <div className={cn(
            "rounded-xl border px-4 py-3 flex items-center gap-2 text-sm",
            crawl.status === "concluido" && "border-success/30 bg-success/5 text-success",
            crawl.status === "erro" && "border-destructive/30 bg-destructive/5 text-destructive",
            crawlProcessando && "border-brand/30 bg-brand/5 text-brand-dark",
            (crawl.status !== "concluido" && crawl.status !== "erro" && !crawlProcessando) && "border-border bg-surface-light text-muted-foreground",
          )}>
            {crawlProcessando && <Loader2Icon className="size-4 animate-spin" />}
            <span className="font-medium">Crawl: {crawl.status}</span>
            {crawl.origem === "upload" && <span className="text-xs">· upload manual</span>}
            {crawl.fase_destino && <span className="text-xs">· {crawl.fase_destino}</span>}
            {crawl.erro_msg && <span className="text-xs truncate">· {crawl.erro_msg}</span>}
          </div>
        )}

        {/* Upload zone */}
        {auditoria.fase !== "concluida" && !crawlProcessando && (
          <div
            className="rounded-2xl border-2 border-dashed border-border p-8 text-center hover:border-brand/40 hover:bg-brand/5 transition-colors cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files[0];
              if (f) handleUpload(f);
            }}
            onDragOver={(e) => e.preventDefault()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
              }}
            />
            {enviando ? (
              <div className="flex flex-col items-center gap-2">
                <Loader2Icon className="size-8 animate-spin text-brand" />
                <p className="text-sm text-muted-foreground">Enviando pacote...</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <UploadCloudIcon className="size-8 text-muted-foreground" />
                <p className="text-sm font-medium">Enviar pacote do Screaming Frog (.zip)</p>
                <p className="text-xs text-muted-foreground">Clique ou arraste o arquivo aqui</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Fase destino: <span className="font-medium">{auditoria.fase === "before" ? "before" : "after"}</span>
                </p>
              </div>
            )}
          </div>
        )}

        {/* Checklist por categoria */}
        {categorias.map((categoria) => (
          <div key={categoria} className="glass-card rounded-2xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">{categoria}</h2>
              <span className="text-xs text-muted-foreground">{porCategoria[categoria].length} itens</span>
            </div>
            <div className="space-y-2">
              {porCategoria[categoria].map((item) => (
                <ItemCard
                  key={item.item_slug}
                  item={item}
                  salvando={salvandoSlug === item.item_slug}
                  onEditar={(dados) => handleEditarItem(item.item_slug, dados)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: StatusItem | null }) {
  if (!status) {
    return <span className="inline-flex items-center rounded-md border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground bg-muted/40">—</span>;
  }
  const meta = STATUS_META[status];
  const Icon = meta.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-medium", meta.cor)}>
      <Icon className="size-3" /> {meta.label}
    </span>
  );
}

function ItemCard({
  item,
  salvando,
  onEditar,
}: {
  item: ItemRespostaSeotec;
  salvando: boolean;
  onEditar: (dados: ItemPatchSeotec) => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const [editandoObs, setEditandoObs] = useState(false);
  const [obsCliente, setObsCliente] = useState(item.observacao_cliente ?? "");
  const [obsSeo, setObsSeo] = useState(item.observacao_seo ?? "");
  const temConteudoIA = !!(item.diagnostico || item.recomendacao);
  const temEvidencias = Object.keys(item.evidencias_json ?? {}).length > 0;

  return (
    <div className="rounded-lg border bg-surface-light px-4 py-3 space-y-2">
      {/* Linha 1: nome + badges */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <button
            type="button"
            onClick={() => setExpandido((v) => !v)}
            className="flex items-center gap-1.5 text-left"
          >
            <ChevronDownIcon className={cn("size-3.5 text-muted-foreground transition-transform", !expandido && "-rotate-90")} />
            <p className="text-sm font-medium" title={item.nome}>{item.nome}</p>
          </button>
          <div className="flex items-center gap-1.5 mt-1 ml-5">
            <span className="text-[10px] text-muted-foreground">slug: {item.item_slug}</span>
            <span className="text-[10px] text-muted-foreground">· peso: {item.peso}</span>
            <span className="text-[10px] text-muted-foreground">· {item.fonte}</span>
            <span className="text-[10px] text-muted-foreground">· {item.modo}</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {item.prioridade && (
            <Badge variant="outline" className={cn("text-[9px]", PRIORIDADE_CORES[item.prioridade] || "")}>
              {item.prioridade}
            </Badge>
          )}
          <StatusBadge status={item.status_antes} />
          {item.status_depois && (
            <>
              <span className="text-muted-foreground text-[10px]">→</span>
              <StatusBadge status={item.status_depois} />
            </>
          )}
        </div>
      </div>

      {/* Indicador IA */}
      {temConteudoIA && !expandido && (
        <div className="ml-5 flex items-center gap-1.5">
          <SparklesIcon className="size-3 text-brand" />
          <span className="text-[11px] text-muted-foreground">
            {item.diagnostico ? "Diagnóstico IA" : ""}
            {item.diagnostico && item.recomendacao ? " + " : ""}
            {item.recomendacao ? "Recomendação IA" : ""}
          </span>
        </div>
      )}

      {/* Conteúdo expandido */}
      {expandido && (
        <div className="ml-5 space-y-3 pt-2 border-t border-border">
          {/* Diagnóstico */}
          {item.diagnostico && (
            <div className="space-y-1">
              <p className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
                <SparklesIcon className="size-3" /> Diagnóstico
              </p>
              <div className="prose prose-sm max-w-none text-muted-foreground rounded-lg border bg-card p-3">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.diagnostico}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* Recomendação */}
          {item.recomendacao && (
            <div className="space-y-1">
              <p className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
                <SparklesIcon className="size-3" /> Recomendação
              </p>
              <div className="prose prose-sm max-w-none text-muted-foreground rounded-lg border bg-card p-3">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.recomendacao}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* Evidências */}
          {temEvidencias && (
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Evidências</summary>
              <pre className="mt-1 rounded-lg border bg-card p-2 overflow-x-auto text-[10px]">
                {JSON.stringify(item.evidencias_json, null, 2)}
              </pre>
            </details>
          )}

          {/* Status cliente / validação SEO */}
          <div className="flex flex-wrap items-center gap-3">
            {salvando && <Loader2Icon className="size-3 animate-spin text-muted-foreground" />}
            <label className="flex items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">Status cliente:</span>
              <select
                className="text-xs rounded border bg-card px-2 py-0.5"
                value={item.status_cliente ?? ""}
                onChange={(e) => onEditar({ status_cliente: e.target.value || null })}
              >
                <option value="">—</option>
                <option value="implementado">Implementado</option>
                <option value="em_andamento">Em andamento</option>
                <option value="nao_executado">Não executado</option>
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">Validação SEO:</span>
              <select
                className="text-xs rounded border bg-card px-2 py-0.5"
                value={item.validacao_seo ?? ""}
                onChange={(e) => onEditar({ validacao_seo: e.target.value || null })}
              >
                <option value="">—</option>
                <option value="aprovado">Aprovado</option>
                <option value="reprovado">Reprovado</option>
                <option value="pendente">Pendente</option>
              </select>
            </label>
          </div>

          {/* Observações */}
          {editandoObs ? (
            <div className="space-y-2">
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">Obs. cliente</label>
                  <textarea
                    className="w-full text-xs rounded border bg-card px-2 py-1 resize-none"
                    rows={2}
                    value={obsCliente}
                    onChange={(e) => setObsCliente(e.target.value)}
                    placeholder="Observação do cliente..."
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] text-muted-foreground">Obs. SEO</label>
                  <textarea
                    className="w-full text-xs rounded border bg-card px-2 py-1 resize-none"
                    rows={2}
                    value={obsSeo}
                    onChange={(e) => setObsSeo(e.target.value)}
                    placeholder="Observação do consultor SEO..."
                  />
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  className="text-[11px] rounded bg-brand px-2 py-0.5 text-white"
                  onClick={() => {
                    onEditar({ observacao_cliente: obsCliente || null, observacao_seo: obsSeo || null });
                    setEditandoObs(false);
                  }}
                >
                  Salvar
                </button>
                <button
                  className="text-[11px] text-muted-foreground"
                  onClick={() => {
                    setObsCliente(item.observacao_cliente ?? "");
                    setObsSeo(item.observacao_seo ?? "");
                    setEditandoObs(false);
                  }}
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : (
            <button
              className="text-[11px] text-muted-foreground hover:text-foreground"
              onClick={() => {
                setObsCliente(item.observacao_cliente ?? "");
                setObsSeo(item.observacao_seo ?? "");
                setEditandoObs(true);
              }}
            >
              {(() => {
                const obs = item.observacao_cliente || item.observacao_seo;
                if (!obs) return "+ Adicionar observações";
                return `📝 ${obs.slice(0, 60)}${obs.length > 60 ? "…" : ""}`;
              })()}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

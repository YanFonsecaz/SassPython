"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeftIcon,
  CheckCircle2Icon,
  Loader2Icon,
  ArrowRightIcon,
  CircleIcon,
  GaugeIcon,
  NetworkIcon,
  LayersIcon,
  SearchIcon,
  FileTextIcon,
  ListOrderedIcon,
  SaveIcon,
  ShieldCheckIcon,
  DownloadIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { createSSEConnection } from "@/lib/sse-client";
import {
  buscarExecucaoCwv,
  buscarHealthScoreCwv,
  buscarPageExperienceCwv,
  exportarExecucaoCwvDocx,
  type HealthScoreResposta,
  type PageExperienceListResponse,
} from "@/lib/api/cwv";
import { mensagemErroAmigavel } from "@/lib/api";
import { CwvErroExecucao } from "@/components/cwv/cwv-erro-execucao";
import { classificarMetrica, corClassificacao, rotuloClassificacao, THRESHOLDS } from "@/lib/cwv/thresholds";

interface ExecucaoCwv {
  id: string;
  ferramenta: string;
  status: string;
  etapa_atual: string | null;
  creditos_cobrados: number;
  criado_em: string;
  resultado_json: Record<string, unknown> | null;
  erro_msg: string | null;
  concluida_em: string | null;
}

// SPEC_CWV_Page_Experience: lista fixa de etapas do workflow CWV (inclui o nó
// novo coletar_page_experience). O stepper acende conforme node_start/
// node_complete chegam via SSE. Ordem = ordem do grafo em construir_workflow().
const ETAPAS_CWV: { node: string; label: string; icon: React.ElementType }[] = [
  { node: "coletar_psi", label: "Coletar métricas", icon: GaugeIcon },
  { node: "coletar_page_experience", label: "Page Experience", icon: ShieldCheckIcon },
  { node: "detectar_plataformas", label: "Detectar plataformas", icon: LayersIcon },
  { node: "analisar_seo", label: "Analisar SEO", icon: SearchIcon },
  { node: "documentar", label: "Documentar problemas", icon: FileTextIcon },
  { node: "pesquisar_outros", label: "Pesquisar residual", icon: NetworkIcon },
  { node: "priorizar", label: "Priorizar", icon: ListOrderedIcon },
  { node: "persistir", label: "Salvar análises", icon: SaveIcon },
];

type NodeStatus = "pendente" | "andamento" | "concluida";

export function CwvExecucaoClient() {
  const pathname = usePathname();
  const id = pathname.split("/").filter(Boolean).pop() || "";
  const [execucao, setExecucao] = useState<ExecucaoCwv | null>(null);
  const [etapaAtual, setEtapaAtual] = useState<string | null>(null);
  const [statusFinal, setStatusFinal] = useState<string | null>(null);
  const [erroMsg, setErroMsg] = useState<string | null>(null);
  const [conectandoSSE, setConectandoSSE] = useState(false);
  const [healthScore, setHealthScore] = useState<HealthScoreResposta | null>(null);
  const [pageExperience, setPageExperience] = useState<PageExperienceListResponse | null>(null);
  const [exportandoExecucao, setExportandoExecucao] = useState(false);
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeStatus>>({});
  const closeRef = useRef<{ close: () => void } | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (!id) return;
    buscarExecucaoCwv(id).then((dados) => {
      setExecucao(dados);
      setEtapaAtual(dados.etapa_atual);
      if (["concluida", "falhou", "cancelada"].includes(dados.status)) {
        setStatusFinal(dados.status);
        setErroMsg(dados.erro_msg);
      }
    }).catch(() => {
      setErroMsg("Execução não encontrada");
      setStatusFinal("falhou");
    });
  }, [id]);

  useEffect(() => {
    if (!id || statusFinal) return;

    const close = createSSEConnection(
      `/ferramentas/historico/${id}/progresso`,
      (data: unknown) => {
        if (typeof data !== "object" || data === null) return;
        const evt = data as Record<string, unknown>;
        const type = evt.type as string;

        if (type === "status") {
          setEtapaAtual(evt.etapa as string | null);
          setExecucao((prev) => prev ? { ...prev, status: evt.status as string, etapa_atual: evt.etapa as string | null } : prev);
        } else if (type === "node_start") {
          const node = evt.node as string;
          setNodeStatuses((prev) => ({ ...prev, [node]: "andamento" }));
          setEtapaAtual(evt.detail as string | null);
        } else if (type === "node_complete") {
          const node = evt.node as string;
          setNodeStatuses((prev) => ({ ...prev, [node]: "concluida" }));
          setEtapaAtual(evt.detail as string | null);
        } else if (type === "node_progress") {
          setEtapaAtual(evt.detail as string | null);
        } else if (type === "concluida") {
          setStatusFinal("concluida");
          setConectandoSSE(false);
          buscarExecucaoCwv(id).then(setExecucao);
        } else if (type === "falhou") {
          setStatusFinal("falhou");
          setErroMsg((evt.erro as string) || "Erro desconhecido");
          setConectandoSSE(false);
        }
      },
      {
        onComplete: () => setConectandoSSE(false),
        onError: () => { setConectandoSSE(false); setErroMsg("Erro na conexão"); },
      }
    );
    closeRef.current = close;
    setConectandoSSE(true);

    return () => { close.close(); closeRef.current = null; };
  }, [id, statusFinal]);

  // SPEC_CWV_Health_Score: lê do resultado_json se já vier; senão (execução
  // antiga) chama o endpoint que calcula on-the-fly.
  useEffect(() => {
    if (!id || statusFinal !== "concluida") return;
    const embutido = execucao?.resultado_json as { health_score?: HealthScoreResposta | null } | null;
    if (embutido && "health_score" in embutido && embutido.health_score !== undefined) {
      const hs = embutido.health_score;
      setHealthScore(hs === null
        ? { health_score: null, n_pass: 0, n_total: 0, por_estrategia: { mobile: null, desktop: null } }
        : hs);
      return;
    }
    buscarHealthScoreCwv(id).then(setHealthScore).catch(() => setHealthScore(null));
  }, [id, statusFinal, execucao]);

  // SPEC_CWV_Page_Experience: busca checagens por origem ao concluir.
  useEffect(() => {
    if (!id || statusFinal !== "concluida") return;
    buscarPageExperienceCwv(id).then(setPageExperience).catch(() => setPageExperience(null));
  }, [id, statusFinal]);

  if (!execucao && !erroMsg) {
    return (
      <div className="space-y-6">
        <PageHeader title="Core Web Vitals" description="Carregando..." />
        <div className="max-w-lg mx-auto space-y-4">
          <div className="h-8 rounded-lg bg-muted/50 animate-pulse" />
          <div className="h-24 rounded-xl bg-muted/50 animate-pulse" />
        </div>
      </div>
    );
  }

  const resultado = execucao?.resultado_json as Record<string, unknown> | null;
  const analiseIds = (resultado?.analise_ids as string[]) ?? [];

  async function handleExportarExecucao() {
    if (!id || exportandoExecucao) return;
    setExportandoExecucao(true);
    try {
      const blob = await exportarExecucaoCwvDocx(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cwv-auditoria-${id.slice(0, 8)}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setExportandoExecucao(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Core Web Vitals"
        description="Processando análise..."
        action={
          <Link href="/ferramentas/core-web-vitals" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" /> Voltar
          </Link>
        }
      />

      <div className="max-w-lg mx-auto">
        <div className="glass-card rounded-2xl p-6 sm:p-8 space-y-6">
          {statusFinal === "concluida" ? (
            <>
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center size-12 rounded-full bg-success/10">
                  <CheckCircle2Icon className="size-6 text-success" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">Análise concluída!</h2>
                  <p className="text-sm text-muted-foreground">
                    {execucao?.creditos_cobrados ?? 0} créditos cobrados
                  </p>
                </div>
              </div>

              {analiseIds.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">{analiseIds.length} URL{analiseIds.length !== 1 ? "s" : ""} analisada{analiseIds.length !== 1 ? "s" : ""}:</p>
                  <div className="space-y-1.5">
                    {analiseIds.map((aId) => (
                      <Link key={aId} href={`/ferramentas/core-web-vitals/url/${aId}`}
                        className="flex items-center gap-3 rounded-lg border bg-surface-light px-3 py-2.5 group transition-all hover:border-brand/30 hover:shadow-sm">
                        <ArrowRightIcon className="size-4 text-muted-foreground group-hover:text-brand-dark transition-colors shrink-0" />
                        <span className="text-sm font-medium text-brand-dark">Ver dashboard</span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}

              {healthScore && <HealthScoreCard hs={healthScore} />}

              {pageExperience && pageExperience.origens.length > 0 && (
                <PageExperienceSection pe={pageExperience} />
              )}

              <div className="flex gap-2 pt-2">
                <Button onClick={handleExportarExecucao} disabled={exportandoExecucao}>
                  {exportandoExecucao ? <Loader2Icon className="size-4 mr-1 animate-spin" /> : <DownloadIcon className="size-4 mr-1" />}
                  Baixar relatório completo (.docx)
                </Button>
                <Button variant="outline" onClick={() => router.push("/ferramentas/core-web-vitals")}>
                  Nova análise
                </Button>
              </div>
            </>
          ) : statusFinal === "falhou" ? (
            <CwvErroExecucao
              motivo={(execucao?.resultado_json as { motivo_falha?: string } | null)?.motivo_falha}
              erroMsg={erroMsg}
              onTentarNovamente={() => router.push("/ferramentas/core-web-vitals")}
            />
          ) : (
            <>
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center size-12 rounded-full bg-brand/10">
                  <Loader2Icon className="size-6 text-brand-dark animate-spin" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">Analisando URLs...</h2>
                  <p className="text-sm text-muted-foreground">{etapaAtual || "Aguardando..."}</p>
                </div>
              </div>
              <StepperCWV nodeStatuses={nodeStatuses} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function HealthScoreCard({ hs }: { hs: HealthScoreResposta }) {
  if (hs.health_score === null) {
    return (
      <div className="rounded-xl border bg-surface-light p-4">
        <p className="text-sm font-medium">Health Score</p>
        <p className="text-xs text-muted-foreground mt-1">
          Sem score disponível (nenhuma URL analisada com sucesso).
        </p>
      </div>
    );
  }
  const classif = classificarMetrica(hs.health_score, THRESHOLDS.score);
  const cores = corClassificacao(classif);
  const pct = Number(hs.health_score.toFixed(1)).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return (
    <div className={`rounded-xl border p-4 ${cores.bg}`}>
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-medium">Health Score</p>
        <span className={`text-xs font-medium ${cores.text}`}>{rotuloClassificacao(classif)}</span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={`text-3xl font-bold ${cores.text}`}>{pct}%</span>
        <span className="text-xs text-muted-foreground">{hs.n_pass}/{hs.n_total} audits saudáveis</span>
      </div>
      {(hs.por_estrategia.mobile !== null || hs.por_estrategia.desktop !== null) && (
        <div className="mt-2 flex gap-3 text-xs text-muted-foreground">
          {hs.por_estrategia.mobile !== null && (
            <span>Mobile: {hs.por_estrategia.mobile.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</span>
          )}
          {hs.por_estrategia.desktop !== null && (
            <span>Desktop: {hs.por_estrategia.desktop.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</span>
          )}
        </div>
      )}
    </div>
  );
}

function StepperCWV({ nodeStatuses }: { nodeStatuses: Record<string, NodeStatus> }) {
  return (
    <div className="space-y-1.5">
      {ETAPAS_CWV.map((etapa, idx) => {
        const status = nodeStatuses[etapa.node] ?? "pendente";
        const Icon = etapa.icon;
        const isLast = idx === ETAPAS_CWV.length - 1;
        return (
          <div key={etapa.node} className="flex items-center gap-3">
            <div className="flex flex-col items-center">
              {status === "concluida" ? (
                <CheckCircle2Icon className="size-5 text-success shrink-0" />
              ) : status === "andamento" ? (
                <Loader2Icon className="size-5 text-brand-dark animate-spin shrink-0" />
              ) : (
                <CircleIcon className="size-5 text-muted-foreground/40 shrink-0" />
              )}
              {!isLast && <div className="w-px h-4 bg-border" />}
            </div>
            <div className="flex items-center gap-2 pb-4">
              <Icon className={`size-3.5 ${status === "pendente" ? "text-muted-foreground/40" : "text-muted-foreground"}`} />
              <span className={`text-sm ${status === "pendente" ? "text-muted-foreground/50" : status === "andamento" ? "text-foreground font-medium" : "text-muted-foreground"}`}>
                {etapa.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

const VEREDITO_LABELS: Record<string, string> = {
  pass: "OK",
  fail: "Falha",
  erro: "Inconclusivo",
  na: "N/A",
};

function corVeredito(v: string): string {
  if (v === "pass") return "border-success/30 text-success bg-success/10";
  if (v === "fail") return "border-destructive/30 text-destructive bg-destructive/10";
  if (v === "erro") return "border-yellow-500/30 text-yellow-600 bg-yellow-500/10";
  return "border-border text-muted-foreground bg-muted/40";
}

const PAGE_EXP_CHECKS: { key: string; label: string }[] = [
  { key: "https", label: "HTTPS" },
  { key: "ssl", label: "SSL" },
  { key: "redirect_301", label: "Redirect 301" },
  { key: "security_headers", label: "Headers de segurança" },
  { key: "safe_browsing", label: "Safe Browsing" },
  { key: "mixed_content", label: "Mixed content" },
  { key: "mobile_friendly", label: "Mobile-friendly" },
];

function PageExperienceSection({ pe }: { pe: PageExperienceListResponse }) {
  return (
    <div className="rounded-xl border bg-surface-light p-4">
      <p className="text-sm font-medium mb-3">Page Experience (por origem)</p>
      <div className="space-y-3">
        {pe.origens.map((o) => (
          <div key={o.origem} className="space-y-1.5">
            <p className="text-xs font-mono text-muted-foreground truncate" title={o.origem}>{o.origem}</p>
            <div className="flex flex-wrap gap-1.5">
              {PAGE_EXP_CHECKS.map((c) => {
                const v = o[c.key as keyof typeof o] as string;
                return (
                  <span
                    key={c.key}
                    className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${corVeredito(v)}`}
                    title={`${c.label}: ${VEREDITO_LABELS[v] ?? v}`}
                  >
                    {c.label}: {VEREDITO_LABELS[v] ?? v}
                  </span>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

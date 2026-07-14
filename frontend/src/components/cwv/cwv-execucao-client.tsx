"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { ArrowLeftIcon, CheckCircle2Icon, Loader2Icon, ArrowRightIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { createSSEConnection } from "@/lib/sse-client";
import { buscarExecucaoCwv, buscarHealthScoreCwv, type HealthScoreResposta } from "@/lib/api/cwv";
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

export function CwvExecucaoClient() {
  const pathname = usePathname();
  const id = pathname.split("/").filter(Boolean).pop() || "";
  const [execucao, setExecucao] = useState<ExecucaoCwv | null>(null);
  const [etapaAtual, setEtapaAtual] = useState<string | null>(null);
  const [statusFinal, setStatusFinal] = useState<string | null>(null);
  const [erroMsg, setErroMsg] = useState<string | null>(null);
  const [conectandoSSE, setConectandoSSE] = useState(false);
  const [healthScore, setHealthScore] = useState<HealthScoreResposta | null>(null);
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

              <div className="flex gap-2 pt-2">
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
              <div className="space-y-2">
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div className="h-full rounded-full gradient-bg animate-pulse w-2/3" />
                </div>
              </div>
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

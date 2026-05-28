"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { ArrowLeftIcon, RefreshCwIcon, AlertTriangleIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { MetricasResumo } from "@/components/cwv/cwv-metricas-resumo";
import { EvolucaoChart } from "@/components/cwv/cwv-evolucao-chart";
import { PlanoAcaoAccordion } from "@/components/cwv/cwv-plano-acao";
import { ReanalisarDialog } from "@/components/cwv/cwv-reanalisar-dialog";
import { ComparadorComponent } from "@/components/cwv/comparador-component";
import { CwvEstadoBanner } from "@/components/cwv/cwv-estado-banner";
import { PlataformaOverrideDialog } from "@/components/cwv/cwv-plataforma-override-dialog";
import { classificarAnalise } from "@/lib/cwv-estado";
import { PencilIcon, SparklesIcon } from "lucide-react";
import type { CwvAnaliseResposta, CwvAnaliseResumo, ComparacaoResposta } from "@/lib/api/cwv";
import { buscarComparacao } from "@/lib/api/cwv";

interface DashboardUrlClientProps {
  analiseAtual: CwvAnaliseResposta;
  historico: CwvAnaliseResumo[];
  clienteId: string;
}

export function DashboardUrlClient({ analiseAtual, historico, clienteId }: DashboardUrlClientProps) {
  const [reanalisarOpen, setReanalisarOpen] = useState(false);
  const [plataformaOpen, setPlataformaOpen] = useState(false);
  const [comparacao, setComparacao] = useState<ComparacaoResposta | null>(null);
  const [carregandoComparacao, setCarregandoComparacao] = useState(true);
  const [erroComparacao, setErroComparacao] = useState<string | null>(null);

  useEffect(() => {
    async function carregarComparacao() {
      setCarregandoComparacao(true);
      setErroComparacao(null);
      try {
        const data = await buscarComparacao(analiseAtual.id);
        setComparacao(data);
      } catch (error) {
        // Ignorar erros de comparação - pode não ter análise anterior
        setErroComparacao(error instanceof Error ? error.message : "Erro ao carregar comparação");
      } finally {
        setCarregandoComparacao(false);
      }
    }
    
    // Só tentar carregar se houver histórico e análise atual
    if (historico.length >= 1 && analiseAtual) {
      carregarComparacao();
    } else {
      setCarregandoComparacao(false);
    }
  }, [analiseAtual.id, historico.length]);

  const analiseAnterior = historico.length >= 2 ? historico[1] : undefined;
  const estado = useMemo(() => classificarAnalise(analiseAtual), [analiseAtual]);

  if (analiseAtual.status === "falhou_psi" || analiseAtual.status === "falhou") {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Core Web Vitals"
          description={analiseAtual.url_canonica}
          action={
            <Link href={`/ferramentas/core-web-vitals/historico/${clienteId}`} className={buttonVariants({ variant: "ghost", size: "sm" })}>
              <ArrowLeftIcon className="size-4 mr-1" /> Voltar ao historico
            </Link>
          }
        />
        <div className="max-w-2xl mx-auto glass-card rounded-2xl p-6 sm:p-8 space-y-4 text-center">
          <div className="flex items-center justify-center size-12 rounded-full bg-destructive/10 mx-auto">
            <AlertTriangleIcon className="size-6 text-destructive" />
          </div>
          <h2 className="text-lg font-semibold">Analise falhou</h2>
          <p className="text-sm text-muted-foreground">{analiseAtual.erro_msg || "Erro desconhecido ao consultar PageSpeed Insights."}</p>
          <Button onClick={() => setReanalisarOpen(true)}>
            <RefreshCwIcon className="size-4 mr-1" /> Tentar novamente
          </Button>
        </div>
        <ReanalisarDialog analiseId={analiseAtual.id} open={reanalisarOpen} onOpenChange={setReanalisarOpen} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Core Web Vitals"
        description=""
        action={
          <Link href={`/ferramentas/core-web-vitals/historico/${clienteId}`} className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" /> Voltar ao historico
          </Link>
        }
      />

      <div className="max-w-4xl space-y-6">
        <div className="glass-card rounded-2xl p-6 sm:p-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
            <div className="min-w-0">
              <p className="text-sm font-medium truncate max-w-md" title={analiseAtual.url_canonica}>
                {analiseAtual.url_canonica}
              </p>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                {analiseAtual.plataforma_detectada && analiseAtual.plataforma_detectada !== "desconhecida" ? (
                  <button
                    type="button"
                    onClick={() => setPlataformaOpen(true)}
                    className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs hover:bg-surface-light transition-colors"
                    title="Trocar plataforma manualmente"
                  >
                    {analiseAtual.plataforma_detectada}
                    <PencilIcon className="size-2.5 opacity-60" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => setPlataformaOpen(true)}
                    className="inline-flex items-center gap-1 rounded-md border border-amber-400 bg-amber-50 dark:bg-amber-950/20 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300 hover:bg-amber-100 transition-colors"
                  >
                    ⚠ plataforma nao detectada · selecionar
                  </button>
                )}
                <Badge variant="outline">{analiseAtual.template_tipo}</Badge>
                <Badge variant="outline">{analiseAtual.estrategia === "mobile" ? "Mobile" : "Desktop"}</Badge>
                {analiseAtual.llm_usado && (
                  <Badge
                    variant="outline"
                    className="gap-1 border-purple-300 text-purple-700 dark:text-purple-300"
                    title={`${analiseAtual.llm_audits_processados ?? 0} audits processados por IA`}
                  >
                    <SparklesIcon className="size-3" />
                    IA · {analiseAtual.llm_audits_processados ?? 0}
                  </Badge>
                )}
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => setReanalisarOpen(true)}>
              <RefreshCwIcon className="size-4 mr-1" /> Re-analisar
            </Button>
          </div>

          <MetricasResumo analiseAtual={analiseAtual} analiseAnterior={analiseAnterior} />

          <CwvEstadoBanner estado={estado} score={analiseAtual.score_performance} />

          {/* Comparador com análise anterior */}
          {carregandoComparacao && (
            <div className="mt-6 border-t border-border pt-6">
              <div className="animate-pulse space-y-2">
                <div className="h-4 bg-muted/50 rounded w-3/4"></div>
                <div className="h-4 bg-muted/50 rounded w-1/2"></div>
                <div className="h-4 bg-muted/50 rounded w-2/3"></div>
              </div>
            </div>
          )}
          
          {!carregandoComparacao && comparacao && <ComparadorComponent comparacao={comparacao} />}

          {!carregandoComparacao && !comparacao && historico.length >= 1 && (
            <div className="mt-6 border-t border-border pt-6">
              <p className="text-sm text-muted-foreground text-center py-4">
                Primeira análise — registre mais para acompanhar evolução.
              </p>
            </div>
          )}

          <div className="mt-6 border-t border-border pt-6">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">
              Plano de acao
            </h3>
            <PlanoAcaoAccordion problemas={analiseAtual.problemas ?? []} />
          </div>
        </div>

        {historico.length >= 2 && (
          <div className="glass-card rounded-2xl p-6 sm:p-8">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">
              Evolucao ({historico.length} analise{historico.length !== 1 ? "s" : ""})
            </h3>
            <EvolucaoChart historico={historico} />
          </div>
        )}
      </div>

      <ReanalisarDialog analiseId={analiseAtual.id} open={reanalisarOpen} onOpenChange={setReanalisarOpen} />
      <PlataformaOverrideDialog
        analiseId={analiseAtual.id}
        open={plataformaOpen}
        onOpenChange={setPlataformaOpen}
        plataformaAtual={analiseAtual.plataforma_detectada}
        onSuccess={() => window.location.reload()}
      />
    </div>
  );
}

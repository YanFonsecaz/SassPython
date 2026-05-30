"use client";

import { cn } from "@/lib/utils";
import {
  THRESHOLDS,
  classificarMetrica,
  rotuloClassificacao,
  corClassificacao,
  tooltipThresholds,
  formatMs,
  formatCls,
  calcularDelta,
  type ThresholdConfig,
} from "@/lib/cwv/thresholds";
import type { CwvAnaliseResposta, CwvAnaliseResumo } from "@/lib/api/cwv";
import { TermoComAjuda } from "@/components/ui/termo-com-ajuda";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";

interface MetricasResumoProps {
  analiseAtual: CwvAnaliseResposta;
  analiseAnterior?: CwvAnaliseResposta | CwvAnaliseResumo;
}

interface TileProps {
  label: string;
  value: number | null;
  cfg: ThresholdConfig;
  formatter: (v: number | null) => string;
}

function MetricaTile({ label, value, cfg, formatter }: TileProps) {
  const classe = classificarMetrica(value, cfg);
  const cores = corClassificacao(classe);
  const tooltip = tooltipThresholds(label, cfg);

  return (
    <div
      className="rounded-xl border bg-card p-4 flex flex-col items-center justify-center gap-1"
    >
      <p className="text-sm font-medium text-muted-foreground">
        <TermoComAjuda termo={label} texto={tooltip} />
      </p>
      <p className={cn("text-xl font-bold tabular-nums", cores.text)}>{formatter(value)}</p>
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium",
          cores.bg,
          cores.text,
        )}
      >
        <span className={cn("h-1.5 w-1.5 rounded-full", cores.dot)} aria-hidden />
        {rotuloClassificacao(classe)}
      </span>
    </div>
  );
}

export function MetricasResumo({ analiseAtual, analiseAnterior }: MetricasResumoProps) {
  const score = analiseAtual.score_performance;
  const scoreAnt = analiseAnterior?.score_performance ?? null;
  const scoreCfg = THRESHOLDS.score;
  const scoreClasse = classificarMetrica(score, scoreCfg);
  const scoreCores = corClassificacao(scoreClasse);
  const scoreDelta = calcularDelta(score, scoreAnt, scoreCfg);

  const tilesAnterior = analiseAnterior as CwvAnaliseResposta | undefined;

  const metricas: Array<{
    label: string;
    value: number | null;
    ant: number | null;
    cfg: ThresholdConfig;
    formatter: (v: number | null) => string;
  }> = [
    { label: "LCP", value: analiseAtual.lcp_ms, ant: analiseAnterior?.lcp_ms ?? null, cfg: THRESHOLDS.lcp, formatter: formatMs },
    { label: "CLS", value: analiseAtual.cls, ant: analiseAnterior?.cls ?? null, cfg: THRESHOLDS.cls, formatter: formatCls },
    { label: "INP", value: analiseAtual.inp_ms, ant: analiseAnterior?.inp_ms ?? null, cfg: THRESHOLDS.inp, formatter: formatMs },
    { label: "TBT", value: analiseAtual.tbt_ms, ant: tilesAnterior?.tbt_ms ?? null, cfg: THRESHOLDS.tbt, formatter: formatMs },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        <div
          className={cn("rounded-xl border p-4 flex flex-col items-center justify-center gap-1", scoreCores.bg)}
        >
          <p className="text-sm font-medium text-muted-foreground">
            <TermoComAjuda termo="Score" texto={tooltipThresholds("Score", scoreCfg)} />
          </p>
          <div className="flex items-baseline gap-1">
            <p className={cn("text-3xl font-bold tabular-nums", scoreCores.text)}>{score ?? "—"}</p>
            <span className="text-xs text-muted-foreground">/ 100</span>
          </div>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium",
              scoreCores.bg,
              scoreCores.text,
            )}
          >
            <span className={cn("h-1.5 w-1.5 rounded-full", scoreCores.dot)} aria-hidden />
            {rotuloClassificacao(scoreClasse)}
          </span>
        </div>

        {metricas.map((m) => (
          <MetricaTile key={m.label} label={m.label} value={m.value} cfg={m.cfg} formatter={m.formatter} />
        ))}
      </div>

      {analiseAnterior && (
        <div className="rounded-lg bg-surface-light border px-4 py-3">
          <p className="text-xs text-muted-foreground mb-2">
            vs. análise anterior
            {analiseAnterior.criado_em && (
              <> (em {new Date(analiseAnterior.criado_em).toLocaleDateString("pt-BR")})</>
            )}
            :
          </p>
          <div className="flex flex-wrap gap-4 text-sm">
            {scoreDelta && (
              <span className="font-medium">
                Score: <span className={scoreDelta.color}>{scoreDelta.text}</span>
              </span>
            )}
            {metricas.map((m) => {
              const d = calcularDelta(m.value, m.ant, m.cfg);
              if (!d) return null;
              return (
                <span key={m.label} className="font-medium">
                  {m.label}: <span className={d.color}>{d.text}</span>
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

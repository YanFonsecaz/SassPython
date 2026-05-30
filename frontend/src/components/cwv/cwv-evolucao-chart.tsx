"use client";

import { useMemo, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceArea, ReferenceLine } from "recharts";
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
import type { CwvAnaliseResumo } from "@/lib/api/cwv";

interface MetricaDef {
  id: "score" | "lcp" | "cls" | "inp";
  label: string;
  campo: keyof Pick<CwvAnaliseResumo, "score_performance" | "lcp_ms" | "cls" | "inp_ms">;
  cor: string;
  cfg: ThresholdConfig;
  formatter: (v: number | null) => string;
  yMax?: number;
}

const METRICAS: MetricaDef[] = [
  { id: "score", label: "Score", campo: "score_performance", cor: "var(--chart-1)", cfg: THRESHOLDS.score, formatter: (v) => (v === null ? "—" : String(v)), yMax: 100 },
  { id: "lcp", label: "LCP", campo: "lcp_ms", cor: "var(--chart-2)", cfg: THRESHOLDS.lcp, formatter: formatMs },
  { id: "cls", label: "CLS", campo: "cls", cor: "var(--chart-3)", cfg: THRESHOLDS.cls, formatter: formatCls },
  { id: "inp", label: "INP", campo: "inp_ms", cor: "var(--chart-4)", cfg: THRESHOLDS.inp, formatter: formatMs },
];

interface EvolucaoChartProps {
  historico: CwvAnaliseResumo[];
}

function formatarDataPonto(iso: string, comHora: boolean): string {
  const d = new Date(iso);
  const data = d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  if (!comHora) return data;
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${data} ${hora}`;
}

function ChipClassificacao({ value, cfg }: { value: number | null; cfg: ThresholdConfig }) {
  const classe = classificarMetrica(value, cfg);
  const cores = corClassificacao(classe);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
        cores.bg,
        cores.text,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", cores.dot)} aria-hidden />
      {rotuloClassificacao(classe)}
    </span>
  );
}

/**
 * Sparkline minimalista. Orientado por "melhor = mais alto" sempre:
 * para métricas onde menor é melhor (LCP/CLS/INP) o eixo é invertido,
 * então uma série que melhora SEMPRE sobe visualmente.
 */
function Sparkline({
  valores,
  cor,
  lowerIsBetter,
}: {
  valores: (number | null)[];
  cor: string;
  lowerIsBetter: boolean;
}) {
  const pts = valores.filter((v): v is number => v !== null && !Number.isNaN(v));
  if (pts.length < 2) return null;

  const w = 120;
  const h = 36;
  const pad = 4;
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const range = max - min || 1;
  const step = (w - pad * 2) / (pts.length - 1);

  const coords = pts.map((v, i) => {
    const norm = (v - min) / range; // 0..1 (cru)
    const bom = lowerIsBetter ? 1 - norm : norm; // 1 = melhor
    const x = pad + i * step;
    const y = pad + (h - pad * 2) * (1 - bom);
    return [x, y] as const;
  });

  const d = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lastX, lastY] = coords[coords.length - 1];

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden className="overflow-visible">
      <path d={d} fill="none" stroke={cor} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r={3} fill={cor} />
    </svg>
  );
}

interface PainelProps {
  ordenado: CwvAnaliseResumo[];
}

/** Painel de cards: cada métrica num card com antes→agora, sparkline e veredito normalizado. */
function PainelResumo({ ordenado }: PainelProps) {
  const primeiro = ordenado[0];
  const ultimo = ordenado[ordenado.length - 1];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {METRICAS.map((m) => {
        const valores = ordenado.map((a) => a[m.campo] as number | null);
        const vAntes = primeiro[m.campo] as number | null;
        const vAgora = ultimo[m.campo] as number | null;
        const delta = calcularDelta(vAgora, vAntes, m.cfg);

        // Veredito normalizado: verde = melhorou sempre, independente da métrica.
        let veredito: { label: string; icon: typeof TrendingUp; cls: string };
        if (!delta || delta.improved === null) {
          veredito = { label: "Estável", icon: Minus, cls: "text-muted-foreground" };
        } else if (delta.improved) {
          veredito = { label: "Melhorou", icon: TrendingUp, cls: "text-success" };
        } else {
          veredito = { label: "Piorou", icon: TrendingDown, cls: "text-destructive" };
        }
        const Icon = veredito.icon;
        const corSpark =
          veredito.cls === "text-success"
            ? "#16a34a"
            : veredito.cls === "text-destructive"
            ? "#dc2626"
            : "#94a3b8";

        return (
          <div
            key={m.id}
            className="rounded-xl border bg-card p-4 flex flex-col gap-3"
            title={tooltipThresholds(m.label, m.cfg)}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground">{m.label}</span>
              <span className={cn("inline-flex items-center gap-1 text-xs font-semibold", veredito.cls)}>
                <Icon className="h-3.5 w-3.5" />
                {veredito.label}
                {delta && delta.improved !== null && (
                  <span className="tabular-nums font-medium">· {delta.text.replace(/^[+-]/, "")}</span>
                )}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex flex-col">
                <span className="text-sm font-medium tabular-nums text-muted-foreground">{m.formatter(vAntes)}</span>
                <span className="text-[10px] text-muted-foreground">antes</span>
              </div>
              <div className="flex-1 px-1">
                <Sparkline valores={valores} cor={corSpark} lowerIsBetter={m.cfg.lowerIsBetter} />
              </div>
              <div className="flex flex-col items-end">
                <span className="text-lg font-bold tabular-nums">{m.formatter(vAgora)}</span>
                <span className="text-[10px] text-muted-foreground">agora</span>
              </div>
            </div>

            <ChipClassificacao value={vAgora} cfg={m.cfg} />
          </div>
        );
      })}
    </div>
  );
}

export function EvolucaoChart({ historico }: EvolucaoChartProps) {
  const [tab, setTab] = useState<MetricaDef["id"]>("score");
  const [modo, setModo] = useState<"resumo" | "linha">("resumo");

  const ordenado = useMemo(
    () => [...historico].sort((a, b) => new Date(a.criado_em).getTime() - new Date(b.criado_em).getTime()),
    [historico],
  );

  const comHora = useMemo(() => {
    const dias = new Set(ordenado.map((a) => a.criado_em.slice(0, 10)));
    return dias.size < ordenado.length;
  }, [ordenado]);

  if (ordenado.length < 2) {
    return (
      <div className="rounded-xl border bg-surface-light p-6 text-center">
        <p className="text-sm text-muted-foreground">
          Faca outra analise para comecar a ver evolucao.
        </p>
      </div>
    );
  }

  const antes = ordenado[0];
  const agora = ordenado[ordenado.length - 1];

  const dados = ordenado.map((a) => ({
    data: formatarDataPonto(a.criado_em, comHora),
    score_performance: a.score_performance ?? 0,
    lcp_ms: a.lcp_ms ?? 0,
    cls: a.cls ?? 0,
    inp_ms: a.inp_ms ?? 0,
  }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">
          {ordenado.length} análises · {new Date(antes.criado_em).toLocaleDateString("pt-BR")} →{" "}
          {new Date(agora.criado_em).toLocaleDateString("pt-BR")}
        </div>
        <div className="inline-flex rounded-md border bg-card p-0.5 text-xs">
          <button
            type="button"
            onClick={() => setModo("resumo")}
            className={cn(
              "px-3 py-1 rounded transition-colors",
              modo === "resumo" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            Resumo
          </button>
          <button
            type="button"
            onClick={() => setModo("linha")}
            className={cn(
              "px-3 py-1 rounded transition-colors",
              modo === "linha" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            Linha do tempo
          </button>
        </div>
      </div>

      {modo === "resumo" ? (
        <PainelResumo ordenado={ordenado} />
      ) : (
        <Tabs value={tab} onValueChange={(v) => setTab(v as MetricaDef["id"])}>
          <TabsList className="mb-4">
            {METRICAS.map((m) => (
              <TabsTrigger key={m.id} value={m.id}>
                {m.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {METRICAS.map((m) => {
            const cfg = m.cfg;
            const vAntes = antes[m.campo] as number | null;
            const vAgora = agora[m.campo] as number | null;
            const delta = calcularDelta(vAgora, vAntes, cfg);
            const maxValor = Math.max(...dados.map((d) => d[m.campo] as number));
            const yMax = m.yMax ?? Math.max(maxValor * 1.1, cfg.poor * 1.2);
            const bandaBom = cfg.lowerIsBetter ? { y1: 0, y2: cfg.good } : { y1: cfg.good, y2: yMax };
            const bandaMid = cfg.lowerIsBetter
              ? { y1: cfg.good, y2: cfg.poor }
              : { y1: cfg.poor, y2: cfg.good };

            let veredito: { label: string; cls: string };
            if (!delta || delta.improved === null) {
              veredito = { label: "Estável", cls: "text-muted-foreground" };
            } else if (delta.improved) {
              veredito = { label: `Melhorou ${delta.text.replace(/^[+-]/, "")}`, cls: "text-success" };
            } else {
              veredito = { label: `Piorou ${delta.text.replace(/^[+-]/, "")}`, cls: "text-destructive" };
            }

            return (
              <TabsContent key={m.id} value={m.id}>
                <div className="flex items-center justify-between mb-2">
                  <p className={cn("text-sm font-semibold", veredito.cls)}>
                    {veredito.label}
                    <span className="ml-2 text-xs font-normal text-muted-foreground tabular-nums">
                      {m.formatter(vAntes)} → {m.formatter(vAgora)}
                    </span>
                  </p>
                </div>
                <p className="text-xs text-muted-foreground mb-2">{tooltipThresholds(m.label, cfg)}</p>
                <div className="h-[280px] w-full">
                  <ChartContainer config={{ [m.campo]: { label: m.label, color: m.cor } }} className="h-full w-full">
                    <LineChart data={dados} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                      <XAxis dataKey="data" tick={{ fontSize: 12 }} className="text-muted-foreground" />
                      <YAxis tick={{ fontSize: 12 }} className="text-muted-foreground" domain={[0, yMax]} />
                      <ReferenceArea
                        y1={bandaBom.y1}
                        y2={bandaBom.y2}
                        fill="var(--color-success, #16a34a)"
                        fillOpacity={0.12}
                        ifOverflow="extendDomain"
                        label={{ value: "Bom", position: "insideTopLeft", fontSize: 10, fill: "#16a34a" }}
                      />
                      <ReferenceArea
                        y1={bandaMid.y1}
                        y2={bandaMid.y2}
                        fill="#eab308"
                        fillOpacity={0.12}
                        ifOverflow="extendDomain"
                        label={{ value: "Precisa melhorar", position: "insideTopLeft", fontSize: 10, fill: "#a16207" }}
                      />
                      <ReferenceLine
                        y={cfg.good}
                        stroke="#16a34a"
                        strokeDasharray="4 4"
                        strokeOpacity={0.5}
                      />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Line
                        type="monotone"
                        dataKey={m.campo}
                        stroke={m.cor}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                      />
                    </LineChart>
                  </ChartContainer>
                </div>
              </TabsContent>
            );
          })}
        </Tabs>
      )}
    </div>
  );
}

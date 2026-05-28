"use client";

import { useMemo, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { ArrowRight } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceArea } from "recharts";
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

interface ComparativoProps {
  antes: CwvAnaliseResumo;
  agora: CwvAnaliseResumo;
}

function AntesAgora({ antes, agora }: ComparativoProps) {
  const linhas = METRICAS.map((m) => {
    const vAntes = antes[m.campo] as number | null;
    const vAgora = agora[m.campo] as number | null;
    const delta = calcularDelta(vAgora, vAntes, m.cfg);
    return { ...m, vAntes, vAgora, delta };
  });

  const dataAntes = new Date(antes.criado_em).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  const dataAgora = new Date(agora.criado_em).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-4 text-xs text-muted-foreground px-1">
        <div>
          <span className="font-medium text-foreground">Antes</span> · {dataAntes}
        </div>
        <div className="text-right md:text-left">
          <span className="font-medium text-foreground">Agora</span> · {dataAgora}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {linhas.map((l) => (
          <div
            key={l.id}
            className="rounded-xl border bg-card p-3 flex flex-col gap-2"
            title={tooltipThresholds(l.label, l.cfg)}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{l.label}</span>
              {l.delta && (
                <span className={cn("text-xs font-medium tabular-nums", l.delta.color)}>
                  {l.delta.text}
                  {l.delta.improved === true && " ▲"}
                  {l.delta.improved === false && " ▼"}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <div className="flex-1 flex flex-col items-center gap-1">
                <span className="text-lg font-semibold tabular-nums">{l.formatter(l.vAntes)}</span>
                <ChipClassificacao value={l.vAntes} cfg={l.cfg} />
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="flex-1 flex flex-col items-center gap-1">
                <span className="text-lg font-semibold tabular-nums">{l.formatter(l.vAgora)}</span>
                <ChipClassificacao value={l.vAgora} cfg={l.cfg} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function EvolucaoChart({ historico }: EvolucaoChartProps) {
  const [tab, setTab] = useState<MetricaDef["id"]>("score");
  const [modo, setModo] = useState<"comparar" | "linha">("comparar");

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
            onClick={() => setModo("comparar")}
            className={cn(
              "px-3 py-1 rounded transition-colors",
              modo === "comparar" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            Antes × Agora
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

      {modo === "comparar" ? (
        <AntesAgora antes={antes} agora={agora} />
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
            const maxValor = Math.max(...dados.map((d) => d[m.campo] as number));
            const yMax = m.yMax ?? Math.max(maxValor * 1.1, cfg.poor * 1.2);
            const bandaBom = cfg.lowerIsBetter ? { y1: 0, y2: cfg.good } : { y1: cfg.good, y2: yMax };
            const bandaMid = cfg.lowerIsBetter
              ? { y1: cfg.good, y2: cfg.poor }
              : { y1: cfg.poor, y2: cfg.good };

            return (
              <TabsContent key={m.id} value={m.id}>
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
                        fillOpacity={0.1}
                        ifOverflow="extendDomain"
                      />
                      <ReferenceArea
                        y1={bandaMid.y1}
                        y2={bandaMid.y2}
                        fill="#eab308"
                        fillOpacity={0.1}
                        ifOverflow="extendDomain"
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

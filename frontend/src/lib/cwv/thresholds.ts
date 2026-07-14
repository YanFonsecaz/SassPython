export type Classificacao = "bom" | "precisa-melhorar" | "ruim";

export interface ThresholdConfig {
  good: number;
  poor: number;
  lowerIsBetter: boolean;
  unidade: "ms" | "score" | "cls";
  labelGood: string;
  labelMid: string;
  labelPoor: string;
}

export const THRESHOLDS: Record<"score" | "lcp" | "cls" | "inp" | "tbt", ThresholdConfig> = {
  score: {
    good: 90,
    poor: 50,
    lowerIsBetter: false,
    unidade: "score",
    labelGood: "≥ 90",
    labelMid: "50–89",
    labelPoor: "< 50",
  },
  lcp: {
    good: 2500,
    poor: 4000,
    lowerIsBetter: true,
    unidade: "ms",
    labelGood: "≤ 2,5s",
    labelMid: "2,5–4,0s",
    labelPoor: "> 4,0s",
  },
  cls: {
    good: 0.1,
    poor: 0.25,
    lowerIsBetter: true,
    unidade: "cls",
    labelGood: "≤ 0,10",
    labelMid: "0,10–0,25",
    labelPoor: "> 0,25",
  },
  inp: {
    good: 200,
    poor: 500,
    lowerIsBetter: true,
    unidade: "ms",
    labelGood: "≤ 200ms",
    labelMid: "200–500ms",
    labelPoor: "> 500ms",
  },
  tbt: {
    good: 200,
    poor: 600,
    lowerIsBetter: true,
    unidade: "ms",
    labelGood: "≤ 200ms",
    labelMid: "200–600ms",
    labelPoor: "> 600ms",
  },
};

export function classificarMetrica(value: number | null, cfg: ThresholdConfig): Classificacao | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  if (cfg.lowerIsBetter) {
    if (value <= cfg.good) return "bom";
    if (value >= cfg.poor) return "ruim";
    return "precisa-melhorar";
  }
  if (value >= cfg.good) return "bom";
  if (value <= cfg.poor) return "ruim";
  return "precisa-melhorar";
}

export function rotuloClassificacao(c: Classificacao | null): string {
  if (c === "bom") return "Bom";
  if (c === "precisa-melhorar") return "Precisa melhorar";
  if (c === "ruim") return "Ruim";
  return "Sem dados";
}

export function corClassificacao(c: Classificacao | null): {
  text: string;
  bg: string;
  dot: string;
} {
  if (c === "bom") return { text: "text-success", bg: "bg-success/10", dot: "bg-success" };
  if (c === "precisa-melhorar") return { text: "text-yellow-600", bg: "bg-yellow-500/10", dot: "bg-yellow-500" };
  if (c === "ruim") return { text: "text-destructive", bg: "bg-destructive/10", dot: "bg-destructive" };
  return { text: "text-muted-foreground", bg: "bg-muted/40", dot: "bg-muted-foreground" };
}

export function tooltipThresholds(label: string, cfg: ThresholdConfig): string {
  return `${label} — Bom ${cfg.labelGood} · Precisa melhorar ${cfg.labelMid} · Ruim ${cfg.labelPoor}`;
}

export function formatMs(ms: number | null): string {
  if (ms === null || ms === undefined) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1).replace(".", ",")}s`;
  return `${Math.round(ms)}ms`;
}

export function formatCls(cls: number | null): string {
  if (cls === null || cls === undefined) return "—";
  return cls.toFixed(3).replace(".", ",");
}

export interface Delta {
  text: string;
  color: string;
  improved: boolean | null;
}

export function calcularDelta(
  atual: number | null,
  anterior: number | null,
  cfg: ThresholdConfig,
  thresholdPct = 0.05,
): Delta | null {
  if (atual === null || anterior === null) return null;
  const diff = atual - anterior;
  const pct = anterior !== 0 ? Math.abs(diff / anterior) : Math.abs(diff);
  if (pct < thresholdPct) return { text: "=", color: "text-muted-foreground", improved: null };
  const improved = cfg.lowerIsBetter ? diff < 0 : diff > 0;
  const color = improved ? "text-success" : "text-destructive";
  if (cfg.unidade === "ms") {
    const abs = Math.abs(diff);
    const val = abs >= 1000 ? `${(abs / 1000).toFixed(1).replace(".", ",")}s` : `${Math.round(abs)}ms`;
    return { text: `${diff < 0 ? "-" : "+"}${val}`, color, improved };
  }
  if (cfg.unidade === "cls") {
    return { text: `${diff > 0 ? "+" : ""}${diff.toFixed(3).replace(".", ",")}`, color, improved };
  }
  return { text: `${diff > 0 ? "+" : ""}${Math.round(diff)}`, color, improved };
}

// --- SPEC_CWV_Estimador_Esforco -------------------------------------------

export type Esforco = "baixo" | "medio" | "alto";

export function corEsforco(e: Esforco | null | undefined): { text: string; bg: string } {
  if (e === "baixo") return { text: "text-success", bg: "bg-success/10 border-success/30" };
  if (e === "medio") return { text: "text-yellow-600", bg: "bg-yellow-500/10 border-yellow-500/30" };
  if (e === "alto") return { text: "text-destructive", bg: "bg-destructive/10 border-destructive/30" };
  return { text: "text-muted-foreground", bg: "bg-muted/40 border-border" };
}

export function rotuloEsforco(e: Esforco | null | undefined): string {
  if (e === "baixo") return "Baixo";
  if (e === "medio") return "Médio";
  if (e === "alto") return "Alto";
  return "—";
}

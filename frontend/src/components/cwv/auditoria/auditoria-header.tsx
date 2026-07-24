"use client";

// Header fixo da auditoria: fase + donuts compactos + delta (SPEC_CWV_Auditoria_UI_V2 §3.1).

import { Badge } from "@/components/ui/badge";
import { HealthDonut } from "./health-donut";
import type { FaseAuditoria } from "@/lib/api/cwv";

export const FASE_LABELS: Record<FaseAuditoria, string> = {
  before: "Before (auditoria inicial)",
  aguardando_implementacao: "Aguardando implementação",
  after: "After (re-auditoria)",
  concluida: "Concluída",
};

export const FASE_CORES: Record<FaseAuditoria, string> = {
  before: "border-blue-400 text-blue-700 bg-blue-50",
  aguardando_implementacao: "border-yellow-400 text-yellow-700 bg-yellow-50",
  after: "border-purple-400 text-purple-700 bg-purple-50",
  concluida: "border-success/30 text-success bg-success/10",
};

interface Props {
  titulo: string;
  fase: FaseAuditoria;
  healthBefore: number | null;
  healthAfter: number | null;
  nPassBefore: number;
  nFailBefore: number;
  nPassAfter: number | null;
  nFailAfter: number | null;
  criadoEm: string;
}

// % aprovado no mesmo critério do HealthDonut (pass / (pass+fail), arredondado).
function pctAprovado(pass: number | null, fail: number | null): number | null {
  if (pass === null || fail === null) return null;
  const total = pass + fail;
  if (total === 0) return null;
  return Math.round((pass / total) * 100);
}

export function AuditoriaHeader(p: Props) {
  // Delta deriva da MESMA razão exibida nos donuts (não do health_score, que usa
  // outro denominador) — senão os dois números se contradizem lado a lado.
  const pctBefore = pctAprovado(p.nPassBefore, p.nFailBefore);
  const pctAfter = pctAprovado(p.nPassAfter, p.nFailAfter);
  const delta = pctBefore !== null && pctAfter !== null ? pctAfter - pctBefore : null;
  return (
    <div className="glass-card rounded-2xl p-5">
      <div className="flex items-center justify-between gap-3">
        <Badge variant="outline" className={FASE_CORES[p.fase]}>
          {FASE_LABELS[p.fase]}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {new Date(p.criadoEm).toLocaleDateString("pt-BR")}
        </span>
      </div>
      <h1 className="mt-2 text-lg font-semibold">{p.titulo}</h1>
      <div className="mt-3 flex items-center justify-center gap-8">
        <HealthDonut pass={p.nPassBefore} fail={p.nFailBefore} label="Before" size={90} />
        <div className="text-center">
          {delta !== null ? (
            <p className={`text-lg font-bold ${delta >= 0 ? "text-success" : "text-destructive"}`}>
              {delta >= 0 ? "+" : ""}
              {delta} p.p. {delta >= 0 ? "↑" : "↓"}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">Δ após re-auditoria</p>
          )}
        </div>
        <HealthDonut pass={p.nPassAfter} fail={p.nFailAfter} label="After" size={90} hint="pendente" />
      </div>
    </div>
  );
}

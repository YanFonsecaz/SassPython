"use client";

// Evolução do health score entre auditorias do cliente
// (SPEC_CWV_Auditoria_UI_V2 §3.1 — dados de listarAuditoriasCwv, zero backend novo).

import type { AuditoriaResumo } from "@/lib/api/cwv";

interface Props {
  auditorias: AuditoriaResumo[];
  auditoriaAtualId: string;
}

function healthDaAuditoria(a: AuditoriaResumo): number | null {
  return a.health_score_after ?? a.health_score_before;
}

export function HealthEvolucaoChart({ auditorias, auditoriaAtualId }: Props) {
  const pontos = auditorias
    .map((a) => ({ a, v: healthDaAuditoria(a) }))
    .filter((p): p is { a: AuditoriaResumo; v: number } => p.v !== null)
    .sort((p1, p2) => p1.a.criado_em.localeCompare(p2.a.criado_em));

  if (pontos.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border bg-surface-light">
        <p className="text-xs text-muted-foreground">
          Primeira auditoria do cliente — a evolução aparece a partir da segunda.
        </p>
      </div>
    );
  }

  const w = 320;
  const h = 140;
  const pad = 22;
  const xs = (i: number) => pad + (i * (w - 2 * pad)) / (pontos.length - 1);
  const ys = (v: number) => h - pad - (v / 100) * (h - 2 * pad);
  const path = pontos.map((p, i) => `${i === 0 ? "M" : "L"}${xs(i)},${ys(p.v)}`).join(" ");

  return (
    <div className="rounded-xl border bg-surface-light p-3">
      <p className="mb-1 text-xs font-medium text-muted-foreground">Evolução do health score</p>
      <svg
        width="100%"
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Evolução do health score"
      >
        <line x1={pad} y1={ys(50)} x2={w - pad} y2={ys(50)} className="stroke-border" strokeDasharray="3 3" />
        <path d={path} fill="none" className="stroke-brand" strokeWidth={2} />
        <g data-testid="evolucao-pontos">
          {pontos.map((p, i) => (
            <g key={p.a.id}>
              <circle
                cx={xs(i)}
                cy={ys(p.v)}
                r={p.a.id === auditoriaAtualId ? 5 : 3.5}
                className={p.a.id === auditoriaAtualId ? "fill-brand" : "fill-brand/60"}
              />
              <text x={xs(i)} y={ys(p.v) - 8} textAnchor="middle" fontSize={10} className="fill-foreground">
                {p.v}
              </text>
              <text x={xs(i)} y={h - 6} textAnchor="middle" fontSize={9} className="fill-muted-foreground">
                {new Date(p.a.criado_em).toLocaleDateString("pt-BR", { month: "short", year: "2-digit" })}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}

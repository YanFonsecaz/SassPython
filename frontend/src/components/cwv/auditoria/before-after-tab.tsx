"use client";

// Aba Before/After por URL (SPEC_CWV_Auditoria_UI_V2 §3.1 + Comparativo API).

import { useEffect, useState } from "react";
import { ArrowDownIcon, ArrowUpIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  buscarComparativoAuditoria,
  type ComparativoPar,
  type ComparativoMetricas,
  type FaseAuditoria,
} from "@/lib/api/cwv";
import { mensagemErroAmigavel } from "@/lib/api";

interface Props {
  auditoriaId: string;
  fase: FaseAuditoria;
  onReauditar?: () => void;
}

// menorMelhor: LCP/CLS/INP/TBT melhoram quando caem; score melhora quando sobe.
const METRICAS: {
  chave: keyof ComparativoMetricas;
  rotulo: string;
  menorMelhor: boolean;
  fmt: (v: number) => string;
  minDelta: number;
  fmtDelta: (v: number) => string;
}[] = [
  { chave: "score_performance", rotulo: "Score", menorMelhor: false, fmt: (v) => String(v),
    minDelta: 1, fmtDelta: (v) => String(Math.round(v)) },
  { chave: "lcp_ms", rotulo: "LCP", menorMelhor: true, fmt: (v) => `${(v / 1000).toFixed(1)}s`,
    minDelta: 100, fmtDelta: (v) => (v < 1000 ? `${Math.round(v)}ms` : `${(v / 1000).toFixed(1)}s`) },
  { chave: "cls", rotulo: "CLS", menorMelhor: true, fmt: (v) => v.toFixed(2),
    minDelta: 0.01, fmtDelta: (v) => v.toFixed(2) },
  { chave: "inp_ms", rotulo: "INP", menorMelhor: true, fmt: (v) => `${Math.round(v)}ms`,
    minDelta: 10, fmtDelta: (v) => `${Math.round(v)}ms` },
  { chave: "tbt_ms", rotulo: "TBT", menorMelhor: true, fmt: (v) => `${Math.round(v)}ms`,
    minDelta: 10, fmtDelta: (v) => `${Math.round(v)}ms` },
];

export function BeforeAfterTab({ auditoriaId, fase, onReauditar }: Props) {
  const [pares, setPares] = useState<ComparativoPar[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    buscarComparativoAuditoria(auditoriaId)
      .then((r) => setPares(r.pares))
      .catch((e) => setErro(mensagemErroAmigavel(e)));
  }, [auditoriaId]);

  if (erro) return <p className="text-sm text-destructive">{erro}</p>;
  if (!pares) return <div className="h-32 animate-pulse rounded-xl bg-muted/50" />;

  const semAfter = pares.every((p) => p.after === null);

  return (
    <div className="space-y-4">
      {semAfter && (
        <div className="rounded-xl border border-yellow-400/40 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
          Baseline registrado — comparação disponível após a re-auditoria (aguardando re-auditoria).
          {onReauditar && (fase === "aguardando_implementacao" || fase === "after") && (
            <button
              className="ml-2 rounded bg-purple-600 px-3 py-1 text-xs font-medium text-white hover:bg-purple-700"
              onClick={onReauditar}
            >
              Iniciar re-auditoria
            </button>
          )}
        </div>
      )}
      {pares.map((p) => (
        <CardPar key={`${p.url_canonica}-${p.estrategia}`} par={p} />
      ))}
    </div>
  );
}

function CardPar({ par }: { par: ComparativoPar }) {
  const [expandido, setExpandido] = useState(false);
  return (
    <div className="glass-card space-y-3 rounded-2xl p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-medium" title={par.url_canonica}>
          {par.url_canonica}
        </p>
        <Badge variant="outline" className="text-[10px]">
          {par.estrategia}
        </Badge>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase text-muted-foreground">
            <th className="py-1">Métrica</th>
            <th>Before</th>
            <th>After</th>
            <th>Δ</th>
          </tr>
        </thead>
        <tbody>
          {METRICAS.map(({ chave, rotulo, menorMelhor, fmt, minDelta, fmtDelta }) => {
            const antes = par.before[chave] as number | null;
            const depois = par.after ? (par.after[chave] as number | null) : null;
            const delta = antes !== null && depois !== null ? depois - antes : null;
            const melhorou = delta !== null && (menorMelhor ? delta < 0 : delta > 0);
            return (
              <tr key={chave} className="border-t">
                <td className="py-1.5 text-muted-foreground">{rotulo}</td>
                <td>{antes !== null ? fmt(antes) : "—"}</td>
                <td>{depois !== null ? fmt(depois) : "—"}</td>
                <td>
                  {delta !== null && Math.abs(delta) >= minDelta && (
                    <span
                      className={`inline-flex items-center gap-0.5 text-xs ${melhorou ? "text-success" : "text-destructive"}`}
                    >
                      {melhorou ? <ArrowUpIcon className="size-3" /> : <ArrowDownIcon className="size-3" />}
                      {fmtDelta(Math.abs(delta))}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {par.problemas && (
        <div className="space-y-1">
          <button
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setExpandido(!expandido)}
          >
            <span className="text-success">✔ {par.problemas.resolvidos} resolvidos</span>
            {" · "}
            <span>⚑ {par.problemas.persistentes} persistentes</span>
            {" · "}
            <span className="text-destructive">✖ {par.problemas.novos} novos</span>
          </button>
          {expandido && (
            <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
              <div>
                <p className="font-medium text-success">Resolvidos</p>
                <ul className="list-inside list-disc">
                  {par.problemas.titulos_resolvidos.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="font-medium text-destructive">Novos</p>
                <ul className="list-inside list-disc">
                  {par.problemas.titulos_novos.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

// Aba Visão Geral (SPEC_CWV_Auditoria_UI_V2 §3.1): donuts grandes + evolução + top-5 consolidados.

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { HealthDonut } from "./health-donut";
import { HealthEvolucaoChart } from "./health-evolucao-chart";
import {
  listarAuditoriasCwv,
  type AuditoriaResposta,
  type AuditoriaResumo,
  type ProblemaConsolidadoResposta,
} from "@/lib/api/cwv";

interface Props {
  auditoria: AuditoriaResposta;
  consolidados: ProblemaConsolidadoResposta[] | null;
  onIrParaChecklist: () => void;
}

export function VisaoGeralTab({ auditoria, consolidados, onIrParaChecklist }: Props) {
  const [historico, setHistorico] = useState<AuditoriaResumo[]>([]);

  useEffect(() => {
    listarAuditoriasCwv(auditoria.cliente_id)
      .then((r) => setHistorico(r.auditorias))
      .catch(() => {});
  }, [auditoria.cliente_id]);

  const passAfter = auditoria.checklist.filter((i) => i.status_after === "pass").length;
  const failAfter = auditoria.checklist.filter((i) => i.status_after === "fail").length;
  const temAfter = auditoria.health_score_after !== null;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="glass-card flex items-center justify-around rounded-2xl p-5">
          <HealthDonut pass={auditoria.n_pass_before} fail={auditoria.n_fail_before} label="Before" />
          <HealthDonut
            pass={temAfter ? passAfter : null}
            fail={temAfter ? failAfter : null}
            label="After"
            hint="aguardando re-auditoria"
          />
        </div>
        <HealthEvolucaoChart auditorias={historico} auditoriaAtualId={auditoria.id} />
      </div>

      {consolidados && consolidados.length > 0 && (
        <div className="glass-card space-y-2 rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Top problemas consolidados</h2>
            <button className="text-xs text-brand hover:underline" onClick={onIrParaChecklist}>
              Ver checklist completo →
            </button>
          </div>
          {consolidados.slice(0, 5).map((c) => (
            <div key={c.id} className="rounded-lg border bg-surface-light px-4 py-2.5">
              <div className="flex items-start justify-between gap-2">
                <p className="flex-1 text-sm font-medium">{c.titulo}</p>
                <div className="flex shrink-0 gap-1">
                  <Badge variant="outline" className="text-[9px]">
                    Sev {c.severidade}
                  </Badge>
                  {c.esforco && (
                    <Badge variant="outline" className="text-[9px]">
                      {c.esforco}
                    </Badge>
                  )}
                </div>
              </div>
              {c.causa_raiz && <p className="mt-0.5 text-xs text-muted-foreground">{c.causa_raiz}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

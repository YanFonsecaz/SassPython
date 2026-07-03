"use client";

import { ChevronRightIcon, InfoIcon } from "lucide-react";
import type { FunilInlinks } from "@/types";

interface Props {
  funil?: FunilInlinks | null;
  modo: "receber" | "distribuir";
}

interface Etapa {
  label: string;
  valor: number | undefined;
}

/** Strip compacto do funil: onde cada candidata parou, com motivos agregados. */
export function InlinksFunilStrip({ funil, modo }: Props) {
  if (!funil) return null;

  const etapas: Etapa[] =
    modo === "receber"
      ? [
          { label: "solicitadas", valor: funil.n_solicitadas },
          { label: "lidas", valor: funil.n_scrape_ok },
          { label: "relacionadas", valor: funil.n_pos_piso_ruido },
          { label: "avaliadas pela IA", valor: funil.n_enviadas_juiz },
          { label: "aplicadas", valor: funil.n_aplicadas ?? funil.n_decisao_aplicar },
        ]
      : [
          { label: "solicitadas", valor: funil.n_solicitadas },
          { label: "lidas", valor: funil.n_scrape_ok },
          { label: "viáveis", valor: funil.n_viaveis },
          { label: "avaliadas pela IA", valor: funil.n_enviadas_juiz },
          { label: "aplicadas", valor: funil.n_aplicadas ?? funil.n_decisao_aplicar },
        ];

  const visiveis = etapas.filter((e) => typeof e.valor === "number");
  if (visiveis.length < 2) return null;

  const sufixos: string[] = [];
  if (funil.n_decisao_sugerir) sufixos.push(`${funil.n_decisao_sugerir} sugestão${funil.n_decisao_sugerir === 1 ? "" : "ões"}`);
  const descartadas = (funil.n_decisao_descartar ?? 0) + (funil.n_sem_match ?? 0);
  if (descartadas) sufixos.push(`${descartadas} descartada${descartadas === 1 ? "" : "s"}`);
  if (funil.n_rejeitados_revisor) sufixos.push(`${funil.n_rejeitados_revisor} rejeitada${funil.n_rejeitados_revisor === 1 ? "" : "s"} na revisão`);
  if (funil.n_scrape_falhas) sufixos.push(`${funil.n_scrape_falhas} falha${funil.n_scrape_falhas === 1 ? "" : "s"} de leitura`);

  const motivos = Object.entries(funil.motivos ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <div className="rounded-xl border bg-surface-light p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-1 text-xs">
        {visiveis.map((e, i) => (
          <span key={e.label} className="inline-flex items-center gap-1">
            {i > 0 && <ChevronRightIcon className="size-3 text-muted-foreground/50" />}
            <span className={i === visiveis.length - 1 ? "font-semibold text-foreground" : "text-muted-foreground"}>
              {e.valor} {e.label}
            </span>
          </span>
        ))}
        {sufixos.length > 0 && (
          <span className="text-muted-foreground"> · {sufixos.join(" · ")}</span>
        )}
      </div>
      {motivos.length > 0 && (
        <div className="space-y-0.5 border-t border-dashed pt-2">
          <div className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <InfoIcon className="size-3" />
            Por que candidatas não viraram link
          </div>
          <ul className="text-xs text-muted-foreground space-y-0.5">
            {motivos.slice(0, 5).map(([motivo, n]) => (
              <li key={motivo}>
                {n}× {motivo}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

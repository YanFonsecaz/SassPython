"use client";

import { InfoIcon, SparklesIcon, ZapIcon, TargetIcon } from "lucide-react";
import type { EstadoAnalise } from "@/lib/cwv-estado";

interface Props {
  estado: EstadoAnalise;
  score: number | null;
}

export function CwvEstadoBanner({ estado, score }: Props) {
  if (estado.tipo === "normal" || estado.tipo === "falhou") return null;

  if (estado.tipo === "rasa") {
    return (
      <div className="rounded-xl border border-blue-200 bg-blue-50 dark:bg-blue-950/20 dark:border-blue-900 p-5">
        <div className="flex items-start gap-3">
          <InfoIcon className="size-5 text-blue-600 mt-0.5 shrink-0" />
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Analise rasa</h3>
            <p className="text-sm text-muted-foreground">
              Este site e muito simples para gerarmos diagnostico util de Core Web Vitals:
            </p>
            <ul className="text-sm text-muted-foreground space-y-0.5 pl-2">
              {estado.motivos.map((m, i) => <li key={i}>- {m}</li>)}
            </ul>
            <p className="text-xs text-muted-foreground pt-1">
              Use uma URL de pagina real (com conteudo, imagens, JS) para analise significativa.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (estado.tipo === "otimizado") {
    return (
      <div className="rounded-xl border border-green-200 bg-green-50 dark:bg-green-950/20 dark:border-green-900 p-5">
        <div className="flex items-start gap-3">
          <SparklesIcon className="size-5 text-green-600 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <h3 className="text-sm font-semibold">Site otimizado</h3>
            <p className="text-sm text-muted-foreground">
              Suas metricas estao dentro dos thresholds recomendados pelo Google. Continue monitorando.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (estado.tipo === "quase_pronto") {
    return (
      <div className="rounded-xl border border-yellow-200 bg-yellow-50 dark:bg-yellow-950/20 dark:border-yellow-900 p-5">
        <div className="flex items-start gap-3">
          <ZapIcon className="size-5 text-yellow-600 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <h3 className="text-sm font-semibold">Site quase pronto</h3>
            <p className="text-sm text-muted-foreground">
              {estado.nProblemas} ajuste{estado.nProblemas !== 1 ? "s" : ""} pequeno{estado.nProblemas !== 1 ? "s" : ""}
              {" "}pode{estado.nProblemas !== 1 ? "m" : ""} subir seu score
              {score != null ? ` de ${score}` : ""} para ~95.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (estado.tipo === "muitos_problemas") {
    return (
      <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <div className="flex items-start gap-3">
          <TargetIcon className="size-5 text-destructive mt-0.5 shrink-0" />
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Por onde comecar</h3>
            <p className="text-sm text-muted-foreground">
              Encontramos {estado.nProblemas} problemas ({estado.nCriticos} criticos). Foque nestes 3 primeiro:
            </p>
            <ol className="text-sm space-y-1 pt-1 pl-4 list-decimal">
              {estado.top3.map((titulo) => <li key={titulo}>{titulo}</li>)}
            </ol>
          </div>
        </div>
      </div>
    );
  }

  return null;
}

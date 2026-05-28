"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ComparacaoResposta, MetricaComparada } from "@/lib/api/cwv";

interface ComparadorComponentProps {
  comparacao: ComparacaoResposta | null;
}

function formatDelta(delta: number, melhorou: boolean | null) {
  if (melhorou === null) return null;
  const isPositive = delta > 0;
  const abs = Math.abs(delta);
  
  // Formatar delta de acordo com a métrica
  if (delta < 1 && delta > -1) {
    return (isPositive ? '+' : '') + delta.toFixed(2);
  } else if (delta > 1000) {
    return (isPositive ? '+' : '') + (abs / 1000).toFixed(1) + 's';
  } else {
    return (isPositive ? '+' : '') + Math.round(abs);
  }
}

export function ComparadorComponent({ comparacao }: ComparadorComponentProps) {
  if (!comparacao || !comparacao.analise_anterior_id) {
    return null;
  }

  const { dias_decorridos, metricas, problemas_resolvidos, problemas_novos, problemas_persistentes } = comparacao;

  return (
    <div className="mt-6 border-t border-border pt-6">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">
        Comparação com análise anterior ({dias_decorridos} dias atrás)
      </h3>

      <div className="space-y-4">
        {/* Métricas que melhoraram */}
        {Object.entries(metricas).filter(([_, m]) => m.melhorou === true).length > 0 && (
          <div>
            <h4 className="flex items-center gap-1 text-sm font-medium text-green-600 mb-2">
              <span className="w-2 h-2 rounded-full bg-green-600" />
              Melhoraram
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {Object.entries(metricas)
                .filter(([_, m]) => m.melhorou === true)
                .map(([metrica, m]) => (
                  <div key={metrica} className="flex items-center justify-between p-2 rounded-lg bg-green-50/50">
                    <span className="text-sm font-medium">{metrica.toUpperCase()}</span>
                    <div className="text-right">
                      <span className="text-xs text-muted-foreground line-through">
                        {formatDelta(m.antes, true)}
                      </span>
                      <span className="mx-1 text-xs text-muted-foreground">→</span>
                      <span className="text-xs font-bold text-green-700">
                        {formatDelta(m.depois, true)}
                      </span>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Métricas que pioraram */}
        {Object.entries(metricas).filter(([_, m]) => m.melhorou === false).length > 0 && (
          <div>
            <h4 className="flex items-center gap-1 text-sm font-medium text-red-600 mb-2">
              <span className="w-2 h-2 rounded-full bg-red-600" />
              Pioraram
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {Object.entries(metricas)
                .filter(([_, m]) => m.melhorou === false)
                .map(([metrica, m]) => (
                  <div key={metrica} className="flex items-center justify-between p-2 rounded-lg bg-red-50/50">
                    <span className="text-sm font-medium">{metrica.toUpperCase()}</span>
                    <div className="text-right">
                      <span className="text-xs text-muted-foreground line-through">
                        {formatDelta(m.antes, false)}
                      </span>
                      <span className="mx-1 text-xs text-muted-foreground">→</span>
                      <span className="text-xs font-bold text-red-700">
                        {formatDelta(m.depois, false)}
                      </span>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Problemas resolvidos */}
        {problemas_resolvidos.length > 0 && (
          <div>
            <h4 className="flex items-center gap-1 text-sm font-medium text-green-600 mb-2">
              <span className="w-2 h-2 rounded-full bg-green-600" />
              Problemas resolvidos ({problemas_resolvidos.length})
            </h4>
            <div className="space-y-1">
              {problemas_resolvidos.map((problema, index) => (
                <div key={index} className="flex items-center gap-2 p-2 rounded-lg bg-green-50/50">
                  <span className="text-xs font-bold text-green-700">✓</span>
                  <span className="text-sm">{problema.titulo}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Novos problemas */}
        {problemas_novos.length > 0 && (
          <div>
            <h4 className="flex items-center gap-1 text-sm font-medium text-red-600 mb-2">
              <span className="w-2 h-2 rounded-full bg-red-600" />
              Novos problemas ({problemas_novos.length})
            </h4>
            <div className="space-y-1">
              {problemas_novos.map((problema, index) => (
                <div key={index} className="flex items-center gap-2 p-2 rounded-lg bg-red-50/50">
                  <span className="text-xs font-bold text-red-700">!</span>
                  <span className="text-sm">{problema.titulo}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Problemas persistentes */}
        {problemas_persistentes.length > 0 && (
          <div>
            <h4 className="flex items-center gap-1 text-sm font-medium text-yellow-600 mb-2">
              <span className="w-2 h-2 rounded-full bg-yellow-600" />
              Problemas persistentes ({problemas_persistentes.length})
            </h4>
            <div className="space-y-1">
              {problemas_persistentes.map((problema, index) => (
                <div key={index} className="flex items-center gap-2 p-2 rounded-lg bg-yellow-50/50">
                  <span className="text-xs font-bold text-yellow-700">≈</span>
                  <span className="text-sm">{problema.titulo}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {Object.entries(metricas).filter(([_, m]) => m.melhorou === true).length === 0 &&
         Object.entries(metricas).filter(([_, m]) => m.melhorou === false).length === 0 &&
         problemas_resolvidos.length === 0 &&
         problemas_novos.length === 0 &&
         problemas_persistentes.length === 0 && (
          <div className="text-center py-4 text-sm text-muted-foreground">
            Nenhuma mudança significativa detectada
          </div>
        )}
      </div>
    </div>
  );
}
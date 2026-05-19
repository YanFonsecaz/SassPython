"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import type { VersaoArtigo } from "@/types";

interface ComparadorVersoesProps {
  versoes: VersaoArtigo[];
  conteudosMap?: Record<number, string>;
}

function scoreColor(score: number | null): "default" | "secondary" | "destructive" {
  if (score === null) return "secondary";
  if (score >= 80) return "default";
  if (score >= 60) return "secondary";
  return "destructive";
}

function origemLabel(origem: string): string {
  switch (origem) {
    case "redator_inicial":
      return "Inicial";
    case "revisao_auto":
      return "Revisao auto";
    case "feedback_humano":
      return "Feedback";
    default:
      return origem;
  }
}

export function ComparadorVersoes({ versoes, conteudosMap }: ComparadorVersoesProps) {
  const [esquerda, setEsquerda] = useState(versoes.length - 2 >= 0 ? versoes.length - 2 : 0);
  const [direita, setDireita] = useState(versoes.length - 1);

  const versaoEsquerda = versoes[esquerda];
  const versaoDireita = versoes[direita];

  if (!versaoEsquerda || !versaoDireita) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div className="flex-1 space-y-2">
          <label className="text-sm font-medium">Versao esquerda</label>
          <select
            className="flex h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm"
            value={esquerda}
            onChange={(e) => setEsquerda(Number(e.target.value))}
          >
            {versoes.map((v) => (
              <option key={v.versao} value={versoes.indexOf(v)}>
                v{v.versao} — {v.titulo}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 space-y-2">
          <label className="text-sm font-medium">Versao direita</label>
          <select
            className="flex h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm"
            value={direita}
            onChange={(e) => setDireita(Number(e.target.value))}
          >
            {versoes.map((v) => (
              <option key={v.versao} value={versoes.indexOf(v)}>
                v{v.versao} — {v.titulo}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium">v{versaoEsquerda.versao}</h4>
            <Badge variant="outline" className="text-xs">
              {origemLabel(versaoEsquerda.origem)}
            </Badge>
          </div>
          <p className="text-sm font-medium">{versaoEsquerda.titulo}</p>
          <div className="flex gap-2 text-xs text-muted-foreground">
            <span>{versaoEsquerda.contagem_palavras} palavras</span>
            {versaoEsquerda.score_revisao !== null && (
              <Badge variant={scoreColor(versaoEsquerda.score_revisao)} className="text-xs">
                {versaoEsquerda.score_revisao}
              </Badge>
            )}
          </div>
          {versaoEsquerda.feedback_recebido && (
            <div className="rounded bg-muted/50 p-2">
              <p className="text-xs font-medium text-muted-foreground">Feedback:</p>
              <p className="text-xs">{versaoEsquerda.feedback_recebido}</p>
            </div>
          )}
          {conteudosMap?.[versaoEsquerda.versao] && (
            <pre className="whitespace-pre-wrap text-xs leading-relaxed max-h-96 overflow-y-auto">
              {conteudosMap[versaoEsquerda.versao]}
            </pre>
          )}
        </div>

        <div className="rounded-lg border p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium">v{versaoDireita.versao}</h4>
            <Badge variant="outline" className="text-xs">
              {origemLabel(versaoDireita.origem)}
            </Badge>
          </div>
          <p className="text-sm font-medium">{versaoDireita.titulo}</p>
          <div className="flex gap-2 text-xs text-muted-foreground">
            <span>{versaoDireita.contagem_palavras} palavras</span>
            {versaoDireita.score_revisao !== null && (
              <Badge variant={scoreColor(versaoDireita.score_revisao)} className="text-xs">
                {versaoDireita.score_revisao}
              </Badge>
            )}
          </div>
          {versaoDireita.feedback_recebido && (
            <div className="rounded bg-muted/50 p-2">
              <p className="text-xs font-medium text-muted-foreground">Feedback:</p>
              <p className="text-xs">{versaoDireita.feedback_recebido}</p>
            </div>
          )}
          {conteudosMap?.[versaoDireita.versao] && (
            <pre className="whitespace-pre-wrap text-xs leading-relaxed max-h-96 overflow-y-auto">
              {conteudosMap[versaoDireita.versao]}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

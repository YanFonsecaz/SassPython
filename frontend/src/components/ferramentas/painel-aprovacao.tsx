"use client";

import { useState, useEffect } from "react";
import { 
  Loader2Icon, 
  EyeIcon, 
  CircleCheckIcon, 
  AlertTriangleIcon, 
  MessageSquareIcon, 
  SendIcon 
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { VersaoArtigo } from "@/types";

interface PainelAprovacaoProps {
  versaoAtual: VersaoArtigo | null;
  tentativasRevisao: number;
  tentativasFeedback: number;
  onAprovar: () => void;
  onReprovar: (feedback: string) => void;
  onCancelar: () => void;
  enviando: boolean;
}

function scoreColor(score: number | null): "default" | "secondary" | "destructive" {
  if (score === null) return "secondary";
  if (score >= 80) return "default";
  if (score >= 60) return "secondary";
  return "destructive";
}

export function PainelAprovacao({
  versaoAtual,
  tentativasRevisao,
  tentativasFeedback,
  onAprovar,
  onReprovar,
  onCancelar,
  enviando,
}: PainelAprovacaoProps) {
  const [feedback, setFeedback] = useState("");
  const [mostrarFeedback, setMostrarFeedback] = useState(false);
  const [aparecendo, setAparecendo] = useState(true);

  if (!versaoAtual) return null;

  // Animação de entrada
  useEffect(() => {
    if (aparecendo) {
      const timer = setTimeout(() => setAparecendo(false), 500);
      return () => clearTimeout(timer);
    }
  }, [aparecendo]);

return (
    <div className={cn("space-y-6", aparecendo && 'animate-slide-in-up')}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="size-10 rounded-full bg-brand/10 flex items-center justify-center">
            <EyeIcon className="size-5 text-brand animate-pulse-dot" />
          </div>
          <div>
            <h3 className="font-semibold text-lg">Revisão da Versão {versaoAtual.versao}</h3>
            <p className="text-sm text-muted-foreground">
              Seu feedback é essencial para o resultado final
            </p>
          </div>
          {versaoAtual.score_revisao !== null && (
            <Badge variant={scoreColor(versaoAtual.score_revisao)} className="text-sm">
              Score: {versaoAtual.score_revisao}
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground font-medium">
          {versaoAtual.contagem_palavras} palavras
        </p>
      </div>

      {/* Status cards */}
      <div className="grid gap-3 sm:grid-cols-2">
        {versaoAtual.origem && (
          <div className="rounded-lg border bg-surface-light p-3">
            <p className="text-xs font-medium text-muted-foreground mb-1">Origem</p>
            <p className="text-sm">
              {versaoAtual.origem === "redator_inicial"
                ? "Redação inicial"
                : versaoAtual.origem === "revisao_auto"
                  ? "Revisão automática"
                  : "Feedback humano"}
            </p>
          </div>
        )}

        {tentativasRevisao > 0 && (
          <div className="rounded-lg border bg-surface-light p-3">
            <p className="text-xs font-medium text-muted-foreground mb-1">Revisões automáticas</p>
            <p className="text-sm">
              {tentativasRevisao}/3 realizadas
            </p>
          </div>
        )}

        {tentativasFeedback > 0 && (
          <div className="rounded-lg border bg-surface-light p-3">
            <p className="text-xs font-medium text-muted-foreground mb-1">Rodadas de feedback</p>
            <p className="text-sm">
              {tentativasFeedback}/3 realizadas
            </p>
          </div>
        )}

        {versaoAtual.feedback_recebido && (
          <div className="rounded-lg border bg-yellow-50 border-yellow-200 p-3">
            <p className="text-xs font-medium text-yellow-800 mb-1">Feedback anterior</p>
            <p className="text-sm text-yellow-700">{versaoAtual.feedback_recebido}</p>
          </div>
        )}
      </div>

      {/* Action buttons */}
      {!mostrarFeedback ? (
        <div className="space-y-4">
          <div className="rounded-lg bg-green-50 border border-green-200 p-4">
            <p className="text-sm text-green-800 text-center">
              O artigo está pronto para sua aprovação ou feedback.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 justify-center">
            <Button 
              onClick={onAprovar} 
              disabled={enviando}
              className="gradient-bg border-0 hover:opacity-90 transition-opacity px-8"
            >
              {enviando ? (
                <>
                  <Loader2Icon className="size-4 animate-spin mr-2" />
                  Enviando...
                </>
              ) : (
                <>
                  <CircleCheckIcon className="size-4 mr-2" />
                  Aprovar e Continuar
                </>
              )}
            </Button>
            {tentativasFeedback < 3 && (
              <Button
                variant="outline"
                onClick={() => setMostrarFeedback(true)}
                disabled={enviando}
                className="px-8"
              >
                Solicitar Alterações
              </Button>
            )}
            <Button
              variant="destructive"
              onClick={onCancelar}
              disabled={enviando}
              className="px-8"
            >
              {enviando ? (
                <>
                  <Loader2Icon className="size-4 animate-spin mr-2" />
                  Enviando...
                </>
              ) : (
                <>
                  <AlertTriangleIcon className="size-4 mr-2" />
                  Cancelar Execução
                </>
              )}
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4 animate-slide-in-up">
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
            <p className="text-sm text-blue-800">
              <MessageSquareIcon className="size-4 inline mr-2" />
              Descreva as alterações que você gostaria de ver no artigo
            </p>
          </div>
          <Textarea
            placeholder="Descreva as alterações desejadas..."
            maxLength={2000}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={4}
            className="resize-none"
          />
          <div className="flex gap-3 justify-center">
            <Button
              onClick={() => onReprovar(feedback)}
              disabled={!feedback.trim() || enviando}
              className="gradient-bg border-0 hover:opacity-90 transition-opacity px-8"
            >
              {enviando ? (
                <>
                  <Loader2Icon className="size-4 animate-spin mr-2" />
                  Enviando...
                </>
              ) : (
                <>
                  <SendIcon className="size-4 mr-2" />
                  Enviar Feedback
                </>
              )}
            </Button>
            <Button
              variant="outline"
              onClick={() => setMostrarFeedback(false)}
              disabled={enviando}
              className="px-8"
            >
              Voltar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

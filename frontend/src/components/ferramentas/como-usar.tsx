"use client";

import { HelpCircleIcon, LightbulbIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { AJUDA_FERRAMENTAS } from "@/lib/ferramentas-ajuda";

interface ComoUsarProps {
  /** chave em AJUDA_FERRAMENTAS: "gerar-artigo" | "inlinks" | "core-web-vitals" | "parecer" */
  ferramenta: string;
  /** "botao" = ghost com rótulo (headers); "icone" = só o ícone (cards) */
  variant?: "botao" | "icone";
  className?: string;
}

export function ComoUsar({ ferramenta, variant = "botao", className }: ComoUsarProps) {
  const ajuda = AJUDA_FERRAMENTAS[ferramenta];
  if (!ajuda) return null;

  const trigger =
    variant === "icone" ? (
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={`Como usar: ${ajuda.titulo}`}
        title="Como usar"
        className={cn("text-muted-foreground hover:text-brand-dark", className)}
      />
    ) : (
      <Button
        variant="ghost"
        size="sm"
        aria-label="Como usar esta ferramenta"
        className={className}
      />
    );

  return (
    <Dialog>
      <DialogTrigger render={trigger}>
        <HelpCircleIcon className="size-4" />
        {variant === "botao" && <span className="ml-1">Como usar</span>}
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 pr-6">
            <HelpCircleIcon className="size-4 shrink-0 text-brand-dark" />
            Como usar — {ajuda.titulo}
          </DialogTitle>
          <DialogDescription className="leading-relaxed">{ajuda.paraQueServe}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Passo a passo
          </p>
          <ol className="space-y-2.5">
            {ajuda.passos.map((passo, i) => (
              <li key={i} className="flex gap-2.5 text-sm">
                <span className="flex items-center justify-center size-5 shrink-0 rounded-full bg-brand/10 text-brand-dark text-[11px] font-semibold tabular-nums">
                  {i + 1}
                </span>
                <span className="leading-relaxed text-foreground/90">{passo}</span>
              </li>
            ))}
          </ol>

          {ajuda.dica && (
            <div className="mt-1 flex gap-2 rounded-lg border border-border bg-surface-light p-3">
              <LightbulbIcon className="size-4 shrink-0 text-brand-dark" />
              <p className="text-xs leading-relaxed text-muted-foreground">
                <span className="font-medium text-foreground">Dica: </span>
                {ajuda.dica}
              </p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

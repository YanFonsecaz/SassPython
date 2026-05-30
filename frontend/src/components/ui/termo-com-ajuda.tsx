"use client";

import { InfoIcon } from "lucide-react";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { GLOSSARIO } from "@/lib/glossario";

interface TermoComAjudaProps {
  termo: string;
  texto?: string;
}

export function TermoComAjuda({ termo, texto }: TermoComAjudaProps) {
  const definition = texto ?? GLOSSARIO[termo.toLowerCase()];

  if (!definition) return <span>{termo}</span>;

  return (
    <Tooltip>
      <TooltipTrigger
        className="inline-flex items-center gap-0.5 border-b border-dashed border-muted-foreground/40 cursor-help"
      >
        {termo}
        <InfoIcon className="size-3 text-muted-foreground/60" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        {definition}
      </TooltipContent>
    </Tooltip>
  );
}

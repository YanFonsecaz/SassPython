"use client";

import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Cliente } from "@/types";

interface CardClienteProps {
  cliente: Cliente;
  onExcluir?: (id: string) => void;
}

export function CardCliente({ cliente, onExcluir }: CardClienteProps) {
  const numPersonas = cliente.config_json?.personas?.length || 0;

  return (
    <div className="group rounded-xl border bg-card p-5 transition-all duration-200 hover:border-brand/30 hover:shadow-md animate-fade-in">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center justify-center size-10 rounded-lg gradient-bg shrink-0">
            <span className="text-sm font-bold text-white">
              {cliente.nome.charAt(0).toUpperCase()}
            </span>
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-sm truncate">{cliente.nome}</h3>
            {cliente.site_url && (
              <p className="text-xs text-muted-foreground truncate">{cliente.site_url}</p>
            )}
          </div>
        </div>
        <Badge variant={cliente.ativo ? "default" : "secondary"} className="shrink-0">
          {cliente.ativo ? "Ativo" : "Inativo"}
        </Badge>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4">
        <span>{numPersonas} persona{numPersonas !== 1 ? "s" : ""}</span>
        {cliente.config_json?.persona_global?.tom_voz && (
          <>
            <span className="text-border">&middot;</span>
            <span>{cliente.config_json.persona_global.tom_voz}</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Link href={`/clientes/${cliente.id}`} className={buttonVariants({ size: "sm", variant: "outline" }) + " flex-1"}>
          Ver detalhes
        </Link>
        {onExcluir && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onExcluir(cliente.id)}
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
          >
            Excluir
          </Button>
        )}
      </div>
    </div>
  );
}

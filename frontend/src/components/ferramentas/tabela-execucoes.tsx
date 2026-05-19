"use client";

import Link from "next/link";
import { CircleCheckIcon, ClockIcon, AlertTriangleIcon, BanIcon, Loader2Icon, EyeIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Execucao } from "@/types";

interface TabelaExecucoesProps {
  execucoes: Execucao[];
  total: number;
  carregando: boolean;
  onCarregarMais?: () => void;
}

function statusBadge(status: string) {
  switch (status) {
    case "pendente":
    case "enfileirado":
      return <Badge variant="secondary" className="gap-1"><ClockIcon className="size-3" /> Pendente</Badge>;
    case "executando":
      return <Badge variant="outline" className="gap-1"><Loader2Icon className="size-3 animate-spin" /> Executando</Badge>;
    case "aguardando_aprovacao":
      return <Badge className="gap-1"><EyeIcon className="size-3" /> Aguardando</Badge>;
    case "aguardando_revisao":
      return <Badge variant="secondary" className="gap-1"><EyeIcon className="size-3" /> Revisao</Badge>;
    case "concluida":
      return <Badge className="gap-1 bg-green-600 hover:bg-green-600"><CircleCheckIcon className="size-3" /> Concluida</Badge>;
    case "falhou":
      return <Badge variant="destructive" className="gap-1"><AlertTriangleIcon className="size-3" /> Falhou</Badge>;
    case "cancelada":
      return <Badge variant="secondary" className="gap-1"><BanIcon className="size-3" /> Cancelada</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

function formatarData(data: string): string {
  return new Date(data).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TabelaExecucoes({
  execucoes,
  total,
  carregando,
  onCarregarMais,
}: TabelaExecucoesProps) {
  if (carregando && execucoes.length === 0) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex gap-4 animate-pulse">
            <div className="h-4 flex-1 rounded bg-muted" />
            <div className="h-4 w-24 rounded bg-muted" />
            <div className="h-4 w-20 rounded bg-muted" />
          </div>
        ))}
      </div>
    );
  }

  if (execucoes.length === 0) {
    return (
      <div className="text-center py-12 space-y-3">
        <p className="text-muted-foreground">
          Nenhuma execucao encontrada
        </p>
        <Link
          href="/ferramentas/gerar-artigo"
          className={buttonVariants({ size: "sm" })}
        >
          Gerar primeiro artigo
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {total} execucao{total !== 1 ? "es" : ""}
      </p>

      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="text-left px-3 py-2 font-medium">
                Ferramenta
              </th>
              <th className="text-left px-3 py-2 font-medium">
                Status
              </th>
              <th className="text-left px-3 py-2 font-medium">
                Etapa
              </th>
              <th className="text-left px-3 py-2 font-medium">
                Creditos
              </th>
              <th className="text-left px-3 py-2 font-medium">
                Data
              </th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {execucoes.map((exec) => (
              <tr
                key={exec.id}
                className="border-b last:border-0"
              >
                <td className="px-3 py-2">{exec.ferramenta}</td>
                <td className="px-3 py-2">
                  {statusBadge(exec.status)}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {exec.etapa_atual || "—"}
                </td>
                <td className="px-3 py-2">
                  {exec.creditos_cobrados > 0
                    ? exec.creditos_cobrados
                    : "—"}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {formatarData(exec.criado_em)}
                </td>
                <td className="px-3 py-2 text-right">
                  <Link
                    href={`/ferramentas/historico/${exec.id}`}
                    className={buttonVariants({
                      variant: "ghost",
                      size: "sm",
                    })}
                  >
                    Ver
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {onCarregarMais && execucoes.length < total && (
        <div className="text-center">
          <Button
            variant="outline"
            size="sm"
            onClick={onCarregarMais}
            disabled={carregando}
          >
            {carregando ? "Carregando..." : "Carregar mais"}
          </Button>
        </div>
      )}
    </div>
  );
}

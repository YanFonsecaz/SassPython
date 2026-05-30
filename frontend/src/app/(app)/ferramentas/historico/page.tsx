"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRightIcon, CircleCheckIcon, ClockIcon, AlertTriangleIcon, BanIcon, Loader2Icon, EyeIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useExecucao } from "@/hooks/use-execucao";
import { labelFerramenta } from "@/lib/ferramentas";
import { cn } from "@/lib/utils";
import type { Execucao } from "@/types";

function statusConfig(status: string) {
  switch (status) {
    case "pendente":
    case "enfileirado":
      return { icon: ClockIcon, label: "Pendente", color: "text-muted-foreground", dot: "bg-muted-foreground" };
    case "executando":
      return { icon: Loader2Icon, label: "Executando", color: "text-brand-dark", dot: "bg-brand-light" };
    case "aguardando_aprovacao":
      return { icon: EyeIcon, label: "Aguardando", color: "text-brand-dark", dot: "bg-brand-light" };
    case "aguardando_revisao":
      return { icon: EyeIcon, label: "Revisão", color: "text-muted-foreground", dot: "bg-muted-foreground" };
    case "concluida":
      return { icon: CircleCheckIcon, label: "Concluída", color: "text-success", dot: "bg-success" };
    case "falhou":
      return { icon: AlertTriangleIcon, label: "Falhou", color: "text-destructive", dot: "bg-destructive" };
    case "cancelada":
      return { icon: BanIcon, label: "Cancelada", color: "text-muted-foreground", dot: "bg-muted-foreground" };
    default:
      return { icon: ClockIcon, label: status, color: "text-muted-foreground", dot: "bg-muted-foreground" };
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

function ExecucaoCard({ exec }: { exec: Execucao }) {
  const cfg = statusConfig(exec.status);
  const StatusIcon = cfg.icon;

  return (
    <Link
      href={`/ferramentas/historico/${exec.id}`}
      className="group flex items-center gap-4 rounded-xl border bg-card px-4 py-4 transition-all duration-200 hover:border-brand/30 hover:shadow-md animate-fade-in"
    >
      <div className={`flex items-center justify-center size-10 rounded-lg bg-surface-light shrink-0`}>
        <StatusIcon className={`size-5 ${cfg.color} ${exec.status === "executando" ? "animate-spin" : ""}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium truncate">{labelFerramenta(exec.ferramenta)}</p>
          <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
        </div>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-xs text-muted-foreground">{formatarData(exec.criado_em)}</span>
          {exec.etapa_atual && exec.status === "executando" && (
            <span className="text-xs text-muted-foreground truncate">{exec.etapa_atual}</span>
          )}
          {exec.creditos_cobrados > 0 && (
            <span className="text-xs text-muted-foreground">{exec.creditos_cobrados} créds</span>
          )}
        </div>
      </div>
      <ArrowRightIcon className="size-4 text-muted-foreground group-hover:text-brand-dark group-hover:translate-x-1 transition-all shrink-0" />
    </Link>
  );
}

export default function HistóricoPage() {
  const { execucoes, total, carregando, listar, listarErro } = useExecucao();
  const [offset, setOffset] = useState(0);
  const [filtro, setFiltro] = useState<string | null>(null);
  const limite = 20;

  useEffect(() => {
    listar(0);
  }, [listar]);

  // Ferramentas presentes na lista carregada, na ordem de primeira aparição.
  const ferramentasPresentes = Array.from(new Set(execucoes.map((e) => e.ferramenta)));
  const execucoesFiltradas = filtro ? execucoes.filter((e) => e.ferramenta === filtro) : execucoes;

  async function carregarMais() {
    await listar(offset + limite);
    setOffset((prev) => prev + limite);
  }

  if (carregando && execucoes.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="Histórico" description="Acompanhe todas as suas execuções" />
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-muted/50 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (listarErro && execucoes.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="Histórico" description="Acompanhe todas as suas execuções" />
        <ErrorState
          title="Erro ao carregar"
          description={listarErro}
          action={
            <Button variant="outline" onClick={() => listar(0)}>
              Tentar novamente
            </Button>
          }
        />
      </div>
    );
  }

  if (execucoes.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Histórico"
          description="Acompanhe todas as suas execuções"
          action={
            <Link href="/ferramentas" className={buttonVariants()}>
              Ver ferramentas
            </Link>
          }
        />
        <EmptyState
          icon={ClockIcon}
          title="Nenhuma execução ainda"
          description="Use uma das ferramentas para começar — artigos, inlinks ou Core Web Vitals."
          action={
            <Link href="/ferramentas" className={buttonVariants()}>
              Ver ferramentas
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Histórico"
        description={`${total} ${total !== 1 ? "execuções" : "execução"}`}
        action={
          <Link href="/ferramentas" className={buttonVariants()}>
            Ver ferramentas
          </Link>
        }
      />

      {ferramentasPresentes.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setFiltro(null)}
            className={cn(
              "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
              filtro === null ? "border-brand bg-brand/5 text-brand-dark" : "text-muted-foreground hover:bg-surface-light",
            )}
          >
            Todas
          </button>
          {ferramentasPresentes.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFiltro(f)}
              className={cn(
                "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                filtro === f ? "border-brand bg-brand/5 text-brand-dark" : "text-muted-foreground hover:bg-surface-light",
              )}
            >
              {labelFerramenta(f)}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {execucoesFiltradas.map((exec) => (
          <ExecucaoCard key={exec.id} exec={exec} />
        ))}
      </div>

      {filtro === null && execucoes.length < total && (
        <div className="text-center">
          <Button variant="outline" size="sm" onClick={carregarMais} disabled={carregando}>
            {carregando ? "Carregando..." : "Carregar mais"}
          </Button>
        </div>
      )}
    </div>
  );
}

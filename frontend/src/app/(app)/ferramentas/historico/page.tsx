"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRightIcon, CircleCheckIcon, ClockIcon, AlertTriangleIcon, BanIcon, Loader2Icon, EyeIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { useExecucao } from "@/hooks/use-execucao";
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
          <p className="text-sm font-medium truncate">{exec.ferramenta}</p>
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
  const { execucoes, total, carregando, listar } = useExecucao();
  const [offset, setOffset] = useState(0);
  const limite = 20;

  useEffect(() => {
    listar(0);
  }, [listar]);

  async function carregarMais() {
    await listar(offset + limite);
    setOffset((prev) => prev + limite);
  }

  if (carregando && execucoes.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="Histórico" description="Acompanhe todas as suas execucoes" />
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-muted/50 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (execucoes.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Histórico"
          description="Acompanhe todas as suas execucoes"
          action={
            <Link href="/ferramentas/gerar-artigo" className={buttonVariants()}>
              Gerar artigo
            </Link>
          }
        />
        <EmptyState
          icon={ClockIcon}
          title="Nenhuma execução ainda"
          description="Comece gerando seu primeiro artigo otimizado para SEO."
          action={
            <Link href="/ferramentas/gerar-artigo" className={buttonVariants()}>
              Gerar primeiro artigo
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
        description={`${total} ${total !== 1 ? "execucoes" : "execução"}`}
        action={
          <Link href="/ferramentas/gerar-artigo" className={buttonVariants()}>
            Gerar artigo
          </Link>
        }
      />

      <div className="space-y-2">
        {execucoes.map((exec) => (
          <ExecucaoCard key={exec.id} exec={exec} />
        ))}
      </div>

      {execucoes.length < total && (
        <div className="text-center">
          <Button variant="outline" size="sm" onClick={carregarMais} disabled={carregando}>
            {carregando ? "Carregando..." : "Carregar mais"}
          </Button>
        </div>
      )}
    </div>
  );
}

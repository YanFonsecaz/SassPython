"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { PenLineIcon, HistoryIcon, CreditCardIcon, ArrowRightIcon, FileTextIcon, SparklesIcon, LinkIcon, GaugeIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { ComoUsar } from "@/components/ferramentas/como-usar";
import { labelFerramenta } from "@/lib/ferramentas";
import { useAuth } from "@/hooks/use-auth";
import { useCreditos } from "@/hooks/use-creditos";
import { useExecucao } from "@/hooks/use-execucao";
import { useClientes } from "@/hooks/use-clientes";

function saudacao() {
  const h = new Date().getHours();
  if (h < 12) return "Bom dia";
  if (h < 18) return "Boa tarde";
  return "Boa noite";
}

export default function FerramentasPage() {
  const { usuario } = useAuth();
  const { saldo } = useCreditos();
  const { clientes } = useClientes();
  const { execucoes, total, listar } = useExecucao();

  useEffect(() => {
    listar(0);
  }, [listar]);

  const ultimasExecucoes = useMemo(() => {
    return [...execucoes]
      .filter((e) => e.status === "concluida" || e.status === "falhou")
      .sort((a, b) => new Date(b.criado_em).getTime() - new Date(a.criado_em).getTime())
      .slice(0, 3);
  }, [execucoes]);

  return (
    <div className="space-y-8">
      <PageHeader
        title={`${saudacao()}, ${usuario?.nome?.split(" ")[0] ?? "Usuário"}`}
        description="Crie conteúdo otimizado para SEO com inteligência artificial"
      />

      {!clientes.length && (
        <div className="rounded-xl border border-brand/20 bg-brand/5 p-4 flex items-center justify-between gap-4 animate-fade-in">
          <div>
            <p className="text-sm font-medium">Comece cadastrando um cliente</p>
            <p className="text-xs text-muted-foreground mt-0.5">Você precisa de pelo menos um cliente para usar as ferramentas.</p>
          </div>
          <Link href="/clientes/novo" className={`${buttonVariants({ variant: "outline", size: "sm" })} shrink-0`}>
            Cadastrar cliente
          </Link>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Créditos disponíveis"
          value={saldo?.saldo_total ?? 0}
          icon={CreditCardIcon}
          variant={saldo && saldo.saldo_total < 20 ? "danger" : "default"}
        />
        <StatCard
          label="Total de execuções"
          value={total}
          icon={FileTextIcon}
        />
        <StatCard
          label="Ferramentas ativas"
          value="4"
          icon={SparklesIcon}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="relative animate-fade-in">
          <Link
            href="/ferramentas/gerar-artigo"
            className="group block overflow-hidden rounded-2xl border border-brand/30 bg-gradient-to-br from-brand/8 via-brand/3 to-transparent p-6 transition-all duration-300 hover:border-brand/50 hover:shadow-xl hover:-translate-y-0.5"
          >
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center size-12 rounded-xl gradient-bg shadow-md shrink-0">
                <PenLineIcon className="size-6 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-heading font-semibold text-base tracking-tight">Gerar Artigo SEO</h3>
                <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
                  Crie artigos otimizados para SEO com IA, seguindo personas e briefs personalizados.
                </p>
                <p className="text-xs font-medium text-brand-dark mt-3">20–38 créditos</p>
              </div>
              <ArrowRightIcon className="size-5 text-brand-dark group-hover:translate-x-1 transition-all shrink-0 mt-1" />
            </div>
          </Link>
          <ComoUsar ferramenta="gerar-artigo" variant="icone" className="absolute bottom-3 right-3 z-10" />
        </div>

        <div className="relative animate-fade-in">
          <Link
            href="/ferramentas/inlinks"
            className="group block overflow-hidden rounded-2xl border border-brand/30 bg-gradient-to-br from-brand/8 via-brand/3 to-transparent p-6 transition-all duration-300 hover:border-brand/50 hover:shadow-xl hover:-translate-y-0.5"
          >
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center size-12 rounded-xl gradient-bg shadow-md shrink-0">
                <LinkIcon className="size-6 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-heading font-semibold text-base tracking-tight">Inlinks Internos</h3>
                <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
                  Crie links entre páginas do seu site. Receba links em um artigo OU distribua uma URL para várias páginas.
                </p>
                <p className="text-xs font-medium text-brand-dark mt-3">15–115 créditos</p>
              </div>
              <ArrowRightIcon className="size-5 text-brand-dark group-hover:translate-x-1 transition-all shrink-0 mt-1" />
            </div>
          </Link>
          <ComoUsar ferramenta="inlinks" variant="icone" className="absolute bottom-3 right-3 z-10" />
        </div>

        <div className="relative animate-fade-in">
          <Link
            href="/ferramentas/core-web-vitals"
            className="group block overflow-hidden rounded-2xl border border-brand/30 bg-gradient-to-br from-brand/8 via-brand/3 to-transparent p-6 transition-all duration-300 hover:border-brand/50 hover:shadow-xl hover:-translate-y-0.5"
          >
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center size-12 rounded-xl gradient-bg shadow-md shrink-0">
                <GaugeIcon className="size-6 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-heading font-semibold text-base tracking-tight">Core Web Vitals</h3>
                <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
                  Audite a performance das suas URLs e receba um plano de ação por página, com evolução ao longo do tempo.
                </p>
                <p className="text-xs font-medium text-brand-dark mt-3">15–50 créditos</p>
              </div>
              <ArrowRightIcon className="size-5 text-brand-dark group-hover:translate-x-1 transition-all shrink-0 mt-1" />
            </div>
          </Link>
          <ComoUsar ferramenta="core-web-vitals" variant="icone" className="absolute bottom-3 right-3 z-10" />
        </div>

        <div className="relative animate-fade-in">
          <Link
            href="/ferramentas/parecer"
            className="group block overflow-hidden rounded-2xl border border-brand/30 bg-gradient-to-br from-brand/8 via-brand/3 to-transparent p-6 transition-all duration-300 hover:border-brand/50 hover:shadow-xl hover:-translate-y-0.5"
          >
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center size-12 rounded-xl gradient-bg shadow-md shrink-0">
                <FileTextIcon className="size-6 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-heading font-semibold text-base tracking-tight">Parecer Técnico</h3>
                <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
                  Cole prints e descreva o problema; a IA gera um documento de correções de SEO pronto para enviar.
                </p>
                <p className="text-xs font-medium text-brand-dark mt-3">10–90 créditos</p>
              </div>
              <ArrowRightIcon className="size-5 text-brand-dark group-hover:translate-x-1 transition-all shrink-0 mt-1" />
            </div>
          </Link>
          <ComoUsar ferramenta="parecer" variant="icone" className="absolute bottom-3 right-3 z-10" />
        </div>

        <Link
          href="/ferramentas/historico"
          className="group rounded-2xl border bg-card p-6 transition-all duration-300 hover:border-brand/40 hover:shadow-xl hover:-translate-y-0.5 animate-fade-in"
        >
          <div className="flex items-start gap-4">
            <div className="flex items-center justify-center size-12 rounded-xl bg-surface-light border border-border shrink-0">
              <HistoryIcon className="size-6 text-brand-dark" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-heading font-semibold text-base tracking-tight">Histórico</h3>
              <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
                Acompanhe todas as suas execuções, revise resultados e gerencie artigos.
              </p>
              {total > 0 && (
                <p className="text-xs font-medium text-muted-foreground mt-3">
                  {total} execuç{total !== 1 ? "ões" : "ão"}
                </p>
              )}
            </div>
            <ArrowRightIcon className="size-5 text-muted-foreground group-hover:text-brand-dark group-hover:translate-x-1 transition-all shrink-0 mt-1" />
          </div>
        </Link>
      </div>

      {ultimasExecucoes.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading text-lg font-semibold tracking-tight">Últimas execuções</h2>
            <Link
              href="/ferramentas/historico"
              className="text-sm font-medium text-brand-dark hover:text-brand-deep underline-offset-4 hover:underline transition-colors"
            >
              Ver todas
            </Link>
          </div>
          <div className="space-y-2">
            {ultimasExecucoes.map((exec) => (
              <Link
                key={exec.id}
                href={`/ferramentas/historico/${exec.id}`}
                className="flex items-center justify-between rounded-xl border bg-card px-4 py-3.5 transition-all hover:border-brand/40 hover:shadow-md animate-fade-in"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`size-2 rounded-full shrink-0 ${exec.status === "concluida" ? "bg-success" : "bg-destructive"}`} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{labelFerramenta(exec.ferramenta)}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {new Date(exec.criado_em).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {exec.creditos_cobrados > 0 && (
                    <span className="text-xs font-medium text-muted-foreground tabular-nums">
                      {exec.creditos_cobrados} créds
                    </span>
                  )}
                  <ArrowRightIcon className="size-4 text-muted-foreground" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

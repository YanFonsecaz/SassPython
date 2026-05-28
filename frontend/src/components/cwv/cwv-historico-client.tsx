"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { ArrowLeftIcon, ArrowRightIcon, GaugeIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { buscarHistoricoCwv } from "@/lib/api/cwv";
import type { CwvHistoricoUrlResposta } from "@/lib/api/cwv";
import { cn } from "@/lib/utils";

function scoreColor(score: number | null) {
  if (score === null) return "text-muted-foreground";
  if (score >= 90) return "text-success";
  if (score >= 50) return "text-yellow-500";
  return "text-destructive";
}

function formatData(data: string) {
  return new Date(data).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

function UrlCard({ urlEntry }: { urlEntry: CwvHistoricoUrlResposta }) {
  const ultima = urlEntry.analises[0];

  return (
    <Link
      href={`/ferramentas/core-web-vitals/url/${ultima?.id ?? ""}`}
      className="group flex items-center gap-4 rounded-xl border bg-card px-4 py-4 transition-all duration-200 hover:border-brand/30 hover:shadow-md animate-fade-in"
    >
      <div className="flex items-center justify-center size-10 rounded-lg bg-surface-light shrink-0">
        <GaugeIcon className="size-5 text-brand-dark" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{urlEntry.url_canonica}</p>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <Badge variant="outline" className="text-[10px]">{urlEntry.template_tipo}</Badge>
          {urlEntry.plataforma_detectada && urlEntry.plataforma_detectada !== "desconhecida" && (
            <Badge variant="outline" className="text-[10px]">{urlEntry.plataforma_detectada}</Badge>
          )}
          {ultima && (
            <>
              <span className="text-xs text-muted-foreground">{formatData(ultima.criado_em)}</span>
              <span className={cn("text-xs font-bold tabular-nums", scoreColor(ultima.score_performance))}>
                {ultima.score_performance ?? "—"}
              </span>
            </>
          )}
          {urlEntry.analises.length > 1 && (
            <span className="text-xs text-muted-foreground">
              {urlEntry.analises.length} analises
            </span>
          )}
        </div>
      </div>
      <ArrowRightIcon className="size-4 text-muted-foreground group-hover:text-brand-dark group-hover:translate-x-1 transition-all shrink-0" />
    </Link>
  );
}

export function CwvHistoricoClient() {
  const pathname = usePathname();
  const clienteId = pathname.split("/").filter(Boolean).pop() || "";

  const [urls, setUrls] = useState<CwvHistoricoUrlResposta[]>([]);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    async function load() {
      setCarregando(true);
      try {
        const dados = await buscarHistoricoCwv(clienteId);
        setUrls(dados.urls);
      } catch {
      } finally {
        setCarregando(false);
      }
    }
    if (clienteId) load();
  }, [clienteId]);

  if (carregando) {
    return (
      <div className="space-y-6">
        <PageHeader title="Historico CWV" description="Carregando..." />
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-muted/50 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Historico Core Web Vitals"
        description={urls.length > 0 ? `${urls.length} URL${urls.length !== 1 ? "s" : ""} analisada${urls.length !== 1 ? "s" : ""}` : "Nenhuma analise ainda"}
        action={
          <div className="flex gap-2 pl-12 lg:pl-0">
            <Link href="/ferramentas/core-web-vitals" className={buttonVariants({ variant: "outline", size: "sm" })}>
              Nova analise
            </Link>
            <Link href="/ferramentas/core-web-vitals" className={buttonVariants({ variant: "ghost", size: "sm" })}>
              <ArrowLeftIcon className="size-4 mr-1" /> Voltar
            </Link>
          </div>
        }
      />

      {urls.length === 0 ? (
        <EmptyState
          icon={GaugeIcon}
          title="Nenhuma analise ainda"
          description="Comece analisando as URLs do seu site."
          action={
            <Link href="/ferramentas/core-web-vitals" className={buttonVariants()}>
              Analisar URLs
            </Link>
          }
        />
      ) : (
        <div className="space-y-2">
          {urls.map((entry) => (
            <UrlCard key={entry.url_canonica} urlEntry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}

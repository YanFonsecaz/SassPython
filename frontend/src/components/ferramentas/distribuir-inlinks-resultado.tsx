"use client";

import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ExternalLinkIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  XCircleIcon,
  CopyIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  MapPinIcon,
  SparklesIcon,
  InfoIcon,
} from "lucide-react";
import type { ResultadoDistribuirInlinks, CandidataResultado } from "@/types";

type TabKey = "aplicadas" | "sugestoes" | "sem_match" | "falhas";

interface Props {
  resultado: ResultadoDistribuirInlinks;
}

function CandidataAccordion({ candidata, urlAlvo }: { candidata: CandidataResultado; urlAlvo: string }) {
  const [aberto, setAberto] = useState(false);

  const statusConfig: Record<string, { icon: React.ElementType; label: string; classe: string }> = {
    aplicado: { icon: CheckCircleIcon, label: "Aplicado", classe: "text-success" },
    sugestao_manual: { icon: AlertTriangleIcon, label: "Revisar antes de aplicar", classe: "text-warning" },
    sem_match: { icon: XCircleIcon, label: "Sem relação suficiente", classe: "text-muted-foreground" },
    falhou_extracao: { icon: XCircleIcon, label: "Erro ao ler URL", classe: "text-destructive" },
  };

  const cfg = statusConfig[candidata.status] || statusConfig.sem_match;
  const StatusIcon = cfg.icon;

  async function copiarMarkdown() {
    if (!candidata.markdown_modificado) return;
    await navigator.clipboard.writeText(candidata.markdown_modificado);
  }

  function renderTrecho(trecho: string) {
    // Suporta «ancora», [ancora](url) e **bold** no mesmo texto.
    const partes: ReactNode[] = [];
    const regex = /«([^»]+)»|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+?)\*\*/g;
    let cursor = 0;
    let key = 0;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(trecho)) !== null) {
      if (match.index > cursor) {
        partes.push(trecho.slice(cursor, match.index));
      }
      const ancoraChevron = match[1];
      const ancoraLink = match[2];
      const negrito = match[4];
      if (ancoraChevron || ancoraLink) {
        partes.push(
          <mark
            key={key++}
            className="rounded bg-brand/20 px-1 py-0.5 font-medium text-brand-dark"
          >
            {ancoraChevron ?? ancoraLink}
          </mark>
        );
      } else if (negrito) {
        partes.push(<strong key={key++}>{negrito}</strong>);
      }
      cursor = match.index + match[0].length;
    }
    if (cursor < trecho.length) {
      partes.push(trecho.slice(cursor));
    }
    return <span>{partes}</span>;
  }

  return (
    <div className={cn("rounded-xl border bg-card transition-colors", candidata.status === "sem_match" && "opacity-70")}>
      <button
        type="button"
        onClick={() => setAberto(!aberto)}
        className="flex items-center gap-3 w-full px-4 py-3 text-left"
      >
        <StatusIcon className={cn("size-4 shrink-0", cfg.classe)} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate">{candidata.titulo || candidata.url}</p>
          <a
            href={candidata.url_canonica || candidata.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:text-brand-dark truncate block"
            onClick={(e) => e.stopPropagation()}
          >
            {candidata.url_canonica || candidata.url}
          </a>
        </div>
        {candidata.score_semantico != null && (
          <span className="text-xs font-mono font-semibold text-muted-foreground shrink-0">
            {(candidata.score_semantico * 100).toFixed(0)}%
          </span>
        )}
        {aberto ? <ChevronUpIcon className="size-4 shrink-0 text-muted-foreground" /> : <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />}
      </button>

      {aberto && (
        <div className="px-4 pb-4 pt-0 space-y-3 border-t border-border/50">
          <div className="pt-3">
            <div className="flex items-center gap-2 mb-1">
              <ExternalLinkIcon className="size-3 text-brand-dark" />
              <span className="text-xs font-medium text-muted-foreground">Link para URL alvo</span>
            </div>
            <a
              href={urlAlvo}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-brand-dark hover:underline"
            >
              {urlAlvo}
            </a>
          </div>

          {candidata.anchor_text && (
            <div className="rounded-lg bg-surface-light p-3 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <MapPinIcon className="size-3" />
                Ancora: &ldquo;{candidata.anchor_text}&rdquo;
                {candidata.ancora_preferida_usada && (
                  <Badge className="bg-success/10 text-success border-success/30">
                    Ancora preferida
                  </Badge>
                )}
                {candidata.paragrafo_idx != null && (
                  <span className="font-normal normal-case tracking-normal">
                    {" "}· paragrafo {candidata.paragrafo_idx + 1}
                  </span>
                )}
              </div>
              {candidata.trecho_contexto && (
                <p className="text-sm leading-relaxed text-foreground/90">
                  {renderTrecho(candidata.trecho_contexto)}
                </p>
              )}
            </div>
          )}

          {candidata.trecho_original && candidata.anchor_text && (
            <div className="rounded-lg border border-dashed p-3 space-y-1">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Trecho original</p>
              <p className="text-sm text-foreground/90">{candidata.trecho_original}</p>
            </div>
          )}

          {(candidata.justificativa || candidata.motivo) && (
            <div className="rounded-lg border border-dashed p-3 space-y-1">
              <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <SparklesIcon className="size-3" />
                Justificativa
              </div>
              <p className="text-sm text-foreground/90">{candidata.justificativa || candidata.motivo}</p>
            </div>
          )}

          {candidata.status === "aplicado" && candidata.markdown_modificado && (
            <div className="flex gap-2 pt-1">
              <Button size="sm" variant="outline" className="text-xs" onClick={copiarMarkdown}>
                <CopyIcon className="size-3 mr-1" /> Copiar markdown modificado
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function DistribuirInlinksResultado({ resultado }: Props) {
  const [tabAtiva, setTabAtiva] = useState<TabKey>("aplicadas");

  if (!resultado || !Array.isArray(resultado.candidatas)) {
    return (
      <div className="rounded-xl border bg-muted/30 p-6 text-center text-sm text-muted-foreground">
        Carregando resultado...
      </div>
    );
  }

  const tabs: { key: TabKey; label: string; count: number }[] = [
    { key: "aplicadas", label: "Aplicadas", count: resultado.n_aplicadas ?? 0 },
    { key: "sugestoes", label: "Sugestoes", count: resultado.n_sugestoes ?? 0 },
    { key: "sem_match", label: "Sem match", count: resultado.n_sem_match ?? 0 },
    { key: "falhas", label: "Falhas", count: resultado.n_falhas ?? 0 },
  ];

  const filtradas = resultado.candidatas.filter((c) => {
    switch (tabAtiva) {
      case "aplicadas": return c.status === "aplicado";
      case "sugestoes": return c.status === "sugestao_manual";
      case "sem_match": return c.status === "sem_match";
      case "falhas": return c.status === "falhou_extracao";
    }
  });

  return (
    <div className="space-y-4">
      {resultado.alvo_modo === "slug_only" && (
        <div className="rounded-xl border border-warning/30 bg-warning/5 p-3 flex items-start gap-2.5 text-sm">
          <InfoIcon className="size-4 text-warning shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <p className="font-medium text-warning-dark">Pagina de categoria/produto sem conteudo redacional</p>
            <p className="text-xs text-muted-foreground">
              A URL alvo e uma listagem (categoria, produto ou arquivo) e nao tem texto suficiente para analise.
              Usamos os termos do slug da URL para identificar o tema e encontrar candidatas relacionadas.
              Resultados nesse modo podem ter scores menores &mdash; o sistema relaxa o filtro automaticamente.
            </p>
          </div>
        </div>
      )}

      <div className="rounded-xl border bg-surface-light p-4 space-y-2">
        <div className="flex items-center gap-2 mb-2">
          <ExternalLinkIcon className="size-4 text-brand-dark" />
          <span className="text-sm font-medium">URL alvo</span>
        </div>
        <a
          href={resultado.url_alvo}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-brand-dark hover:underline break-all"
        >
          {resultado.titulo_alvo ? (
            <>
              {resultado.titulo_alvo}
              <br />
              <span className="text-xs text-muted-foreground">{resultado.url_alvo}</span>
            </>
          ) : (
            resultado.url_alvo
          )}
        </a>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {tabs.map((t) => (
          <span key={t.key}>
            {t.count > 0 ? (
              <button
                type="button"
                onClick={() => setTabAtiva(t.key)}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
                  tabAtiva === t.key
                    ? "border-brand bg-brand/10 text-brand-dark"
                    : "border-border text-muted-foreground hover:bg-accent"
                )}
              >
                {t.label} ({t.count})
              </button>
            ) : (
              <span className="text-muted-foreground/60">{t.label} ({t.count})</span>
            )}
          </span>
        ))}
      </div>

      {filtradas.length === 0 ? (
        <div className="rounded-xl border bg-muted/30 p-6 text-center text-sm text-muted-foreground">
          Nenhuma candidata nesta categoria.
        </div>
      ) : (
        <div className="space-y-3">
          {filtradas.map((c, i) => (
            <CandidataAccordion key={`${c.url}-${i}`} candidata={c} urlAlvo={resultado.url_alvo} />
          ))}
        </div>
      )}
    </div>
  );
}

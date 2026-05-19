"use client";

import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ExternalLinkIcon, MapPinIcon, SparklesIcon } from "lucide-react";
import type { InlinkAplicado } from "@/types";

const CATEGORIA_INFO: Record<
  string,
  { label: string; descricao: string; classe: string }
> = {
  alta_similaridade: {
    label: "Conexão forte",
    descricao: "Tema do destino bate fortemente com o trecho do pilar — link confiável",
    classe: "bg-success/10 text-success border-success/30",
  },
  boa_similaridade: {
    label: "Conexão sólida",
    descricao: "Conexão temática consistente entre trecho e destino",
    classe: "bg-brand/15 text-brand-dark border-brand/30",
  },
  complemento_contextual: {
    label: "Conexão indireta · revise",
    descricao: "Destino se conecta por contexto, não por tema direto. Confirme se o leitor vai querer clicar.",
    classe: "bg-warning/15 text-warning border-warning/40",
  },
  similaridade_media: {
    label: "Conexão fraca · revise",
    descricao: "Relação tênue entre trecho e destino. Considere remover ou trocar a âncora.",
    classe: "bg-muted text-muted-foreground border-border",
  },
};

function categoriaInfo(cat?: string | null) {
  if (cat && CATEGORIA_INFO[cat]) return CATEGORIA_INFO[cat];
  return CATEGORIA_INFO.similaridade_media;
}

function renderTrecho(trecho: string) {
  // Suporta tres formatos no mesmo trecho:
  //   «ancora»             — formato legado (delimitadores chevron)
  //   [ancora](url)        — markdown inline link
  //   **texto**            — markdown bold
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

interface Props {
  inlinks: InlinkAplicado[];
  totalCandidatas?: number;
}

export function InlinksResultado({ inlinks, totalCandidatas }: Props) {
  if (!inlinks || inlinks.length === 0) {
    return (
      <div className="rounded-xl border bg-muted/30 p-6 text-center text-sm text-muted-foreground">
        Nenhum inlink foi aplicado neste artigo.
      </div>
    );
  }

  const aplicados = inlinks.filter((il) => il.status === "aplicado");
  const rejeitados = inlinks.filter((il) => il.status === "rejeitado" || il.status === "rejeitado_revisor");
  const sugestoes = inlinks.filter((il) => il.status === "sugestao_manual");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-semibold text-foreground">
          {aplicados.length} inlink{aplicados.length === 1 ? "" : "s"} aplicado
          {aplicados.length === 1 ? "" : "s"}
        </span>
        {rejeitados.length > 0 && (
          <span>· {rejeitados.length} rejeitado pelo revisor</span>
        )}
        {sugestoes.length > 0 && (
          <span>· {sugestoes.length} sugestão{sugestoes.length === 1 ? "" : "ões"} manual</span>
        )}
        {typeof totalCandidatas === "number" && (
          <span>· {totalCandidatas} candidatas analisadas</span>
        )}
      </div>

      <ul className="space-y-3">
        {inlinks.map((il, i) => {
          const info = categoriaInfo(il.categoria_match);
          const rejeitado = il.status === "rejeitado" || il.status === "rejeitado_revisor";
          const sugestaoManual = il.status === "sugestao_manual";

          return (
            <li
              key={`${il.url_destino}-${il.offset_chars}-${i}`}
              className={cn(
                "rounded-xl border bg-card p-4 space-y-3 transition-colors",
                (rejeitado || sugestaoManual) && "opacity-80",
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Âncora
                    </span>
                    <span
                      className={cn(
                        "inline-flex h-5 items-center rounded-full border px-2 text-xs font-medium",
                        info.classe,
                      )}
                      title={info.descricao}
                    >
                      {info.label}
                    </span>
                    {rejeitado && (
                      <Badge variant="destructive">Rejeitado</Badge>
                    )}
                    {sugestaoManual && (
                      <Badge className="bg-warning/15 text-warning border-warning/40">Sugestão manual</Badge>
                    )}
                  </div>
                  <p className="font-medium leading-tight">
                    "{il.anchor_text}"
                  </p>
                  <a
                    href={il.url_destino}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-brand-dark hover:underline"
                  >
                    <ExternalLinkIcon className="size-3" />
                    {il.titulo_destino || il.url_destino}
                  </a>
                </div>
                <div className="text-right text-xs">
                  <p className="font-mono font-semibold text-foreground">
                    {(il.score_total * 100).toFixed(0)}%
                  </p>
                  <p className="text-muted-foreground">
                    sem {(il.score_semantico * 100).toFixed(0)} · ctx{" "}
                    {(il.score_contexto * 100).toFixed(0)}
                  </p>
                </div>
              </div>

              {!sugestaoManual && il.trecho_contexto && (
                <div className="rounded-lg bg-surface-light p-3 text-sm leading-relaxed">
                  <div className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <MapPinIcon className="size-3" />
                    Onde foi inserido
                    <span className="font-normal normal-case tracking-normal">
                      · parágrafo {il.paragrafo_idx + 1}
                    </span>
                  </div>
                  <p className="text-foreground/90">
                    {renderTrecho(il.trecho_contexto)}
                  </p>
                </div>
              )}

              {(il.motivo_contexto || rejeitado || sugestaoManual) && (
                <div className="rounded-lg border border-dashed p-3 text-sm">
                  <div className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <SparklesIcon className="size-3" />
                    {sugestaoManual ? "Por que sugerimos" : "Por que aqui"}
                  </div>
                  {il.motivo_contexto && (
                    <p className="text-foreground/90">{il.motivo_contexto}</p>
                  )}
                  {rejeitado && il.motivo_rejeicao && (
                    <p className="mt-1 text-destructive">
                      Revisor rejeitou: {il.motivo_rejeicao}
                    </p>
                  )}
                  {sugestaoManual && (il.motivo_sugestao || il.motivo_rejeicao) && (
                    <p className="mt-1 text-warning">
                      {il.motivo_sugestao || il.motivo_rejeicao}
                    </p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

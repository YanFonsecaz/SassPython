"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Item {
  url?: string;
  selector?: string;
  snippet?: string;
  node_label?: string;
  dom_path?: string;
  bounding_rect?: { top?: number; left?: number; width?: number; height?: number };
  label?: string;
  entity?: string;
  source?: string;
  group?: string;
  group_label?: string;
  mime_type?: string;
  name?: string;
  timing_type?: string;
  wastedMs?: number;
  wastedBytes?: number;
  wastedPercent?: number;
  totalBytes?: number;
  transferSize?: number;
  resourceBytes?: number;
  resourceSize?: number;
  duration?: number;
  scriptParseCompile?: number;
  scripting?: number;
  startTime?: number;
  endTime?: number;
  mainThreadTime?: number;
  total?: number;
  value?: number;
  statistic?: number | string;
  cacheLifetimeMs?: number;
  responseTime?: number;
  serverResponseTime?: number;
  requestCount?: number;
  sub_items?: SubItem[];
}

interface SubItem {
  signal?: string;
  source?: string;
  location?: string;
  url?: string;
  label?: string;
  snippet?: string;
  node_label?: string;
  group_label?: string;
  value?: string | number;
  wastedBytes?: number;
  wastedMs?: number;
  wastedPercent?: number;
  totalBytes?: number;
  duration?: number;
  mainThreadTime?: number;
}

interface Contexto {
  display_value?: string | null;
  title?: string | null;
  description?: string | null;
  details_type?: string | null;
  savings_ms?: number | null;
  savings_bytes?: number | null;
  metric_savings?: Record<string, number> | null;
  numeric_value?: number | null;
  numeric_unit?: string | null;
  warnings?: string[];
  headings?: { key?: string; label?: string; valueType?: string }[];
  items?: Item[];
  audit_id?: string | null;
}

function formatBytes(b?: number | null): string {
  if (b == null) return "—";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KiB`;
  return `${(b / (1024 * 1024)).toFixed(2)} MiB`;
}

function formatMs(ms?: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function shortUrl(u: string): string {
  try {
    const x = new URL(u);
    const path = x.pathname + x.search;
    const tail = path.length > 40 ? "…" + path.slice(-37) : path;
    return `${x.host}${tail}`;
  } catch {
    return u.length > 60 ? u.slice(0, 28) + "…" + u.slice(-28) : u;
  }
}

export function ProblemaDetalhes({
  contexto,
  documentacaoMd,
  threshold,
}: {
  contexto: Contexto;
  documentacaoMd: string;
  threshold?: string | null;
}) {
  const [verMais, setVerMais] = useState(false);
  const items = contexto.items ?? [];
  const limiteInicial = 10;
  // SPEC_CWV_Evidencias_Destacadas: ordena por desperdício decrescente (os
  // piores primeiro). Items sem desperdício mensurável ficam ao final.
  const itemsOrdenados = [...items].sort((a, b) => {
    const pa = a.wastedMs ?? a.wastedBytes ?? a.mainThreadTime ?? 0;
    const pb = b.wastedMs ?? b.wastedBytes ?? b.mainThreadTime ?? 0;
    return pb - pa;
  });
  const itemsVisiveis = verMais ? itemsOrdenados : itemsOrdenados.slice(0, limiteInicial);
  const temItens = items.length > 0;
  const hasSavings = contexto.savings_bytes != null || contexto.savings_ms != null;
  const colWasted = items.some(
    (i) =>
      i.wastedBytes != null ||
      i.wastedMs != null ||
      i.wastedPercent != null ||
      i.mainThreadTime != null
  );
  const colTotal = items.some(
    (i) =>
      i.totalBytes != null ||
      i.transferSize != null ||
      i.duration != null ||
      i.total != null ||
      i.value != null ||
      i.cacheLifetimeMs != null
  );
  const colLabel = items.some(
    (i) =>
      i.label ||
      i.selector ||
      i.snippet ||
      i.node_label ||
      i.source ||
      i.group_label ||
      i.mime_type ||
      i.name
  );

  return (
    <div className="space-y-4 pb-2">
      {(contexto.display_value || hasSavings) && (
        <div className="rounded-lg border bg-amber-50 border-amber-200 px-4 py-3 space-y-2">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-xs font-medium uppercase tracking-wide text-amber-900">
              {hasSavings ? "Economia estimada" : "Valor medido"}
            </span>
            <span className="text-base font-semibold text-amber-900">
              {contexto.display_value ||
                (contexto.savings_bytes != null && formatBytes(contexto.savings_bytes)) ||
                (contexto.savings_ms != null && formatMs(contexto.savings_ms)) ||
                "—"}
            </span>
            {contexto.savings_bytes != null && contexto.display_value && (
              <span className="text-xs text-amber-800">
                · {formatBytes(contexto.savings_bytes)} desperdiçados
              </span>
            )}
            {contexto.savings_ms != null && contexto.display_value && (
              <span className="text-xs text-amber-800">
                · {formatMs(contexto.savings_ms)} de carregamento
              </span>
            )}
          </div>
          {contexto.metric_savings && Object.keys(contexto.metric_savings).length > 0 && (
            <div className="flex flex-wrap gap-2 text-[10px]">
              {Object.entries(contexto.metric_savings)
                .filter(([, v]) => v != null && v !== 0)
                .map(([k, v]) => (
                  <Badge key={k} variant="outline" className="border-amber-300 text-amber-900">
                    {k}: −{formatMs(v)}
                  </Badge>
                ))}
            </div>
          )}
        </div>
      )}

      {contexto.description && (
        <div className="prose prose-sm max-w-none text-muted-foreground">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{contexto.description}</ReactMarkdown>
        </div>
      )}

      {(contexto.warnings ?? []).length > 0 && (
        <div className="rounded border border-yellow-300 bg-yellow-50 px-3 py-2 text-xs text-yellow-900">
          <strong>Avisos:</strong>
          <ul className="mt-1 list-disc pl-5 space-y-0.5">
            {(contexto.warnings ?? []).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {temItens && (
        <div className="rounded-lg border bg-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/40">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Evidências ({items.length})
            </p>
            <div className="flex items-center gap-1">
              {threshold && (
                <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-800" title="Meta de referência para este tipo de problema">
                  meta: {threshold}
                </Badge>
              )}
              {contexto.details_type && (
                <Badge variant="outline" className="text-[10px]">
                  {contexto.details_type}
                </Badge>
              )}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/20 text-muted-foreground">
                <tr>
                  <th className="text-left font-medium px-3 py-2">Recurso</th>
                  {colLabel && <th className="text-left font-medium px-3 py-2">Detalhe</th>}
                  {colWasted && (
                    <th className="text-right font-medium px-3 py-2 whitespace-nowrap">
                      Desperdiçado
                    </th>
                  )}
                  {colTotal && (
                    <th className="text-right font-medium px-3 py-2 whitespace-nowrap">Total</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y">
                {itemsVisiveis.map((it, idx) => {
                  const recursoTexto = it.url || it.group_label || it.selector || it.snippet || it.label || it.name || "—";
                  const isUrl = !!it.url;
                  const detalheCandidatos = [it.label, it.group_label, it.node_label, it.selector, it.snippet, it.source, it.name];
                  const detalheTexto = detalheCandidatos.find((v) => v && v !== recursoTexto) || "";
                  return (
                    <>
                      <tr key={idx} className="hover:bg-muted/30">
                        <td className="px-3 py-2 font-mono text-[11px] break-all max-w-[420px]">
                          {isUrl ? (
                            <a
                              href={it.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-blue-700 hover:underline"
                              title={it.url}
                            >
                              {shortUrl(it.url!)}
                            </a>
                          ) : (
                            <span title={recursoTexto}>{recursoTexto.length > 80 ? recursoTexto.slice(0, 78) + "…" : recursoTexto}</span>
                          )}
                          {it.entity && (
                            <Badge variant="outline" className="ml-2 text-[9px]">
                              {it.entity}
                            </Badge>
                          )}
                        </td>
                        {colLabel && (
                          <td className="px-3 py-2 text-muted-foreground text-[11px] max-w-[280px] truncate" title={detalheTexto || it.mime_type || ""}>
                            {detalheTexto || (it.mime_type ? "" : "—")}
                            {it.mime_type && (
                              <span className="ml-1 text-[9px] text-muted-foreground/70">{detalheTexto ? `(${it.mime_type})` : it.mime_type}</span>
                            )}
                          </td>
                        )}
                        {colWasted && (
                          <td className="px-3 py-2 text-right font-medium whitespace-nowrap text-amber-700">
                            {it.wastedBytes != null
                              ? formatBytes(it.wastedBytes)
                              : it.wastedMs != null
                              ? formatMs(it.wastedMs)
                              : it.mainThreadTime != null
                              ? formatMs(it.mainThreadTime)
                              : "—"}
                            {it.wastedPercent != null && (
                              <span className="ml-1 text-[10px] text-amber-600">
                                ({Math.round(it.wastedPercent)}%)
                              </span>
                            )}
                          </td>
                        )}
                        {colTotal && (
                          <td className="px-3 py-2 text-right whitespace-nowrap text-muted-foreground">
                            {it.totalBytes != null
                              ? formatBytes(it.totalBytes)
                              : it.transferSize != null
                              ? formatBytes(it.transferSize)
                              : it.duration != null
                              ? formatMs(it.duration)
                              : it.cacheLifetimeMs != null
                              ? formatMs(it.cacheLifetimeMs)
                              : it.total != null
                              ? typeof it.total === "number" && it.total > 1000
                                ? formatMs(it.total)
                                : String(it.total)
                              : it.value != null
                              ? String(it.value)
                              : "—"}
                          </td>
                        )}
                      </tr>
                      {(it.sub_items ?? []).map((s, sidx) => (
                        <tr key={`${idx}-${sidx}`} className="bg-muted/10 text-muted-foreground">
                          <td className="px-3 py-1 pl-8 font-mono text-[10px]" colSpan={1}>
                            ↳ {s.signal || s.source || s.location || s.url || "—"}
                          </td>
                          {colLabel && <td className="px-3 py-1" />}
                          {colWasted && (
                            <td className="px-3 py-1 text-right text-[10px] whitespace-nowrap">
                              {s.wastedBytes != null
                                ? formatBytes(s.wastedBytes)
                                : s.wastedMs != null
                                ? formatMs(s.wastedMs)
                                : ""}
                            </td>
                          )}
                          {colTotal && (
                            <td className="px-3 py-1 text-right text-[10px] whitespace-nowrap">
                              {s.totalBytes != null ? formatBytes(s.totalBytes) : ""}
                            </td>
                          )}
                        </tr>
                      ))}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
          {items.length > limiteInicial && (
            <div className="px-4 py-2 border-t bg-muted/20 text-center">
              <button
                onClick={() => setVerMais((v) => !v)}
                className="text-xs text-primary hover:underline"
              >
                {verMais
                  ? `Mostrar apenas ${limiteInicial}`
                  : `Ver todos os ${items.length} recursos`}
              </button>
            </div>
          )}
        </div>
      )}

      {documentacaoMd && (
        <div className="rounded-lg border bg-emerald-50/40 border-emerald-200 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-emerald-900 mb-2">
            Como corrigir
          </p>
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{documentacaoMd}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

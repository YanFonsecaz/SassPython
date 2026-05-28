"use client";

import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import type { CwvProblemaResposta } from "@/lib/api/cwv";
import { ProblemaDetalhes } from "./cwv-problema-detalhes";

function SeveridadeIcon({ severidade }: { severidade: number }) {
  if (severidade >= 4) return <span aria-label="critico" className="text-base">🔴</span>;
  if (severidade >= 3) return <span aria-label="alto" className="text-base">🟠</span>;
  if (severidade >= 2) return <span aria-label="medio" className="text-base">🟡</span>;
  return <span aria-label="baixo" className="text-base">🔵</span>;
}

interface PlanoAcaoProps {
  problemas: CwvProblemaResposta[];
}

export function PlanoAcaoAccordion({ problemas }: PlanoAcaoProps) {
  if (problemas.length === 0) {
    return (
      <div className="rounded-lg border bg-success/5 border-success/20 p-6 text-center">
        <p className="text-sm font-medium text-success">Nenhum problema identificado nessa analise.</p>
        <p className="text-xs text-muted-foreground mt-1">Continue monitorando e re-analisando periodicamente.</p>
      </div>
    );
  }

  const criticos = problemas.filter((p) => p.severidade >= 4).length;

  const tituloCount = new Map<string, number>();
  for (const p of problemas) {
    tituloCount.set(p.titulo, (tituloCount.get(p.titulo) ?? 0) + 1);
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Plano de acao — {problemas.length} problema{problemas.length !== 1 ? "s" : ""}
        {criticos > 0 && <span className="text-destructive font-medium"> · {criticos} critico{criticos !== 1 ? "s" : ""}</span>}
        {" "}· ordenado por prioridade
      </p>

      <Accordion multiple className="space-y-2">
        {problemas.map((p) => {
          const isDuplicate = (tituloCount.get(p.titulo) ?? 0) > 1;
          return (
            <AccordionItem key={p.id} value={p.id}
              className="rounded-xl border bg-card px-4 data-[state=open]:shadow-sm transition-shadow">
              <AccordionTrigger className="hover:no-underline py-3">
                <div className="flex items-center gap-3 text-left flex-1 pr-4">
                  <span className="text-xs text-muted-foreground font-mono shrink-0">#{p.prioridade_ordem}</span>
                  <SeveridadeIcon severidade={p.severidade} />
                  <span className="text-sm font-medium flex-1 truncate">{p.titulo}</span>
                  <div className="flex gap-1 shrink-0">
                    {(p.metricas_afetadas ?? []).map((m) => (
                      <Badge key={m} variant="outline" className="text-[10px] px-1.5">{m}</Badge>
                    ))}
                    {p.severidade >= 4 && <Badge variant="destructive" className="text-[10px] px-1.5">critico</Badge>}
                    {isDuplicate && p.audit_id && (
                      <Badge variant="outline" className="text-[10px] px-1.5 font-mono">{p.audit_id}</Badge>
                    )}
                    {!p.kb_codigo && (
                      <Badge variant="outline" className="text-[10px] px-1.5 border-amber-400 text-amber-700 dark:text-amber-300" title={p.audit_id ? `Audit ${p.audit_id} sem entrada na base de conhecimento` : "Audit sem mapeamento na KB"}>
                        sem mapeamento KB
                      </Badge>
                    )}
                    {p.pesquisado && (
                      <Badge variant="outline" className="text-[10px] px-1.5 border-blue-400 text-blue-700 dark:text-blue-300" title="Documentacao gerada com pesquisa em tempo real">
                        pesquisado em tempo real
                      </Badge>
                    )}
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <ProblemaDetalhes
                  contexto={(p.contexto_especifico ?? {}) as Parameters<typeof ProblemaDetalhes>[0]["contexto"]}
                  documentacaoMd={p.documentacao_md}
                />
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </div>
  );
}

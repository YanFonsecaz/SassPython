"use client";

// Painel de auditorias agênticas na landing do CWV (acesso via sidebar).
// Lista todas as auditorias do usuário; sem cliente_id lista tudo.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2Icon, ShieldCheckIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { listarAuditoriasCwv, type AuditoriaResumo, type FaseAuditoria } from "@/lib/api/cwv";
import { FASE_CORES, FASE_LABELS } from "./auditoria-header";

function pct(v: number | null): string {
  return v === null ? "—" : `${Math.round(v)}%`;
}

export function AuditoriasPainel() {
  const [auditorias, setAuditorias] = useState<AuditoriaResumo[] | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    // SPEC_CWV_Paginacao_Listagens: limit=8 direto do backend (sem slice client-side).
    listarAuditoriasCwv(undefined, { limit: 8 })
      .then((r) => setAuditorias(r.auditorias))
      .catch(() => setErro(true));
  }, []);

  return (
    <div className="glass-card rounded-2xl p-5">
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheckIcon className="size-4 text-brand" />
        <h2 className="text-sm font-semibold">Auditorias</h2>
      </div>

      {erro && (
        <p className="text-xs text-muted-foreground">Não foi possível carregar as auditorias.</p>
      )}
      {!erro && auditorias === null && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2Icon className="size-3 animate-spin" /> Carregando…
        </p>
      )}
      {auditorias !== null && auditorias.length === 0 && (
        <p className="text-xs leading-relaxed text-muted-foreground">
          Nenhuma auditoria ainda. Rode uma análise e clique em{" "}
          <span className="font-medium text-foreground">Criar auditoria</span> no resultado — ela
          vira o checklist before/after do cliente.
        </p>
      )}

      {auditorias !== null && auditorias.length > 0 && (
        <ul className="space-y-2">
          {auditorias.map((a) => (
            <li key={a.id}>
              <Link
                href={`/ferramentas/core-web-vitals/auditoria/${a.id}`}
                className="group block rounded-lg border bg-surface-light px-3 py-2.5 transition-all hover:border-brand/30 hover:shadow-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium group-hover:text-brand-dark">
                    {a.cliente_nome ?? a.titulo}
                  </span>
                  <Badge variant="outline" className={`shrink-0 text-[9px] ${FASE_CORES[a.fase as FaseAuditoria] ?? ""}`}>
                    {FASE_LABELS[a.fase as FaseAuditoria] ?? a.fase}
                  </Badge>
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span>{new Date(a.criado_em).toLocaleDateString("pt-BR")}</span>
                  <span>·</span>
                  <span>{a.n_itens} itens</span>
                  <span>·</span>
                  <span>
                    Health {pct(a.health_score_before)}
                    {a.health_score_after !== null && ` → ${pct(a.health_score_after)}`}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

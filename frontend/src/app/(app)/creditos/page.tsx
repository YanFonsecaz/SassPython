"use client";

import { useCreditos } from "@/hooks/use-creditos";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { StatCard } from "@/components/ui/stat-card";
import { CreditCardIcon, WalletIcon, GiftIcon, ArrowDownIcon, ArrowUpIcon, ClockIcon } from "lucide-react";
import { Separator } from "@/components/ui/separator";

function formatarData(iso: string) {
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function tipoConfig(tipo: string) {
  const map: Record<string, { variant: "default" | "destructive" | "secondary"; label: string; icon: typeof ArrowDownIcon; color: string }> = {
    entrada: { variant: "default", label: "Entrada", icon: ArrowDownIcon, color: "text-success" },
    debito: { variant: "destructive", label: "Debito", icon: ArrowUpIcon, color: "text-destructive" },
    expiracao: { variant: "secondary", label: "Expiracao", icon: ClockIcon, color: "text-muted-foreground" },
    compra: { variant: "default", label: "Compra", icon: ArrowDownIcon, color: "text-success" },
    renovacao: { variant: "default", label: "Renovacao", icon: ArrowDownIcon, color: "text-success" },
  };
  return map[tipo] || { variant: "secondary" as const, label: tipo, icon: ClockIcon, color: "text-muted-foreground" };
}

export default function CreditosPage() {
  const { saldo, transacoes, totalTransacoes, carregando } = useCreditos();

  if (carregando) {
    return (
      <div className="space-y-6">
        <PageHeader title="Creditos" description="Gerencie seus creditos e transacoes" />
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-muted/50 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Creditos" description="Gerencie seus creditos e transacoes" />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Saldo total"
          value={saldo?.saldo_total ?? 0}
          icon={CreditCardIcon}
          variant={saldo && saldo.saldo_total < 20 ? "danger" : "default"}
        />
        <StatCard
          label="Saldo do plano"
          value={saldo?.saldo_plano ?? 0}
          icon={WalletIcon}
          variant="success"
        />
        <StatCard
          label="Saldo extra"
          value={saldo?.saldo_extras ?? 0}
          icon={GiftIcon}
          variant="warning"
        />
      </div>

      {saldo && (
        <p className="text-sm text-muted-foreground">
          Ciclo atual: {formatarData(saldo.ciclo_inicio)} ate {formatarData(saldo.ciclo_fim)}
        </p>
      )}

      <Separator />

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Transacoes</h2>
          <span className="text-sm text-muted-foreground">
            {totalTransacoes} transacao{totalTransacoes !== 1 ? "es" : ""}
          </span>
        </div>

        {transacoes.length === 0 ? (
          <EmptyState
            icon={CreditCardIcon}
            title="Nenhuma transacao"
            description="Suas transacoes de creditos aparecerão aqui."
          />
        ) : (
          <div className="space-y-2">
            {transacoes.map((t) => {
              const cfg = tipoConfig(t.tipo);
              const TipoIcon = cfg.icon;
              return (
                <div
                  key={t.id}
                  className="flex items-center gap-4 rounded-xl border bg-card px-4 py-3 transition-all hover:border-brand/20 animate-fade-in"
                >
                  <div className="flex items-center justify-center size-9 rounded-lg bg-surface-light shrink-0">
                    <TipoIcon className={`size-4 ${cfg.color}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant={cfg.variant}>{cfg.label}</Badge>
                      {t.ferramenta && (
                        <span className="text-xs text-muted-foreground">{t.ferramenta}</span>
                      )}
                    </div>
                    <p className="text-sm truncate mt-0.5">{t.descricao}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className={`text-sm font-semibold ${t.quantidade < 0 ? "text-destructive" : "text-success"}`}>
                      {t.quantidade > 0 ? "+" : ""}{t.quantidade}
                    </p>
                    <p className="text-xs text-muted-foreground">{formatarData(t.criado_em)}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

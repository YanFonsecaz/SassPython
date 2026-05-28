"use client";

import {
  AlertTriangleIcon,
  ClockIcon,
  BanIcon,
  CreditCardIcon,
  RefreshCwIcon,
  XCircleIcon,
} from "lucide-react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";

interface Props {
  motivo?: string | null;
  erroMsg?: string | null;
  saldoAtual?: number | null;
  saldoNecessario?: number | null;
  onTentarNovamente?: () => void;
}

const ICONES = {
  saldo_insuficiente: CreditCardIcon,
  rate_limit: ClockIcon,
  cliente_invalido: BanIcon,
  cliente_removido: BanIcon,
  psi_total: AlertTriangleIcon,
  timeout: ClockIcon,
  cancelada: XCircleIcon,
  erro_interno: AlertTriangleIcon,
} as const;

const TITULOS = {
  saldo_insuficiente: "Saldo insuficiente",
  rate_limit: "Aguarde alguns minutos",
  cliente_invalido: "Cliente inválido",
  cliente_removido: "Cliente foi removido",
  psi_total: "PageSpeed Insights indisponível",
  timeout: "Análise demorou demais",
  cancelada: "Análise cancelada",
  erro_interno: "Erro ao processar análise",
} as const;

const DESCRICOES = {
  rate_limit: "Você atingiu o limite temporário (3 análises a cada 5 minutos).",
  cliente_invalido: "O cliente selecionado é inválido. Recarregue a página.",
  cliente_removido: "O cliente desta análise foi removido. Selecione outro para nova análise.",
  psi_total:
    "Não conseguimos analisar nenhuma URL — provavelmente a cota da Google PSI está esgotada. Os créditos foram devolvidos.",
  timeout: "Tente com menos URLs por análise. Recomendamos no máximo 20 URLs por vez.",
  cancelada: "A análise foi cancelada antes de concluir.",
  erro_interno:
    "Algo inesperado aconteceu. Nossa equipe foi notificada. Tente novamente em alguns minutos.",
} as const;

export function CwvErroExecucao({
  motivo,
  erroMsg,
  saldoAtual,
  saldoNecessario,
  onTentarNovamente,
}: Props) {
  const motivoKey = (motivo ?? "erro_interno") as keyof typeof ICONES;
  const Icon = ICONES[motivoKey] ?? AlertTriangleIcon;
  const titulo = TITULOS[motivoKey] ?? "Erro ao processar análise";
  const descricao =
    motivoKey === "saldo_insuficiente" ? null : (DESCRICOES[motivoKey as keyof typeof DESCRICOES] ?? erroMsg);

  return (
    <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-6 sm:p-8">
      <div className="flex items-start gap-4">
        <div className="flex items-center justify-center size-12 rounded-full bg-destructive/10 shrink-0">
          <Icon className="size-6 text-destructive" />
        </div>
        <div className="space-y-3 flex-1">
          <h3 className="text-lg font-semibold">{titulo}</h3>
          {motivoKey === "saldo_insuficiente" ? (
            <>
              <p className="text-sm text-muted-foreground">
                Saldo: <b>{saldoAtual ?? "—"}</b> · Necessário: <b>{saldoNecessario ?? "—"}</b>
              </p>
              <div className="pt-2">
                <Link href="/creditos" className={buttonVariants()}>
                  Comprar créditos
                </Link>
              </div>
            </>
          ) : (
            <>
              {descricao && <p className="text-sm text-muted-foreground">{descricao}</p>}
              {(motivoKey === "erro_interno" || motivoKey === "timeout" || motivoKey === "cancelada") && (
                <div className="pt-2">
                  <Button variant="outline" onClick={onTentarNovamente}>
                    <RefreshCwIcon className="size-4 mr-1" /> Tentar novamente
                  </Button>
                </div>
              )}
              {motivoKey === "psi_total" && (
                <div className="pt-2">
                  <Link
                    href="/ferramentas/core-web-vitals"
                    className={buttonVariants({ variant: "outline" })}
                  >
                    Tentar mais tarde
                  </Link>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

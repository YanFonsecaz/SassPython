"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { ArrowLeftIcon, CheckCircle2Icon, Loader2Icon, ArrowRightIcon } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { createSSEConnection } from "@/lib/sse-client";
import { buscarExecucaoCwv } from "@/lib/api/cwv";
import { CwvErroExecucao } from "@/components/cwv/cwv-erro-execucao";

interface ExecucaoCwv {
  id: string;
  ferramenta: string;
  status: string;
  etapa_atual: string | null;
  creditos_cobrados: number;
  criado_em: string;
  resultado_json: Record<string, unknown> | null;
  erro_msg: string | null;
  concluida_em: string | null;
}

export function CwvExecucaoClient() {
  const pathname = usePathname();
  const id = pathname.split("/").filter(Boolean).pop() || "";
  const [execucao, setExecucao] = useState<ExecucaoCwv | null>(null);
  const [etapaAtual, setEtapaAtual] = useState<string | null>(null);
  const [statusFinal, setStatusFinal] = useState<string | null>(null);
  const [erroMsg, setErroMsg] = useState<string | null>(null);
  const [conectandoSSE, setConectandoSSE] = useState(false);
  const closeRef = useRef<{ close: () => void } | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (!id) return;
    buscarExecucaoCwv(id).then((dados) => {
      setExecucao(dados);
      setEtapaAtual(dados.etapa_atual);
      if (["concluida", "falhou", "cancelada"].includes(dados.status)) {
        setStatusFinal(dados.status);
        setErroMsg(dados.erro_msg);
      }
    }).catch(() => {
      setErroMsg("Execucao nao encontrada");
      setStatusFinal("falhou");
    });
  }, [id]);

  useEffect(() => {
    if (!id || statusFinal) return;

    const close = createSSEConnection(
      `/ferramentas/historico/${id}/progresso`,
      (data: unknown) => {
        if (typeof data !== "object" || data === null) return;
        const evt = data as Record<string, unknown>;
        const type = evt.type as string;

        if (type === "status") {
          setEtapaAtual(evt.etapa as string | null);
          setExecucao((prev) => prev ? { ...prev, status: evt.status as string, etapa_atual: evt.etapa as string | null } : prev);
        } else if (type === "node_progress") {
          setEtapaAtual(evt.detail as string | null);
        } else if (type === "concluida") {
          setStatusFinal("concluida");
          setConectandoSSE(false);
          buscarExecucaoCwv(id).then(setExecucao);
        } else if (type === "falhou") {
          setStatusFinal("falhou");
          setErroMsg((evt.erro as string) || "Erro desconhecido");
          setConectandoSSE(false);
        }
      },
      {
        onComplete: () => setConectandoSSE(false),
        onError: () => { setConectandoSSE(false); setErroMsg("Erro na conexao"); },
      }
    );
    closeRef.current = close;
    setConectandoSSE(true);

    return () => { close.close(); closeRef.current = null; };
  }, [id, statusFinal]);

  if (!execucao && !erroMsg) {
    return (
      <div className="space-y-6">
        <PageHeader title="Core Web Vitals" description="Carregando..." />
        <div className="max-w-lg mx-auto space-y-4">
          <div className="h-8 rounded-lg bg-muted/50 animate-pulse" />
          <div className="h-24 rounded-xl bg-muted/50 animate-pulse" />
        </div>
      </div>
    );
  }

  const resultado = execucao?.resultado_json as Record<string, unknown> | null;
  const analiseIds = (resultado?.analise_ids as string[]) ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Core Web Vitals"
        description="Processando analise..."
        action={
          <Link href="/ferramentas/core-web-vitals" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" /> Voltar
          </Link>
        }
      />

      <div className="max-w-lg mx-auto">
        <div className="glass-card rounded-2xl p-6 sm:p-8 space-y-6">
          {statusFinal === "concluida" ? (
            <>
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center size-12 rounded-full bg-success/10">
                  <CheckCircle2Icon className="size-6 text-success" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">Analise concluida!</h2>
                  <p className="text-sm text-muted-foreground">
                    {execucao?.creditos_cobrados ?? 0} creditos cobrados
                  </p>
                </div>
              </div>

              {analiseIds.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">{analiseIds.length} URL{analiseIds.length !== 1 ? "s" : ""} analisada{analiseIds.length !== 1 ? "s" : ""}:</p>
                  <div className="space-y-1.5">
                    {analiseIds.map((aId) => (
                      <Link key={aId} href={`/ferramentas/core-web-vitals/url/${aId}`}
                        className="flex items-center gap-3 rounded-lg border bg-surface-light px-3 py-2.5 group transition-all hover:border-brand/30 hover:shadow-sm">
                        <ArrowRightIcon className="size-4 text-muted-foreground group-hover:text-brand-dark transition-colors shrink-0" />
                        <span className="text-sm font-medium text-brand-dark">Ver dashboard</span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <Button variant="outline" onClick={() => router.push("/ferramentas/core-web-vitals")}>
                  Nova analise
                </Button>
              </div>
            </>
          ) : statusFinal === "falhou" ? (
            <CwvErroExecucao
              motivo={(execucao?.resultado_json as { motivo_falha?: string } | null)?.motivo_falha}
              erroMsg={erroMsg}
              onTentarNovamente={() => router.push("/ferramentas/core-web-vitals")}
            />
          ) : (
            <>
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center size-12 rounded-full bg-brand/10">
                  <Loader2Icon className="size-6 text-brand-dark animate-spin" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">Analisando URLs...</h2>
                  <p className="text-sm text-muted-foreground">{etapaAtual || "Aguardando..."}</p>
                </div>
              </div>
              <div className="space-y-2">
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div className="h-full rounded-full gradient-bg animate-pulse w-2/3" />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

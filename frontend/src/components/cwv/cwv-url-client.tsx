"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { notFound } from "next/navigation";
import { DashboardUrlClient } from "@/components/cwv/cwv-dashboard-client";
import { buscarAnaliseCwv, buscarHistoricoUrlCwv, buscarIrmaCwv } from "@/lib/api/cwv";
import type { CwvAnaliseResposta, CwvAnaliseResumo } from "@/lib/api/cwv";

export type CwvEstrategia = "mobile" | "desktop";

export function CwvUrlClient() {
  const pathname = usePathname();
  const analiseId = pathname.split("/").filter(Boolean).pop() || "";

  const [analiseAtual, setAnaliseAtual] = useState<CwvAnaliseResposta | null>(null);
  const [irma, setIrma] = useState<CwvAnaliseResposta | null>(null);
  const [estrategiaAtiva, setEstrategiaAtiva] = useState<CwvEstrategia>("mobile");
  const [historico, setHistorico] = useState<CwvAnaliseResumo[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [naoEncontrado, setNaoEncontrado] = useState(false);

  useEffect(() => {
    if (!analiseId) return;

    async function load() {
      setCarregando(true);
      setNaoEncontrado(false);
      try {
        const analise = await buscarAnaliseCwv(analiseId);
        setAnaliseAtual(analise);
        setEstrategiaAtiva(analise.estrategia as CwvEstrategia);

        try {
          const irmaRes = await buscarIrmaCwv(analiseId);
          setIrma(irmaRes.analise);
        } catch {
        }
      } catch {
        setNaoEncontrado(true);
      } finally {
        setCarregando(false);
      }
    }
    load();
  }, [analiseId]);

  // Histórico/evolução acompanham a estratégia ativa (mobile↔mobile, desktop↔desktop).
  // Re-busca ao trocar o toggle para não mostrar a evolução da estratégia errada.
  useEffect(() => {
    if (!analiseAtual) return;
    let cancelado = false;
    buscarHistoricoUrlCwv(analiseAtual.cliente_id, analiseAtual.url_canonica, estrategiaAtiva)
      .then((hist) => {
        if (!cancelado) setHistorico(hist.analises ?? []);
      })
      .catch(() => {});
    return () => {
      cancelado = true;
    };
  }, [analiseAtual, estrategiaAtiva]);

  if (naoEncontrado) notFound();

  if (carregando || !analiseAtual) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 bg-muted/50 rounded animate-pulse" />
        <div className="max-w-4xl space-y-6">
          <div className="h-[300px] rounded-2xl bg-muted/50 animate-pulse" />
        </div>
      </div>
    );
  }

  const analiseExibida = analiseAtual.estrategia === estrategiaAtiva ? analiseAtual : irma;
  const irmaExiste = irma !== null;

  return (
    <DashboardUrlClient
      analiseAtual={analiseExibida ?? analiseAtual}
      irma={irma}
      irmaExiste={irmaExiste}
      estrategiaAtiva={estrategiaAtiva}
      onTrocarEstrategia={setEstrategiaAtiva}
      historico={historico}
      clienteId={analiseAtual.cliente_id}
    />
  );
}

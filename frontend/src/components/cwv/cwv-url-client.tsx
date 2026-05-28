"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { notFound } from "next/navigation";
import { DashboardUrlClient } from "@/components/cwv/cwv-dashboard-client";
import { buscarAnaliseCwv, buscarHistoricoUrlCwv } from "@/lib/api/cwv";
import type { CwvAnaliseResposta, CwvAnaliseResumo } from "@/lib/api/cwv";

export function CwvUrlClient() {
  const pathname = usePathname();
  const analiseId = pathname.split("/").filter(Boolean).pop() || "";

  const [analiseAtual, setAnaliseAtual] = useState<CwvAnaliseResposta | null>(null);
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

        try {
          const hist = await buscarHistoricoUrlCwv(analise.cliente_id, analise.url_canonica);
          setHistorico(hist.analises ?? []);
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

  return (
    <DashboardUrlClient
      analiseAtual={analiseAtual}
      historico={historico}
      clienteId={analiseAtual.cliente_id}
    />
  );
}

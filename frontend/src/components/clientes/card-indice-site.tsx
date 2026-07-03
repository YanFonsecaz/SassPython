"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, mensagemErroAmigavel } from "@/lib/api";
import { GlobeIcon, RefreshCwIcon, LoaderIcon, CheckCircleIcon, AlertCircleIcon } from "lucide-react";
import type { IndiceSiteStatus, IndexarSiteResponse } from "@/types";

/**
 * SPEC_Inlinks_Descoberta_Automatica_Candidatas — card "Índice do site" na
 * página do cliente. Mostra status, nº de páginas, última atualização e dispara
 * a indexação/reindexação (cobrança estimada pelo teto).
 */
export function CardIndiceSite({ clienteId }: { clienteId: string }) {
  const [indice, setIndice] = useState<IndiceSiteStatus | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [indexando, setIndexando] = useState(false);

  async function carregar() {
    setCarregando(true);
    try {
      const dados = await api.get<IndiceSiteStatus>(`/clientes/${clienteId}/indice-site`);
      setIndice(dados);
    } catch {
      setIndice(null);
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    carregar();
    // Polla enquanto estiver indexando.
    const intervalo = setInterval(() => {
      if (indice?.status === "indexando") carregar();
    }, 5000);
    return () => clearInterval(intervalo);
  }, [clienteId, indice?.status]);

  async function indexar() {
    setIndexando(true);
    try {
      const resp = await api.post<IndexarSiteResponse>(`/clientes/${clienteId}/indexar-site`, {});
      toast.success(
        `Indexação iniciada (custo estimado: até ${resp.custo_maximo_estimado} créditos).`,
      );
      // Marca como indexando imediatamente para a UI refletir.
      setIndice({ ...indice, status: "indexando", dominio: resp.dominio, n_paginas: 0, n_falhas: 0, atualizado_em: null, erro_msg: null });
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setIndexando(false);
    }
  }

  if (carregando) {
    return (
      <div className="rounded-xl border bg-card p-4 flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderIcon className="size-4 animate-spin" /> Carregando índice…
      </div>
    );
  }

  const status = indice?.status ?? "nao_indexado";
  const indexandoAgora = status === "indexando";

  return (
    <div className="rounded-xl border bg-card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GlobeIcon className="size-4 text-brand" />
          <h3 className="text-sm font-semibold">Índice do site</h3>
        </div>
        <BadgeStatus status={status} />
      </div>

      {indice?.dominio && (
        <p className="text-xs text-muted-foreground truncate">{indice.dominio}</p>
      )}

      {status === "pronto" && indice && (
        <div className="flex gap-4 text-xs">
          <span className="text-muted-foreground">
            <strong className="text-foreground">{indice.n_paginas}</strong> páginas indexadas
          </span>
          {indice.n_falhas > 0 && (
            <span className="text-muted-foreground">
              <strong className="text-foreground">{indice.n_falhas}</strong> falhas
            </span>
          )}
          {indice.atualizado_em && (
            <span className="text-muted-foreground">
              atualizado em {new Date(indice.atualizado_em).toLocaleDateString("pt-BR")}
            </span>
          )}
        </div>
      )}

      {status === "falhou" && indice?.erro_msg && (
        <p className="text-xs text-destructive">{indice.erro_msg}</p>
      )}

      {status === "nao_indexado" && (
        <p className="text-xs text-muted-foreground">
          Indexe o site do cliente (via sitemap) para descobrir automaticamente
          páginas candidatas a inlinks nas ferramentas Receber e Distribuir.
        </p>
      )}

      <Button
        type="button"
        variant={indexandoAgora ? "outline" : "default"}
        size="sm"
        onClick={indexar}
        disabled={indexando || indexandoAgora}
      >
        {indexando || indexandoAgora ? (
          <LoaderIcon className="size-4 animate-spin" />
        ) : status === "pronto" ? (
          <RefreshCwIcon className="size-4" />
        ) : (
          <GlobeIcon className="size-4" />
        )}
        {status === "pronto" ? "Reindexar" : "Indexar site"}
      </Button>
    </div>
  );
}

function BadgeStatus({ status }: { status: IndiceSiteStatus["status"] }) {
  if (status === "pronto")
    return (
      <Badge className="bg-success/10 text-success border-success/30">
        <CheckCircleIcon className="size-3 mr-1" /> Pronto
      </Badge>
    );
  if (status === "indexando")
    return (
      <Badge className="bg-brand/15 text-brand-dark border-brand/30">
        <LoaderIcon className="size-3 mr-1 animate-spin" /> Indexando
      </Badge>
    );
  if (status === "falhou")
    return (
      <Badge variant="destructive">
        <AlertCircleIcon className="size-3 mr-1" /> Falhou
      </Badge>
    );
  return <Badge variant="outline">Não indexado</Badge>;
}

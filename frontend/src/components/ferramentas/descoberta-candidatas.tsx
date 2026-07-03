"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { api, mensagemErroAmigavel } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SearchIcon, SparklesIcon, LoaderIcon } from "lucide-react";
import type {
  ClienteResumido,
  IndiceSiteStatus,
  CandidataSugerida,
} from "@/types";

interface Props {
  /** "receber" usa a URL do pilar como consulta; "distribuir" usa a URL alvo. */
  modo: "receber" | "distribuir";
  /** URL que serve de consulta à descoberta (pilar no receber, alvo no distribuir). */
  urlConsulta: string;
  /** URLs já presentes na lista — para não sugerir duplicatas. */
  urlsJaPresentes: string[];
  /** Recebe as URLs selecionadas pelo usuário. */
  onAdicionar: (urls: string[]) => void;
}

/**
 * SPEC_Inlinks_Descoberta_Automatica_Candidatas: componente de descoberta
 * reutilizável nos dois formulários. O usuário escolhe o cliente, clica em
 * "Buscar candidatas do site", revisa a lista sugerida (com score) e adiciona
 * as selecionadas. Sem índice, oferece CTA para indexar na página do cliente.
 */
export function DescobertaCandidatas({ modo, urlConsulta, urlsJaPresentes, onAdicionar }: Props) {
  const [clientes, setClientes] = useState<ClienteResumido[]>([]);
  const [clienteId, setClienteId] = useState<string>("");
  const [indice, setIndice] = useState<IndiceSiteStatus | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [sugestoes, setSugestoes] = useState<CandidataSugerida[]>([]);
  const [selecionadas, setSelecionadas] = useState<Set<string>>(new Set());
  const [erro, setErro] = useState("");

  // Carrega a lista de clientes do usuário.
  useEffect(() => {
    api
      .get<{ clientes: ClienteResumido[]; total: number }>("/clientes?limite=100")
      .then((d) => setClientes(d.clientes))
      .catch(() => setClientes([]));
  }, []);

  // Ao selecionar um cliente, checa o status do índice.
  useEffect(() => {
    if (!clienteId) {
      setIndice(null);
      return;
    }
    api
      .get<IndiceSiteStatus>(`/clientes/${clienteId}/indice-site`)
      .then(setIndice)
      .catch(() => setIndice(null));
  }, [clienteId]);

  const buscar = useCallback(async () => {
    if (!clienteId || !urlConsulta) return;
    setBuscando(true);
    setErro("");
    setSugestoes([]);
    setSelecionadas(new Set());
    try {
      const resp = await api.get<{ candidatas: CandidataSugerida[] }>(
        `/clientes/${clienteId}/candidatas?modo=${modo}&url=${encodeURIComponent(urlConsulta)}&k=30`,
      );
      setSugestoes(resp.candidatas);
      // Pré-marca as top-10.
      setSelecionadas(new Set(resp.candidatas.slice(0, 10).map((c) => c.url)));
      if (resp.candidatas.length === 0) {
        setErro("Nenhuma candidata encontrada no índice para esta consulta.");
      }
    } catch (e) {
      setErro(mensagemErroAmigavel(e));
    } finally {
      setBuscando(false);
    }
  }, [clienteId, urlConsulta, modo]);

  function toggle(url: string) {
    setSelecionadas((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  function adicionarSelecionadas() {
    const novas = [...selecionadas].filter((u) => !urlsJaPresentes.includes(u));
    if (novas.length === 0) {
      setErro("Todas as selecionadas já estão na lista.");
      return;
    }
    onAdicionar(novas);
    setSugestoes([]);
    setSelecionadas(new Set());
    setErro("");
  }

  const indicePronto = indice?.status === "pronto";

  return (
    <div className="rounded-xl border bg-surface-light p-4 space-y-3">
      <div className="flex items-center gap-2">
        <SparklesIcon className="size-4 text-brand" />
        <h4 className="text-sm font-semibold">Descobrir candidatas do site</h4>
      </div>

      <div className="space-y-2">
        <Label htmlFor="cliente-descoberta" className="text-xs text-muted-foreground">
          Cliente (índice do site)
        </Label>
        <select
          id="cliente-descoberta"
          value={clienteId}
          onChange={(e) => setClienteId(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        >
          <option value="">Selecione um cliente…</option>
          {clientes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nome}
            </option>
          ))}
        </select>
      </div>

      {clienteId && indice && !indicePronto && (
        <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
          {indice.status === "nao_indexado" && "Este cliente ainda não tem o site indexado."}
          {indice.status === "indexando" && "Indexação em andamento — aguarde concluir para buscar."}
          {indice.status === "falhou" && `Falha na indexação${indice.erro_msg ? `: ${indice.erro_msg}` : ""}.`}
          {" "}
          <a href={`/clientes/${clienteId}`} className="underline">
            Ir para a página do cliente para indexar
          </a>
          .
        </div>
      )}

      {indicePronto && (
        <p className="text-xs text-muted-foreground">
          Índice pronto: {indice.n_paginas} páginas.{" "}
          {urlConsulta
            ? "A busca usa a URL acima como consulta."
            : "Preencha a URL de consulta para buscar."}
        </p>
      )}

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={buscar}
        disabled={!indicePronto || !urlConsulta || buscando}
        className="w-full"
      >
        {buscando ? (
          <LoaderIcon className="size-4 animate-spin" />
        ) : (
          <SearchIcon className="size-4" />
        )}
        Buscar candidatas do site
      </Button>

      {sugestoes.length > 0 && (
        <div className="space-y-2">
          <div className="max-h-64 space-y-1 overflow-y-auto">
            {sugestoes.map((s) => {
              const jaPresente = urlsJaPresentes.includes(s.url);
              const checked = selecionadas.has(s.url);
              return (
                <label
                  key={s.url}
                  className={cn(
                    "flex items-start gap-2 rounded-md border p-2 text-xs cursor-pointer hover:bg-muted/50",
                    jaPresente && "opacity-50",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked && !jaPresente}
                    disabled={jaPresente}
                    onChange={() => toggle(s.url)}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{s.titulo || s.url}</span>
                      <Badge variant="outline" className="shrink-0 font-mono">
                        {(s.score * 100).toFixed(0)}%
                      </Badge>
                    </div>
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block truncate text-muted-foreground hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {s.url}
                    </a>
                    {jaPresente && <span className="text-muted-foreground">já na lista</span>}
                  </div>
                </label>
              );
            })}
          </div>
          <Button type="button" size="sm" onClick={adicionarSelecionadas} className="w-full">
            Adicionar {selecionadas.size} selecionada{selecionadas.size !== 1 ? "s" : ""}
          </Button>
        </div>
      )}

      {erro && <p className="text-xs text-destructive">{erro}</p>}
    </div>
  );
}

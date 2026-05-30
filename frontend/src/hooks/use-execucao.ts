"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { createSSEConnection } from "@/lib/sse-client";
import type {
  Execucao,
  ExecucaoCriada,
  GerarArtigoRequest,
  SSEStatusEvent,
  SSEConcluidaEvent,
  SSEFalhouEvent,
  SSENodeProgressEvent,
  NodeActivity,
} from "@/types";

interface UseExecucaoReturn {
  listarErro: string | null;
  execucao: Execucao | null;
  etapaAtual: string | null;
  statusFinal: string | null;
  erro: string | null;
  carregando: boolean;
  conectandoSSE: boolean;
  nodeHistory: NodeActivity[];
  currentNodeDetail: string | null;
  criarExecucao: (
    dados: GerarArtigoRequest
  ) => Promise<ExecucaoCriada | null>;
  aprovar: (
    id: string,
    acao: "aprovar" | "reprovar",
    feedback?: string
  ) => Promise<boolean>;
  cancelar: (id: string) => Promise<boolean>;
  conectarProgresso: (id: string) => () => void;
  desconectarProgresso: () => void;
  carregarExecucao: (id: string) => Promise<void>;
  execucoes: Execucao[];
  total: number;
  listar: (offset?: number) => Promise<void>;
  buscar: (busca: string) => Promise<void>;
}

export function useExecucao(): UseExecucaoReturn {
  const [execucao, setExecucao] = useState<Execucao | null>(null);
  const [etapaAtual, setEtapaAtual] = useState<string | null>(null);
  const [statusFinal, setStatusFinal] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [conectandoSSE, setConectandoSSE] = useState(false);
  const [nodeHistory, setNodeHistory] = useState<NodeActivity[]>([]);
  const [currentNodeDetail, setCurrentNodeDetail] = useState<string | null>(null);
  const [execucoes, setExecucoes] = useState<Execucao[]>([]);
  const [total, setTotal] = useState(0);
  const [listarErro, setListarErro] = useState<string | null>(null);
  const closeRef = useRef<(() => void) | null>(null);

  const desconectarProgresso = useCallback(() => {
    if (closeRef.current) {
      closeRef.current();
      closeRef.current = null;
    }
  }, []);

  const conectarProgresso = useCallback(
    (id: string) => {
      desconectarProgresso();
      setConectandoSSE(true);
      setNodeHistory([]);
      setCurrentNodeDetail(null);

      const { close } = createSSEConnection(
        `/ferramentas/historico/${id}/progresso`,
        (data: unknown) => {
          if (typeof data !== "object" || data === null) return;

          const evt = data as
            | SSEStatusEvent
            | SSEConcluidaEvent
            | SSEFalhouEvent
            | SSENodeProgressEvent;

          if (evt.type === "status") {
            setEtapaAtual(evt.etapa);
            setExecucao((prev) =>
              prev
                ? { ...prev, status: evt.status, etapa_atual: evt.etapa }
                : { id: "", ferramenta: "", status: evt.status, etapa_atual: evt.etapa, creditos_cobrados: 0, criado_em: "", concluida_em: null, erro_msg: null, tentativas_revisao: 0, tentativas_feedback: 0 }
            );
          } else if (evt.type === "node_progress") {
            const activity: NodeActivity = {
              node: evt.node,
              detail: evt.detail,
              timestamp: evt.timestamp,
              isStart: evt.detail.endsWith("..."),
            };
            setNodeHistory((prev) => [...prev, activity]);
            setCurrentNodeDetail(evt.detail);
          } else if (evt.type === "concluida") {
            setStatusFinal("concluida");
            setConectandoSSE(false);
            setCurrentNodeDetail(null);
          } else if (evt.type === "falhou") {
            setStatusFinal("falhou");
            setErro(evt.erro || "Erro desconhecido");
            setConectandoSSE(false);
            setCurrentNodeDetail(null);
          }
        },
        {
          onComplete: () => {
            setConectandoSSE(false);
          },
          onError: () => {
            setConectandoSSE(false);
            setErro("Erro na conexao de progresso");
          },
        }
      );

      closeRef.current = close;
      return desconectarProgresso;
    },
    [desconectarProgresso]
  );

  const criarExecucao = useCallback(
    async (
      dados: GerarArtigoRequest
    ): Promise<ExecucaoCriada | null> => {
      try {
        setCarregando(true);
        return await api.post<ExecucaoCriada>(
          "/ferramentas/gerar-artigo",
          dados
        );
      } catch {
        return null;
      } finally {
        setCarregando(false);
      }
    },
    []
  );

  const aprovar = useCallback(
    async (
      id: string,
      acao: "aprovar" | "reprovar",
      feedback?: string
    ): Promise<boolean> => {
      try {
        await api.post(`/ferramentas/historico/${id}/aprovacao`, {
          acao,
          feedback,
        });
        return true;
      } catch {
        return false;
      }
    },
    []
  );

  const cancelar = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        await api.post(`/ferramentas/historico/${id}/cancelar`);
        return true;
      } catch {
        return false;
      }
    },
    []
  );

  const carregarExecucao = useCallback(async (id: string) => {
    setCarregando(true);
    try {
      const dados = await api.get<Execucao>(
        `/ferramentas/historico/${id}`
      );
      setExecucao(dados);
      setEtapaAtual(dados.etapa_atual);
      if (
        dados.status === "concluida" ||
        dados.status === "falhou" ||
        dados.status === "cancelada"
      ) {
        setStatusFinal(dados.status);
      }
    } catch {
      setErro("Execucao nao encontrada");
    } finally {
      setCarregando(false);
    }
  }, []);

  const listar = useCallback(async (offset = 0) => {
    try {
      setListarErro(null);
      const dados = await api.get<{
        execucoes: Execucao[];
        total: number;
      }>(`/ferramentas/historico?offset=${offset}`, { noRefresh: true });
      setExecucoes(dados.execucoes);
      setTotal(dados.total);
    } catch {
      setListarErro("Não foi possível carregar o histórico de execuções.");
    }
  }, []);

  const buscar = useCallback(
    async (busca: string) => {
      if (!busca.trim()) {
        await listar();
      } else {
        try {
          const dados = await api.get<{
            execucoes: Execucao[];
            total: number;
          }>(
            `/ferramentas/historico?busca=${encodeURIComponent(busca)}`,
            { noRefresh: true }
          );
          setExecucoes(dados.execucoes);
          setTotal(dados.total);
        } catch {
          setListarErro("Não foi possível buscar execuções.");
        }
      }
    },
    [listar]
  );

  useEffect(() => {
    return () => {
      desconectarProgresso();
    };
  }, [desconectarProgresso]);

  return {
    execucao,
    etapaAtual,
    statusFinal,
    erro,
    carregando,
    conectandoSSE,
    nodeHistory,
    currentNodeDetail,
    criarExecucao,
    aprovar,
    cancelar,
    conectarProgresso,
    desconectarProgresso,
    carregarExecucao,
    execucoes,
    total,
    listar,
    buscar,
    listarErro,
  };
}

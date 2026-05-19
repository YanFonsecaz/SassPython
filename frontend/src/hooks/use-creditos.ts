"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Saldo, TransacaoCredito } from "@/types";

interface UseCreditosReturn {
  saldo: Saldo | null;
  transacoes: TransacaoCredito[];
  totalTransacoes: number;
  carregando: boolean;
  recarregarSaldo: () => Promise<void>;
  carregarTransacoes: (limite?: number, offset?: number) => Promise<void>;
}

export function useCreditos(): UseCreditosReturn {
  const [saldo, setSaldo] = useState<Saldo | null>(null);
  const [transacoes, setTransacoes] = useState<TransacaoCredito[]>([]);
  const [totalTransacoes, setTotalTransacoes] = useState(0);
  const [carregando, setCarregando] = useState(true);

  const recarregarSaldo = useCallback(async () => {
    try {
      const dados = await api.get<Saldo>("/creditos/saldo");
      setSaldo(dados);
    } catch {
      // silent
    }
  }, []);

  const carregarTransacoes = useCallback(async () => {
    try {
      const dados = await api.get<{
        transacoes: TransacaoCredito[];
        total: number;
      }>("/creditos/transacoes");
      setTransacoes(dados.transacoes);
      setTotalTransacoes(dados.total);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    async function init() {
      setCarregando(true);
      await Promise.all([recarregarSaldo(), carregarTransacoes()]);
      setCarregando(false);
    }
    init();
  }, [recarregarSaldo, carregarTransacoes]);

  return {
    saldo,
    transacoes,
    totalTransacoes,
    carregando,
    recarregarSaldo,
    carregarTransacoes,
  };
}

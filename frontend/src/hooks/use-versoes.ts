"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import type { VersaoArtigo } from "@/types";

interface UseVersoesReturn {
  versoes: VersaoArtigo[];
  carregando: boolean;
  carregar: (execucaoId: string) => Promise<void>;
}

export function useVersoes(): UseVersoesReturn {
  const [versoes, setVersoes] = useState<VersaoArtigo[]>([]);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async (execucaoId: string) => {
    setCarregando(true);
    try {
      const dados = await api.get<{
        execucao_id: string;
        versoes: VersaoArtigo[];
      }>(`/ferramentas/historico/${execucaoId}/versoes`);
      setVersoes(dados.versoes);
    } catch {
      setVersoes([]);
    } finally {
      setCarregando(false);
    }
  }, []);

  return { versoes, carregando, carregar };
}

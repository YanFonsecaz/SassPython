"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import type {
  Cliente,
  ClienteCreate,
  ClienteUpdate,
  ClienteListResponse,
} from "@/types";

interface UseClientesReturn {
  clientes: Cliente[];
  total: number;
  carregando: boolean;
  listar: (busca?: string, limite?: number, offset?: number) => Promise<void>;
  buscar: (id: string) => Promise<Cliente | null>;
  criar: (dados: ClienteCreate) => Promise<Cliente>;
  atualizar: (
    id: string,
    dados: ClienteUpdate
  ) => Promise<Cliente | null>;
  remover: (id: string) => Promise<boolean>;
}

export function useClientes(): UseClientesReturn {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [total, setTotal] = useState(0);
  const [carregando, setCarregando] = useState(true);

  const listar = useCallback(
    async (busca = "", limite = 50, offset = 0) => {
      setCarregando(true);
      try {
        const params = new URLSearchParams();
        if (busca) params.set("busca", busca);
        params.set("limite", String(limite));
        params.set("offset", String(offset));

        const dados = await api.get<ClienteListResponse>(
          `/clientes?${params.toString()}`
        );
        setClientes(dados.clientes);
        setTotal(dados.total);
      } catch {
        toast.error("Erro ao carregar clientes");
      } finally {
        setCarregando(false);
      }
    },
    []
  );

  const buscar = useCallback(async (id: string): Promise<Cliente | null> => {
    try {
      return await api.get<Cliente>(`/clientes/${id}`);
    } catch {
      return null;
    }
  }, []);

  const criar = useCallback(
    async (dados: ClienteCreate): Promise<Cliente> => {
      const cliente = await api.post<Cliente>("/clientes", dados);
      setClientes((prev) => [cliente, ...prev]);
      setTotal((prev) => prev + 1);
      return cliente;
    },
    []
  );

  const atualizar = useCallback(
    async (
      id: string,
      dados: ClienteUpdate
    ): Promise<Cliente | null> => {
      try {
        const cliente = await api.put<Cliente>(`/clientes/${id}`, dados);
        setClientes((prev) =>
          prev.map((c) => (c.id === id ? cliente : c))
        );
        return cliente;
      } catch {
        return null;
      }
    },
    []
  );

  const remover = useCallback(async (id: string): Promise<boolean> => {
    try {
      await api.delete(`/clientes/${id}`);
      setClientes((prev) => prev.filter((c) => c.id !== id));
      setTotal((prev) => prev - 1);
      return true;
    } catch {
      return false;
    }
  }, []);

  useEffect(() => {
    async function load() {
      setCarregando(true);
      try {
        const params = new URLSearchParams({
          limite: "50",
          offset: "0",
        });
        const dados = await api.get<ClienteListResponse>(
          `/clientes?${params.toString()}`
        );
        setClientes(dados.clientes);
        setTotal(dados.total);
      } catch {
        toast.error("Erro ao carregar clientes");
      } finally {
        setCarregando(false);
      }
    }
    load();
  }, []);

  return { clientes, total, carregando, listar, buscar, criar, atualizar, remover };
}

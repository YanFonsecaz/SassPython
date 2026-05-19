"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { FormularioCliente } from "@/components/clientes/formulario-cliente";
import { api } from "@/lib/api";
import type { Cliente } from "@/types";

export function ClienteDetalheConteudo() {
  const params = useParams();
  const id = params.id as string;
  const [cliente, setCliente] = useState<Cliente | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [removido, setRemovido] = useState(false);

  useEffect(() => {
    async function carregar() {
      try {
        const dados = await api.get<Cliente>(`/clientes/${id}`);
        setCliente(dados);
      } catch {
        // not found
      } finally {
        setCarregando(false);
      }
    }
    carregar();
  }, [id]);

  if (carregando) {
    return <p className="text-sm text-muted-foreground">Carregando...</p>;
  }

  if (!cliente || removido) {
    return (
      <div className="text-center py-12 space-y-3">
        <p className="text-muted-foreground">Cliente nao encontrado</p>
        <Link
          href="/clientes"
          className={buttonVariants({ size: "sm" })}
        >
          Voltar para clientes
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{cliente.nome}</h1>
        <div className="flex gap-2">
          <button
            onClick={async () => {
              try {
                await api.delete(`/clientes/${id}`);
                setRemovido(true);
              } catch {
                // error
              }
            }}
            className={buttonVariants({
              variant: "destructive",
              size: "sm",
            })}
          >
            Excluir
          </button>
        </div>
      </div>

      <FormularioCliente cliente={cliente} />
    </div>
  );
}

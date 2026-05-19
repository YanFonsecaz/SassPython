"use client";

import { useState } from "react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { useClientes } from "@/hooks/use-clientes";
import { CardCliente } from "@/components/clientes/card-cliente";
import { SearchIcon } from "lucide-react";

export default function ClientesPage() {
  const { clientes, total, carregando, listar, remover } = useClientes();
  const [busca, setBusca] = useState("");
  const [removendo, setRemovendo] = useState<string | null>(null);

  function handleBuscar(e: React.FormEvent) {
    e.preventDefault();
    listar(busca);
  }

  async function handleRemover(id: string) {
    setRemovendo(id);
    await remover(id);
    setRemovendo(null);
  }

  if (carregando && clientes.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="Clientes" description="Gerencie seus clientes e configuracoes" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-32 rounded-xl bg-muted/50 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Clientes"
        description={`${total} cliente${total !== 1 ? "s" : ""}`}
        action={
          <Link href="/clientes/novo" className={buttonVariants()}>
            Novo cliente
          </Link>
        }
      />

      <form onSubmit={handleBuscar} className="relative">
        <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <Input
          placeholder="Buscar clientes..."
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          className="pl-9"
        />
      </form>

      {clientes.length === 0 ? (
        <EmptyState
          icon={SearchIcon}
          title="Nenhum cliente encontrado"
          description={busca ? "Tente uma busca diferente." : "Cadastre seu primeiro cliente para comecar."}
          action={!busca && (
            <Link href="/clientes/novo" className={buttonVariants()}>
              Cadastrar primeiro cliente
            </Link>
          )}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {clientes
            .filter((c) => c.ativo)
            .map((cliente) => (
              <CardCliente
                key={cliente.id}
                cliente={cliente}
                onExcluir={removendo !== cliente.id ? handleRemover : undefined}
              />
            ))}
        </div>
      )}
    </div>
  );
}

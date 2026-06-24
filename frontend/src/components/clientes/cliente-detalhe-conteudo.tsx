"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { buttonVariants } from "@/components/ui/button";
import { FormularioCliente } from "@/components/clientes/formulario-cliente";
import { api, mensagemErroAmigavel } from "@/lib/api";
import type { Cliente } from "@/types";

export function ClienteDetalheConteudo() {
  // Em export estatico, useParams() devolve o "placeholder" embutido no build,
  // entao lemos o id real direto da URL (mesmo padrao do CWV).
  const pathname = usePathname();
  const router = useRouter();
  const id = pathname.split("/").filter(Boolean).pop() || "";
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
      <Link
        href="/clientes"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        &larr; Voltar para clientes
      </Link>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{cliente.nome}</h1>
        <div className="flex gap-2">
          <button
            onClick={async () => {
              if (!window.confirm("Tem certeza que deseja excluir este cliente?")) return;
              try {
                await api.delete(`/clientes/${id}`);
                setRemovido(true);
                toast.success("Cliente excluido");
                router.push("/clientes");
              } catch (err) {
                toast.error(mensagemErroAmigavel(err));
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

      <FormularioCliente
        cliente={cliente}
        onSucesso={(atualizado) => {
          setCliente(atualizado);
          toast.success("Alteracoes salvas");
        }}
      />
    </div>
  );
}

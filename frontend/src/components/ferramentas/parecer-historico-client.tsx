"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { useClientes } from "@/hooks/use-clientes";
import { listarPareceres, type ParecerResumo } from "@/lib/api/parecer";
import { mensagemErroAmigavel } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ArrowLeftIcon,
  FileTextIcon,
  Loader2Icon,
  PlusIcon,
  ImageIcon,
} from "lucide-react";

function dataFormatada(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function ParecerHistoricoClient() {
  const router = useRouter();
  const { clientes, carregando: carregandoClientes } = useClientes();
  const [clienteFilter, setClienteFilter] = useState("");
  const [pareceres, setPareceres] = useState<ParecerResumo[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    setCarregando(true);
    setErro(null);
    try {
      const r = await listarPareceres(clienteFilter || undefined);
      setPareceres(r.pareceres);
    } catch (e) {
      setErro(mensagemErroAmigavel(e));
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    carregar();
  }, [clienteFilter]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Meus Pareceres"
        description="Histórico de pareceres técnicos gerados"
        action={
          <div className="flex items-center gap-2">
            <Link
              href="/ferramentas/parecer"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              <ArrowLeftIcon className="size-4 mr-1" />
              Voltar
            </Link>
            <Link
              href="/ferramentas/parecer"
              className={buttonVariants({ variant: "default", size: "sm" })}
            >
              <PlusIcon className="size-4" />
              Novo Parecer
            </Link>
          </div>
        }
      />

      <div className="max-w-4xl animate-slide-up">
        <div className="glass-card rounded-2xl p-6 sm:p-8">
          {erro && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 mb-6">
              <p className="text-sm text-destructive" role="alert">{erro}</p>
              <Button variant="outline" size="sm" className="mt-2" onClick={carregar}>
                Tentar novamente
              </Button>
            </div>
          )}

          {clientes.length > 1 && (
            <div className="mb-6">
              <label className="text-sm font-medium text-muted-foreground mb-2 block">Filtrar por cliente</label>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => setClienteFilter("")}
                  className={cn(
                    "rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors",
                    !clienteFilter ? "border-brand bg-brand/5 text-brand-dark" : "text-muted-foreground hover:bg-surface-light"
                  )}
                >
                  Todos
                </button>
                {clientes.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setClienteFilter(c.id)}
                    className={cn(
                      "rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors",
                      clienteFilter === c.id ? "border-brand bg-brand/5 text-brand-dark" : "text-muted-foreground hover:bg-surface-light"
                    )}
                  >
                    {c.nome}
                  </button>
                ))}
              </div>
            </div>
          )}

          {carregando ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-16 rounded-lg bg-muted/30 animate-pulse" />
              ))}
            </div>
          ) : pareceres.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center">
              <FileTextIcon className="size-10 text-muted-foreground/40 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                Você ainda não gerou nenhum parecer.
              </p>
              <Link
                href="/ferramentas/parecer"
                className="inline-flex items-center gap-1.5 mt-3 text-sm font-medium text-brand-dark hover:underline"
              >
                <PlusIcon className="size-4" />
                Criar primeiro parecer
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {pareceres.map((p) => (
                <Link
                  key={p.id}
                  href={`/ferramentas/parecer/${p.id}`}
                  className="flex items-center gap-4 rounded-lg border px-4 py-3 transition-colors hover:bg-surface-light group"
                >
                  <div className="flex items-center justify-center size-9 rounded-lg bg-brand/10 shrink-0">
                    <FileTextIcon className="size-4 text-brand-dark" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{p.titulo}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-muted-foreground">{p.cliente_nome}</span>
                      {p.site && (
                        <>
                          <span className="text-xs text-muted-foreground/40">&middot;</span>
                          <span className="text-xs text-muted-foreground truncate">{p.site}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {p.n_imagens > 0 && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <ImageIcon className="size-3" />
                        {p.n_imagens}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {dataFormatada(p.criado_em)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

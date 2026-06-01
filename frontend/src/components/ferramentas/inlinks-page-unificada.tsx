"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeftIcon, ChevronLeftIcon } from "lucide-react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { FormularioInlinks } from "@/components/ferramentas/formulario-inlinks";
import { FormularioDistribuirInlinks } from "@/components/ferramentas/formulario-distribuir-inlinks";
import { InlinksSeletorModo, type ModoInlinks } from "@/components/ferramentas/inlinks-seletor-modo";
import { ComoUsar } from "@/components/ferramentas/como-usar";

const MODOS_VALIDOS: ModoInlinks[] = ["receber", "distribuir"];

export function InlinksPageUnificada() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [modo, setModo] = useState<ModoInlinks | null>(null);

  useEffect(() => {
    const m = searchParams.get("modo") as ModoInlinks | null;
    setModo(m && MODOS_VALIDOS.includes(m) ? m : null);
  }, [searchParams]);

  const trocarModo = useCallback((novoModo: ModoInlinks) => {
    setModo(novoModo);
    const params = new URLSearchParams(searchParams.toString());
    params.set("modo", novoModo);
    router.replace(`/ferramentas/inlinks?${params.toString()}`, { scroll: false });
  }, [router, searchParams]);

  const limparModo = useCallback(() => {
    setModo(null);
    router.replace("/ferramentas/inlinks", { scroll: false });
  }, [router]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inlinks Internos"
        description="Links entre páginas do seu site que melhoram SEO e a leitura"
        action={
          <div className="flex items-center gap-1">
            <ComoUsar ferramenta="inlinks" />
            <Link href="/ferramentas" className={buttonVariants({ variant: "ghost", size: "sm" })}>
              <ArrowLeftIcon className="size-4 mr-1" />
              Voltar
            </Link>
          </div>
        }
      />

      {modo === null ? (
        <InlinksSeletorModo onSelecionar={trocarModo} />
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-xl border bg-surface-light p-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex items-center justify-center size-9 rounded-lg gradient-bg shrink-0">
                <span className="text-white text-sm font-bold">
                  {modo === "receber" ? "↓" : "↑"}
                </span>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">
                  {modo === "receber" ? "Receber links" : "Distribuir um link"}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {modo === "receber"
                    ? "Um artigo recebe links de várias páginas"
                    : "Uma URL é linkada em várias páginas"}
                </p>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={limparModo}>
              <ChevronLeftIcon className="size-4 mr-1" />
              Trocar modo
            </Button>
          </div>

          {modo === "receber" ? <FormularioInlinks /> : <FormularioDistribuirInlinks />}
        </div>
      )}
    </div>
  );
}

"use client";

import { FormularioGerarArtigo } from "@/components/ferramentas/formulario-gerar-artigo";
import { PageHeader } from "@/components/ui/page-header";
import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

export default function GerarArtigoPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Gerar Artigo"
        description="Configure e crie seu artigo otimizado para SEO"
        action={
          <Link href="/ferramentas" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" />
            Voltar
          </Link>
        }
      />
      <FormularioGerarArtigo />
    </div>
  );
}

"use client";

import Link from "next/link";
import { ArrowLeftIcon } from "lucide-react";
import { FormularioCliente } from "@/components/clientes/formulario-cliente";
import { PageHeader } from "@/components/ui/page-header";
import { buttonVariants } from "@/components/ui/button";

export default function NovoClientePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Novo cliente"
        description="Cadastre um site/marca para gerar conteúdo e auditar performance"
        action={
          <Link href="/clientes" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" /> Voltar
          </Link>
        }
      />
      <FormularioCliente />
    </div>
  );
}

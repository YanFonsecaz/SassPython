"use client";

import { FormularioCliente } from "@/components/clientes/formulario-cliente";

export default function NovoClientePage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Novo Cliente</h1>
      <FormularioCliente />
    </div>
  );
}

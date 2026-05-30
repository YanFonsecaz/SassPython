"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { FormularioConfigurarMfa } from "@/components/auth/formulario-configurar-mfa";
import { PageHeader } from "@/components/ui/page-header";

export default function ConfigurarMfaPage() {
  const router = useRouter();
  const { usuario } = useAuth();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Configurar MFA"
        description="Autenticação em duas etapas para proteger sua conta"
      />
      <div className="max-w-md">
        <FormularioConfigurarMfa
          mfaAtivo={usuario!.mfa_ativo}
          onSucesso={() => router.push("/perfil")}
          onVoltar={() => router.push("/perfil")}
        />
      </div>
    </div>
  );
}

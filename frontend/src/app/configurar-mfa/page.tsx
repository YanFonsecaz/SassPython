"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { FormularioConfigurarMfa } from "@/components/auth/formulario-configurar-mfa";

export default function ConfigurarMfaPage() {
  const router = useRouter();
  const { usuario } = useAuth();

  if (!usuario) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <p className="text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <FormularioConfigurarMfa
        mfaAtivo={usuario.mfa_ativo}
        onSucesso={() => router.push("/perfil")}
        onVoltar={() => router.push("/perfil")}
      />
    </div>
  );
}

"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { FormularioResetarSenha } from "@/components/auth/formulario-resetar-senha";
import { AlertTriangleIcon } from "lucide-react";

function ResetarSenhaConteudo() {
  const searchParams = useSearchParams();
  const tokenUrl = searchParams.get("token");
  const [sucesso, setSucesso] = useState(false);

  if (sucesso) {
    return (
      <div className="relative z-10 w-full max-w-md animate-slide-up">
        <div className="glass-card rounded-2xl p-8 text-center">
          <h2 className="text-lg font-semibold">Senha redefinida</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Sua senha foi alterada com sucesso. Voce ja pode fazer login com a nova senha.
          </p>
          <a
            href="/login"
            className="mt-6 inline-block text-sm text-brand-dark underline-offset-4 hover:underline transition-colors"
          >
            Ir para o login
          </a>
        </div>
      </div>
    );
  }

  if (!tokenUrl) {
    return (
      <div className="relative z-10 w-full max-w-md animate-slide-up">
        <div className="glass-card rounded-2xl p-8 text-center">
          <div className="mx-auto mb-4 flex items-center justify-center size-12 rounded-full bg-warning/10">
            <AlertTriangleIcon className="size-6 text-warning" />
          </div>
          <h2 className="text-lg font-semibold">Token invalido</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            O link de redefinicao de senha e invalido ou expirou. Solicite uma nova recuperacao.
          </p>
          <a
            href="/recuperar-senha"
            className="mt-6 inline-block text-sm text-brand-dark underline-offset-4 hover:underline transition-colors"
          >
            Solicitar recuperacao
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="relative z-10 w-full max-w-md animate-slide-up">
      <FormularioResetarSenha token={tokenUrl} onSucesso={() => setSucesso(true)} />
    </div>
  );
}

export default function ResetarSenhaPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center px-4 bg-surface overflow-hidden">
      <div className="pointer-events-none absolute -top-40 -right-40 h-[500px] w-[500px] rounded-full bg-brand/15 blur-[120px]" />
      <div className="pointer-events-none absolute -bottom-40 -left-40 h-[400px] w-[400px] rounded-full bg-brand-dark/20 blur-[100px]" />
      <div className="absolute inset-0 bg-dot-pattern opacity-30" />
      <Suspense>
        <ResetarSenhaConteudo />
      </Suspense>
    </div>
  );
}

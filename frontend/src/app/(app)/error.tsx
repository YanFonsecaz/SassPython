"use client";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { RefreshCwIcon } from "lucide-react";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="space-y-6 p-6 max-w-lg mx-auto">
      <ErrorState
        title="Algo deu errado"
        description={error.message || "Ocorreu um erro inesperado. Tente recarregar a página."}
        action={
          <div className="flex gap-2">
            <Button onClick={reset} variant="outline">
              <RefreshCwIcon className="size-4 mr-1" /> Tentar novamente
            </Button>
            <Button variant="ghost" onClick={() => window.location.href = "/ferramentas"}>
              Ir para o início
            </Button>
          </div>
        }
      />
    </div>
  );
}

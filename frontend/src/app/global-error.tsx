"use client";

import { ErrorState } from "@/components/ui/error-state";
import { Button } from "@/components/ui/button";
import { RefreshCwIcon } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body style={{ margin: 0, padding: "1rem", fontFamily: "system-ui, sans-serif" }}>
        <ErrorState
          title="Erro inesperado"
          description="Ocorreu um erro crítico. Tente recarregar a página."
          action={
            <div className="flex gap-2">
              <Button onClick={reset} variant="outline">
                <RefreshCwIcon className="size-4 mr-1" /> Tentar novamente
              </Button>
              <Button variant="ghost" onClick={() => window.location.href = "/"}>Página inicial</Button>
            </div>
          }
        />
      </body>
    </html>
  );
}

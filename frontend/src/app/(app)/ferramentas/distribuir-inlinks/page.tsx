"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DistribuirInlinksRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/ferramentas/inlinks?modo=distribuir");
  }, [router]);
  return (
    <div className="text-center py-12 text-sm text-muted-foreground">
      Redirecionando para a nova rota unificada...
    </div>
  );
}

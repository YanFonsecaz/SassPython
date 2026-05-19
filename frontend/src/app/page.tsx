"use client";

import { useEffect } from "react";
import { useAuth } from "@/hooks/use-auth";
import { useRouter } from "next/navigation";

export default function Home() {
  const { carregando, autenticado } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (carregando) return;
    if (autenticado) {
      router.push("/ferramentas");
    } else {
      router.push("/login");
    }
  }, [carregando, autenticado, router]);

  if (carregando) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p>Carregando...</p>
      </div>
    );
  }

  return null;
}
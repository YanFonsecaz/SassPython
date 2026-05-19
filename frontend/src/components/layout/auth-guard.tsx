"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { Sidebar } from "@/components/layout/sidebar";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { carregando, autenticado } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (carregando) return;
    if (!autenticado) {
      router.push("/login");
    }
  }, [carregando, autenticado, router]);

  if (carregando) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="size-8 rounded-lg gradient-bg animate-pulse" />
          <p className="text-sm text-muted-foreground">Carregando...</p>
        </div>
      </div>
    );
  }

  if (!autenticado) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background bg-dot-pattern">
      <Sidebar />
      <main className="lg:pl-64">
        <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
          {children}
        </div>
      </main>
    </div>
  );
}

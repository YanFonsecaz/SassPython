"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormularioMfa } from "@/components/auth/formulario-mfa";
import type { ApiError } from "@/types";

export function FormularioLogin() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [mfaData, setMfaData] = useState<{
    token_temporario: string;
    tipo: string;
  } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    setEnviando(true);

    try {
      const resultado = await login(email, senha);
      if (resultado.tipo === "mfa" && resultado.token_temporario) {
        setMfaData({
          token_temporario: resultado.token_temporario,
          tipo: "totp",
        });
      } else {
        router.push("/ferramentas");
      }
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao fazer login");
    } finally {
      setEnviando(false);
    }
  }

  if (mfaData) {
    return (
      <FormularioMfa
        tokenTemporario={mfaData.token_temporario}
        tipo={mfaData.tipo}
        onSucesso={() => router.push("/ferramentas")}
        onVoltar={() => setMfaData(null)}
      />
    );
  }

  return (
    <div className="glass-card rounded-2xl p-6 sm:p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Entrar</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Acesse sua conta para continuar
        </p>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="space-y-4">
          {erro && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
              <p className="text-sm text-destructive" role="alert">{erro}</p>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="email" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              E-mail
            </Label>
            <Input
              id="email"
              type="email"
              placeholder="seu@email.com"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={enviando}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="senha" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Senha
            </Label>
            <Input
              id="senha"
              type="password"
              placeholder="Sua senha"
              required
              autoComplete="current-password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              disabled={enviando}
            />
          </div>
        </div>
        <div className="mt-6 space-y-4">
          <Button type="submit" className="w-full gradient-bg border-0 hover:opacity-90 transition-opacity" disabled={enviando}>
            {enviando ? "Entrando..." : "Entrar"}
          </Button>
          <div className="flex w-full justify-between text-sm">
            <a
              href="/cadastro"
              className="text-muted-foreground hover:text-brand-dark underline-offset-4 hover:underline transition-colors"
            >
              Criar conta
            </a>
            <a
              href="/recuperar-senha"
              className="text-muted-foreground hover:text-brand-dark underline-offset-4 hover:underline transition-colors"
            >
              Esqueci a senha
            </a>
          </div>
        </div>
      </form>
    </div>
  );
}

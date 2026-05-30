"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ApiError } from "@/types";

interface FormularioMfaProps {
  tokenTemporario: string;
  tipo: string;
  onSucesso: () => void;
  onVoltar: () => void;
}

export function FormularioMfa({
  tokenTemporario,
  tipo,
  onSucesso,
  onVoltar,
}: FormularioMfaProps) {
  const { verificarMfa } = useAuth();
  const [codigo, setCodigo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro("");

    if (codigo.length !== 6 || !/^\d{6}$/.test(codigo)) {
      setErro("Digite o codigo de 6 digitos");
      return;
    }

    setEnviando(true);
    try {
      await verificarMfa(tokenTemporario, codigo);
      onSucesso();
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Código inválido");
    } finally {
      setEnviando(false);
    }
  }

  const descricao =
    tipo === "totp"
      ? "Abra seu app autenticador e digite o codigo de 6 digitos"
      : "Insira seu dispositivo de seguranca para continuar";

  return (
    <div className="glass-card rounded-2xl p-6 sm:p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Verificacao em duas etapas</h2>
        <p className="text-sm text-muted-foreground mt-0.5">{descricao}</p>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="space-y-4">
          {erro && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
              <p className="text-sm text-destructive" role="alert">{erro}</p>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="codigo-totp" className="text-sm font-medium text-muted-foreground">Codigo</Label>
            <Input
              id="codigo-totp"
              type="text"
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              placeholder="000000"
              required
              autoComplete="one-time-code"
              value={codigo}
              onChange={(e) => {
                const apenasDigitos = e.target.value.replace(/\D/g, "").slice(0, 6);
                setCodigo(apenasDigitos);
              }}
              disabled={enviando}
            />
          </div>
        </div>
        <div className="mt-6 space-y-3">
          <Button type="submit" className="w-full gradient-bg border-0 hover:opacity-90 transition-opacity" disabled={enviando || codigo.length !== 6}>
            {enviando ? "Verificando..." : "Verificar"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="w-full text-muted-foreground"
            onClick={onVoltar}
            disabled={enviando}
          >
            Voltar ao login
          </Button>
        </div>
      </form>
    </div>
  );
}

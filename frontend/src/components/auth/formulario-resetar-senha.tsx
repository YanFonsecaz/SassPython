"use client";

import { useState } from "react";
import { validarSenha } from "@/lib/validar-senha";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ApiError, MensagemResponse, ResetarSenhaRequest } from "@/types";

interface FormularioResetarSenhaProps {
  token: string;
  onSucesso: () => void;
}

export function FormularioResetarSenha({
  token,
  onSucesso,
}: FormularioResetarSenhaProps) {
  const [novaSenha, setNovaSenha] = useState("");
  const [novaSenhaConfirmacao, setNovaSenhaConfirmacao] = useState("");
  const [errosSenha, setErrosSenha] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  function handleSenhaChange(valor: string) {
    setNovaSenha(valor);
    if (valor.length === 0) {
      setErrosSenha([]);
      return;
    }
    const resultado = validarSenha(valor);
    setErrosSenha(resultado.erros);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro("");

    if (novaSenha !== novaSenhaConfirmacao) {
      setErro("As senhas não conferem");
      return;
    }

    const validacao = validarSenha(novaSenha);
    if (!validacao.valida) {
      setErrosSenha(validacao.erros);
      setErro("Corrija os erros na senha");
      return;
    }

    setEnviando(true);
    try {
      await api.post<MensagemResponse>(
        "/auth/resetar-senha",
        {
          token,
          nova_senha: novaSenha,
          nova_senha_confirmacao: novaSenhaConfirmacao,
        } satisfies ResetarSenhaRequest,
        { noAuth: true }
      );
      onSucesso();
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao redefinir senha");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="glass-card rounded-2xl p-6 sm:p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Redefinir senha</h2>
        <p className="text-sm text-muted-foreground mt-0.5">Digite sua nova senha abaixo</p>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="space-y-4">
          {erro && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
              <p className="text-sm text-destructive" role="alert">{erro}</p>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="nova-senha" className="text-sm font-medium text-muted-foreground">Nova senha</Label>
            <Input
              id="nova-senha"
              type="password"
              placeholder="Minimo 12 caracteres"
              required
              minLength={12}
              maxLength={64}
              autoComplete="new-password"
              value={novaSenha}
              onChange={(e) => handleSenhaChange(e.target.value)}
              disabled={enviando}
            />
            {errosSenha.length > 0 && (
              <ul className="text-xs text-destructive space-y-0.5">
                {errosSenha.map((msg) => (<li key={msg}>{msg}</li>))}
              </ul>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="nova-senha-confirmacao" className="text-sm font-medium text-muted-foreground">Confirmar nova senha</Label>
            <Input
              id="nova-senha-confirmacao"
              type="password"
              placeholder="Repita a nova senha"
              required
              minLength={12}
              maxLength={64}
              autoComplete="new-password"
              value={novaSenhaConfirmacao}
              onChange={(e) => setNovaSenhaConfirmacao(e.target.value)}
              disabled={enviando}
            />
          </div>
        </div>
        <div className="mt-6 space-y-4">
          <Button type="submit" className="w-full gradient-bg border-0 hover:opacity-90 transition-opacity" disabled={enviando}>
            {enviando ? "Redefinindo..." : "Redefinir senha"}
          </Button>
          <a href="/login" className="block text-center text-sm text-muted-foreground hover:text-brand-dark underline-offset-4 hover:underline transition-colors">Voltar ao login</a>
        </div>
      </form>
    </div>
  );
}

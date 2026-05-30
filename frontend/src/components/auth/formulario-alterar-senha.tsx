"use client";

import { useState } from "react";
import { validarSenha } from "@/lib/validar-senha";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AlterarSenhaRequest, ApiError, MensagemResponse } from "@/types";

interface FormularioAlterarSenhaProps {
  mfaAtivo: boolean;
  onSucesso: () => void;
}

export function FormularioAlterarSenha({
  mfaAtivo,
  onSucesso,
}: FormularioAlterarSenhaProps) {
  const [senhaAtual, setSenhaAtual] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [novaSenhaConfirmacao, setNovaSenhaConfirmacao] = useState("");
  const [codigoTotp, setCodigoTotp] = useState("");
  const [errosSenha, setErrosSenha] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState(false);

  function handleNovaSenhaChange(valor: string) {
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
    setSucesso(false);

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

    if (mfaAtivo && (codigoTotp.length !== 6 || !/^\d{6}$/.test(codigoTotp))) {
      setErro("Digite o codigo MFA de 6 digitos");
      return;
    }

    setEnviando(true);
    try {
      const body: AlterarSenhaRequest = {
        senha_atual: senhaAtual,
        nova_senha: novaSenha,
        nova_senha_confirmacao: novaSenhaConfirmacao,
      };
      if (mfaAtivo) {
        body.codigo_totp = codigoTotp;
      }
      await api.put<MensagemResponse>("/auth/alterar-senha", body);
      setSucesso(true);
      setSenhaAtual("");
      setNovaSenha("");
      setNovaSenhaConfirmacao("");
      setCodigoTotp("");
      setErrosSenha([]);
      onSucesso();
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao alterar senha");
    } finally {
      setEnviando(false);
    }
  }

  if (sucesso) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Senha alterada</CardTitle>
          <CardDescription>
            Sua senha foi alterada com sucesso.
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Button
            type="button"
            variant="ghost"
            className="w-full"
            onClick={() => setSucesso(false)}
          >
            Alterar novamente
          </Button>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Alterar senha</CardTitle>
        <CardDescription>
          Atualize sua senha de acesso
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          {erro && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
              <p className="text-sm text-destructive" role="alert">
                {erro}
              </p>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="senha-atual">Senha atual</Label>
            <Input
              id="senha-atual"
              type="password"
              placeholder="Sua senha atual"
              required
              autoComplete="current-password"
              value={senhaAtual}
              onChange={(e) => setSenhaAtual(e.target.value)}
              disabled={enviando}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="nova-senha">Nova senha</Label>
            <Input
              id="nova-senha"
              type="password"
              placeholder="Minimo 12 caracteres"
              required
              minLength={12}
              maxLength={64}
              autoComplete="new-password"
              value={novaSenha}
              onChange={(e) => handleNovaSenhaChange(e.target.value)}
              disabled={enviando}
            />
            {errosSenha.length > 0 && (
              <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
                <ul className="text-sm text-destructive space-y-1">
                  {errosSenha.map((msg) => (
                    <li key={msg}>{msg}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="nova-senha-confirmacao">Confirmar nova senha</Label>
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
          {mfaAtivo && (
            <div className="space-y-2">
              <Label htmlFor="codigo-totp-alterar">Codigo MFA</Label>
              <Input
                id="codigo-totp-alterar"
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                placeholder="000000"
                required
                autoComplete="one-time-code"
                value={codigoTotp}
                onChange={(e) => {
                  const apenasDigitos = e.target.value.replace(/\D/g, "").slice(0, 6);
                  setCodigoTotp(apenasDigitos);
                }}
                disabled={enviando}
              />
            </div>
          )}
        </CardContent>
        <CardFooter>
          <Button type="submit" className="w-full" disabled={enviando}>
            {enviando ? "Alterando..." : "Alterar senha"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

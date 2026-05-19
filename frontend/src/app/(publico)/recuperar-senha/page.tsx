"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { validarSenha } from "@/lib/validar-senha";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CheckCircleIcon } from "lucide-react";
import type { ApiError, MensagemResponse, RecuperarSenhaRequest, ResetarSenhaRequest } from "@/types";

function RecuperarSenhaConteudo() {
  const searchParams = useSearchParams();
  const tokenUrl = searchParams.get("token");
  const [token, setToken] = useState(tokenUrl || "");
  const [etapa, setEtapa] = useState<"solicitar" | "resetar" | "sucesso">(
    tokenUrl ? "resetar" : "solicitar"
  );
  const [email, setEmail] = useState("");
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

  async function handleSolicitar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      await api.post<MensagemResponse>(
        "/auth/recuperar-senha",
        { email } satisfies RecuperarSenhaRequest,
        { noAuth: true }
      );
      setEtapa("sucesso");
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao solicitar recuperacao");
    } finally {
      setEnviando(false);
    }
  }

  async function handleResetar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");

    if (novaSenha !== novaSenhaConfirmacao) {
      setErro("As senhas nao conferem");
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
      setEtapa("sucesso");
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao redefinir senha");
    } finally {
      setEnviando(false);
    }
  }

  if (etapa === "sucesso") {
    return (
      <div className="relative z-10 w-full max-w-md animate-slide-up">
        <div className="glass-card rounded-2xl p-8 text-center">
          <div className="mx-auto mb-4 flex items-center justify-center size-12 rounded-full bg-success/10">
            <CheckCircleIcon className="size-6 text-success" />
          </div>
          <h2 className="text-lg font-semibold">Sucesso</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Se este e-mail esta cadastrado, voce recebera as instrucoes para redefinir sua senha.
          </p>
          <a
            href="/login"
            className="mt-6 inline-block text-sm text-brand-dark hover:underline underline-offset-4 transition-colors"
          >
            Voltar ao login
          </a>
        </div>
      </div>
    );
  }

  if (etapa === "resetar") {
    return (
      <div className="relative z-10 w-full max-w-md animate-slide-up">
        <div className="glass-card rounded-2xl p-6 sm:p-8">
          <div className="mb-6">
            <h2 className="text-lg font-semibold">Redefinir senha</h2>
            <p className="text-sm text-muted-foreground mt-0.5">Digite sua nova senha abaixo</p>
          </div>
          <form onSubmit={handleResetar}>
            <div className="space-y-4">
              {erro && (
                <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
                  <p className="text-sm text-destructive" role="alert">{erro}</p>
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="token" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Token</Label>
                <Input id="token" type="text" required value={token} onChange={(e) => setToken(e.target.value)} disabled={enviando} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="nova-senha" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Nova senha</Label>
                <Input
                  id="nova-senha" type="password" placeholder="Minimo 12 caracteres" required minLength={12} maxLength={64}
                  autoComplete="new-password" value={novaSenha} onChange={(e) => handleSenhaChange(e.target.value)} disabled={enviando}
                />
                {errosSenha.length > 0 && (
                  <ul className="text-xs text-destructive space-y-0.5">{errosSenha.map((msg) => (<li key={msg}>{msg}</li>))}</ul>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="nova-senha-confirmacao" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Confirmar nova senha</Label>
                <Input
                  id="nova-senha-confirmacao" type="password" placeholder="Repita a nova senha" required minLength={12} maxLength={64}
                  autoComplete="new-password" value={novaSenhaConfirmacao} onChange={(e) => setNovaSenhaConfirmacao(e.target.value)} disabled={enviando}
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
      </div>
    );
  }

  return (
    <div className="relative z-10 w-full max-w-md animate-slide-up">
      <div className="glass-card rounded-2xl p-6 sm:p-8">
        <div className="mb-6">
          <h2 className="text-lg font-semibold">Recuperar senha</h2>
          <p className="text-sm text-muted-foreground mt-0.5">Informe seu e-mail para receber as instrucoes</p>
        </div>
        <form onSubmit={handleSolicitar}>
          <div className="space-y-4">
            {erro && (
              <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
                <p className="text-sm text-destructive" role="alert">{erro}</p>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="email" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">E-mail</Label>
              <Input id="email" type="email" placeholder="seu@email.com" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={enviando} />
            </div>
          </div>
          <div className="mt-6 space-y-4">
            <Button type="submit" className="w-full gradient-bg border-0 hover:opacity-90 transition-opacity" disabled={enviando}>
              {enviando ? "Enviando..." : "Enviar instrucoes"}
            </Button>
            <a href="/login" className="block text-center text-sm text-muted-foreground hover:text-brand-dark underline-offset-4 hover:underline transition-colors">Voltar ao login</a>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function RecuperarSenhaPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center px-4 bg-surface overflow-hidden">
      <div className="pointer-events-none absolute -top-40 -right-40 h-[500px] w-[500px] rounded-full bg-brand/15 blur-[120px]" />
      <div className="pointer-events-none absolute -bottom-40 -left-40 h-[400px] w-[400px] rounded-full bg-brand-dark/20 blur-[100px]" />
      <div className="absolute inset-0 bg-dot-pattern opacity-30" />
      <Suspense>
        <RecuperarSenhaConteudo />
      </Suspense>
    </div>
  );
}

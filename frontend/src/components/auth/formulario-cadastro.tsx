"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { validarSenha } from "@/lib/validar-senha";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ApiError, CadastroRequest } from "@/types";

export function FormularioCadastro() {
  const router = useRouter();
  const { cadastro } = useAuth();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [senhaConfirmacao, setSenhaConfirmacao] = useState("");
  const [errosSenha, setErrosSenha] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  function handleSenhaChange(valor: string) {
    setSenha(valor);
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

    if (senha !== senhaConfirmacao) {
      setErro("As senhas nao conferem");
      return;
    }

    const validacao = validarSenha(senha);
    if (!validacao.valida) {
      setErrosSenha(validacao.erros);
      setErro("Corrija os erros na senha");
      return;
    }

    setEnviando(true);
    try {
      await cadastro({
        nome,
        email,
        senha,
        senha_confirmacao: senhaConfirmacao,
      } satisfies CadastroRequest);
      router.push("/ferramentas");
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao criar conta");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="glass-card rounded-2xl p-6 sm:p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Criar conta</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Preencha seus dados para comecar
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
            <Label htmlFor="nome" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Nome
            </Label>
            <Input
              id="nome"
              type="text"
              placeholder="Seu nome"
              required
              minLength={1}
              maxLength={255}
              autoComplete="name"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              disabled={enviando}
            />
          </div>
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
              placeholder="Minimo 12 caracteres"
              required
              minLength={12}
              maxLength={64}
              autoComplete="new-password"
              value={senha}
              onChange={(e) => handleSenhaChange(e.target.value)}
              disabled={enviando}
            />
            {errosSenha.length > 0 && (
              <ul className="text-xs text-destructive space-y-0.5">
                {errosSenha.map((msg) => (
                  <li key={msg}>{msg}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="senha-confirmacao" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Confirmar senha
            </Label>
            <Input
              id="senha-confirmacao"
              type="password"
              placeholder="Repita a senha"
              required
              minLength={12}
              maxLength={64}
              autoComplete="new-password"
              value={senhaConfirmacao}
              onChange={(e) => setSenhaConfirmacao(e.target.value)}
              disabled={enviando}
            />
          </div>
        </div>
        <div className="mt-6 space-y-4">
          <Button type="submit" className="w-full gradient-bg border-0 hover:opacity-90 transition-opacity" disabled={enviando}>
            {enviando ? "Criando conta..." : "Criar conta"}
          </Button>
          <a
            href="/login"
            className="block text-center text-sm text-muted-foreground hover:text-brand-dark underline-offset-4 hover:underline transition-colors"
          >
            Ja tem uma conta? Entrar
          </a>
        </div>
      </form>
    </div>
  );
}

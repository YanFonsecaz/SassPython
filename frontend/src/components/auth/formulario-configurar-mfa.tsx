"use client";
/* eslint-disable @next/next/no-img-element */

import { useState } from "react";
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
import type {
  ApiError,
  MensagemResponse,
  MfaAtivarRequest,
  MfaConfigurarRequest,
  MfaConfigurarResponse,
} from "@/types";

interface FormularioConfigurarMfaProps {
  mfaAtivo: boolean;
  onSucesso: () => void;
  onVoltar: () => void;
}

export function FormularioConfigurarMfa({
  mfaAtivo,
  onSucesso,
  onVoltar,
}: FormularioConfigurarMfaProps) {
  const [etapa, setEtapa] = useState<"iniciar" | "escanear" | "ativando">("iniciar");
  const [nomeDispositivo, setNomeDispositivo] = useState("");
  const [qrCode, setQrCode] = useState("");
  const [segredo, setSegredo] = useState("");
  const [dispositivoId, setDispositivoId] = useState("");
  const [codigo, setCodigo] = useState("");
  const [senhaConfirmacao, setSenhaConfirmacao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  async function handleConfigurar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      const dados = await api.post<MfaConfigurarResponse>(
        "/auth/mfa/configurar",
        {
          tipo: "totp",
          nome: nomeDispositivo,
        } satisfies MfaConfigurarRequest
      );
      setQrCode(dados.qr_code_base64);
      setSegredo(dados.segredo);
      setDispositivoId(dados.dispositivo_id);
      setEtapa("escanear");
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao configurar MFA");
    } finally {
      setEnviando(false);
    }
  }

  async function handleAtivar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");

    if (codigo.length !== 6 || !/^\d{6}$/.test(codigo)) {
      setErro("Digite o codigo de 6 digitos");
      return;
    }

    if (!senhaConfirmacao) {
      setErro("Confirme sua senha para ativar o MFA");
      return;
    }

    setEnviando(true);
    setEtapa("ativando");
    try {
      await api.post<MensagemResponse>(
        "/auth/mfa/ativar",
        {
          dispositivo_id: dispositivoId,
          codigo,
          senha_confirmacao: senhaConfirmacao,
        } satisfies MfaAtivarRequest
      );
      onSucesso();
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao ativar MFA");
      setEtapa("escanear");
      setEnviando(false);
    }
  }

  if (mfaAtivo) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Autenticacao em duas etapas</CardTitle>
          <CardDescription>
            O MFA ja esta ativo na sua conta. Voce pode gerenciar seus dispositivos na pagina de perfil.
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Button variant="ghost" className="w-full" onClick={onVoltar}>
            Voltar ao perfil
          </Button>
        </CardFooter>
      </Card>
    );
  }

  if (etapa === "escanear" || etapa === "ativando") {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Escanear QR Code</CardTitle>
          <CardDescription>
            Escaneie o QR Code com seu app autenticador (Google Authenticator, Authy, etc.)
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleAtivar}>
          <CardContent className="space-y-4">
            {erro && (
              <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
              <p className="text-sm text-destructive" role="alert">
                {erro}
              </p>
            </div>
            )}
            <div className="flex justify-center">
              {qrCode && (
                <img
                  src={`data:image/png;base64,${qrCode}`}
                  alt="QR Code para configuração MFA"
                  className="w-48 h-48 rounded-lg"
                />
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="segredo-manual">Chave manual (se nao conseguir escanear)</Label>
              <code className="block rounded-md bg-muted px-3 py-2 text-sm break-all select-all">
                {segredo}
              </code>
            </div>
            <div className="space-y-2">
              <Label htmlFor="codigo-mfa">Codigo de verificacao</Label>
              <Input
                id="codigo-mfa"
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
            <div className="space-y-2">
              <Label htmlFor="senha-confirmacao">Confirme sua senha</Label>
              <Input
                id="senha-confirmacao"
                type="password"
                placeholder="Sua senha atual"
                required
                autoComplete="current-password"
                value={senhaConfirmacao}
                onChange={(e) => setSenhaConfirmacao(e.target.value)}
                disabled={enviando}
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={enviando || codigo.length !== 6}>
              {etapa === "ativando" ? "Ativando..." : "Ativar MFA"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={onVoltar}
              disabled={enviando}
            >
              Cancelar
            </Button>
          </CardFooter>
        </form>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Configurar MFA</CardTitle>
        <CardDescription>
          Ative a autenticacao em duas etapas para proteger sua conta
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleConfigurar}>
        <CardContent className="space-y-4">
          {erro && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
            <p className="text-sm text-destructive" role="alert">
              {erro}
            </p>
          </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="nome-dispositivo">Nome do dispositivo</Label>
            <Input
              id="nome-dispositivo"
              type="text"
              placeholder="Ex: Celular pessoal"
              required
              minLength={1}
              maxLength={100}
              value={nomeDispositivo}
              onChange={(e) => setNomeDispositivo(e.target.value)}
              disabled={enviando}
            />
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={enviando || !nomeDispositivo.trim()}>
            {enviando ? "Gerando..." : "Gerar QR Code"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="w-full"
            onClick={onVoltar}
            disabled={enviando}
          >
            Cancelar
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

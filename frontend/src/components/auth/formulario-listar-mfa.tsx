"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ApiError, MensagemResponse, MfaRemoverRequest, MfaDispositivo } from "@/types";

interface FormularioListarMfaProps {
  dispositivos: MfaDispositivo[];
  onRemovido: () => void;
}

export function FormularioListarMfa({
  dispositivos,
  onRemovido,
}: FormularioListarMfaProps) {
  const [removendoId, setRemovendoId] = useState<string | null>(null);
  const [codigoTotp, setCodigoTotp] = useState("");
  const [erro, setErro] = useState("");

  async function handleRemover(dispositivoId: string, e: React.FormEvent) {
    e.preventDefault();
    setErro("");

    if (codigoTotp.length !== 6 || !/^\d{6}$/.test(codigoTotp)) {
      setErro("Digite o codigo MFA de 6 digitos");
      return;
    }

    setRemovendoId(dispositivoId);
    try {
      await api.delete<MensagemResponse>(
        `/auth/mfa/${dispositivoId}`,
        { codigo_totp: codigoTotp } satisfies MfaRemoverRequest
      );
      setCodigoTotp("");
      setRemovendoId(null);
      onRemovido();
    } catch (err) {
      const apiErr = err as ApiError;
      setErro(apiErr.detalhe || "Erro ao remover dispositivo");
      setRemovendoId(null);
    }
  }

  if (dispositivos.length === 0) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Dispositivos MFA</CardTitle>
          <CardDescription>
            Nenhum dispositivo configurado.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="w-full max-w-md space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Dispositivos MFA</CardTitle>
          <CardDescription>
            Gerencie seus dispositivos de autenticacao
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {dispositivos.map((disp) => (
            <div
              key={disp.id}
              className="flex items-center justify-between rounded-lg border px-4 py-3"
            >
              <div>
                <p className="text-sm font-medium">{disp.nome}</p>
                <p className="text-xs text-muted-foreground">
                  {disp.tipo} &middot; {new Date(disp.criado_em).toLocaleDateString("pt-BR")}
                </p>
              </div>
              <form onSubmit={(e) => handleRemover(disp.id, e)}>
                <div className="flex items-end gap-2">
                  <div className="space-y-1">
                    <Label htmlFor={`codigo-remover-${disp.id}`} className="sr-only">
                      Codigo MFA
                    </Label>
                    <Input
                      id={`codigo-remover-${disp.id}`}
                      type="text"
                      inputMode="numeric"
                      pattern="\d{6}"
                      maxLength={6}
                      placeholder="000000"
                      required
                      autoComplete="one-time-code"
                      value={removendoId === disp.id ? codigoTotp : ""}
                      onChange={(e) => {
                        const apenasDigitos = e.target.value.replace(/\D/g, "").slice(0, 6);
                        setCodigoTotp(apenasDigitos);
                      }}
                      disabled={removendoId !== null && removendoId !== disp.id}
                      className="w-28"
                    />
                  </div>
                  <Button
                    type="submit"
                    variant="destructive"
                    size="sm"
                    disabled={removendoId !== null && removendoId !== disp.id}
                  >
                    {removendoId === disp.id ? "..." : "Remover"}
                  </Button>
                </div>
              </form>
            </div>
          ))}
          {erro && (
            <p className="text-sm text-destructive" role="alert">
              {erro}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

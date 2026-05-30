"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { FormularioAlterarSenha } from "@/components/auth/formulario-alterar-senha";
import { FormularioListarMfa } from "@/components/auth/formulario-listar-mfa";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { TermoComAjuda } from "@/components/ui/termo-com-ajuda";
import type { MfaDispositivo } from "@/types";

export default function PerfilPage() {
  const router = useRouter();
  const { usuario, logout } = useAuth();
  const [secao, setSecao] = useState<"principal" | "alterar-senha">("principal");
  const [dispositivos, setDispositivos] = useState<MfaDispositivo[]>([]);

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  async function handleCarregarDispositivos() {
    try {
      const dados = await api.get<MfaDispositivo[]>("/auth/mfa/dispositivos");
      setDispositivos(dados);
    } catch {
      setDispositivos([]);
    }
  }

  if (secao === "alterar-senha") {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Alterar senha"
          action={
            <Button variant="ghost" size="sm" onClick={() => setSecao("principal")}>
              ← Voltar ao perfil
            </Button>
          }
        />
        <div className="max-w-md">
          <FormularioAlterarSenha
            mfaAtivo={usuario!.mfa_ativo}
            onSucesso={() => setSecao("principal")}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Perfil"
        description="Dados da sua conta e configurações de segurança"
      />

      <div className="max-w-md space-y-4">
        <div className="rounded-lg border bg-card p-6">
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="font-medium text-muted-foreground">Nome</dt>
              <dd>{usuario?.nome}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">E-mail</dt>
              <dd>{usuario?.email}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Plano</dt>
              <dd>{usuario?.plano || "Gratuito"}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground"><TermoComAjuda termo="MFA" /></dt>
              <dd>{usuario?.mfa_ativo ? "Ativo" : "Inativo"}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Membro desde</dt>
              <dd>{new Date(usuario!.criado_em).toLocaleDateString("pt-BR")}</dd>
            </div>
          </dl>
        </div>

        <div className="flex flex-col gap-2">
          <Button
            variant="outline"
            className="w-full"
            onClick={() => setSecao("alterar-senha")}
          >
            Alterar senha
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => router.push("/configurar-mfa")}
          >
            {usuario?.mfa_ativo ? "Gerenciar MFA" : "Configurar MFA"}
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={handleCarregarDispositivos}
          >
            Ver dispositivos MFA
          </Button>
          <Button
            variant="ghost"
            className="w-full text-destructive hover:text-destructive"
            onClick={handleLogout}
          >
            Sair
          </Button>
        </div>

        {dispositivos.length > 0 && (
          <FormularioListarMfa
            dispositivos={dispositivos}
            onRemovido={handleCarregarDispositivos}
          />
        )}
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Cliente, ClienteCreate, ConfigJson, Persona } from "@/types";
import { FormularioPersona } from "./formulario-persona";

interface FormularioClienteProps {
  cliente?: Cliente;
  onSucesso?: (cliente: Cliente) => void;
  onCancelar?: () => void;
}

const CONFIG_DEFAULT: ConfigJson = {
  persona_global: {
    tom_voz: "profissional",
    nivel_tecnico: "intermediario",
    estilo_escrita: "didatico",
    instrucoes_gerais: "",
    exemplos_textos: [],
  },
  personas: [],
};

export function FormularioCliente({
  cliente,
  onSucesso,
  onCancelar,
}: FormularioClienteProps) {
  const router = useRouter();
  const [nome, setNome] = useState(cliente?.nome || "");
  const [siteUrl, setSiteUrl] = useState(cliente?.site_url || "");
  const [config, setConfig] = useState<ConfigJson>(
    cliente?.config_json || CONFIG_DEFAULT
  );
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [mostrarPersonas, setMostrarPersonas] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    setEnviando(true);

    try {
      const body: ClienteCreate = {
        nome,
        site_url: siteUrl || null,
        config_json: config,
      };

      const dados = cliente
        ? await api.put<Cliente>(`/clientes/${cliente.id}`, body)
        : await api.post<Cliente>("/clientes", body);

      if (onSucesso) {
        onSucesso(dados);
      } else {
        router.push(`/clientes/${dados.id}`);
      }
    } catch (err) {
      setErro(
        err && typeof err === "object" && "detalhe" in err
          ? (err as { detalhe: string }).detalhe
          : "Erro desconhecido"
      );
    } finally {
      setEnviando(false);
    }
  }

  function adicionarPersona(persona: Persona) {
    setConfig((prev) => ({
      ...prev,
      personas: [...prev.personas, persona],
    }));
    setMostrarPersonas(false);
  }

  function removerPersona(index: number) {
    setConfig((prev) => ({
      ...prev,
      personas: prev.personas.filter((_, i) => i !== index),
    }));
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {erro && (
        <p className="text-sm text-destructive" role="alert">
          {erro}
        </p>
      )}

      <div className="space-y-2">
        <Label htmlFor="nome">Nome do cliente</Label>
        <Input
          id="nome"
          placeholder="Ex: Clinica OdontoVida"
          required
          minLength={2}
          maxLength={255}
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          disabled={enviando}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="site_url">URL do site</Label>
        <Input
          id="site_url"
          placeholder="https://exemplo.com.br/"
          value={siteUrl}
          onChange={(e) => setSiteUrl(e.target.value)}
          disabled={enviando}
        />
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Label>Persona Global</Label>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="tom_voz">Tom de voz</Label>
            <Input
              id="tom_voz"
              placeholder="Ex: formal mas acessivel"
              value={config.persona_global.tom_voz}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  persona_global: {
                    ...prev.persona_global,
                    tom_voz: e.target.value,
                  },
                }))
              }
              disabled={enviando}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="nivel_tecnico">Nivel tecnico</Label>
            <Input
              id="nivel_tecnico"
              placeholder="Ex: intermediario"
              value={config.persona_global.nivel_tecnico}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  persona_global: {
                    ...prev.persona_global,
                    nivel_tecnico: e.target.value,
                  },
                }))
              }
              disabled={enviando}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="estilo_escrita">Estilo de escrita</Label>
            <Input
              id="estilo_escrita"
              placeholder="Ex: didatico"
              value={config.persona_global.estilo_escrita}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  persona_global: {
                    ...prev.persona_global,
                    estilo_escrita: e.target.value,
                  },
                }))
              }
              disabled={enviando}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="instrucoes_gerais">Instrucoes gerais</Label>
            <Input
              id="instrucoes_gerais"
              placeholder="Ex: Foque em resultados praticos"
              value={config.persona_global.instrucoes_gerais}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  persona_global: {
                    ...prev.persona_global,
                    instrucoes_gerais: e.target.value,
                  },
                }))
              }
              disabled={enviando}
            />
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label>Personas especificas</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setMostrarPersonas(true)}
          >
            + Adicionar persona
          </Button>
        </div>

        {config.personas.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Nenhuma persona cadastrada. Personas permitem gerar conteudo com
            tom diferente para cada publico-alvo.
          </p>
        )}

        {config.personas.map((persona, index) => (
          <div
            key={index}
            className="flex items-start justify-between rounded-lg border p-3"
          >
            <div className="space-y-1">
              <p className="font-medium">{persona.nome}</p>
              <p className="text-sm text-muted-foreground">
                {persona.tom_voz} &middot; {persona.nivel_tecnico}
              </p>
              {persona.objetivo && (
                <p className="text-sm text-muted-foreground">
                  {persona.objetivo}
                </p>
              )}
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              onClick={() => removerPersona(index)}
              disabled={enviando}
            >
              &times;
            </Button>
          </div>
        ))}
      </div>

      {mostrarPersonas && (
        <FormularioPersona
          onSalvar={adicionarPersona}
          onCancelar={() => setMostrarPersonas(false)}
        />
      )}

      <div className="flex gap-3">
        <Button type="submit" disabled={enviando}>
          {enviando
            ? "Salvando..."
            : cliente
              ? "Salvar alteracoes"
              : "Criar cliente"}
        </Button>
        {onCancelar && (
          <Button type="button" variant="outline" onClick={onCancelar}>
            Cancelar
          </Button>
        )}
      </div>
    </form>
  );
}

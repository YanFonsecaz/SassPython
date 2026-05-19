"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Persona } from "@/types";

interface FormularioPersonaProps {
  onSalvar: (persona: Persona) => void;
  onCancelar: () => void;
}

export function FormularioPersona({ onSalvar, onCancelar }: FormularioPersonaProps) {
  const [nome, setNome] = useState("");
  const [tomVoz, setTomVoz] = useState("profissional");
  const [nivelTecnico, setNivelTecnico] = useState("intermediario");
  const [estiloEscrita, setEstiloEscrita] = useState("didatico");
  const [objetivo, setObjetivo] = useState("");
  const [palavrasProibidas, setPalavrasProibidas] = useState("");
  const [palavrasRecomendadas, setPalavrasRecomendadas] = useState("");
  const [instrucoes, setInstrucoes] = useState("");
  const [erro, setErro] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro("");

    if (!nome.trim()) {
      setErro("Nome da persona e obrigatorio");
      return;
    }

    const proibidas = palavrasProibidas
      .split(",")
      .map((w) => w.trim())
      .filter(Boolean);
    const recomendadas = palavrasRecomendadas
      .split(",")
      .map((w) => w.trim())
      .filter(Boolean);

    if (proibidas.length > 50) {
      setErro("Maximo de 50 palavras proibidas");
      return;
    }

    if (recomendadas.length > 50) {
      setErro("Maximo de 50 palavras recomendadas");
      return;
    }

    onSalvar({
      nome: nome.trim(),
      tom_voz: tomVoz,
      nivel_tecnico: nivelTecnico,
      estilo_escrita: estiloEscrita,
      objetivo,
      palavras_proibidas: proibidas,
      palavras_recomendadas: recomendadas,
      instrucoes_gerais: instrucoes,
    });
  }

  return (
    <div className="rounded-lg border p-4 space-y-4">
      {erro && (
        <p className="text-sm text-destructive" role="alert">
          {erro}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="persona-nome">Nome da persona</Label>
          <Input
            id="persona-nome"
            placeholder="Ex: Gestor de Clinica"
            required
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="persona-tom">Tom de voz</Label>
          <Input
            id="persona-tom"
            placeholder="Ex: direto e persuasivo"
            value={tomVoz}
            onChange={(e) => setTomVoz(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="persona-nivel">Nivel tecnico</Label>
          <Input
            id="persona-nivel"
            placeholder="Ex: basico"
            value={nivelTecnico}
            onChange={(e) => setNivelTecnico(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="persona-estilo">Estilo de escrita</Label>
          <Input
            id="persona-estilo"
            placeholder="Ex: direto"
            value={estiloEscrita}
            onChange={(e) => setEstiloEscrita(e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="persona-objetivo">Objetivo</Label>
        <Input
          id="persona-objetivo"
          placeholder="Ex: converter leads em pacientes"
          value={objetivo}
          onChange={(e) => setObjetivo(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="persona-proibidas">
          Palavras proibidas <span className="text-muted-foreground">(separadas por virgula)</span>
        </Label>
        <Input
          id="persona-proibidas"
          placeholder="impulsionar, surpreendente, revolucionario"
          value={palavrasProibidas}
          onChange={(e) => setPalavrasProibidas(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="persona-recomendadas">
          Palavras recomendadas <span className="text-muted-foreground">(separadas por virgula)</span>
        </Label>
        <Input
          id="persona-recomendadas"
          placeholder="resultado, pratico, comprovado"
          value={palavrasRecomendadas}
          onChange={(e) => setPalavrasRecomendadas(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="persona-instrucoes">Instrucoes gerais</Label>
        <Textarea
          id="persona-instrucoes"
          placeholder="Instrucoes especificas para esta persona..."
          value={instrucoes}
          onChange={(e) => setInstrucoes(e.target.value)}
          rows={3}
        />
      </div>

      <div className="flex gap-3">
        <Button type="button" onClick={handleSubmit}>
          Salvar persona
        </Button>
        <Button type="button" variant="outline" onClick={onCancelar}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

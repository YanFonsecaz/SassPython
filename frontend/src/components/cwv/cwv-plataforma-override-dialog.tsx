"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { overridePlataformaCwv } from "@/lib/api/cwv";

const PLATAFORMAS = [
  { value: "vtex", label: "VTEX" },
  { value: "wordpress", label: "WordPress" },
  { value: "nextjs", label: "Next.js" },
  { value: "shopify", label: "Shopify" },
  { value: "wix", label: "Wix" },
  { value: "squarespace", label: "Squarespace" },
  { value: "magento", label: "Magento" },
  { value: "hugo", label: "Hugo" },
  { value: "jekyll", label: "Jekyll" },
  { value: "webflow", label: "Webflow" },
  { value: "outros", label: "Outra / Customizado" },
] as const;

interface Props {
  analiseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  plataformaAtual: string;
  onSuccess: () => void;
}

export function PlataformaOverrideDialog({
  analiseId,
  open,
  onOpenChange,
  plataformaAtual,
  onSuccess,
}: Props) {
  const [selecionada, setSelecionada] = useState<string>(plataformaAtual);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    setEnviando(true);
    setErro(null);
    try {
      await overridePlataformaCwv(analiseId, selecionada);
      onSuccess();
      onOpenChange(false);
    } catch {
      setErro("Erro ao salvar. Tente novamente.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Qual a plataforma deste site?</DialogTitle>
          <DialogDescription>
            {plataformaAtual === "desconhecida"
              ? "Não conseguimos detectar automaticamente. Selecione para receber soluções adaptadas à sua plataforma."
              : "Selecione outra plataforma para regenerar o plano de ação com soluções específicas."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-2 my-4">
          {PLATAFORMAS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setSelecionada(p.value)}
              className={cn(
                "rounded-lg border px-3 py-2 text-sm text-left transition-colors",
                selecionada === p.value
                  ? "border-brand bg-brand/5 text-brand-dark font-medium"
                  : "hover:bg-surface-light"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        {erro && <p className="text-sm text-destructive">{erro}</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={enviando}>
            Cancelar
          </Button>
          <Button
            onClick={salvar}
            disabled={enviando || selecionada === plataformaAtual}
          >
            {enviando ? "Salvando..." : "Salvar e recarregar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

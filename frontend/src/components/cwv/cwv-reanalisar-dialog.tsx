"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogClose } from "@/components/ui/dialog";
import { Loader2Icon } from "lucide-react";
import { reanalisarCwv } from "@/lib/api/cwv";
import { toast } from "sonner";

interface ReanalisarDialogProps {
  analiseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReanalisarDialog({ analiseId, open, onOpenChange }: ReanalisarDialogProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleConfirm() {
    setLoading(true);
    try {
      const resultado = await reanalisarCwv(analiseId);
      onOpenChange(false);
      router.push(`/ferramentas/core-web-vitals/execucao/${resultado.id}`);
    } catch (err) {
      const detalhe = err && typeof err === "object" && "detalhe" in err
        ? (err as { detalhe: string }).detalhe : "Erro ao re-analisar";
      toast.error(detalhe);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Re-analisar URL</DialogTitle>
          <DialogDescription>
            Sera criada uma nova analise para esta URL usando os mesmos parametros (template, estrategia).
            Custo: 16 creditos.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <DialogClose className={buttonVariants({ variant: "outline" })} disabled={loading}>Cancelar</DialogClose>
          <Button className="gradient-bg border-0 hover:opacity-90" onClick={handleConfirm} disabled={loading}>
            {loading && <Loader2Icon className="size-4 mr-1 animate-spin" />}
            Confirmar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

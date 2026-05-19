"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ModalCreditosInsuficientesProps {
  aberto: boolean;
  onFechar: () => void;
}

export function ModalCreditosInsuficientes({
  aberto,
  onFechar,
}: ModalCreditosInsuficientesProps) {
  return (
    <Dialog open={aberto} onOpenChange={onFechar}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Creditos insuficientes</DialogTitle>
          <DialogDescription>
            Voce nao tem creditos suficientes para realizar esta acao.
            Adquira um pacote de creditos para continuar.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <button
            onClick={onFechar}
            className={buttonVariants({ variant: "outline" })}
          >
            Fechar
          </button>
          <Link href="/creditos" className={buttonVariants()}>
            Ver pacotes
          </Link>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

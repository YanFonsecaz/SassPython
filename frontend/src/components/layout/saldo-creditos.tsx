"use client";

import { Badge } from "@/components/ui/badge";

interface SaldoCreditosProps {
  saldo?: number | null;
}

export function SaldoCreditos({ saldo }: SaldoCreditosProps) {
  if (saldo === undefined || saldo === null) return null;

  return (
    <Badge variant={saldo < 20 ? "destructive" : "secondary"} className="cursor-pointer">
      {saldo} creditos
    </Badge>
  );
}
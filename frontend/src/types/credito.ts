export interface Saldo {
  saldo_plano: number;
  saldo_extras: number;
  saldo_total: number;
  ciclo_inicio: string;
  ciclo_fim: string;
}

export interface TransacaoCredito {
  id: string;
  tipo: string;
  quantidade: number;
  descricao: string;
  ferramenta: string | null;
  criado_em: string;
}

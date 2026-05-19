export interface Plano {
  id: string | null;
  nome: string;
  creditos_por_mes: number;
  preco_mensal: number;
  cliente_limite: number;
  permite_extras: boolean;
}

export interface Pacote {
  id: string;
  nome: string;
  creditos: number;
  preco: number;
  ativo: boolean;
}

export interface Compra {
  id: string;
  tipo: string;
  pacote_id: string | null;
  valor_pago: number;
  status: string;
  criado_em: string;
}

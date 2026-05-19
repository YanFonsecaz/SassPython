import type { Cliente } from "./cliente";
import type { Execucao, VersaoArtigo } from "./ferramenta";
import type { TransacaoCredito } from "./credito";
import type { Pacote, Compra } from "./billing";
import type { CustoItem } from "./ferramenta";

export interface ClienteListResponse {
  clientes: Cliente[];
  total: number;
}

export interface ExecucoesListResponse {
  execucoes: Execucao[];
  total: number;
}

export interface VersoesListResponse {
  execucao_id: string;
  versoes: VersaoArtigo[];
}

export interface TransacoesListResponse {
  transacoes: TransacaoCredito[];
  total: number;
}

export interface PacotesListResponse {
  pacotes: Pacote[];
}

export interface ComprasListResponse {
  compras: Compra[];
  total: number;
}

export interface CustosResponse {
  custos: CustoItem[];
}

export type {
  LoginRequest,
  LoginResponse,
  CadastroRequest,
  MfaVerificarRequest,
  RecuperarSenhaRequest,
  ResetarSenhaRequest,
  TokenResponse,
  MfaRequeridoResponse,
  MensagemResponse,
  UsuarioResponse,
  ApiError,
  AlterarSenhaRequest,
  MfaConfigurarRequest,
  MfaConfigurarResponse,
  MfaAtivarRequest,
  MfaRemoverRequest,
  MfaDispositivo,
  ValidaSenhaResultado,
} from "./auth";

export type {
  Cliente,
  ClienteCreate,
  ClienteUpdate,
  ConfigJson,
  PersonaGlobal,
  Persona,
} from "./cliente";

export type { Saldo, TransacaoCredito } from "./credito";

export type {
  Execucao,
  ExecucaoDetalhe,
  ExecucaoCriada,
  VersaoArtigo,
  GerarArtigoRequest,
  CustoItem,
  CancelarResultado,
  InlinksRequest,
  CustoInlinksResponse,
  InlinkAplicado,
  ResultadoInlinks,
  CategoriaMatchInlink,
  DistribuirInlinksRequest,
  CustoDistribuirInlinksResponse,
  CandidataResultado,
  ResultadoDistribuirInlinks,
  FunilInlinks,
  StatusIndiceSite,
  IndiceSiteStatus,
  CandidataSugerida,
  RespostaCandidatas,
  IndexarSiteResponse,
  ClienteResumido,
} from "./ferramenta";

export type { Pacote, Compra, Plano } from "./billing";

export type { ClienteListResponse } from "./responses";
export type { ExecucoesListResponse, VersoesListResponse } from "./responses";
export type { TransacoesListResponse, PacotesListResponse, ComprasListResponse, CustosResponse } from "./responses";

export interface SSEStatusEvent {
  type: "status";
  status: string;
  etapa: string | null;
  timestamp: string;
}

export interface SSEConcluidaEvent {
  type: "concluida";
  creditos_cobrados?: number;
}

export interface SSEFalhouEvent {
  type: "falhou";
  erro?: string;
}

export interface SSENodeProgressEvent {
  type: "node_progress";
  node: string;
  detail: string;
  timestamp: string;
}

export interface NodeActivity {
  node: string;
  detail: string;
  timestamp: string;
  isStart: boolean;
}

export type SSEEvent = SSEStatusEvent | SSEConcluidaEvent | SSEFalhouEvent | SSENodeProgressEvent;

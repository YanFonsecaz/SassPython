export interface LoginRequest {
  email: string;
  senha: string;
}

export interface CadastroRequest {
  nome: string;
  email: string;
  senha: string;
  senha_confirmacao: string;
}

export interface MfaVerificarRequest {
  token_temporario: string;
  codigo_totp: string;
}

export interface RecuperarSenhaRequest {
  email: string;
}

export interface ResetarSenhaRequest {
  token: string;
  nova_senha: string;
  nova_senha_confirmacao: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  csrf_token?: string;
}

export interface MfaRequeridoResponse {
  mfa_requerido: true;
  tipo: string;
  token_temporario: string;
}

export type LoginResponse = TokenResponse | MfaRequeridoResponse;

export interface MensagemResponse {
  mensagem: string;
}

export interface UsuarioResponse {
  id: string;
  email: string;
  nome: string;
  mfa_ativo: boolean;
  email_verificado: boolean;
  plano: string | null;
  criado_em: string;
}

export interface ApiError {
  detalhe: string;
}

export interface AlterarSenhaRequest {
  senha_atual: string;
  nova_senha: string;
  nova_senha_confirmacao: string;
  codigo_totp?: string;
}

export interface MfaConfigurarRequest {
  tipo?: string;
  nome: string;
}

export interface MfaConfigurarResponse {
  dispositivo_id: string;
  qr_code_base64: string;
  segredo: string;
}

export interface MfaAtivarRequest {
  dispositivo_id: string;
  codigo: string;
  senha_confirmacao: string;
}

export interface MfaRemoverRequest {
  codigo_totp: string;
}

export interface MfaDispositivo {
  id: string;
  nome: string;
  tipo: string;
  criado_em: string;
}

export interface ValidaSenhaResultado {
  valida: boolean;
  erros: string[];
}

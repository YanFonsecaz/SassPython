"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type {
  CadastroRequest,
  LoginRequest,
  LoginResponse,
  MensagemResponse,
  MfaVerificarRequest,
  TokenResponse,
  UsuarioResponse,
} from "@/types";
import {
  api,
  getAccessToken,
  setAccessToken,
  setCsrfToken,
  setOnAuthExpired,
  setRefreshToken,
} from "@/lib/api";

interface AuthContextType {
  usuario: UsuarioResponse | null;
  carregando: boolean;
  autenticado: boolean;
  login: (
    email: string,
    senha: string
  ) => Promise<{ tipo: "token" | "mfa"; token_temporario?: string }>;
  verificarMfa: (
    tokenTemporario: string,
    codigoTotp: string
  ) => Promise<TokenResponse>;
  cadastro: (dados: CadastroRequest) => Promise<TokenResponse>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<UsuarioResponse | null>(null);
  const [carregando, setCarregando] = useState(true);

  const logout = useCallback(async () => {
    try {
      await api.post<MensagemResponse>("/auth/logout", undefined, {
        noAuth: true,
      });
    } catch {
      // ignore
    }
    document.cookie =
      "csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    setAccessToken(null);
    setUsuario(null);
  }, []);

  const carregarUsuario = useCallback(async () => {
    try {
      const u = await api.get<UsuarioResponse>("/auth/me");
      setUsuario(u);
    } catch {
      setAccessToken(null);
      setUsuario(null);
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    setOnAuthExpired(async () => {
      setAccessToken(null);
      setUsuario(null);
    });

    async function init() {
      const token = getAccessToken();
      if (!token) {
        document.cookie =
          "csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      }
      if (token) {
        await carregarUsuario();
      } else {
        try {
          await api.post<TokenResponse>("/auth/refresh");
          await carregarUsuario();
        } catch {
          setCarregando(false);
        }
      }
    }
    init();
  }, [carregarUsuario]);

  const login = useCallback(
    async (email: string, senha: string) => {
      const dados = await api.post<LoginResponse>("/auth/login", {
        email,
        senha,
      } satisfies LoginRequest, {
        noAuth: true
      });

      if ("mfa_requerido" in dados && dados.mfa_requerido) {
        return { tipo: "mfa" as const, token_temporario: dados.token_temporario };
      }

      const tokenResp = dados as TokenResponse;
      setAccessToken(tokenResp.access_token);
      setRefreshToken(tokenResp.refresh_token);
      if ("csrf_token" in tokenResp && tokenResp.csrf_token) setCsrfToken(tokenResp.csrf_token);
      await carregarUsuario();
      return { tipo: "token" as const };
    },
    [carregarUsuario]
  );

  const verificarMfa = useCallback(
    async (tokenTemporario: string, codigoTotp: string) => {
      const dados = await api.post<TokenResponse>(
        "/auth/mfa/verificar",
        {
          token_temporario: tokenTemporario,
          codigo_totp: codigoTotp,
        } satisfies MfaVerificarRequest,
        { noAuth: true }
      );
      setAccessToken(dados.access_token);
      setRefreshToken(dados.refresh_token);
      if (dados.csrf_token) setCsrfToken(dados.csrf_token);
      await carregarUsuario();
      return dados;
    },
    [carregarUsuario]
  );

  const cadastro = useCallback(
    async (req: CadastroRequest) => {
      const dados = await api.post<TokenResponse>("/auth/cadastro", req, {
        noAuth: true,
      });
      setAccessToken(dados.access_token);
      setRefreshToken(dados.refresh_token);
      if (dados.csrf_token) setCsrfToken(dados.csrf_token);
      await carregarUsuario();
      return dados;
    },
    [carregarUsuario]
  );

  const valor = useMemo<AuthContextType>(
    () => ({
      usuario,
      carregando,
      autenticado: usuario !== null,
      login,
      verificarMfa,
      cadastro,
      logout,
    }),
    [usuario, carregando, login, verificarMfa, cadastro, logout]
  );

  return (
    <AuthContext.Provider value={valor}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth deve ser usado dentro de AuthProvider");
  }
  return ctx;
}
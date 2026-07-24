import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/ferramentas/core-web-vitals/execucao/test-id",
}));

vi.mock("@/lib/sse-client", () => ({
  createSSEConnection: vi.fn(() => ({ close: () => {} })),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  mensagemErroAmigavel: (e: unknown) => String(e),
}));

const mockBuscarExecucao = vi.fn();
const mockBuscarHealth = vi.fn();
const mockBuscarPageExp = vi.fn();

vi.mock("@/lib/api/cwv", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/cwv")>()),
  buscarExecucaoCwv: (...a: unknown[]) => mockBuscarExecucao(...a),
  buscarHealthScoreCwv: (...a: unknown[]) => mockBuscarHealth(...a),
  buscarPageExperienceCwv: (...a: unknown[]) => mockBuscarPageExp(...a),
  criarAuditoriaCwv: vi.fn(),
  exportarExecucaoCwvDocx: vi.fn(),
}));

import { CwvExecucaoClient } from "@/components/cwv/cwv-execucao-client";

function mockExecucaoConcluida(overrides: Record<string, unknown> = {}) {
  return {
    id: "test-id",
    ferramenta: "core_web_vitals",
    status: "concluida",
    etapa_atual: null,
    creditos_cobrados: 17,
    criado_em: "2026-07-16T10:00:00Z",
    concluida_em: "2026-07-16T10:05:00Z",
    erro_msg: null,
    cliente_id: "cliente-1",
    resultado_json: {
      n_urls_analisadas: 2,
      n_urls_falharam: 0,
      analise_ids: ["a1", "a2"],
      analises: [
        { id: "a1", url_canonica: "https://jeitto.com.br/", estrategia: "mobile", score_performance: 45 },
        { id: "a2", url_canonica: "https://jeitto.com.br/", estrategia: "desktop", score_performance: 72 },
      ],
      health_score: { health_score: 58, n_pass: 30, n_total: 52, por_estrategia: { mobile: 45, desktop: 72 } },
    },
    entrada_json: {},
    ...overrides,
  };
}

describe("CwvExecucaoClient — SPEC_CWV_Execucao_Pos_Analise_UX", () => {
  beforeEach(() => {
    mockBuscarExecucao.mockResolvedValue(mockExecucaoConcluida());
    mockBuscarHealth.mockResolvedValue(null);
    mockBuscarPageExp.mockResolvedValue({ origens: [] });
  });

  it("links mostram URL + badge de estratégia", async () => {
    render(<CwvExecucaoClient />);
    await waitFor(() => expect(screen.getByText(/Análise concluída/i)).toBeInTheDocument());
    expect(screen.getAllByText("https://jeitto.com.br/")).toHaveLength(2);
    expect(screen.getByText("mobile")).toBeInTheDocument();
    expect(screen.getByText("desktop")).toBeInTheDocument();
  });

  it("mostra 'Criar auditoria' quando sem auditoria_id", async () => {
    render(<CwvExecucaoClient />);
    await waitFor(() => expect(screen.getByText(/Criar auditoria/i)).toBeInTheDocument());
    expect(screen.queryByText(/Ver auditoria/i)).not.toBeInTheDocument();
  });

  it("mostra 'Ver auditoria (comparativo)' quando entrada_json tem auditoria_id", async () => {
    mockBuscarExecucao.mockResolvedValue(
      mockExecucaoConcluida({ entrada_json: { auditoria_id: "aud-123" } })
    );
    render(<CwvExecucaoClient />);
    await waitFor(() => expect(screen.getByText(/Ver auditoria \(comparativo\)/i)).toBeInTheDocument());
    expect(screen.queryByText(/Criar auditoria/i)).not.toBeInTheDocument();
  });

  it("mostra 'Ver auditoria (comparativo)' quando resultado_json tem auditoria_id", async () => {
    mockBuscarExecucao.mockResolvedValue(
      mockExecucaoConcluida({ resultado_json: { ...mockExecucaoConcluida().resultado_json, auditoria_id: "aud-auto-123" } })
    );
    render(<CwvExecucaoClient />);
    await waitFor(() => expect(screen.getByText(/Ver auditoria \(comparativo\)/i)).toBeInTheDocument());
    expect(screen.queryByText(/Criar auditoria/i)).not.toBeInTheDocument();
  });
});

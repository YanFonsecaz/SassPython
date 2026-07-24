import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

const mockBuscar = vi.fn();
vi.mock("@/lib/api/cwv", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/cwv")>()),
  buscarComparativoAuditoria: (...a: unknown[]) => mockBuscar(...a),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
}));

import { BeforeAfterTab } from "@/components/cwv/auditoria/before-after-tab";

const par = {
  url_canonica: "https://a.com/",
  estrategia: "mobile",
  template_tipo: "home",
  before: { analise_id: "b1", score_performance: 23, lcp_ms: 4200, cls: 0.57, inp_ms: 348, tbt_ms: 890, n_problemas: 22 },
  after: { analise_id: "a1", score_performance: 61, lcp_ms: 2100, cls: 0.09, inp_ms: 180, tbt_ms: 300, n_problemas: 10 },
  problemas: { resolvidos: 12, persistentes: 8, novos: 2, titulos_resolvidos: ["Imagem grande"], titulos_novos: ["Novo problema"] },
};

describe("BeforeAfterTab", () => {
  it("card por URL com métricas e deltas", async () => {
    mockBuscar.mockResolvedValue({ fase: "after", pares: [par] });
    render(<BeforeAfterTab auditoriaId="x" fase="after" />);
    await waitFor(() => expect(screen.getByText("https://a.com/")).toBeInTheDocument());
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText("61")).toBeInTheDocument();
    expect(screen.getByText(/12 resolvidos/)).toBeInTheDocument();
    expect(screen.getByText(/2 novos/)).toBeInTheDocument();
  });

  it("fase before mostra baseline + aviso", async () => {
    mockBuscar.mockResolvedValue({ fase: "before", pares: [{ ...par, after: null, problemas: null }] });
    render(<BeforeAfterTab auditoriaId="x" fase="before" />);
    await waitFor(() => expect(screen.getByText(/aguardando re-auditoria/i)).toBeInTheDocument());
  });

  it("CTA re-auditar aparece no empty state quando fase permite", async () => {
    mockBuscar.mockResolvedValue({ fase: "aguardando_implementacao", pares: [{ ...par, after: null, problemas: null }] });
    const onReauditar = vi.fn();
    render(<BeforeAfterTab auditoriaId="x" fase="aguardando_implementacao" onReauditar={onReauditar} />);
    await waitFor(() => expect(screen.getByText(/Iniciar re-auditoria/i)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Iniciar re-auditoria/i));
    expect(onReauditar).toHaveBeenCalledOnce();
  });

  it("delta LCP < 100ms nao exibe delta", async () => {
    mockBuscar.mockResolvedValue({
      fase: "after",
      pares: [{ ...par, after: { ...par.after, lcp_ms: 1215 } }],
    });
    render(<BeforeAfterTab auditoriaId="x" fase="after" />);
    await waitFor(() => expect(screen.getByText("https://a.com/")).toBeInTheDocument());
    expect(screen.queryByText("15ms")).not.toBeInTheDocument();
  });

  it("delta LCP >= 100ms exibe em ms", async () => {
    mockBuscar.mockResolvedValue({
      fase: "after",
      pares: [{ ...par, before: { ...par.before, lcp_ms: 1200 }, after: { ...par.after, lcp_ms: 1680 } }],
    });
    render(<BeforeAfterTab auditoriaId="x" fase="after" />);
    await waitFor(() => expect(screen.getByText("480ms")).toBeInTheDocument());
  });

  it("delta TBT < 10ms nao exibe delta", async () => {
    mockBuscar.mockResolvedValue({
      fase: "after",
      pares: [{ ...par, before: { ...par.before, tbt_ms: 32 }, after: { ...par.after, tbt_ms: 33 } }],
    });
    render(<BeforeAfterTab auditoriaId="x" fase="after" />);
    await waitFor(() => expect(screen.getByText("https://a.com/")).toBeInTheDocument());
    expect(screen.queryByText("1ms")).not.toBeInTheDocument();
  });
});

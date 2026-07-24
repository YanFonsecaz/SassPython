import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

const mockListar = vi.fn();
vi.mock("@/lib/api/cwv", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/cwv")>()),
  listarAuditoriasCwv: (...a: unknown[]) => mockListar(...a),
}));

import { HealthEvolucaoChart } from "@/components/cwv/auditoria/health-evolucao-chart";
import type { AuditoriaResumo } from "@/lib/api/cwv";

const aud = (id: string, before: number | null, after: number | null, criado: string): AuditoriaResumo => ({
  id, titulo: `Auditoria ${id}`, fase: "concluida",
  health_score_before: before, health_score_after: after,
  n_itens: 40, criado_em: criado,
});

describe("HealthEvolucaoChart", () => {
  it("plota pontos por auditoria com health", () => {
    render(
      <HealthEvolucaoChart
        auditorias={[aud("a", 48.3, 72.0, "2026-05-01T00:00:00Z"), aud("b", 70.0, null, "2026-07-01T00:00:00Z")]}
        auditoriaAtualId="b"
      />
    );
    expect(screen.getByTestId("evolucao-pontos").textContent).toContain("72");
    expect(screen.getByTestId("evolucao-pontos").textContent).toContain("70");
  });

  it("com < 2 pontos mostra empty state", () => {
    render(<HealthEvolucaoChart auditorias={[aud("a", 48.3, null, "2026-07-01T00:00:00Z")]} auditoriaAtualId="a" />);
    expect(screen.getByText(/primeira auditoria/i)).toBeInTheDocument();
  });
});

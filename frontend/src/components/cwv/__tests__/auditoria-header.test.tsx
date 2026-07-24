import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

import { AuditoriaHeader } from "@/components/cwv/auditoria/auditoria-header";

describe("AuditoriaHeader", () => {
  it("mostra fase, donuts compactos e delta", () => {
    render(
      <AuditoriaHeader
        titulo="Kumon" fase="after"
        healthBefore={48.3} healthAfter={72.0}
        nPassBefore={9} nFailBefore={29} nPassAfter={20} nFailAfter={8}
        criadoEm="2026-07-15T00:00:00Z"
      />
    );
    expect(screen.getByText(/After \(re-auditoria\)/)).toBeInTheDocument();
    // Delta = diferença das % dos donuts (24% -> 71%), NÃO do health_score.
    expect(screen.getByText(/\+47 p\.p\./)).toBeInTheDocument();
    expect(screen.getByTestId("donut-before")).toBeInTheDocument();
  });

  it("delta bate com as % exibidas nos donuts", () => {
    render(
      <AuditoriaHeader
        titulo="X" fase="after"
        healthBefore={48.3} healthAfter={78.9}
        nPassBefore={3} nFailBefore={6} nPassAfter={5} nFailAfter={4}
        criadoEm="2026-07-15T00:00:00Z"
      />
    );
    // donut before 33%, after 56% => delta +23 (e não +30.6 do health_score).
    expect(screen.getByLabelText(/Before: 33% aprovado/)).toBeInTheDocument();
    expect(screen.getByLabelText(/After: 56% aprovado/)).toBeInTheDocument();
    expect(screen.getByText(/\+23 p\.p\./)).toBeInTheDocument();
  });

  it("sem after (donut vazio) não mostra delta", () => {
    render(
      <AuditoriaHeader
        titulo="X" fase="before"
        healthBefore={48.3} healthAfter={null}
        nPassBefore={3} nFailBefore={6} nPassAfter={null} nFailAfter={null}
        criadoEm="2026-07-15T00:00:00Z"
      />
    );
    expect(screen.getByText(/Δ após re-auditoria/)).toBeInTheDocument();
  });
});

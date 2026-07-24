import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

const mockListar = vi.fn();
vi.mock("@/lib/api/cwv", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/cwv")>()),
  listarAuditoriasCwv: (...a: unknown[]) => mockListar(...a),
}));

import { VisaoGeralTab } from "@/components/cwv/auditoria/visao-geral-tab";
import type { AuditoriaResposta } from "@/lib/api/cwv";

const auditoria = {
  id: "x", cliente_id: "c1", titulo: "Kumon", fase: "after",
  execucao_before_id: "e1", execucao_after_id: "e2",
  health_score_before: 48.3, health_score_after: 72.0,
  consolidacao_status: "concluida", checklist: [
    { id: "i1", origem: "psi_audit", item_codigo: "k", titulo: "t", status_before: "fail", status_after: "pass", status_implementacao: "implementado", nota_cliente: null, nota_seo: null, prioridade: 1, esforco: "alto", escopo_json: {} },
  ],
  n_pass_before: 9, n_fail_before: 29, n_implementados: 1,
  relatorio_json: null, criado_em: "2026-07-15T00:00:00Z", atualizado_em: "2026-07-15T00:00:00Z",
} as unknown as AuditoriaResposta;

describe("VisaoGeralTab", () => {
  it("donuts + top consolidados", async () => {
    mockListar.mockResolvedValue({ auditorias: [] });
    render(
      <VisaoGeralTab
        auditoria={auditoria}
        consolidados={[{ id: "c1", titulo: "Execução pesada", causa_raiz: "Bundle grande", severidade: 5, esforco: "alto", metricas_afetadas: ["TBT"], prioridade_ordem: 1, kb_codigo: null, problemas_origem_ids: [], escopo_json: {}, evidencias_json: {}, recomendacao_md: null } as never]}
        onIrParaChecklist={() => {}}
      />
    );
    expect(screen.getByTestId("donut-before")).toBeInTheDocument();
    expect(screen.getByTestId("donut-after")).toBeInTheDocument();
    expect(screen.getByText("Execução pesada")).toBeInTheDocument();
    await waitFor(() => expect(mockListar).toHaveBeenCalledWith("c1"));
  });
});

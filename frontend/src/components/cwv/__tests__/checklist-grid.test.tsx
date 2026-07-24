import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

const buscarDetalheMock = vi.fn();
vi.mock("@/lib/api/cwv", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/cwv")>()),
  buscarDetalheItemChecklist: (...a: unknown[]) => buscarDetalheMock(...a),
}));

import { ChecklistGrid } from "@/components/cwv/auditoria/checklist-grid";
import type { ChecklistItemResposta } from "@/lib/api/cwv";

const item = (over: Partial<ChecklistItemResposta> = {}): ChecklistItemResposta => ({
  id: "i1", origem: "psi_audit", item_codigo: "k1", titulo: "Execução pesada",
  status_before: "fail", status_after: null, status_implementacao: "nao_executado",
  nota_cliente: null, nota_seo: null, prioridade: 1, esforco: "alto", escopo_json: { urls: [] },
  metricas_afetadas: [],
  ...over,
});

const detalheKb = (over: Record<string, unknown> = {}) => ({
  item_codigo: "k1", titulo: "Execução pesada", tem_kb: true,
  descricao: "Imagem do LCP pesada demais", severidade: 5,
  metricas_afetadas: ["LCP"], solucao_geral: "Comprima a imagem e sirva WebP",
  solucao_plataforma: null, plataforma: "wordpress", links_referencia: [],
  esforco: "alto", urls_escopo: [], evidencias: [],
  ...over,
});

describe("ChecklistGrid", () => {
  it("agrupa por origem com contadores", () => {
    render(
      <ChecklistGrid
        checklist={[item({}), item({ id: "i2", origem: "field_data", item_codigo: "crux_lcp", titulo: "CrUX LCP", status_before: "pass", prioridade: 0 })]}
        salvandoId={null}
        onAtualizarItem={() => {}}
      />
    );
    expect(screen.getByText(/Page Speed Insights/)).toBeInTheDocument();
    expect(screen.getByText(/Dados de campo/)).toBeInTheDocument();
  });

  it("filtro Reprovados esconde os pass", () => {
    render(
      <ChecklistGrid
        checklist={[item({}), item({ id: "i2", titulo: "Item aprovado", status_before: "pass", prioridade: 0 })]}
        salvandoId={null}
        onAtualizarItem={() => {}}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /reprovados/i }));
    expect(screen.getByText("Execução pesada")).toBeInTheDocument();
    expect(screen.queryByText("Item aprovado")).not.toBeInTheDocument();
  });

  it("mudar implementação dispara PATCH", () => {
    const onAtualizar = vi.fn();
    render(<ChecklistGrid checklist={[item({})]} salvandoId={null} onAtualizarItem={onAtualizar} />);
    fireEvent.change(screen.getByDisplayValue("Não executado"), { target: { value: "implementado" } });
    expect(onAtualizar).toHaveBeenCalledWith("i1", { status_implementacao: "implementado" });
  });

  it("editar prioridade dispara PATCH no blur", () => {
    const onAtualizar = vi.fn();
    render(<ChecklistGrid checklist={[item({})]} salvandoId={null} onAtualizarItem={onAtualizar} />);
    const input = screen.getByLabelText(/prioridade de Execução pesada/i);
    fireEvent.change(input, { target: { value: "5" } });
    fireEvent.blur(input);
    expect(onAtualizar).toHaveBeenCalledWith("i1", { prioridade: 5 });
  });

  it("item na não conta como reprovado", () => {
    render(
      <ChecklistGrid
        checklist={[item({ id: "i3", titulo: "Safe Browsing", status_before: "na", prioridade: 0 })]}
        salvandoId={null}
        onAtualizarItem={() => {}}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /reprovados/i }));
    expect(screen.queryByText("Safe Browsing")).not.toBeInTheDocument();
  });

  it("abrir Detalhe busca a ficha da KB e mostra o como corrigir", async () => {
    buscarDetalheMock.mockResolvedValue(detalheKb());
    render(<ChecklistGrid checklist={[item({})]} salvandoId={null} onAtualizarItem={() => {}} auditoriaId="a1" />);
    fireEvent.click(screen.getByRole("button", { name: /detalhe de Execução pesada/i }));
    await waitFor(() => expect(screen.getByText(/Comprima a imagem e sirva WebP/)).toBeInTheDocument());
    expect(buscarDetalheMock).toHaveBeenCalledWith("a1", "i1");
    expect(screen.getByText(/Imagem do LCP pesada demais/)).toBeInTheDocument();
  });

  it("coluna Escopo mostra contagem de URLs do escopo", () => {
    render(
      <ChecklistGrid
        checklist={[item({ escopo_json: { urls: ["https://a.com/", "https://b.com/", "https://c.com/"] } })]}
        salvandoId={null}
        onAtualizarItem={() => {}}
      />
    );
    expect(screen.getByText("3 URL(s)")).toBeInTheDocument();
  });

  // SPEC_CWV_Checklist_Metric_Impact
  it("filtro por métrica INP/TBT esconde itens de outra métrica", () => {
    render(
      <ChecklistGrid
        checklist={[
          item({ id: "a", titulo: "Item LCP", metricas_afetadas: ["LCP", "FCP"] }),
          item({ id: "b", titulo: "Item INP", metricas_afetadas: ["INP"] }),
        ]}
        salvandoId={null}
        onAtualizarItem={() => {}}
      />
    );
    expect(screen.getByText("Item LCP")).toBeInTheDocument();
    expect(screen.getByText("Item INP")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "INP/TBT" }));
    expect(screen.getByText("Item INP")).toBeInTheDocument();
    expect(screen.queryByText("Item LCP")).not.toBeInTheDocument();
  });

  // SPEC_CWV_Checklist_Itens_Manuais
  it("item manual: status Before editável dispara PATCH status_before", () => {
    const onAtualizar = vi.fn();
    render(
      <ChecklistGrid
        checklist={[item({ id: "m", item_codigo: "manual_popups", titulo: "Pop-ups intrusivos", origem: "page_experience", status_before: "na", prioridade: 0 })]}
        salvandoId={null}
        onAtualizarItem={onAtualizar}
      />
    );
    fireEvent.change(screen.getByLabelText(/status before de Pop-ups intrusivos/i), { target: { value: "fail" } });
    expect(onAtualizar).toHaveBeenCalledWith("m", { status_before: "fail" });
  });

  it("item automático não tem select de status (read-only)", () => {
    render(<ChecklistGrid checklist={[item({})]} salvandoId={null} onAtualizarItem={() => {}} />);
    expect(screen.queryByLabelText(/status before de/i)).not.toBeInTheDocument();
  });

  // SPEC_CWV_Detalhe_Evidencias_Elementos
  it("painel Detalhe mostra Elementos com falha quando há evidências", async () => {
    buscarDetalheMock.mockResolvedValue(detalheKb({
      evidencias: [{ url_canonica: "https://a.com/", estrategia: "mobile", elementos: ["img.hero", "div#banner"], total: 2 }],
    }));
    render(<ChecklistGrid checklist={[item({})]} salvandoId={null} onAtualizarItem={() => {}} auditoriaId="a1" />);
    fireEvent.click(screen.getByRole("button", { name: /detalhe de Execução pesada/i }));
    await waitFor(() => expect(screen.getByText(/Elementos com falha/)).toBeInTheDocument());
    expect(screen.getByText("img.hero")).toBeInTheDocument();
    expect(screen.getByText("div#banner")).toBeInTheDocument();
    expect(screen.getByText(/2 elementos/)).toBeInTheDocument();
  });

  it("evidências com total > exibidos mostra '+N não exibidos'", async () => {
    buscarDetalheMock.mockResolvedValue(detalheKb({
      evidencias: [{ url_canonica: "https://a.com/", estrategia: "mobile", elementos: ["a", "b"], total: 12 }],
    }));
    render(<ChecklistGrid checklist={[item({})]} salvandoId={null} onAtualizarItem={() => {}} auditoriaId="a1" />);
    fireEvent.click(screen.getByRole("button", { name: /detalhe de Execução pesada/i }));
    await waitFor(() => expect(screen.getByText(/\+ 10 elementos não exibidos/)).toBeInTheDocument());
  });
});

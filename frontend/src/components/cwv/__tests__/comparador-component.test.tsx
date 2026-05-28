import { ComparadorComponent } from "@/components/cwv/comparador-component";
import { ComparacaoResposta } from "@/lib/api/cwv";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock do CSS module para evitar problemas de importação
jest.mock("@/lib/utils", () => ({
  cn: (...args: any[]) => args.join(" ")
}));

describe("ComparadorComponent", () => {
  const mockComparacao: ComparacaoResposta = {
    analise_atual_id: "current-id",
    analise_anterior_id: "previous-id",
    dias_decorridos: 7,
    metricas: {
      score_performance: {
        antes: 70,
        depois: 85,
        delta: 15,
        melhorou: true
      },
      lcp_ms: {
        antes: 3000,
        depois: 2000,
        delta: -1000,
        melhorou: true
      },
      cls: {
        antes: 0.1,
        depois: 0.08,
        delta: -0.02,
        melhorou: true
      },
      inp_ms: {
        antes: 300,
        depois: 250,
        delta: -50,
        melhorou: true
      }
    },
    problemas_resolvidos: [
      {
        kb_codigo: "LCP_IMAGE",
        titulo: "Imagem do LCP muito grande"
      },
      {
        kb_codigo: "CSS_RENDER_BLOCK", 
        titulo: "CSS bloqueante"
      }
    ],
    problemas_novos: [
      {
        kb_codigo: "CLS_IFRAME",
        titulo: "Layout shift em iframe"
      }
    ],
    problemas_persistentes: [
      {
        kb_codigo: "TBT_LARGE_TASK",
        titulo: "Tarefas longas no main thread"
      }
    ]
  };

  it("deve renderizar quando comparação está disponível", () => {
    render(<ComparadorComponent comparacao={mockComparacao} />);
    
    expect(screen.getByText("Comparação com análise anterior (7 dias atrás)")).toBeInTheDocument();
    expect(screen.getByText("Melhoraram")).toBeInTheDocument();
    expect(screen.getByText("Problemas resolvidos (2)")).toBeInTheDocument();
    expect(screen.getByText("Novos problemas (1)")).toBeInTheDocument();
    expect(screen.getByText("Problemas persistentes (1)")).toBeInTheDocument();
  });

  it("não deve renderizar quando comparação é null", () => {
    const { container } = render(<ComparadorComponent comparacao={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("não deve renderizar quando não tem análise anterior", () => {
    const semAnterior = { ...mockComparacao, analise_anterior_id: null };
    render(<ComparadorComponent comparacao={semAnterior} />);
    expect(screen.getByText("Comparação com análise anterior")).toBeInTheDocument();
    expect(screen.getByText("Primeira análise — registre mais para acompanhar evolução.")).toBeInTheDocument();
  });

  it("deve formatar corretamente deltas positivos e negativos", () => {
    render(<ComparadorComponent comparacao={mockComparacao} />);
    
    // Score melhorou (positivo)
    expect(screen.getByText("+15")).toBeInTheDocument();
    
    // LCP melhorou (negativo mas convertido para positivo)
    expect(screen.getByText("-1.0s")).toBeInTheDocument();
    expect(screen.getByText("2.0s")).toBeInTheDocument();
  });

  it("deve mostrar problemas resolvidos com checkmarks", () => {
    render(<ComparadorComponent comparacao={mockComparacao} />);
    
    const resolvedProblems = screen.getAllByText("✓");
    expect(resolvedProblems).toHaveLength(2);
    expect(screen.getByText("Imagem do LCP muito grande")).toBeInTheDocument();
    expect(screen.getByText("CSS bloqueante")).toBeInTheDocument();
  });

  it("deve mostrar novos problemas com pontos de exclamação", () => {
    render(<ComparadorComponent comparacao={mockComparacao} />);
    
    const newProblems = screen.getAllByText("!");
    expect(newProblems).toHaveLength(1);
    expect(screen.getByText("Layout shift em iframe")).toBeInTheDocument();
  });

  it("deve mostrar problemas persistentes com símbolo de igual", () => {
    render(<ComparadorComponent comparacao={mockComparacao} />);
    
    const persistentProblems = screen.getAllByText("≈");
    expect(persistentProblems).toHaveLength(1);
    expect(screen.getByText("Tarefas longas no main thread")).toBeInTheDocument();
  });

  it("deve mostrar mensagem quando não há mudanças significativas", () => {
    const semMudancas: ComparacaoResposta = {
      ...mockComparacao,
      metricas: {},
      problemas_resolvidos: [],
      problemas_novos: [],
      problemas_persistentes: []
    };
    
    render(<ComparadorComponent comparacao={semMudancas} />);
    
    expect(screen.getByText("Nenhuma mudança significativa detectada")).toBeInTheDocument();
  });

  it("deve filtrar e agrupar corretamente métricas que melhoraram/pioraram", () => {
    const comPiora: ComparacaoResposta = {
      ...mockComparacao,
      metricas: {
        ...mockComparacao.metricas,
        inp_ms: {
          antes: 200,
          depois: 300,
          delta: 100,
          melhorou: false
        },
        fcp_ms: {
          antes: 1000,
          depois: 1200,
          delta: 200,
          melhorou: false
        }
      }
    };
    
    render(<ComparadorComponent comparacao={comPiora} />);
    
    // Deve ter seções para melhoraram e pioraram
    expect(screen.getByText("Melhoraram")).toBeInTheDocument();
    expect(screen.getByText("Pioraram")).toBeInTheDocument();
    
    // Ambas as seções devem ter métricas
    expect(screen.getByText("LCP")).toBeInTheDocument(); // Melhorou
    expect(screen.getByText("INP")).toBeInTheDocument(); // Piorou
    expect(screen.getByText("FCP")).toBeInTheDocument(); // Piorou
  });

  it("deve formatar valores pequenos corretamente", () => {
    const metricaPequena = {
      antes: 0.08,
      depois: 0.05,
      delta: -0.03,
      melhorou: true
    };
    
    const comparacaoPequena: ComparacaoResposta = {
      ...mockComparacao,
      metricas: { cls: metricaPequena }
    };
    
    render(<ComparadorComponent comparacao={comparacaoPequena} />);
    
    expect(screen.getByText("-0.03")).toBeInTheDocument();
  });
});
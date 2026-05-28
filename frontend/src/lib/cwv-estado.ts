import type { CwvAnaliseResposta } from "@/lib/api/cwv";

export type EstadoAnalise =
  | { tipo: "rasa"; motivos: string[] }
  | { tipo: "otimizado" }
  | { tipo: "quase_pronto"; nProblemas: number }
  | { tipo: "muitos_problemas"; nProblemas: number; nCriticos: number; top3: string[] }
  | { tipo: "normal"; nProblemas: number }
  | { tipo: "falhou" };

export function classificarAnalise(analise: CwvAnaliseResposta): EstadoAnalise {
  if (analise.status !== "sucesso") return { tipo: "falhou" };

  const problemas = analise.problemas ?? [];
  const nProblemas = problemas.length;
  const nCriticos = problemas.filter((p) => p.severidade >= 4).length;

  const motivos: string[] = [];
  if (analise.audits_totais > 0 && analise.audits_totais < 30) {
    motivos.push(`Lighthouse rodou apenas ${analise.audits_totais} audits`);
  }
  if (analise.main_document_size_bytes > 0 && analise.main_document_size_bytes < 5000) {
    motivos.push(`HTML muito pequeno (${(analise.main_document_size_bytes / 1024).toFixed(1)}KB)`);
  }
  if (analise.n_network_requests > 0 && analise.n_network_requests < 5) {
    motivos.push(`apenas ${analise.n_network_requests} requisicoes`);
  }
  if (motivos.length >= 1 && nProblemas === 0) {
    return { tipo: "rasa", motivos };
  }

  if (nProblemas === 0) return { tipo: "otimizado" };

  if (nProblemas <= 3 && nCriticos === 0) {
    return { tipo: "quase_pronto", nProblemas };
  }

  if (nProblemas > 5 || nCriticos >= 2) {
    return {
      tipo: "muitos_problemas",
      nProblemas,
      nCriticos,
      top3: problemas.slice(0, 3).map((p) => p.titulo),
    };
  }

  return { tipo: "normal", nProblemas };
}

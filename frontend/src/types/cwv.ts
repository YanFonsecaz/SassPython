export interface MetricaComparada {
  antes: number | null;
  depois: number | null;
  delta: number | null;
  melhorou: boolean | null;
}

export interface ProblemaComparado {
  kb_codigo: string;
  titulo: string;
}

export interface ComparacaoResposta {
  analise_atual_id: string;
  analise_anterior_id: string | null;
  dias_decorridos: number | null;
  metricas: Record<string, MetricaComparada>;
  problemas_resolvidos: ProblemaComparado[];
  problemas_novos: ProblemaComparado[];
  problemas_persistentes: ProblemaComparado[];
}
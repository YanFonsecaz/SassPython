"use client";

import { useEffect, useRef, useState } from "react";
import {
  SearchIcon,
  BarChart3Icon,
  FileTextIcon,
  PenLineIcon,
  ShieldCheckIcon,
  DatabaseIcon,
  ImageIcon,
  EyeIcon,
  CircleCheckIcon,
  Loader2Icon,
  ClockIcon,
  LinkIcon,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { NodeActivity } from "@/types";

const NODE_ICONS: Record<string, React.ElementType> = {
  pesquisar: SearchIcon,
  analisar: BarChart3Icon,
  criar_brief: FileTextIcon,
  redigir: PenLineIcon,
  revisar: ShieldCheckIcon,
  marcar_aguardando: EyeIcon,
  aguardar_aprovacao: EyeIcon,
  salvar_vetorial: DatabaseIcon,
  gerar_imagem: ImageIcon,
  validar_urls: ShieldCheckIcon,
  extrair_pilar: FileTextIcon,
  extrair_candidatos: SearchIcon,
  enriquecer: DatabaseIcon,
  match_rerank: BarChart3Icon,
  gerar_ancoras: PenLineIcon,
  injetar: LinkIcon,
  revisar_inlinks: ShieldCheckIcon,
  persistir: DatabaseIcon,
};

const NODE_LABELS: Record<string, string> = {
  pesquisar: "Pesquisar",
  analisar: "Analisar",
  criar_brief: "Criar Brief",
  redigir: "Redigir",
  revisar: "Revisar",
  marcar_aguardando: "Aguardar Aprovação",
  aguardar_aprovacao: "Aguardar Aprovação",
  salvar_vetorial: "Salvar Vetorial",
  gerar_imagem: "Gerar Imagem",
  validar_urls: "Validar URLs",
  extrair_pilar: "Extrair Pilar",
  extrair_candidatos: "Extrair Candidatos",
  enriquecer: "Gerar Embeddings",
  match_rerank: "Ranquear",
  gerar_ancoras: "Gerar Âncoras",
  injetar: "Injetar Inlinks",
  revisar_inlinks: "Revisar Inlinks",
  persistir: "Persistir",
};

const ETAPAS_ORDER_ARTIGO = [
  "pesquisar",
  "analisar", 
  "criar_brief",
  "redigir",
  "revisar",
  "aguardar_aprovacao",
  "salvar_vetorial",
  "gerar_imagem",
];

const ETAPAS_ORDER_INLINKS = [
  "validar_urls",
  "extrair_pilar",
  "extrair_candidatos",
  "enriquecer",
  "match_rerank",
  "gerar_ancoras",
  "injetar",
  "revisar",
  "persistir",
];

const APROVACAO_LABELS: Record<string, string> = {
  aguardando_aprovacao: "Aguardando sua aprovação...",
  aguardando_revisao: "Aguardando seu feedback...",
};

// Dicas contextuais por etapa
const DICAS_POR_ETAPA: Record<string, string[]> = {
  pesquisar: [
    "Estamos pesquisando as melhores fontes sobre seu tema...",
    "Buscando dados atualizados e relevantes...",
    "Analisando tendências e conteúdo popular...",
  ],
  analisar: [
    "Selecionando os melhores fontes para seu artigo...",
    "Filtrando conteúdo relevante e atual...",
    "Preparando briefing para a redação...",
  ],
  criar_brief: [
    "Criando estrutura ótima para seu artigo...",
    "Definindo tópicos e caminho do conteúdo...",
    "Preparando parâmetros para a IA redatora...",
  ],
  redigir: [
    "A IA está redigindo seu artigo com SEO otimizado...",
    "Criando versão com base no brief definido...",
    "Escrevendo conteúdo de alta qualidade e relevante...",
  ],
  revisar: [
    "Revisando qualidade e precisão do conteúdo...",
    "Verificando otimização SEO e clareza...",
    "Ajustando melhorias na redação...",
  ],
  aguardar_aprovacao: [
    "Artigo pronto! Aguardando sua revisão...",
    "Versão finalizada para sua avaliação...",
    "Pronto para seu feedback e aprovação...",
  ],
  salvar_vetorial: [
    "Salvando seu artigo na base de conhecimento...",
    "Indexando conteúdo para busca futura...",
    "Armazenando artigo para referência posterior...",
  ],
  gerar_imagem: [
    "Gerando imagem com IA para seu artigo...",
    "Criando visualização única para o conteúdo...",
    "Processando imagem otimizada para seu texto...",
  ],
};

const TEMPOS_ESTIMADOS: Record<string, number> = {
  pesquisar: 30, // 30 segundos
  analisar: 25,  // 25 segundos
  criar_brief: 15, // 15 segundos
  redigir: 45,  // 45 segundos (o mais longo)
  revisar: 20,  // 20 segundos
  aguardar_aprovacao: 0, // Não controlável
  salvar_vetorial: 10,  // 10 segundos
  gerar_imagem: 15,  // 15 segundos
};

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString("pt-BR", {
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

interface BarraProgressoWorkflowProps {
  etapaAtual: string | null;
  status: string | null;
  nodeHistory: NodeActivity[];
  currentNodeDetail: string | null;
  ferramenta?: string;
}

export function BarraProgressoWorkflow({
  etapaAtual,
  status,
  nodeHistory,
  currentNodeDetail,
  ferramenta,
}: BarraProgressoWorkflowProps) {
  const isInlinks = ferramenta === "inlinks_automaticos";

  const ETAPAS_ORDER = isInlinks ? ETAPAS_ORDER_INLINKS : ETAPAS_ORDER_ARTIGO;

  const nodeLabelsResolved: Record<string, string> = isInlinks
    ? { ...NODE_LABELS, revisar: "Revisar Inlinks" }
    : NODE_LABELS;
  const inicioRef = useRef<number>(0);
  const [tempoDecorrido, setTempoDecorrido] = useState(0);
  const [indiceDicaAtual, setIndiceDicaAtual] = useState(0);
  const ultimaEtapaRef = useRef<string>(etapaAtual);

  const isFinalizado =
    status === "concluida" ||
    status === "falhou" ||
    status === "cancelada";

  const isAguardando =
    status === "aguardando_aprovacao" ||
    status === "aguardando_revisao";

  // Get current dicas based on etapaAtual
  const dicasAtuais = etapaAtual ? DICAS_POR_ETAPA[etapaAtual] || [] : [];
  const dicaAtual = dicasAtuais[indiceDicaAtual] || dicasAtuais[0] || "Processando...";

  useEffect(() => {
    inicioRef.current = Date.now();
  }, []);

  // Update time elapsed
  useEffect(() => {
    if (isFinalizado) return;
    const interval = setInterval(() => {
      setTempoDecorrido(
        Math.floor((Date.now() - inicioRef.current) / 1000)
      );
    }, 1000);
    return () => clearInterval(interval);
  }, [isFinalizado]);

  // Rotate dicas every 8 seconds
  useEffect(() => {
    if (dicasAtuais.length <= 1) return;
    
    const interval = setInterval(() => {
      setIndiceDicaAtual(prev => (prev + 1) % dicasAtuais.length);
    }, 8000);

    return () => clearInterval(interval);
  }, [dicasAtuais.length]);

  // Update etapaAtual in refs
  useEffect(() => {
    if (etapaAtual) {
      ultimaEtapaRef.current = etapaAtual;
    }
  }, [etapaAtual]);

  const etapaIndex = ETAPAS_ORDER.indexOf(etapaAtual || ultimaEtapaRef.current || "");
  const progresso =
    etapaIndex < 0
      ? 0
      : ((etapaIndex + 1) / ETAPAS_ORDER.length) * 100;

  const completedNodes = new Set<string>();
  for (const a of nodeHistory) {
    if (!a.isStart) {
      completedNodes.add(a.node);
    }
  }

  const lastCompletedIndex = Math.max(
    ...ETAPAS_ORDER.map((n, i) => (completedNodes.has(n) ? i : -1))
  );
  const activeNode = !isFinalizado && !isAguardando ? etapaAtual : null;
  const proximaEtapa = ETAPAS_ORDER[etapaIndex + 1];

  // Calculate estimated time for current stage
  const tempoEtapaAtual = etapaAtual ? TEMPOS_ESTIMADOS[etapaAtual] || 30 : 0;
  const tempoRestanteEstimado = Math.max(0, tempoEtapaAtual - (tempoDecorrido % (tempoEtapaAtual || 30)));

  return (
    <div className="space-y-6 animate-slide-in-up">
      {/* Horizontal Stepper */}
      <div className="space-y-4">
        <div className="relative">
          {/* Progress line */}
          <div className="absolute top-5 left-0 w-full h-1 bg-muted z-0"></div>
          <div
            className="absolute top-5 left-0 h-1 bg-brand transition-all duration-1000 ease-out z-10"
            style={{ width: `${progresso}%` }}
          ></div>
          
          <div className="relative flex items-center justify-between z-20">
            {ETAPAS_ORDER.map((node, index) => {
              const Icon = NODE_ICONS[node] || FileTextIcon;
              const isCompleted = completedNodes.has(node);
              const isActive = node === etapaAtual;
              const isFuture = index > etapaIndex;
              
              return (
                <div key={node} className="flex flex-col items-center flex-1">
                  {/* Step circle */}
                  <div className="relative">
                    <div
                      className={cn(
                        "flex items-center justify-center size-10 rounded-full border-2 transition-all duration-300",
                        isCompleted && "bg-brand border-brand text-white",
                        isActive && "border-brand animate-breathing shadow-lg",
                        isFuture && "border-muted text-muted-foreground"
                      )}
                    >
                      {isCompleted ? (
                        <CircleCheckIcon className="size-5" />
                      ) : isActive ? (
                        <Loader2Icon className="size-5 animate-spin" />
                      ) : (
                        <Icon className="size-5" />
                      )}
                    </div>
                    
                    {/* Active glow */}
                    {isActive && (
                      <div className="absolute inset-0 rounded-full bg-brand/20 animate-pulse-dot"></div>
                    )}
                  </div>
                  
                  {/* Label */}
                  <div className="mt-2 text-center">
                    <p
                      className={cn(
                        "text-xs font-medium transition-colors",
                        isActive && "text-brand",
                        isCompleted && "text-foreground",
                        isFuture && "text-muted-foreground"
                      )}
                    >
                      {nodeLabelsResolved[node] || node}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Activity Panel */}
      {!isFinalizado && (
        <div className="space-y-4">
          {/* Main Activity Card */}
          <div className="glass-card rounded-xl p-6 space-y-4 animate-slide-in-up">
            <div className="flex items-center gap-4">
              {/* Active icon with breathing animation */}
              {etapaAtual ? (
                <div className="animate-breathing">
                  <div className="size-12 rounded-full bg-brand/10 flex items-center justify-center">
                    {(() => {
                      const Icon = NODE_ICONS[etapaAtual] || Loader2Icon;
                      return <Icon className="size-6 text-brand" />;
                    })()}
                  </div>
                </div>
              ) : (
                <div className="animate-breathing">
                  <div className="size-12 rounded-full bg-brand/10 flex items-center justify-center">
                    <Loader2Icon className="size-6 text-brand animate-spin" />
                  </div>
                </div>
              )}
              
              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-lg">
                    {isAguardando ? APROVACAO_LABELS[status || ""] : etapaAtual ? `Processando ${nodeLabelsResolved[etapaAtual] || etapaAtual}` : "Iniciando processo..."}
                  </h3>
                  <ClockIcon className="size-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">
                    {Math.floor(tempoDecorrido / 60)}:{String(tempoDecorrido % 60).padStart(2, "0")}
                  </span>
                </div>
                {tempoRestanteEstimado > 0 && !isAguardando && (
                  <p className="text-sm text-muted-foreground animate-fade-rotate">
                    Estimado: ~{tempoRestanteEstimado}s restantes
                  </p>
                )}
              </div>
            </div>
            
            {/* Shimmer progress bar */}
            <div className="relative">
              <Progress value={progresso} className="h-2" />
              {!isAguardando && (
                <div className="absolute inset-0 h-2 animate-shimmer rounded-full bg-gradient-to-r from-transparent via-white/20 to-transparent"></div>
              )}
            </div>
            
            {/* Contextual Tips */}
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">O que está acontecendo:</p>
              <div className="space-y-1">
                {currentNodeDetail && (
                  <p className="text-sm font-medium">{currentNodeDetail}</p>
                )}
                {!currentNodeDetail && (
                  <p className="text-sm text-muted-foreground animate-fade-rotate">
                    {dicaAtual}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Timeline View - Compact */}
      {nodeHistory.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">
            Atividade Recente
          </p>
          <div className="space-y-1.5">
            {nodeHistory.slice(-5).map((activity, i) => {
              const Icon = NODE_ICONS[activity.node] || FileTextIcon;
              const label = nodeLabelsResolved[activity.node] || activity.node;
              const isLast = i === nodeHistory.length - 1;
              const isActive = isLast && activity.isStart;

              return (
                <div
                  key={`${activity.node}-${activity.timestamp}-${i}`}
                  className="flex items-start gap-3 text-xs"
                >
                  <div className="relative shrink-0 mt-1">
                    {isActive ? (
                      <div className="size-4 rounded-full bg-brand/10 animate-breathing">
                        <Loader2Icon className="size-3 text-brand animate-spin" />
                      </div>
                    ) : !activity.isStart ? (
                      <div className="size-4 rounded-full bg-green-100 flex items-center justify-center">
                        <CircleCheckIcon className="size-3 text-green-600" />
                      </div>
                    ) : (
                      <Icon className="size-4 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={cn(
                          isActive ? "font-medium text-foreground" : "text-muted-foreground"
                        )}
                      >
                        {label}
                      </span>
                      <span className="text-muted-foreground/60">
                        {formatTimestamp(activity.timestamp)}
                      </span>
                    </div>
                    <p
                      className={cn(
                        isActive ? "text-foreground" : "text-muted-foreground"
                      )}
                    >
                      {activity.detail}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Finalizado Panel */}
      {isFinalizado && (
        <div className="glass-card rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-full bg-green-100 flex items-center justify-center">
                <CircleCheckIcon className="size-5 text-green-600" />
              </div>
              <div>
                <p className="font-semibold text-lg">
                  {status === "concluida" ? "Concluído!" : status === "cancelada" ? "Cancelado" : "Falhou"}
                </p>
                <p className="text-sm text-muted-foreground">
                  Duração total: {Math.floor(tempoDecorrido / 60)}:{String(tempoDecorrido % 60).padStart(2, "0")}
                </p>
              </div>
            </div>
          </div>
          
          {nodeHistory.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">
                Histórico Completo
              </p>
              <div className="space-y-1.5">
                {ETAPAS_ORDER.map((node) => {
                  const isCompleted = completedNodes.has(node);
                  const Icon = NODE_ICONS[node] || FileTextIcon;
                  const label = nodeLabelsResolved[node] || node;
                  const activity = nodeHistory.find(a => a.node === node && !a.isStart);
                  const startTime = nodeHistory.find(a => a.node === node && a.isStart);

                  if (!isCompleted) return null;

                  return (
                    <div key={node} className="flex items-start gap-3 text-xs">
                      <div className="size-4 rounded-full bg-green-100 flex items-center justify-center shrink-0 mt-1">
                        <CircleCheckIcon className="size-3 text-green-600" />
                      </div>
                      <div className="flex-1 space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-foreground">{label}</span>
                          {startTime?.timestamp && (
                            <span className="text-muted-foreground/60">
                              {formatTimestamp(startTime.timestamp)}
                            </span>
                          )}
                        </div>
                        {activity?.detail && (
                          <p className="text-muted-foreground">{activity.detail}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
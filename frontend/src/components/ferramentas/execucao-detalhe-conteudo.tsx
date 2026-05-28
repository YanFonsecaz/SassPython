"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useExecucao } from "@/hooks/use-execucao";
import { useVersoes } from "@/hooks/use-versoes";
import { PageHeader } from "@/components/ui/page-header";
import { BarraProgressoWorkflow } from "@/components/ferramentas/barra-progresso-workflow";
import { PainelAprovacao } from "@/components/ferramentas/painel-aprovacao";
import { PreviewArtigo } from "@/components/ferramentas/preview-artigo";
import { ComparadorVersoes } from "@/components/ferramentas/comparador-versoes";
import { ComparadorPilarInlinks } from "@/components/ferramentas/comparador-pilar-inlinks";
import { InlinksResultado } from "@/components/ferramentas/inlinks-resultado";
import { DistribuirInlinksResultado } from "@/components/ferramentas/distribuir-inlinks-resultado";
import { cn } from "@/lib/utils";
import {
  CircleCheckIcon, AlertTriangleIcon, ArrowLeftIcon, CreditCardIcon,
} from "lucide-react";
import type { ExecucaoDetalhe, VersaoArtigo, InlinkAplicado, ResultadoDistribuirInlinks } from "@/types";

function labelFerramenta(f: string): string {
  switch (f) {
    case "gerar_artigo": return "Gerar artigo";
    case "inlinks_automaticos": return "Inlinks automaticos";
    case "distribuir_inlinks": return "Distribuir inlinks";
    case "core_web_vitals": return "Core Web Vitals";
    default: return f;
  }
}

function mensagemSucessoFerramenta(f: string): string {
  switch (f) {
    case "distribuir_inlinks": return "Distribuicao concluida com sucesso";
    case "inlinks_automaticos": return "Inlinks aplicados com sucesso";
    case "core_web_vitals": return "Analise CWV concluida com sucesso";
    default: return "Artigo concluido com sucesso";
  }
}

function statusLabel(status: string) {
  switch (status) {
    case "pendente":
    case "enfileirado":
      return { label: "Pendente", color: "text-muted-foreground", bg: "bg-muted-foreground/10" };
    case "executando":
      return { label: "Executando", color: "text-brand-dark", bg: "bg-brand/15" };
    case "aguardando_aprovacao":
      return { label: "Aguardando aprovação", color: "text-brand-dark", bg: "bg-brand/15" };
    case "aguardando_revisao":
      return { label: "Em revisão", color: "text-warning", bg: "bg-warning/10" };
    case "concluida":
      return { label: "Concluída", color: "text-success", bg: "bg-success/10" };
    case "falhou":
      return { label: "Falhou", color: "text-destructive", bg: "bg-destructive/10" };
    case "cancelada":
      return { label: "Cancelada", color: "text-muted-foreground", bg: "bg-muted-foreground/10" };
    default:
      return { label: status, color: "text-muted-foreground", bg: "bg-muted-foreground/10" };
  }
}

function SkeletonCarregando() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-8 w-20 rounded-lg bg-muted" />
        <div className="h-8 w-48 rounded-lg bg-muted" />
      </div>
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-muted" />
        <div className="h-3 w-3/4 rounded bg-muted" />
      </div>
      <div className="space-y-2">
        <div className="h-4 w-1/3 rounded bg-muted" />
        <div className="h-4 rounded-xl bg-muted" />
      </div>
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-3 rounded bg-muted" style={{ width: `${90 - i * 10}%` }} />
        ))}
      </div>
    </div>
  );
}

export function ExecucaoDetalheConteudo() {
  const pathname = usePathname();
  const router = useRouter();
  const id = pathname.split("/").pop() || "";

  const {
    execucao,
    etapaAtual,
    carregando,
    conectarProgresso,
    desconectarProgresso,
    aprovar,
    cancelar,
    carregarExecucao,
    nodeHistory,
    currentNodeDetail,
  } = useExecucao();

  const { versoes, carregar } = useVersoes();
  const [detalhe, setDetalhe] = useState<ExecucaoDetalhe | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [tab, setTab] = useState("artigo");

  const ultimaVersao: VersaoArtigo | null = useMemo(() => {
    return versoes.length > 0 ? versoes[versoes.length - 1] : null;
  }, [versoes]);

  useEffect(() => {
    carregarExecucao(id);
    conectarProgresso(id);
    return () => desconectarProgresso();
  }, [id, carregarExecucao, conectarProgresso, desconectarProgresso]);

  useEffect(() => {
    if (
      execucao?.status === "aguardando_aprovacao" ||
      execucao?.status === "aguardando_revisao" ||
      execucao?.status === "concluida"
    ) {
      carregar(id);
    }
  }, [execucao?.status, id, carregar]);

  useEffect(() => {
    async function loadDetalhe() {
      try {
        const dados = await api.get<ExecucaoDetalhe>(`/ferramentas/historico/${id}`);
        setDetalhe(dados);
      } catch {
        // silent
      }
    }
    loadDetalhe();
  }, [id, execucao?.status]);

  // CWV: o resultado é renderizado no dashboard dedicado /core-web-vitals/url/{analise_id}.
  // Redireciona automaticamente quando análise está pronta.
  useEffect(() => {
    if (execucao?.ferramenta !== "core_web_vitals") return;
    if (execucao.status !== "concluida" && execucao.status !== "falhou") return;
    const analiseIds = (detalhe?.resultado_json?.analise_ids ?? []) as string[];
    if (analiseIds.length > 0) {
      router.replace(`/ferramentas/core-web-vitals/url/${analiseIds[0]}`);
    }
  }, [execucao?.ferramenta, execucao?.status, detalhe?.resultado_json, router]);

  async function handleAprovar() {
    setEnviando(true);
    const ok = await aprovar(id, "aprovar");
    if (ok) {
      toast.success("Aprovação enviada", { description: "O artigo será finalizado em instantes." });
      await carregarExecucao(id);
    } else {
      toast.error("Erro ao aprovar", { description: "Tente novamente." });
    }
    setEnviando(false);
  }

  async function handleReprovar(feedback: string) {
    setEnviando(true);
    const ok = await aprovar(id, "reprovar", feedback);
    if (ok) {
      toast.success("Feedback enviado", { description: "O artigo será revisado." });
      await carregarExecucao(id);
    } else {
      toast.error("Erro ao enviar feedback", { description: "Tente novamente." });
    }
    setEnviando(false);
  }

  async function handleCancelar() {
    setEnviando(true);
    const ok = await cancelar(id);
    if (ok) {
      toast.info("Execução cancelada");
      await carregarExecucao(id);
    } else {
      toast.error("Erro ao cancelar", { description: "Tente novamente." });
    }
    setEnviando(false);
  }

  if (carregando && !execucao) {
    return <SkeletonCarregando />;
  }

  if (!execucao) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <p className="text-muted-foreground mb-4">Execução não encontrada</p>
        <Link href="/ferramentas/historico" className={buttonVariants({ size: "sm" })}>Voltar ao histórico</Link>
      </div>
    );
  }

  const isAguardando =
    execucao.status === "aguardando_aprovacao" ||
    execucao.status === "aguardando_revisao";

  const resultado = detalhe?.resultado_json ?? {};
  const entrada = detalhe?.entrada_json ?? {};

  const artigoTitulo =
    (resultado.titulo as string) ||
    ultimaVersao?.titulo ||
    (entrada.topico as string) ||
    "Artigo";

  const artigoConteudo =
    (resultado.artigo as string) ||
    (resultado.conteudo_markdown as string) ||
    ultimaVersao?.conteudo_markdown ||
    "";

  const imagemUrl = resultado.imagem_url as string | undefined;
  const st = statusLabel(execucao.status);

  return (
    <div className="space-y-6">
      <PageHeader
        title={labelFerramenta(execucao.ferramenta)}
        description={execucao.ferramenta === "distribuir_inlinks" ? (resultado.titulo_alvo as string) || (entrada.url_alvo as string) || "" : artigoTitulo}
        action={
          <div className="flex items-center gap-2 pl-12 lg:pl-0">
            <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium", st.bg, st.color)}>
              {st.label}
            </span>
            {execucao.creditos_cobrados > 0 && (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <CreditCardIcon className="size-3" />
                {execucao.creditos_cobrados}
              </span>
            )}
          </div>
        }
      />

      {(execucao.status === "executando" ||
        execucao.status === "enfileirado" ||
        execucao.status === "pendente" ||
        isAguardando) && (
        <div className="border rounded-xl p-6">
          <BarraProgressoWorkflow
            etapaAtual={etapaAtual}
            status={execucao.status}
            nodeHistory={nodeHistory}
            currentNodeDetail={currentNodeDetail}
            ferramenta={execucao?.ferramenta}
          />
        </div>
      )}

      {execucao.status === "executando" && !enviando && (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={handleCancelar}>Cancelar execução</Button>
        </div>
      )}

      {execucao.status === "falhou" && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangleIcon className="size-5 text-destructive" />
            <p className="font-heading text-sm font-semibold text-destructive">Falha na execução</p>
          </div>
          <p className="text-sm text-muted-foreground">{execucao.erro_msg || "Erro desconhecido"}</p>
          <Link href="/ferramentas/gerar-artigo" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Tentar novamente
          </Link>
        </div>
      )}

      {execucao.status === "concluida" && execucao.ferramenta !== "core_web_vitals" && (
        <div className="rounded-xl border border-success/30 bg-success/5 px-4 py-3 flex items-center gap-2.5">
          <CircleCheckIcon className="size-5 text-success" />
          <p className="text-sm font-medium text-success">{mensagemSucessoFerramenta(execucao.ferramenta)}</p>
        </div>
      )}

      {execucao.status === "concluida" && execucao.ferramenta === "core_web_vitals" && (
        <div className="rounded-xl border bg-muted/30 p-6 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <span className="animate-spin inline-block size-4 border-2 border-current border-t-transparent rounded-full" />
          Abrindo dashboard CWV...
        </div>
      )}

      {isAguardando && !enviando && ultimaVersao && (
        <PainelAprovacao
          versaoAtual={ultimaVersao}
          tentativasRevisao={execucao.tentativas_revisao}
          tentativasFeedback={execucao.tentativas_feedback}
          onAprovar={handleAprovar}
          onReprovar={handleReprovar}
          onCancelar={handleCancelar}
          enviando={enviando}
        />
      )}

      {isAguardando && enviando && (
        <div className="rounded-xl border bg-muted/30 p-6 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <span className="animate-spin inline-block size-4 border-2 border-current border-t-transparent rounded-full" />
          Processando...
        </div>
      )}

      {execucao.status === "concluida" && execucao.ferramenta === "distribuir_inlinks" && (
        <DistribuirInlinksResultado resultado={resultado as unknown as ResultadoDistribuirInlinks} />
      )}

      {(isAguardando || execucao.status === "concluida") &&
        execucao.ferramenta !== "distribuir_inlinks" &&
        artigoConteudo && (
          execucao.ferramenta === "inlinks_automaticos" ? (
            <ComparadorPilarInlinks
              titulo={artigoTitulo}
              pilarOriginal={(resultado.pilar_original as string) || ""}
              pilarModificado={artigoConteudo}
              qtdInlinksAplicados={
                Array.isArray(resultado.inlinks)
                  ? (resultado.inlinks as InlinkAplicado[]).filter((i) => i.status === "aplicado").length
                  : 0
              }
            />
          ) : (
            <PreviewArtigo
              titulo={artigoTitulo}
              conteudo={artigoConteudo}
              imagemUrl={imagemUrl || undefined}
            />
          )
        )}

      {execucao.ferramenta === "inlinks_automaticos" &&
        execucao.status === "concluida" &&
        Array.isArray(resultado.inlinks) &&
        (resultado.inlinks as InlinkAplicado[]).length > 0 && (
          <div className="space-y-3">
            <div>
              <h3 className="font-heading text-base font-semibold">Inlinks aplicados</h3>
              <p className="text-xs text-muted-foreground">
                Onde cada link entrou no artigo e por que faz sentido aqui.
              </p>
            </div>
            <InlinksResultado
              inlinks={resultado.inlinks as InlinkAplicado[]}
              totalCandidatas={
                typeof resultado.n_candidatas_validas === "number"
                  ? (resultado.n_candidatas_validas as number)
                  : undefined
              }
            />
          </div>
        )}

      {(isAguardando || execucao.status === "concluida") &&
        execucao.ferramenta !== "distribuir_inlinks" &&
        versoes.length > 1 && (
        <>
          <Separator />
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="artigo">Artigo</TabsTrigger>
              <TabsTrigger value="versoes">Versões ({versoes.length})</TabsTrigger>
            </TabsList>
            <TabsContent value="versoes">
              <ComparadorVersoes versoes={versoes} conteudosMap={Object.fromEntries(versoes.filter(v => v.conteudo_markdown).map(v => [v.versao, v.conteudo_markdown!]))} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}

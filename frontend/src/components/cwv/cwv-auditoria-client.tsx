"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeftIcon, DownloadIcon, FileTextIcon, Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  buscarAuditoriaCwv,
  atualizarItemChecklistCwv,
  atualizarAuditoriaCwv,
  reauditarCwv,
  consolidarAuditoriaCwv,
  buscarConsolidadosCwv,
  gerarRelatorioCwv,
  exportarAuditoriaDocxCwv,
  type AuditoriaResposta,
  type ProblemaConsolidadoResposta,
} from "@/lib/api/cwv";
import { mensagemErroAmigavel } from "@/lib/api";
import { AuditoriaHeader } from "./auditoria/auditoria-header";
import { VisaoGeralTab } from "./auditoria/visao-geral-tab";
import { ChecklistGrid, type AtualizarItemDados } from "./auditoria/checklist-grid";
import { BeforeAfterTab } from "./auditoria/before-after-tab";

export function CwvAuditoriaClient() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const id = pathname.split("/").filter(Boolean).pop() || "";
  const router = useRouter();
  const [auditoria, setAuditoria] = useState<AuditoriaResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [salvandoId, setSalvandoId] = useState<string | null>(null);
  const [reauditando, setReauditando] = useState(false);
  const [consolidando, setConsolidando] = useState(false);
  const [consolidados, setConsolidados] = useState<ProblemaConsolidadoResposta[] | null>(null);
  const [gerandoRelatorio, setGerandoRelatorio] = useState(false);
  const [baixandoDocx, setBaixandoDocx] = useState(false);

  const tab = searchParams.get("tab") ?? "visao-geral";

  function setTab(t: string) {
    const sp = new URLSearchParams(searchParams.toString());
    sp.set("tab", t);
    router.replace(`${pathname}?${sp.toString()}`);
  }

  useEffect(() => {
    if (!id) return;
    buscarAuditoriaCwv(id)
      .then(setAuditoria)
      .catch((e) => setErro(mensagemErroAmigavel(e)));
    buscarConsolidadosCwv(id)
      .then((resp) => {
        if (resp.status === "concluida") setConsolidados(resp.consolidados);
      })
      .catch(() => {});
  }, [id]);

  async function handleConsolidar() {
    if (consolidando) return;
    setConsolidando(true);
    try {
      await consolidarAuditoriaCwv(id);
      toast.success("Consolidação iniciada");
      const poll = setInterval(async () => {
        try {
          const resp = await buscarConsolidadosCwv(id);
          if (resp.status === "concluida") {
            setConsolidados(resp.consolidados);
            clearInterval(poll);
            setConsolidando(false);
          } else if (resp.status === "falhou") {
            clearInterval(poll);
            setConsolidando(false);
            toast.error("Consolidação falhou");
          }
        } catch {
          /* ignora erro transiente */
        }
      }, 3000);
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
      setConsolidando(false);
    }
  }

  async function handleGerarRelatorio() {
    if (gerandoRelatorio) return;
    setGerandoRelatorio(true);
    try {
      await gerarRelatorioCwv(id);
      toast.success("Geração de relatório iniciada");
      const poll = setInterval(async () => {
        const att = await buscarAuditoriaCwv(id);
        const rel = att.relatorio_json;
        if (rel && typeof rel === "object" && "sumario_executivo_md" in rel) {
          setAuditoria(att);
          clearInterval(poll);
          setGerandoRelatorio(false);
          toast.success("Relatório gerado!");
        } else if (rel && typeof rel === "object" && rel.status === "falhou") {
          clearInterval(poll);
          setGerandoRelatorio(false);
          toast.error("Geração do relatório falhou");
        }
      }, 4000);
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
      setGerandoRelatorio(false);
    }
  }

  async function handleBaixarDocx() {
    if (baixandoDocx) return;
    setBaixandoDocx(true);
    try {
      const blob = await exportarAuditoriaDocxCwv(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cwv-auditoria-${id.slice(0, 8)}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setBaixandoDocx(false);
    }
  }

  async function handleReauditar() {
    if (reauditando) return;
    setReauditando(true);
    try {
      const resp = await reauditarCwv(id);
      toast.success(`Re-auditoria iniciada (${resp.custo_estimado} créditos)`);
      router.push(`/ferramentas/core-web-vitals/execucao/${resp.id}`);
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setReauditando(false);
    }
  }

  async function handleAtualizarItem(itemId: string, dados: AtualizarItemDados) {
    const anterior = auditoria;
    // Update otimista.
    setAuditoria((a) =>
      a ? { ...a, checklist: a.checklist.map((i) => (i.id === itemId ? { ...i, ...dados } : i)) } : a,
    );
    setSalvandoId(itemId);
    try {
      await atualizarItemChecklistCwv(id, itemId, dados);
      const atualizada = await buscarAuditoriaCwv(id);
      setAuditoria(atualizada);
    } catch (e) {
      setAuditoria(anterior); // rollback
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setSalvandoId(null);
    }
  }

  if (erro) {
    return (
      <div className="space-y-6">
        <PageHeader title="Auditoria CWV" description="Erro ao carregar" />
        <div className="max-w-2xl mx-auto rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-center">
          <p className="text-sm text-destructive">{erro}</p>
        </div>
      </div>
    );
  }

  if (!auditoria) {
    return (
      <div className="space-y-6">
        <PageHeader title="Auditoria CWV" description="Carregando..." />
        <div className="max-w-2xl mx-auto space-y-4">
          <div className="h-8 rounded-lg bg-muted/50 animate-pulse" />
          <div className="h-24 rounded-xl bg-muted/50 animate-pulse" />
        </div>
      </div>
    );
  }

  const passAfter = auditoria.checklist.filter((i) => i.status_after === "pass").length;
  const failAfter = auditoria.checklist.filter((i) => i.status_after === "fail").length;
  const temAfter = auditoria.health_score_after !== null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={auditoria.titulo}
        description="Auditoria Core Web Vitals"
        action={
          <Link href="/ferramentas/core-web-vitals" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" /> Voltar
          </Link>
        }
      />

      <div className="w-full space-y-4">
        <AuditoriaHeader
          titulo={auditoria.titulo}
          fase={auditoria.fase}
          healthBefore={auditoria.health_score_before}
          healthAfter={auditoria.health_score_after}
          nPassBefore={auditoria.n_pass_before}
          nFailBefore={auditoria.n_fail_before}
          nPassAfter={temAfter ? passAfter : null}
          nFailAfter={temAfter ? failAfter : null}
          criadoEm={auditoria.criado_em}
        />

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="visao-geral">Visão geral</TabsTrigger>
            <TabsTrigger value="checklist">Checklist</TabsTrigger>
            <TabsTrigger value="before-after">Before/After</TabsTrigger>
          </TabsList>
          <TabsContent value="visao-geral">
            <VisaoGeralTab
              auditoria={auditoria}
              consolidados={consolidados}
              onIrParaChecklist={() => setTab("checklist")}
            />
          </TabsContent>
          <TabsContent value="checklist">
            <ChecklistGrid
              checklist={auditoria.checklist}
              salvandoId={salvandoId}
              onAtualizarItem={handleAtualizarItem}
              auditoriaId={id}
            />
          </TabsContent>
          <TabsContent value="before-after">
            <BeforeAfterTab auditoriaId={id} fase={auditoria.fase} onReauditar={handleReauditar} />
          </TabsContent>
        </Tabs>

        {/* Ações globais (fora das abas) */}
        {auditoria.consolidacao_status !== "executando" && !consolidados && (
          <button
            className="w-full rounded-lg border border-blue-400 bg-blue-50 px-4 py-2.5 text-sm font-medium text-blue-700 hover:bg-blue-100 transition-colors"
            onClick={handleConsolidar}
          >
            Consolidar problemas (dedup cross-URL + causa raiz)
          </button>
        )}
        {consolidando && (
          <div className="flex items-center justify-center gap-2 rounded-lg border bg-surface-light px-4 py-3 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" /> Consolidando problemas...
          </div>
        )}
        {consolidados && consolidados.length > 0 && (
          <div className="glass-card rounded-2xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Plano consolidado ({consolidados.length})</h2>
              <button className="text-[11px] text-muted-foreground hover:text-foreground" onClick={handleConsolidar}>
                Re-consolidar
              </button>
            </div>
            <div className="space-y-2">
              {consolidados.map((c) => (
                <div key={c.id} className="rounded-lg border bg-surface-light px-4 py-3 space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium flex-1">{c.titulo}</p>
                    <div className="flex items-center gap-1 shrink-0">
                      <Badge variant="outline" className="text-[9px]">Sev {c.severidade}</Badge>
                      {c.esforco && <Badge variant="outline" className="text-[9px]">{c.esforco}</Badge>}
                    </div>
                  </div>
                  {c.causa_raiz && (
                    <p className="text-xs text-muted-foreground"><strong>Causa raiz:</strong> {c.causa_raiz}</p>
                  )}
                  {c.escopo_json.descricao && (
                    <p className="text-xs text-muted-foreground"><strong>Escopo:</strong> {c.escopo_json.descricao}</p>
                  )}
                  <p className="text-[11px] text-muted-foreground">
                    {(c.escopo_json.urls ?? []).length} URL(s) · {(c.escopo_json.estrategias ?? []).join(", ")}
                  </p>
                  {c.recomendacao_md && (
                    <p className="text-xs text-muted-foreground mt-1">{c.recomendacao_md}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Relatório executivo + export DOCX */}
        {auditoria.consolidacao_status === "concluida" && (
          <div className="glass-card rounded-2xl p-5 space-y-3">
            <h2 className="text-sm font-semibold">Relatório executivo</h2>
            {(() => {
              const rel = auditoria.relatorio_json;
              if (rel && typeof rel === "object" && "sumario_executivo_md" in rel) {
                return (
                  <>
                    <div className="rounded-lg border bg-surface-light px-4 py-3 prose prose-sm max-w-none text-muted-foreground">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {String((rel as Record<string, unknown>).sumario_executivo_md)}
                      </ReactMarkdown>
                    </div>
                    <Button variant="outline" size="sm" onClick={handleBaixarDocx} disabled={baixandoDocx}>
                      {baixandoDocx ? <Loader2Icon className="size-4 mr-1 animate-spin" /> : <DownloadIcon className="size-4 mr-1" />}
                      Baixar DOCX completo
                    </Button>
                  </>
                );
              }
              return (
                <Button size="sm" onClick={handleGerarRelatorio} disabled={gerandoRelatorio}>
                  {gerandoRelatorio ? <Loader2Icon className="size-4 mr-1 animate-spin" /> : <FileTextIcon className="size-4 mr-1" />}
                  {gerandoRelatorio ? "Gerando relatório..." : "Gerar relatório executivo"}
                </Button>
              );
            })()}
          </div>
        )}

        {/* Botão avançar fase / re-auditar */}
        {auditoria.fase === "before" && (
          <button
            className="w-full rounded-lg border border-yellow-400 bg-yellow-50 px-4 py-2.5 text-sm font-medium text-yellow-800 hover:bg-yellow-100 transition-colors"
            onClick={async () => {
              try {
                const att = await atualizarAuditoriaCwv(id, { fase: "aguardando_implementacao" });
                setAuditoria(att);
                toast.success("Fase avançada para 'Aguardando implementação'");
              } catch (e) {
                toast.error(mensagemErroAmigavel(e));
              }
            }}
          >
            Avançar para &ldquo;Aguardando implementação&rdquo;
          </button>
        )}
        {(auditoria.fase === "aguardando_implementacao" ||
          (auditoria.fase === "after" && auditoria.health_score_after == null)) && (
          <button
            className="w-full rounded-lg border border-purple-400 bg-purple-50 px-4 py-2.5 text-sm font-medium text-purple-800 hover:bg-purple-100 transition-colors disabled:opacity-50"
            disabled={reauditando}
            onClick={handleReauditar}
          >
            {reauditando
              ? "Iniciando re-auditoria..."
              : auditoria.fase === "after"
                ? "Re-auditar novamente (a anterior não concluiu)"
                : "Re-auditar (verificar implementações)"}
          </button>
        )}
      </div>
    </div>
  );
}

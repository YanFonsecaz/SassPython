"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { ArrowLeftIcon, Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import {
  buscarAuditoriaCwv,
  atualizarItemChecklistCwv,
  atualizarAuditoriaCwv,
  reauditarCwv,
  type AuditoriaResposta,
  type ChecklistItemResposta,
  type FaseAuditoria,
  type OrigemItem,
  type StatusCheck,
  type StatusImplementacao,
} from "@/lib/api/cwv";
import { mensagemErroAmigavel } from "@/lib/api";

const FASE_LABELS: Record<FaseAuditoria, string> = {
  before: "Before (auditoria inicial)",
  aguardando_implementacao: "Aguardando implementação",
  after: "After (re-auditoria)",
  concluida: "Concluída",
};

const FASE_CORES: Record<FaseAuditoria, string> = {
  before: "border-blue-400 text-blue-700 bg-blue-50",
  aguardando_implementacao: "border-yellow-400 text-yellow-700 bg-yellow-50",
  after: "border-purple-400 text-purple-700 bg-purple-50",
  concluida: "border-success/30 text-success bg-success/10",
};

const ORIGEM_LABELS: Record<OrigemItem, string> = {
  psi_audit: "Page Speed Insights",
  field_data: "Dados de campo (CrUX)",
  page_experience: "Page Experience",
};

function corStatus(s: StatusCheck | null): string {
  if (s === "pass") return "border-success/30 text-success bg-success/10";
  if (s === "fail") return "border-destructive/30 text-destructive bg-destructive/10";
  return "border-border text-muted-foreground bg-muted/40";
}

function rotuloStatus(s: StatusCheck | null): string {
  if (s === "pass") return "Pass";
  if (s === "fail") return "Fail";
  if (s === "na") return "N/A";
  return "—";
}

export function CwvAuditoriaClient() {
  const pathname = usePathname();
  const id = pathname.split("/").filter(Boolean).pop() || "";
  const router = useRouter();
  const [auditoria, setAuditoria] = useState<AuditoriaResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [salvandoId, setSalvandoId] = useState<string | null>(null);
  const [reauditando, setReauditando] = useState(false);

  useEffect(() => {
    if (!id) return;
    buscarAuditoriaCwv(id).then(setAuditoria).catch((e) => {
      setErro(mensagemErroAmigavel(e));
    });
  }, [id]);

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

  async function handleAtualizarItem(itemId: string, dados: { status_implementacao?: StatusImplementacao; nota_cliente?: string }) {
    setSalvandoId(itemId);
    try {
      await atualizarItemChecklistCwv(id, itemId, dados);
      // Recarrega a auditoria para refletir contadores.
      const atualizada = await buscarAuditoriaCwv(id);
      setAuditoria(atualizada);
    } catch (e) {
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

  // Agrupa itens por origem.
  const porOrigem: Record<string, ChecklistItemResposta[]> = {};
  for (const item of auditoria.checklist) {
    (porOrigem[item.origem] ??= []).push(item);
  }

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

      <div className="max-w-3xl mx-auto space-y-4">
        {/* Header da auditoria */}
        <div className="glass-card rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <Badge variant="outline" className={FASE_CORES[auditoria.fase]}>
              {FASE_LABELS[auditoria.fase]}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {new Date(auditoria.criado_em).toLocaleDateString("pt-BR")}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-lg border bg-surface-light p-3">
              <p className="text-xs text-muted-foreground">Health Before</p>
              <p className="text-xl font-bold">{auditoria.health_score_before !== null ? `${auditoria.health_score_before}%` : "—"}</p>
            </div>
            <div className="rounded-lg border bg-surface-light p-3">
              <p className="text-xs text-muted-foreground">Health After</p>
              <p className="text-xl font-bold">
                {auditoria.health_score_after !== null ? `${auditoria.health_score_after}%` : "—"}
                {auditoria.health_score_before !== null && auditoria.health_score_after !== null && (
                  <span className={`ml-1 text-xs ${auditoria.health_score_after > auditoria.health_score_before ? "text-success" : "text-destructive"}`}>
                    {auditoria.health_score_after > auditoria.health_score_before ? "↑" : "↓"}
                    {Math.abs(auditoria.health_score_after - auditoria.health_score_before).toFixed(1)}p.p.
                  </span>
                )}
              </p>
            </div>
            <div className="rounded-lg border bg-surface-light p-3">
              <p className="text-xs text-muted-foreground">Implementados</p>
              <p className="text-xl font-bold">{auditoria.n_implementados}/{auditoria.n_fail_before}</p>
            </div>
          </div>
        </div>

        {/* Checklist agrupado por origem */}
        {(["psi_audit", "field_data", "page_experience"] as OrigemItem[]).map((origem) => {
          const itens = porOrigem[origem];
          if (!itens || itens.length === 0) return null;
          return (
            <div key={origem} className="glass-card rounded-2xl p-5 space-y-3">
              <h2 className="text-sm font-semibold">{ORIGEM_LABELS[origem]}</h2>
              <div className="space-y-2">
                {itens.map((item) => (
                  <ItemChecklist
                    key={item.id}
                    item={item}
                    salvando={salvandoId === item.id}
                    onAtualizar={(dados) => handleAtualizarItem(item.id, dados)}
                  />
                ))}
              </div>
            </div>
          );
        })}

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
            Avançar para "Aguardando implementação"
          </button>
        )}
        {auditoria.fase === "aguardando_implementacao" && (
          <button
            className="w-full rounded-lg border border-purple-400 bg-purple-50 px-4 py-2.5 text-sm font-medium text-purple-800 hover:bg-purple-100 transition-colors disabled:opacity-50"
            disabled={reauditando}
            onClick={handleReauditar}
          >
            {reauditando ? "Iniciando re-auditoria..." : "Re-auditar (verificar implementações)"}
          </button>
        )}
      </div>
    </div>
  );
}

function ItemChecklist({
  item,
  salvando,
  onAtualizar,
}: {
  item: ChecklistItemResposta;
  salvando: boolean;
  onAtualizar: (dados: { status_implementacao?: StatusImplementacao; nota_cliente?: string }) => void;
}) {
  const [notaLocal, setNotaLocal] = useState(item.nota_cliente ?? "");
  const [editandoNota, setEditandoNota] = useState(false);
  const urls = (item.escopo_json.urls as string[] | undefined) ?? [];

  return (
    <div className="rounded-lg border bg-surface-light px-4 py-3 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate" title={item.titulo}>{item.titulo}</p>
          {urls.length > 0 && (
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {urls.length} URL(s): {urls.slice(0, 2).join(", ")}{urls.length > 2 ? ` +${urls.length - 2}` : ""}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-medium ${corStatus(item.status_before)}`}>
            {rotuloStatus(item.status_before)}
          </span>
          {item.status_after && (
            <>
              <span className="text-muted-foreground text-[10px]">→</span>
              <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-medium ${corStatus(item.status_after)}`}>
                {rotuloStatus(item.status_after)}
              </span>
            </>
          )}
          {item.esforco && (
            <Badge variant="outline" className="text-[9px]">{item.esforco}</Badge>
          )}
        </div>
      </div>

      {/* Status de implementação */}
      <div className="flex items-center gap-2">
        {salvando && <Loader2Icon className="size-3 animate-spin text-muted-foreground" />}
        <select
          className="text-xs rounded border bg-card px-2 py-1"
          value={item.status_implementacao}
          onChange={(e) => onAtualizar({ status_implementacao: e.target.value as StatusImplementacao })}
        >
          <option value="nao_executado">Não executado</option>
          <option value="em_andamento">Em andamento</option>
          <option value="implementado">Implementado</option>
        </select>
      </div>

      {/* Nota do cliente */}
      {editandoNota ? (
        <div className="space-y-1">
          <textarea
            className="w-full text-xs rounded border bg-card px-2 py-1 resize-none"
            rows={2}
            value={notaLocal}
            onChange={(e) => setNotaLocal(e.target.value)}
            placeholder="Nota do cliente..."
          />
          <div className="flex gap-1">
            <button
              className="text-[11px] rounded bg-brand px-2 py-0.5 text-white"
              onClick={() => { onAtualizar({ nota_cliente: notaLocal }); setEditandoNota(false); }}
            >
              Salvar
            </button>
            <button className="text-[11px] text-muted-foreground" onClick={() => setEditandoNota(false)}>
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <button
          className="text-[11px] text-muted-foreground hover:text-foreground"
          onClick={() => { setNotaLocal(item.nota_cliente ?? ""); setEditandoNota(true); }}
        >
          {item.nota_cliente ? `📝 ${item.nota_cliente.slice(0, 60)}${item.nota_cliente.length > 60 ? "…" : ""}` : "+ Adicionar nota"}
        </button>
      )}
    </div>
  );
}

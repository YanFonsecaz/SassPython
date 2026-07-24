"use client";

// Tabela estilo Excel do checklist (SPEC_CWV_Auditoria_UI_V2 §3.2).
// Pass/Fail somente leitura; edita implementação, notas (cliente+SEO) e prioridade.

import { useEffect, useMemo, useState } from "react";
import { Loader2Icon, ChevronDownIcon, ChevronRightIcon, SparklesIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  buscarArtefatoAgentico,
  buscarDetalheItemChecklist,
  gerarArtefatoAgentico,
  type ArtefatoAgenticoResposta,
  type ChecklistItemResposta,
  type ItemDetalheResposta,
  type OrigemItem,
  type StatusCheck,
  type StatusImplementacao,
  type TipoArtefatoAgentico,
} from "@/lib/api/cwv";

const ORIGEM_LABELS: Record<OrigemItem, string> = {
  psi_audit: "Page Speed Insights",
  field_data: "Dados de campo (CrUX)",
  page_experience: "Page Experience",
  // SPEC_CWV_Navegacao_Agentica: llms.txt, acessibilidade, WebMCP.
  agentic: "Navegação agêntica",
};

type Filtro = "todos" | "reprovados" | "aprovados" | "implementados";
type FiltroMetrica = "todas" | "LCP" | "INP/TBT" | "CLS";

// Grupos de métrica da planilha NPBR (abas LCPFCP / TBTINP / CLS CWV).
const METRICA_GRUPOS: Record<Exclude<FiltroMetrica, "todas">, string[]> = {
  LCP: ["LCP", "FCP"],
  "INP/TBT": ["INP", "TBT"],
  CLS: ["CLS"],
};

export interface AtualizarItemDados {
  status_implementacao?: StatusImplementacao;
  nota_cliente?: string;
  nota_seo?: string;
  prioridade?: number;
  status_before?: StatusCheck;
  status_after?: StatusCheck;
}

function ehManual(item: ChecklistItemResposta): boolean {
  return item.item_codigo.startsWith("manual_");
}

// SPEC_CWV_Navegacao_Agentica_Geracao_IA: qual artefato o item pode gerar.
function tipoArtefatoDoItem(codigo: string): TipoArtefatoAgentico | null {
  if (codigo === "agentic_llms_txt") return "llms_txt";
  if (codigo.startsWith("manual_webmcp_")) return "webmcp";
  return null;
}

function baixarTexto(nome: string, conteudo: string) {
  const blob = new Blob([conteudo], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Bloco "Gerar com IA" na ficha dos itens agênticos (llms.txt / WebMCP).
function GerarArtefatoIA({ auditoriaId, tipo }: { auditoriaId: string; tipo: TipoArtefatoAgentico }) {
  const [artefato, setArtefato] = useState<ArtefatoAgenticoResposta | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [gerando, setGerando] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCarregando(true);
    buscarArtefatoAgentico(auditoriaId, tipo)
      .then(setArtefato)
      .catch(() => {}) // 404 = nunca gerado
      .finally(() => setCarregando(false));
  }, [auditoriaId, tipo]);

  async function gerar() {
    setGerando(true);
    try {
      setArtefato(await gerarArtefatoAgentico(auditoriaId, tipo));
    } catch {
      // silencioso: botão persiste para retry
    } finally {
      setGerando(false);
    }
  }

  const erro = artefato?.meta_json?.erro === true;
  const ferramentas = (artefato?.meta_json?.ferramentas_sugeridas as string[] | undefined) ?? [];
  const comoAplicar = artefato?.meta_json?.como_aplicar_md as string | undefined;
  const pronto = artefato && !erro;

  return (
    <section className="rounded-lg border border-brand/30 bg-brand/5 p-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-brand-dark">
          Gerar com IA
        </h4>
        <Button size="sm" onClick={gerar} disabled={gerando || carregando}>
          {gerando ? <Loader2Icon className="mr-1 size-4 animate-spin" /> : <SparklesIcon className="mr-1 size-4" />}
          {pronto ? "Regenerar" : "Gerar com IA"}
        </Button>
      </div>
      {tipo === "webmcp" && (
        <p className="text-[11px] text-muted-foreground">
          Detecção por HTML estático (não prova ausência). O código é um scaffold para revisão — revise antes de publicar.
        </p>
      )}
      {carregando && !artefato && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2Icon className="size-3 animate-spin" /> Buscando artefato…
        </p>
      )}
      {erro && <p className="text-xs text-destructive">Não foi possível gerar agora. Tente novamente.</p>}
      {pronto && (
        <div className="space-y-2">
          {tipo === "llms_txt" && artefato.diagnostico && (
            <Badge variant="outline" className="text-[9px] uppercase">{artefato.diagnostico}</Badge>
          )}
          {ferramentas.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {ferramentas.map((f) => (
                <Badge key={f} variant="outline" className="text-[9px]">{f}</Badge>
              ))}
            </div>
          )}
          <pre className="max-h-72 overflow-auto rounded bg-card p-2 text-[11px] leading-relaxed">
            <code>{artefato.conteudo_md}</code>
          </pre>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => navigator.clipboard?.writeText(artefato.conteudo_md)}>
              Copiar
            </Button>
            {tipo === "llms_txt" && (
              <Button size="sm" variant="outline" onClick={() => baixarTexto("llms.txt", artefato.conteudo_md)}>
                Baixar llms.txt
              </Button>
            )}
          </div>
          {artefato.explicacao_md && (
            <div>
              <h5 className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Explicação</h5>
              <p className="whitespace-pre-line text-xs text-muted-foreground">{artefato.explicacao_md}</p>
            </div>
          )}
          {comoAplicar && (
            <div>
              <h5 className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Como aplicar</h5>
              <p className="whitespace-pre-line text-xs text-muted-foreground">{comoAplicar}</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

interface Props {
  checklist: ChecklistItemResposta[];
  salvandoId: string | null;
  onAtualizarItem: (itemId: string, dados: AtualizarItemDados) => void;
  auditoriaId?: string;
}

function badgeStatus(s: StatusCheck | null) {
  if (s === "pass")
    return (
      <span className="inline-flex rounded-md border border-success/30 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">
        ✔ Pass
      </span>
    );
  if (s === "fail")
    return (
      <span className="inline-flex rounded-md border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">
        ✖ Fail
      </span>
    );
  if (s === "na")
    return (
      <span className="inline-flex rounded-md border bg-muted/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
        n/a
      </span>
    );
  return <span className="text-[10px] text-muted-foreground">—</span>;
}

function tintaLinha(s: StatusCheck | null): string {
  if (s === "pass") return "bg-success/5";
  if (s === "fail") return "bg-destructive/5";
  return "";
}

// Status editável — só para itens manuais de Page Experience (SPEC_CWV_Checklist_Itens_Manuais).
function StatusManualSelect({
  value,
  ariaLabel,
  onChange,
}: {
  value: StatusCheck | null;
  ariaLabel: string;
  onChange: (v: StatusCheck) => void;
}) {
  return (
    <select
      className="rounded border bg-card px-1.5 py-1 text-[11px]"
      aria-label={ariaLabel}
      value={value ?? "na"}
      onChange={(e) => onChange(e.target.value as StatusCheck)}
    >
      <option value="na">n/a</option>
      <option value="pass">Pass</option>
      <option value="fail">Fail</option>
    </select>
  );
}

export function ChecklistGrid({ checklist, salvandoId, onAtualizarItem, auditoriaId }: Props) {
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [filtroMetrica, setFiltroMetrica] = useState<FiltroMetrica>("todas");
  const [busca, setBusca] = useState("");
  const [colapsados, setColapsados] = useState<Record<string, boolean>>({});
  const [notasAbertas, setNotasAbertas] = useState<string | null>(null);
  const [sort, setSort] = useState<{ campo: "titulo" | "prioridade"; asc: boolean }>({
    campo: "prioridade",
    asc: true,
  });

  function toggleSort(campo: "titulo" | "prioridade") {
    setSort((s) => (s.campo === campo ? { campo, asc: !s.asc } : { campo, asc: true }));
  }

  const visiveis = useMemo(() => {
    return checklist.filter((i) => {
      if (filtro === "reprovados" && i.status_before !== "fail") return false;
      if (filtro === "aprovados" && i.status_before !== "pass") return false;
      if (filtro === "implementados" && i.status_implementacao !== "implementado") return false;
      if (filtroMetrica !== "todas") {
        const alvo = METRICA_GRUPOS[filtroMetrica];
        if (!(i.metricas_afetadas ?? []).some((m) => alvo.includes(m))) return false;
      }
      if (busca && !i.titulo.toLowerCase().includes(busca.toLowerCase())) return false;
      return true;
    });
  }, [checklist, filtro, filtroMetrica, busca]);

  const grupos = useMemo(() => {
    const g: Partial<Record<OrigemItem, ChecklistItemResposta[]>> = {};
    for (const i of visiveis) (g[i.origem] ??= []).push(i);
    for (const lista of Object.values(g)) {
      lista!.sort((a, b) => {
        const cmp =
          sort.campo === "titulo"
            ? a.titulo.localeCompare(b.titulo)
            : (a.prioridade || 999) - (b.prioridade || 999);
        return sort.asc ? cmp : -cmp;
      });
    }
    return g;
  }, [visiveis, sort]);

  const filtros: { id: Filtro; rotulo: string }[] = [
    { id: "todos", rotulo: "Todos" },
    { id: "reprovados", rotulo: "Reprovados" },
    { id: "aprovados", rotulo: "Aprovados" },
    { id: "implementados", rotulo: "Implementados" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {filtros.map((f) => (
          <button
            key={f.id}
            className={`rounded-full border px-3 py-1 text-xs ${filtro === f.id ? "border-brand bg-brand/10 font-medium text-brand" : "text-muted-foreground hover:text-foreground"}`}
            onClick={() => setFiltro(f.id)}
          >
            {f.rotulo}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-border" aria-hidden />
        {(["todas", "LCP", "INP/TBT", "CLS"] as FiltroMetrica[]).map((m) => (
          <button
            key={m}
            className={`rounded-full border px-3 py-1 text-xs ${filtroMetrica === m ? "border-brand bg-brand/10 font-medium text-brand" : "text-muted-foreground hover:text-foreground"}`}
            onClick={() => setFiltroMetrica(m)}
          >
            {m === "todas" ? "Todas métricas" : m}
          </button>
        ))}
        <input
          className="ml-auto w-48 rounded border bg-card px-2 py-1 text-xs"
          placeholder="Buscar item..."
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
      </div>

      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b text-left text-[11px] uppercase text-muted-foreground">
              <th className="px-3 py-2">
                <button onClick={() => toggleSort("titulo")} className="hover:text-foreground">
                  Item {sort.campo === "titulo" ? (sort.asc ? "↑" : "↓") : ""}
                </button>
              </th>
              <th className="px-2 py-2">Before</th>
              <th className="px-2 py-2">After</th>
              <th className="px-2 py-2">Métrica</th>
              <th className="px-2 py-2">Implementação</th>
              <th className="px-2 py-2">Escopo</th>
              <th className="px-2 py-2">
                <button onClick={() => toggleSort("prioridade")} className="hover:text-foreground">
                  Prio {sort.campo === "prioridade" ? (sort.asc ? "↑" : "↓") : ""}
                </button>
              </th>
              <th className="px-2 py-2">Esforço</th>
              <th className="px-2 py-2">Notas</th>
            </tr>
          </thead>
          <tbody>
            {(Object.keys(ORIGEM_LABELS) as OrigemItem[]).map((origem) => {
              const itens = grupos[origem];
              if (!itens || itens.length === 0) return null;
              const nPass = itens.filter((i) => i.status_before === "pass").length;
              const nFail = itens.filter((i) => i.status_before === "fail").length;
              const colapsado = colapsados[origem];
              return (
                <FragmentRows
                  key={origem}
                  origem={origem}
                  itens={itens}
                  nPass={nPass}
                  nFail={nFail}
                  colapsado={!!colapsado}
                  onToggleColapso={() => setColapsados((c) => ({ ...c, [origem]: !c[origem] }))}
                  notasAbertas={notasAbertas}
                  onToggleNotas={(id) => setNotasAbertas(notasAbertas === id ? null : id)}
                  salvandoId={salvandoId}
                  onAtualizar={onAtualizarItem}
                  auditoriaId={auditoriaId}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FragmentRows({
  origem,
  itens,
  nPass,
  nFail,
  colapsado,
  onToggleColapso,
  notasAbertas,
  onToggleNotas,
  salvandoId,
  onAtualizar,
  auditoriaId,
}: {
  origem: OrigemItem;
  itens: ChecklistItemResposta[];
  nPass: number;
  nFail: number;
  colapsado: boolean;
  onToggleColapso: () => void;
  notasAbertas: string | null;
  onToggleNotas: (id: string) => void;
  salvandoId: string | null;
  onAtualizar: (itemId: string, dados: AtualizarItemDados) => void;
  auditoriaId?: string;
}) {
  return (
    <>
      <tr className="cursor-pointer border-b bg-muted/30" onClick={onToggleColapso}>
        <td colSpan={9} className="px-3 py-1.5 text-xs font-semibold">
          <span className="inline-flex items-center gap-1">
            {colapsado ? <ChevronRightIcon className="size-3" /> : <ChevronDownIcon className="size-3" />}
            {ORIGEM_LABELS[origem]} ({itens.length})
            <span className="ml-2 font-normal text-muted-foreground">
              <span className="text-success">✔ {nPass}</span> · <span className="text-destructive">✖ {nFail}</span>
            </span>
          </span>
        </td>
      </tr>
      {!colapsado &&
        itens.map((item) => (
          <LinhaItem
            key={item.id}
            item={item}
            salvando={salvandoId === item.id}
            notasAbertas={notasAbertas === item.id}
            onToggleNotas={() => onToggleNotas(item.id)}
            onAtualizar={(dados) => onAtualizar(item.id, dados)}
            auditoriaId={auditoriaId}
          />
        ))}
    </>
  );
}

function LinhaItem({
  item,
  salvando,
  notasAbertas,
  onToggleNotas,
  onAtualizar,
  auditoriaId,
}: {
  item: ChecklistItemResposta;
  salvando: boolean;
  notasAbertas: boolean;
  onToggleNotas: () => void;
  onAtualizar: (dados: AtualizarItemDados) => void;
  auditoriaId?: string;
}) {
  const [prioLocal, setPrioLocal] = useState(String(item.prioridade ?? 0));
  const [notaCliente, setNotaCliente] = useState(item.nota_cliente ?? "");
  const [notaSeo, setNotaSeo] = useState(item.nota_seo ?? "");
  const [detalhe, setDetalhe] = useState<ItemDetalheResposta | null>(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);
  const nNotas = (item.nota_cliente ? 1 : 0) + (item.nota_seo ? 1 : 0);

  // Carrega a ficha do problema (KB) sob demanda, só na primeira abertura.
  useEffect(() => {
    if (!notasAbertas || detalhe || carregandoDetalhe || !auditoriaId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCarregandoDetalhe(true);
    buscarDetalheItemChecklist(auditoriaId, item.id)
      .then(setDetalhe)
      .catch(() => {})
      .finally(() => setCarregandoDetalhe(false));
  }, [notasAbertas, detalhe, carregandoDetalhe, auditoriaId, item.id]);

  return (
    <>
      <tr className={`border-b ${tintaLinha(item.status_before)}`}>
        <td className="max-w-[280px] truncate px-3 py-2" title={item.titulo}>
          {salvando && <Loader2Icon className="mr-1 inline size-3 animate-spin text-muted-foreground" />}
          {item.titulo}
        </td>
        <td className="px-2 py-2">
          {ehManual(item) ? (
            <StatusManualSelect
              value={item.status_before}
              ariaLabel={`status before de ${item.titulo}`}
              onChange={(v) => onAtualizar({ status_before: v })}
            />
          ) : (
            badgeStatus(item.status_before)
          )}
        </td>
        <td className="px-2 py-2">
          {ehManual(item) ? (
            <StatusManualSelect
              value={item.status_after}
              ariaLabel={`status after de ${item.titulo}`}
              onChange={(v) => onAtualizar({ status_after: v })}
            />
          ) : (
            badgeStatus(item.status_after)
          )}
        </td>
        <td className="px-2 py-2">
          {(item.metricas_afetadas ?? []).length > 0 ? (
            <span className="flex flex-wrap gap-1">
              {(item.metricas_afetadas ?? []).map((m) => (
                <Badge key={m} variant="outline" className="text-[9px]">{m}</Badge>
              ))}
            </span>
          ) : (
            <span className="text-[10px] text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-2 py-2">
          <select
            className="rounded border bg-card px-2 py-1 text-xs"
            value={item.status_implementacao}
            onChange={(e) => onAtualizar({ status_implementacao: e.target.value as StatusImplementacao })}
          >
            <option value="nao_executado">Não executado</option>
            <option value="em_andamento">Em andamento</option>
            <option value="implementado">Implementado</option>
          </select>
        </td>
        <td className="px-2 py-2 text-[11px] text-muted-foreground">
          {(() => {
            const urls = (item.escopo_json?.urls as string[] | undefined) ?? [];
            return urls.length > 0 ? `${urls.length} URL(s)` : "—";
          })()}
        </td>
        <td className="px-2 py-2">
          <input
            type="number"
            min={0}
            aria-label={`prioridade de ${item.titulo}`}
            className="w-14 rounded border bg-card px-1.5 py-1 text-xs"
            value={prioLocal}
            onChange={(e) => setPrioLocal(e.target.value)}
            onBlur={() => {
              const n = Math.max(0, parseInt(prioLocal, 10) || 0);
              if (n !== item.prioridade) onAtualizar({ prioridade: n });
            }}
          />
        </td>
        <td className="px-2 py-2">
          {item.esforco && <Badge variant="outline" className="text-[9px]">{item.esforco}</Badge>}
        </td>
        <td className="px-2 py-2">
          <button
            className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] ${notasAbertas ? "border-brand bg-brand/10 text-brand" : "text-muted-foreground hover:text-foreground"}`}
            onClick={onToggleNotas}
            aria-expanded={notasAbertas}
            aria-label={`detalhe de ${item.titulo}`}
          >
            {notasAbertas ? "Fechar" : "Detalhe"}
            {nNotas > 0 ? ` · 📝${nNotas}` : ""}
          </button>
        </td>
      </tr>
      {notasAbertas && (
        <tr className="border-b bg-muted/30">
          <td colSpan={9} className="px-4 py-4 sm:px-6">
            {carregandoDetalhe && !detalhe && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2Icon className="size-4 animate-spin" /> Carregando explicação…
              </p>
            )}

            {auditoriaId && tipoArtefatoDoItem(item.item_codigo) && (
              <div className="mb-4">
                <GerarArtefatoIA auditoriaId={auditoriaId} tipo={tipoArtefatoDoItem(item.item_codigo)!} />
              </div>
            )}

            {detalhe && (
              <div className="grid gap-5 lg:grid-cols-3">
                {/* Coluna principal: o que é + como corrigir + elementos */}
                <div className="space-y-4 lg:col-span-2">
                  {detalhe.tem_kb ? (
                    <>
                      {detalhe.descricao && (
                        <section>
                          <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                            O que é
                          </h4>
                          <p className="text-sm leading-relaxed">{detalhe.descricao}</p>
                        </section>
                      )}
                      {(detalhe.solucao_plataforma || detalhe.solucao_geral) && (
                        <section className="rounded-lg border border-brand/20 bg-brand/5 p-3">
                          <h4 className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-brand">
                            Como corrigir
                            {detalhe.solucao_plataforma && (
                              <Badge variant="outline" className="text-[9px] uppercase">{detalhe.plataforma}</Badge>
                            )}
                          </h4>
                          <p className="whitespace-pre-line text-sm leading-relaxed">
                            {detalhe.solucao_plataforma ?? detalhe.solucao_geral}
                          </p>
                          {detalhe.solucao_plataforma && detalhe.solucao_geral && (
                            <details className="mt-2">
                              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                                Ver solução geral
                              </summary>
                              <p className="mt-1 whitespace-pre-line text-xs text-muted-foreground">{detalhe.solucao_geral}</p>
                            </details>
                          )}
                        </section>
                      )}
                    </>
                  ) : detalhe.descricao ? (
                    // Itens sem KB mas com descrição fixa (manuais/agênticos).
                    <section>
                      <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        O que verificar
                      </h4>
                      <p className="text-sm leading-relaxed">{detalhe.descricao}</p>
                    </section>
                  ) : (
                    <p className="rounded-lg border bg-card p-3 text-sm text-muted-foreground">
                      Sem explicação detalhada na base para este item (<code className="text-xs">{detalhe.item_codigo}</code>).
                      Use as métricas e o título como referência.
                    </p>
                  )}

                  {detalhe.evidencias.length > 0 && (
                    <section>
                      <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Elementos com falha
                      </h4>
                      <div className="space-y-3">
                        {detalhe.evidencias.map((ev) => {
                          const restantes = ev.total - ev.elementos.length;
                          return (
                            <div key={`${ev.url_canonica}-${ev.estrategia}`} className="overflow-hidden rounded-lg border bg-card">
                              <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-3 py-1.5">
                                <span className="truncate text-xs font-medium" title={ev.url_canonica}>{ev.url_canonica}</span>
                                <span className="flex shrink-0 items-center gap-2">
                                  <Badge variant="outline" className="text-[9px] uppercase">{ev.estrategia}</Badge>
                                  <span className="text-[10px] text-muted-foreground">
                                    {ev.total} elemento{ev.total !== 1 ? "s" : ""}
                                  </span>
                                </span>
                              </div>
                              <ul className="max-h-72 divide-y divide-border/40 overflow-y-auto">
                                {ev.elementos.map((el, idx) => (
                                  <li key={idx} className="px-3 py-1">
                                    <code className="block truncate text-[11px]" title={el}>{el}</code>
                                  </li>
                                ))}
                              </ul>
                              {restantes > 0 && (
                                <p className="border-t px-3 py-1 text-[10px] text-muted-foreground">
                                  + {restantes} elemento{restantes !== 1 ? "s" : ""} não exibido{restantes !== 1 ? "s" : ""}
                                </p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  )}
                </div>

                {/* Sidebar: métricas, sev, URLs, referências, anotações */}
                <div className="space-y-4">
                  {detalhe.tem_kb && (detalhe.severidade != null || detalhe.metricas_afetadas.length > 0) && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {detalhe.severidade != null && (
                        <Badge variant="outline" className="text-[9px]">Sev {detalhe.severidade}</Badge>
                      )}
                      {detalhe.metricas_afetadas.map((m) => (
                        <Badge key={m} variant="outline" className="text-[9px]">{m}</Badge>
                      ))}
                    </div>
                  )}
                  {detalhe.urls_escopo.length > 0 && (
                    <section>
                      <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">URLs afetadas</h4>
                      <ul className="space-y-0.5 text-xs text-muted-foreground">
                        {detalhe.urls_escopo.map((u) => <li key={u} className="truncate" title={u}>{u}</li>)}
                      </ul>
                    </section>
                  )}
                  {detalhe.links_referencia.length > 0 && (
                    <section>
                      <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Referências</h4>
                      <div className="flex flex-col gap-1 text-xs">
                        {detalhe.links_referencia.map((l) => (
                          <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                            {l.titulo} ↗
                          </a>
                        ))}
                      </div>
                    </section>
                  )}

                  <section className="space-y-2">
                    <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Anotações</h4>
                    <label className="block space-y-1 text-[11px] text-muted-foreground">
                      Nota do cliente
                      <textarea
                        className="w-full resize-none rounded border bg-card px-2 py-1 text-xs"
                        rows={2}
                        value={notaCliente}
                        onChange={(e) => setNotaCliente(e.target.value)}
                      />
                    </label>
                    <label className="block space-y-1 text-[11px] text-muted-foreground">
                      Nota SEO
                      <textarea
                        className="w-full resize-none rounded border bg-card px-2 py-1 text-xs"
                        rows={2}
                        value={notaSeo}
                        onChange={(e) => setNotaSeo(e.target.value)}
                      />
                    </label>
                    <button
                      className="rounded bg-brand px-3 py-1 text-[11px] font-medium text-white hover:bg-brand/90"
                      onClick={() => {
                        onAtualizar({ nota_cliente: notaCliente, nota_seo: notaSeo });
                        onToggleNotas();
                      }}
                    >
                      Salvar notas
                    </button>
                  </section>
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

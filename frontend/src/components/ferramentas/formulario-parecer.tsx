"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { useClientes } from "@/hooks/use-clientes";
import { useCreditos } from "@/hooks/use-creditos";
import { useParecer } from "@/hooks/use-parecer";
import { ComoUsar } from "@/components/ferramentas/como-usar";
import { mensagemErroAmigavel } from "@/lib/api";
import { custoParecer, type BlocoEntrada } from "@/lib/api/parecer";
import { cn } from "@/lib/utils";
import {
  ArrowLeftIcon,
  DownloadIcon,
  FileTextIcon,
  Loader2Icon,
  PlusIcon,
  SparklesIcon,
  Trash2Icon,
  ClockIcon,
} from "lucide-react";

const EditorParecer = dynamic(
  () =>
    import("@/components/ferramentas/editor-parecer").then((m) => m.EditorParecer),
  { ssr: false, loading: () => <div className="h-[420px] rounded-lg border border-border bg-muted/30 animate-pulse" /> }
);

const ETAPA_LABELS: Record<string, string> = {
  analisando_imagens: "Analisando evidências...",
  redigindo_parecer: "Redigindo o parecer...",
  processando: "Processando...",
};

export function FormularioParecer() {
  const router = useRouter();
  const { clientes, carregando: carregandoClientes } = useClientes();
  const { saldo } = useCreditos();
  const { estado, html, setHtml, etapaAtual, gerar, baixar, reset } = useParecer();

  const [clienteId, setClienteId] = useState("");
  const [tituloSugerido, setTituloSugerido] = useState("");
  const [editorHtml, setEditorHtml] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [custo, setCusto] = useState<number | null>(null);

  const editorRef = useRef<HTMLDivElement>(null);

  const blocosFromHtml = useCallback((): BlocoEntrada[] => {
    if (!editorHtml || editorHtml === "<p></p>") return [];
    const parser = new DOMParser();
    const doc = parser.parseFromString(editorHtml, "text/html");
    const blocos: BlocoEntrada[] = [];
    let textoAtual = "";
    let imagensAtuais: string[] = [];

    function flush() {
      const txt = textoAtual.trim();
      if (txt || imagensAtuais.length > 0) {
        blocos.push({ texto: txt, imagens: [...imagensAtuais] });
      }
      textoAtual = "";
      imagensAtuais = [];
    }

    const walk = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        textoAtual += (node.textContent || "").trim() ? (node.textContent || "") : " ";
        return;
      }
      if (node.nodeType === Node.ELEMENT_NODE) {
        const el = node as HTMLElement;
        if (el.tagName === "IMG") {
          const src = el.getAttribute("src") || "";
          if (src) imagensAtuais.push(src);
          return;
        }
        if (el.tagName === "HR") return;
        if (el.tagName === "BR") {
          textoAtual += "\n";
          return;
        }
        for (const child of Array.from(node.childNodes)) {
          walk(child);
        }
        if (["P", "DIV", "H1", "H2", "H3", "H4", "H5", "H6", "LI", "BLOCKQUOTE"].includes(el.tagName)) {
          textoAtual += "\n";
        }
      }
    };

    for (const child of Array.from(doc.body.childNodes)) {
      walk(child);
    }
    flush();
    return blocos.filter((b) => b.texto || b.imagens.length > 0);
  }, [editorHtml]);

  useEffect(() => {
    async function loadCusto() {
      const blocos = blocosFromHtml();
      const nImagens = blocos.reduce((acc, b) => acc + b.imagens.length, 0);
      if (!clienteId || blocos.length === 0) {
        setCusto(null);
        return;
      }
      try {
        const r = await custoParecer({
          cliente_id: clienteId,
          titulo_sugerido: tituloSugerido.trim() || undefined,
          blocos,
        });
        setCusto(r.custo);
      } catch {
        setCusto(null);
      }
    }
    const timer = setTimeout(loadCusto, 500);
    return () => clearTimeout(timer);
  }, [clienteId, tituloSugerido, editorHtml, blocosFromHtml]);

  const totalImagens = useMemo(() => {
    return blocosFromHtml().reduce((acc, b) => acc + b.imagens.length, 0);
  }, [blocosFromHtml]);

  const podeGerar = clienteId && editorHtml && editorHtml !== "<p></p>" && !enviando;
  const saldoSuficiente = !custo || (saldo?.saldo_total ?? 0) >= custo;

  async function handleGerar() {
    setErro("");
    setEnviando(true);
    try {
      const blocos = blocosFromHtml();
      await gerar({
        cliente_id: clienteId,
        titulo_sugerido: tituloSugerido.trim() || undefined,
        blocos,
      });
    } catch (err) {
      const e = err as { status?: number; detalhe?: string };
      if (e.status === 402) {
        setErro(`Saldo insuficiente. Necessário ${custo ?? "—"} créditos.`);
      } else if (e.status === 413) {
        setErro("Payload excede o limite. Reduza o número ou tamanho das imagens.");
      } else {
        setErro(e.detalhe || mensagemErroAmigavel(err));
      }
    } finally {
      setEnviando(false);
    }
  }

  async function handleBaixar() {
    await baixar(tituloSugerido.trim() || undefined);
  }

  const isGerando = estado === "gerando";
  const isPronto = estado === "pronto";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Parecer Técnico"
        description="Gere documentos de correção SEO a partir de prints e descrições"
        action={
          <div className="flex items-center gap-2">
            <ComoUsar ferramenta="parecer" />
            <Link
              href="/ferramentas/parecer/historico"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              <ClockIcon className="size-4 mr-1" />
              Meus Pareceres
            </Link>
            <Link
              href="/ferramentas"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              <ArrowLeftIcon className="size-4 mr-1" />
              Voltar
            </Link>
          </div>
        }
      />

      <div className="max-w-4xl animate-slide-up">
        {erro && (
          <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 mb-6">
            <p className="text-sm text-destructive" role="alert">{erro}</p>
          </div>
        )}

        <div className="glass-card rounded-2xl p-6 sm:p-8">
          {!isPronto ? (
            <>
              <div className="space-y-5 mb-6">
                <div className="space-y-2">
                  <Label>Cliente</Label>
                  {carregandoClientes ? (
                    <div className="h-10 rounded-lg bg-muted/50 animate-pulse" />
                  ) : clientes.length === 0 ? (
                    <div className="rounded-lg border bg-surface-light p-4 text-center">
                      <p className="text-sm text-muted-foreground">Nenhum cliente cadastrado.</p>
                      <Link href="/clientes" className="text-sm text-brand-dark font-medium hover:underline mt-1 inline-block">
                        Cadastrar cliente
                      </Link>
                    </div>
                  ) : (
                    <div className="grid gap-2 max-h-40 overflow-y-auto">
                      {clientes.map((c) => (
                        <button key={c.id} type="button" onClick={() => setClienteId(c.id)}
                          className={cn("flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                            clienteId === c.id ? "border-brand bg-brand/5" : "hover:bg-surface-light"
                          )}>
                          <div className={cn("size-2 rounded-full shrink-0",
                            clienteId === c.id ? "bg-brand" : "bg-muted-foreground/30"
                          )} />
                          <span className="text-sm font-medium truncate">{c.nome}</span>
                          {c.site_url && <span className="text-xs text-muted-foreground truncate ml-auto">{c.site_url}</span>}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="titulo-sugerido">Título sugerido (opcional)</Label>
                  <Input
                    id="titulo-sugerido"
                    value={tituloSugerido}
                    onChange={(e) => setTituloSugerido(e.target.value)}
                    placeholder="Ex: Análise SEO - Loja Exemplo"
                    disabled={isGerando}
                  />
                </div>
              </div>

              <div className="space-y-3 mb-6">
                <div className="flex items-center justify-between">
                  <Label>Conteúdo</Label>
                  {totalImagens > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {totalImagens} imagem{totalImagens > 1 ? "s" : ""}
                    </span>
                  )}
                </div>
                <div ref={editorRef}>
                  <EditorParecer
                    content={editorHtml}
                    editable={!isGerando}
                    onChange={setEditorHtml}
                    placeholder="Cole prints (Ctrl/Cmd+V) e descreva o problema SEO..."
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  Cole imagens diretamente no editor ou arraste e solte.
                </p>
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-border">
                <div className="flex items-center gap-3">
                  {custo !== null && (
                    <span className={cn("text-sm font-medium tabular-nums",
                      saldoSuficiente ? "text-brand-dark" : "text-destructive"
                    )}>
                      Custo: {custo} créditos
                    </span>
                  )}
                </div>
                <Button
                  disabled={!podeGerar || !saldoSuficiente || isGerando}
                  onClick={handleGerar}
                >
                  {isGerando ? (
                    <>
                      <Loader2Icon className="size-4 animate-spin" />
                      {ETAPA_LABELS[etapaAtual ?? ""] || etapaAtual || "Analisando..."}
                    </>
                  ) : (
                    <>
                      <SparklesIcon className="size-4" />
                      Gerar Parecer
                    </>
                  )}
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <FileTextIcon className="size-5 text-brand-dark" />
                  <span className="text-sm font-medium text-foreground">
                    Parecer gerado com sucesso
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={reset}>
                    <PlusIcon className="size-4" />
                    Novo Parecer
                  </Button>
                  <Button size="sm" onClick={handleBaixar}>
                    <DownloadIcon className="size-4" />
                    Baixar .docx
                  </Button>
                </div>
              </div>
              <div className="relative">
                <EditorParecer
                  content={html}
                  editable
                  onChange={setHtml}
                />
              </div>
              <div className="flex items-center justify-end pt-4 mt-4 border-t border-border">
                <p className="text-xs text-muted-foreground mr-3">
                  Edite o parecer acima e baixe a versão atualizada.
                </p>
                <Button size="sm" onClick={handleBaixar}>
                  <DownloadIcon className="size-4" />
                  Baixar .docx
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

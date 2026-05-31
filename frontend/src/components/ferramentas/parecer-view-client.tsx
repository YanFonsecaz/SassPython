"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { buscarParecerDoc, exportarParecer, type ParecerDoc } from "@/lib/api/parecer";
import { mensagemErroAmigavel } from "@/lib/api";
import { Loader2Icon, DownloadIcon, ArrowLeftIcon, FileTextIcon } from "lucide-react";

const EditorParecer = dynamic(
  () =>
    import("@/components/ferramentas/editor-parecer").then((m) => m.EditorParecer),
  { ssr: false, loading: () => <div className="h-[420px] rounded-lg border border-border bg-muted/30 animate-pulse" /> }
);

export function ParecerViewClient() {
  // static export: o param vem da URL real (nao do "placeholder" prerenderizado)
  const pathname = usePathname();
  const id = pathname.split("/").filter(Boolean).pop() || "";

  const [parecer, setParecer] = useState<ParecerDoc | null>(null);
  const [html, setHtml] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [baixando, setBaixando] = useState(false);

  useEffect(() => {
    async function carregar() {
      setCarregando(true);
      try {
        const doc = await buscarParecerDoc(id);
        setParecer(doc);
        setHtml(doc.parecer_html);
      } catch (e) {
        setErro(mensagemErroAmigavel(e));
      } finally {
        setCarregando(false);
      }
    }
    if (id) carregar();
  }, [id]);

  async function handleBaixar() {
    setBaixando(true);
    try {
      const blob = await exportarParecer(id, html, parecer?.titulo || undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${parecer?.titulo || "parecer-tecnico"}.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setBaixando(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={parecer?.titulo || "Parecer Técnico"}
        description={parecer?.cliente_nome ? `Cliente: ${parecer.cliente_nome}` : undefined}
        action={
          <div className="flex items-center gap-2">
            <Link
              href="/ferramentas/parecer/historico"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              <ArrowLeftIcon className="size-4 mr-1" />
              Voltar
            </Link>
            <Button
              size="sm"
              disabled={baixando || !parecer}
              onClick={handleBaixar}
            >
              {baixando ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <DownloadIcon className="size-4" />
              )}
              Baixar .docx
            </Button>
          </div>
        }
      />

      <div className="max-w-4xl animate-slide-up">
        <div className="glass-card rounded-2xl p-6 sm:p-8">
          {carregando ? (
            <div className="space-y-3">
              <div className="h-8 rounded-lg bg-muted/30 animate-pulse" />
              <div className="h-[420px] rounded-lg bg-muted/30 animate-pulse" />
            </div>
          ) : erro ? (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3">
              <p className="text-sm text-destructive" role="alert">{erro}</p>
            </div>
          ) : (
            <EditorParecer
              content={html}
              editable
              onChange={setHtml}
            />
          )}

          {!carregando && !erro && parecer && (
            <div className="flex items-center justify-end pt-4 mt-4 border-t border-border">
              <p className="text-xs text-muted-foreground mr-3">
                Edite o parecer acima e baixe a versão atualizada.
              </p>
              <Button size="sm" disabled={baixando} onClick={handleBaixar}>
                {baixando ? (
                  <Loader2Icon className="size-4 animate-spin" />
                ) : (
                  <DownloadIcon className="size-4" />
                )}
                Baixar .docx
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

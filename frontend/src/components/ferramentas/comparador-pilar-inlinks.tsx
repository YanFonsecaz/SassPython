"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { CopyIcon, CheckIcon } from "lucide-react";
import { useState } from "react";

interface Props {
  titulo: string;
  pilarOriginal: string;
  pilarModificado: string;
  qtdInlinksAplicados: number;
}

export function ComparadorPilarInlinks({
  titulo,
  pilarOriginal,
  pilarModificado,
  qtdInlinksAplicados,
}: Props) {
  const [copiadoTipo, setCopiadoTipo] = useState<"md" | "html" | null>(null);

  async function copiarMarkdown() {
    try {
      await navigator.clipboard.writeText(`# ${titulo}\n\n${pilarModificado}`);
      setCopiadoTipo("md");
      setTimeout(() => setCopiadoTipo(null), 2000);
    } catch {
      /* ignore */
    }
  }

  async function copiarHtml() {
    try {
      const { markdownToHtml } = await import("@/lib/markdown");
      const html = await markdownToHtml(`# ${titulo}\n\n${pilarModificado}`);
      await navigator.clipboard.writeText(html);
      setCopiadoTipo("html");
      setTimeout(() => setCopiadoTipo(null), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <section
      className="
        rounded-2xl border bg-card overflow-hidden
        relative left-1/2 -translate-x-1/2
        w-[calc(100vw-2rem)]
        sm:w-[calc(100vw-3rem)]
        lg:w-[calc(100vw-16rem-4rem)]
      "
    >
      <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-border">
        <div>
          <div className="text-sm font-medium text-muted-foreground">
            Conteúdo com links
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {qtdInlinksAplicados} inlink{qtdInlinksAplicados === 1 ? "" : "s"} adicionado
            {qtdInlinksAplicados === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={copiarMarkdown}>
            {copiadoTipo === "md" ? (
              <><CheckIcon className="size-3.5" />Copiado</>
            ) : (
              <><CopyIcon className="size-3.5" />Copiar Markdown</>
            )}
          </Button>
          <Button variant="outline" size="sm" onClick={copiarHtml}>
            {copiadoTipo === "html" ? (
              <><CheckIcon className="size-3.5" />Copiado</>
            ) : (
              <><CopyIcon className="size-3.5" />Copiar HTML</>
            )}
          </Button>
        </div>
      </header>

      <div className="grid gap-0 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border">
        <ColunaPilar rotulo="Conteúdo Original" conteudo={pilarOriginal} variant="original" />
        <ColunaPilar rotulo="Conteúdo Ajustado pela IA" conteudo={pilarModificado} variant="modificado" />
      </div>
    </section>
  );
}

function ColunaPilar({
  rotulo,
  conteudo,
  variant,
}: {
  rotulo: string;
  conteudo: string;
  variant: "original" | "modificado";
}) {
  return (
    <div className="flex flex-col">
      <div className="px-5 py-2 border-b border-border bg-surface-light text-sm font-medium text-muted-foreground">
        {rotulo}
      </div>
      <div className="prose prose-sm max-w-none px-5 py-5 overflow-y-auto max-h-[70vh]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={
            variant === "modificado"
              ? {
                  a: ({ node, ...props }) => (
                    <a
                      {...props}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-semibold underline decoration-foreground/40 underline-offset-2 text-foreground hover:decoration-foreground"
                    />
                  ),
                }
              : undefined
          }
        >
          {conteudo}
        </ReactMarkdown>
      </div>
    </div>
  );
}

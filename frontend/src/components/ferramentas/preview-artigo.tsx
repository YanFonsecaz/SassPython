"use client";
/* eslint-disable @next/next/no-img-element */

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CheckIcon, CopyIcon, DownloadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface PreviewArtigoProps {
  titulo: string;
  conteudo: string;
  imagemUrl?: string | null;
}

function calcularLeitura(texto: string): number {
  const palavras = texto.trim().split(/\s+/).length;
  return Math.max(1, Math.round(palavras / 220));
}

function slugify(texto: string): string {
  const s = texto
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9\-_ ]/g, "")
    .trim()
    .replace(/ +/g, "-")
    .toLowerCase();
  return s || "imagem";
}

function imagemExtension(url: string): string {
  try {
    const pathname = new URL(url, "https://x").pathname;
    if (pathname.includes("/imagem")) return ".webp";
  } catch { /* ignore */ }
  return ".png";
}

async function baixarImagem(url: string, titulo: string) {
  try {
    const resp = await fetch(url, { credentials: "include" });
    if (!resp.ok) {
      toast.error("Imagem indisponivel");
      return;
    }
    const blob = await resp.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = slugify(titulo).slice(0, 80) + imagemExtension(url);
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
  } catch {
    toast.error("Erro ao baixar imagem");
  }
}

export function PreviewArtigo({ titulo, conteudo, imagemUrl }: PreviewArtigoProps) {
  const [copiado, setCopiado] = useState(false);
  const minutosLeitura = calcularLeitura(conteudo);
  const totalPalavras = conteudo.trim().split(/\s+/).length;

  async function copiarMarkdown() {
    const text = `# ${titulo}\n\n${conteudo}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      // ignore
    }
  }

  return (
    <article className="rounded-2xl border border-border bg-card overflow-hidden shadow-sm">
      {imagemUrl && (
        <div className="relative w-full aspect-[16/7] overflow-hidden bg-surface-light group">
          <img
            src={imagemUrl}
            alt={titulo}
            className="w-full h-full object-cover"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => baixarImagem(imagemUrl, titulo)}
            className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity bg-background/90 backdrop-blur"
          >
            <DownloadIcon className="size-3.5" />
            Baixar imagem
          </Button>
        </div>
      )}

      <div className="px-6 py-7 sm:px-10 sm:py-10">
        <header className="mb-8 pb-6 border-b border-border">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground leading-tight">
                {titulo}
              </h1>
              <p className="mt-3 text-xs text-muted-foreground flex items-center gap-3">
                <span>{totalPalavras.toLocaleString("pt-BR")} palavras</span>
                <span className="size-1 rounded-full bg-border" />
                <span>{minutosLeitura} min de leitura</span>
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={copiarMarkdown}
              className="shrink-0"
            >
              {copiado ? (
                <>
                  <CheckIcon className="size-3.5" />
                  Copiado
                </>
              ) : (
                <>
                  <CopyIcon className="size-3.5" />
                  Copiar Markdown
                </>
              )}
            </Button>
          </div>
        </header>

        <div className="markdown-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{conteudo}</ReactMarkdown>
        </div>
      </div>
    </article>
  );
}

"use client";

import { ArrowDownIcon, ArrowUpIcon, CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type ModoInlinks = "receber" | "distribuir";

interface Props {
  modo?: ModoInlinks;
  onSelecionar: (modo: ModoInlinks) => void;
}

export function InlinksSeletorModo({ modo, onSelecionar }: Props) {
  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-brand/20 bg-gradient-to-br from-brand/5 to-transparent p-6">
        <h2 className="font-heading text-lg font-semibold tracking-tight">
          O que são inlinks?
        </h2>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
          Inlinks são links entre páginas do <em>mesmo site</em>. Melhoram SEO
          (Google entende a estrutura), facilitam a navegação e mantêm o leitor
          mais tempo. Escolha a <strong>direção</strong> que quer aplicar:
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <CardModo
          modo="receber"
          ativo={modo === "receber"}
          onClick={() => onSelecionar("receber")}
          icone={ArrowDownIcon}
          titulo="Receber links"
          subtitulo="1 artigo + N candidatas"
          descricao="Tenho um artigo principal e quero adicionar links de outros artigos do meu blog dentro dele."
          quando="Use quando você acabou de publicar um guia/pilar e quer enriquecer com referências internas."
          exemplo='Ex.: artigo "Guia completo de CNAE" recebe links de artigos relacionados sobre tributação, contratação PJ, etc.'
          custo="15-60 créditos"
        />
        <CardModo
          modo="distribuir"
          ativo={modo === "distribuir"}
          onClick={() => onSelecionar("distribuir")}
          icone={ArrowUpIcon}
          titulo="Distribuir um link"
          subtitulo="1 URL alvo + N candidatas"
          descricao="Tenho uma página e quero que outras páginas do meu site linkem para ela."
          quando="Use quando você lançou uma landing/produto/serviço e precisa que páginas existentes apontem para ela."
          exemplo='Ex.: nova página "/categoria/sapatos-femininos" precisa de tráfego — outras páginas do blog recebem o link.'
          custo="15-115 créditos"
        />
      </div>
    </div>
  );
}

function CardModo({
  ativo, onClick, icone: Icone, titulo, subtitulo,
  descricao, quando, exemplo, custo,
}: {
  modo: ModoInlinks;
  ativo: boolean;
  onClick: () => void;
  icone: React.ElementType;
  titulo: string;
  subtitulo: string;
  descricao: string;
  quando: string;
  exemplo: string;
  custo: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "text-left rounded-2xl border bg-card p-5 transition-all duration-200",
        "hover:border-brand/40 hover:shadow-md",
        ativo ? "border-brand ring-2 ring-brand/20 shadow-md" : "border-border",
      )}
    >
      <div className="flex items-start gap-3">
        <div className={cn(
          "flex items-center justify-center size-10 rounded-xl shrink-0",
          ativo ? "gradient-bg shadow-sm" : "bg-surface-light border border-border",
        )}>
          <Icone className={cn("size-5", ativo ? "text-white" : "text-brand-dark")} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-heading font-semibold text-base">{titulo}</h3>
            {ativo && (
              <span className="inline-flex items-center gap-1 rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand-dark">
                <CheckIcon className="size-3" /> Selecionado
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{subtitulo}</p>
        </div>
      </div>

      <div className="mt-4 space-y-2.5 text-sm">
        <p className="text-foreground">{descricao}</p>
        <div className="rounded-lg bg-surface-light px-3 py-2 border border-border/50">
          <p className="text-sm font-medium text-muted-foreground mb-1">
            Use quando
          </p>
          <p className="text-xs text-foreground/90 leading-relaxed">{quando}</p>
        </div>
        <p className="text-xs text-muted-foreground italic leading-relaxed">{exemplo}</p>
      </div>

      <div className="mt-4 pt-3 border-t border-border/50 flex items-center justify-between">
        <span className="text-xs font-medium text-brand-dark">{custo}</span>
        {!ativo && (
          <span className="text-xs text-muted-foreground">Clique para selecionar →</span>
        )}
      </div>
    </button>
  );
}

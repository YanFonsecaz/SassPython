"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import {
  ArrowLeftIcon,
  FileSearchIcon,
  GlobeIcon,
  Loader2Icon,
  PlusIcon,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { useClientes } from "@/hooks/use-clientes";
import { useCreditos } from "@/hooks/use-creditos";
import { cn } from "@/lib/utils";
import { mensagemErroAmigavel } from "@/lib/api";
import {
  criarAuditoriaSeotec,
  listarAuditoriasSeotec,
  type AuditoriaResumoSeotec,
} from "@/lib/api/seotec";

const FASE_LABELS: Record<string, string> = {
  before: "Before",
  after: "After",
  concluida: "Concluída",
};

const FASE_CORES: Record<string, string> = {
  before: "border-blue-400 text-blue-700 bg-blue-50",
  after: "border-purple-400 text-purple-700 bg-purple-50",
  concluida: "border-success/30 text-success bg-success/10",
};

export function SeotecFormClient() {
  const router = useRouter();
  const { clientes, carregando: carregandoClientes } = useClientes();
  const { saldo } = useCreditos();

  const [clienteId, setClienteId] = useState("");
  const [dominio, setDominio] = useState("");
  const [criando, setCriando] = useState(false);
  const [auditorias, setAuditorias] = useState<AuditoriaResumoSeotec[]>([]);
  const [carregandoLista, setCarregandoLista] = useState(true);

  useEffect(() => {
    listarAuditoriasSeotec()
      .then(setAuditorias)
      .catch(() => {})
      .finally(() => setCarregandoLista(false));
  }, []);

  function selecionarCliente(id: string) {
    setClienteId(id);
    const c = clientes.find((c) => c.id === id);
    if (c?.site_url && !dominio) {
      setDominio(c.site_url);
    }
  }

  async function handleCriar() {
    if (!clienteId || !dominio) return;
    setCriando(true);
    try {
      const audit = await criarAuditoriaSeotec(clienteId, dominio);
      toast.success("Auditoria criada");
      router.push(`/ferramentas/auditoria-seo-tecnico/${audit.id}`);
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    } finally {
      setCriando(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Auditoria SEO Técnico"
        description="Faça upload do pacote do Screaming Frog e receba diagnóstico + recomendações por item"
        action={
          <Link href="/ferramentas" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" /> Voltar
          </Link>
        }
      />

      <div className="max-w-2xl mx-auto space-y-6">
        {/* Criar nova auditoria */}
        <div className="glass-card rounded-2xl p-6 sm:p-8 space-y-5">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <PlusIcon className="size-4" /> Nova auditoria
          </h2>

          {/* Step: cliente */}
          <div className="space-y-3">
            <Label className="text-sm font-medium text-muted-foreground">Cliente</Label>
            {carregandoClientes ? (
              <div className="h-10 rounded-lg bg-muted/50 animate-pulse" />
            ) : clientes.length === 0 ? (
              <div className="rounded-lg border bg-surface-light p-4 text-center">
                <p className="text-sm text-muted-foreground">Nenhum cliente cadastrado.</p>
                <Link href="/clientes/novo" className="text-sm text-brand-dark font-medium hover:underline mt-1 inline-block">
                  Cadastrar cliente
                </Link>
              </div>
            ) : (
              <div className="grid gap-2 max-h-48 overflow-y-auto">
                {clientes.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => selecionarCliente(c.id)}
                    className={cn(
                      "flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                      clienteId === c.id ? "border-brand bg-brand/5" : "hover:bg-surface-light",
                    )}
                  >
                    <div className={cn(
                      "size-2 rounded-full shrink-0",
                      clienteId === c.id ? "bg-brand" : "bg-muted-foreground/30",
                    )} />
                    <span className="text-sm font-medium truncate">{c.nome}</span>
                    {c.site_url && (
                      <span className="text-xs text-muted-foreground truncate ml-auto">{c.site_url}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Domínio */}
          <div className="space-y-2">
            <Label htmlFor="dominio" className="text-sm font-medium text-muted-foreground">
              Domínio do site
            </Label>
            <div className="relative">
              <GlobeIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                id="dominio"
                placeholder="https://exemplo.com.br"
                value={dominio}
                onChange={(e) => setDominio(e.target.value)}
                className="pl-9"
                disabled={criando}
              />
            </div>
          </div>

          <Button
            type="button"
            className="w-full gradient-bg border-0 hover:opacity-90 transition-opacity"
            onClick={handleCriar}
            disabled={criando || !clienteId || !dominio}
          >
            {criando ? (
              <>
                <Loader2Icon className="size-4 mr-1 animate-spin" /> Criando...
              </>
            ) : (
              <>
                <FileSearchIcon className="size-4 mr-1" /> Criar auditoria
              </>
            )}
          </Button>

          <p className="text-xs text-muted-foreground text-center">
            Saldo atual: <span className={cn("font-bold", (saldo?.saldo_total ?? 0) < 20 ? "text-destructive" : "text-brand-deep")}>{saldo?.saldo_total ?? "—"}</span> créditos
          </p>
        </div>

        {/* Listar auditorias existentes */}
        <div className="glass-card rounded-2xl p-6 space-y-3">
          <h2 className="text-sm font-semibold">Auditorias recentes</h2>
          {carregandoLista ? (
            <div className="space-y-2">
              <div className="h-16 rounded-lg bg-muted/50 animate-pulse" />
              <div className="h-16 rounded-lg bg-muted/50 animate-pulse" />
            </div>
          ) : auditorias.length === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-center">
              <p className="text-sm text-muted-foreground">Nenhuma auditoria ainda. Crie a primeira acima.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {auditorias.map((a) => (
                <Link
                  key={a.id}
                  href={`/ferramentas/auditoria-seo-tecnico/${a.id}`}
                  className="flex items-center justify-between gap-3 rounded-lg border bg-surface-light px-4 py-3 hover:border-brand/40 hover:bg-brand/5 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{a.dominio}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(a.criado_em).toLocaleDateString("pt-BR")}
                      {a.score_antes !== null && ` · Score: ${a.score_antes.toFixed(0)}%`}
                    </p>
                  </div>
                  <Badge variant="outline" className={cn("text-[10px] shrink-0", FASE_CORES[a.fase] || "")}>
                    {FASE_LABELS[a.fase] || a.fase}
                  </Badge>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

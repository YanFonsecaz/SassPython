"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import Link from "next/link";
import { api, mensagemErroAmigavel } from "@/lib/api";
import { useClientes } from "@/hooks/use-clientes";
import { cn } from "@/lib/utils";
import { CheckIcon, UserIcon, FileTextIcon, MessageSquareIcon, SparklesIcon } from "lucide-react";
import type { Cliente, GerarArtigoRequest, ExecucaoCriada } from "@/types";
import { TermoComAjuda } from "@/components/ui/termo-com-ajuda";

interface FormularioGerarArtigoProps {
  clientePreSelecionado?: Cliente;
  onExecucaoCriada?: (id: string) => void;
}

const TIPOS_CONTEUDO = [
  { value: "blog", label: "Blog" },
  { value: "produto", label: "Produto" },
  { value: "categoria", label: "Categoria" },
  { value: "noticias", label: "Notícias" },
  { value: "instagram", label: "Instagram" },
  { value: "topico", label: "Tópico" },
];

const STEPS = [
  { label: "Cliente", icon: UserIcon },
  { label: "Conteudo", icon: FileTextIcon },
  { label: "Contexto", icon: MessageSquareIcon },
  { label: "Confirmar", icon: SparklesIcon },
] as const;

export function FormularioGerarArtigo({
  clientePreSelecionado,
  onExecucaoCriada,
}: FormularioGerarArtigoProps) {
  const router = useRouter();
  const { clientes, carregando: carregandoClientes } = useClientes();
  const [step, setStep] = useState(0);
  const [saldo, setSaldo] = useState<number | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  const [clientId, setClientId] = useState(clientePreSelecionado?.id || "");
  const [personaId, setPersonaId] = useState(clientePreSelecionado?.config_json?.personas?.[0]?.nome || "");
  const [topico, setTopico] = useState("");
  const [palavraChave, setPalavraChave] = useState("");
  const [palavrasSecundarias, setPalavrasSecundarias] = useState("");
  const [tipoConteudo, setTipoConteudo] = useState("blog");
  const [metaPalavras, setMetaPalavras] = useState(1500);
  const [objetivo, setObjetivo] = useState("");
  const [artigoIntrodutorio, setArtigoIntrodutorio] = useState("");
  const [perguntasClientes, setPerguntasClientes] = useState("");
  const [instrucoesAdicionais, setInstrucoesAdicionais] = useState("");

  const clienteSelecionado = clientes.find((c) => c.id === clientId);
  const personas = clienteSelecionado?.config_json?.personas || [];

  useEffect(() => {
    async function loadSaldo() {
      try {
        const dados = await api.get<{ saldo_total: number }>("/creditos/saldo");
        setSaldo(dados.saldo_total);
      } catch {
        // silent
      }
    }
    loadSaldo();
  }, []);

  const canAdvance = useCallback(() => {
    switch (step) {
      case 0: return !!clientId;
      case 1: return !!topico.trim() && !!palavraChave.trim();
      case 2: return true;
      case 3: return true;
      default: return false;
    }
  }, [step, clientId, topico, palavraChave]);

  async function handleSubmit() {
    setErro("");
    setEnviando(true);

    try {
      const secundarias = palavrasSecundarias.split(",").map((w) => w.trim()).filter(Boolean);

      const body: GerarArtigoRequest = {
        cliente_id: clientId,
        persona_id: personaId,
        topico: topico.trim(),
        palavra_chave_principal: palavraChave.trim(),
        palavras_chave_secundarias: secundarias,
        tipo_conteudo: tipoConteudo,
        meta_palavras: metaPalavras,
        objetivo,
        artigo_introdutorio: artigoIntrodutorio,
        perguntas_clientes: perguntasClientes,
        instrucoes_adicionais: instrucoesAdicionais,
      };

      const resultado = await api.post<ExecucaoCriada>("/ferramentas/gerar-artigo", body);

      if (onExecucaoCriada) {
        onExecucaoCriada(resultado.id);
      } else {
        router.push(`/ferramentas/historico/${resultado.id}`);
      }
    } catch (err) {
      setErro(mensagemErroAmigavel(err));
    } finally {
      setEnviando(false);
    }
  }

  function addNovaSecundaria(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      const val = (e.target as HTMLInputElement).value.trim();
      if (val) {
        setPalavrasSecundarias((prev) => (prev ? prev + ", " + val : val));
        (e.target as HTMLInputElement).value = "";
      }
    }
  }

  function removeSecundaria(index: number) {
    setPalavrasSecundarias((prev) =>
      prev.split(",").filter((_, j) => j !== index).join(",")
    );
  }

  return (
    <div className="max-w-2xl animate-slide-up">
      <div className="mb-8">
        <h2 className="text-xl font-bold">Gerar Artigo com IA</h2>
        <p className="text-sm text-muted-foreground mt-1">Preencha os dados para criar seu artigo otimizado</p>
      </div>

      <div className="flex items-center gap-0 mb-8">
        {STEPS.map((s, i) => {
          const StepIcon = s.icon;
          const isCompleted = i < step;
          const isCurrent = i === step;
          return (
            <div key={s.label} className="flex items-center flex-1 last:flex-none">
              <button
                type="button"
                onClick={() => i < step && setStep(i)}
                className="flex flex-col items-center gap-1.5 group"
                disabled={i > step}
              >
                <div
                  className={cn(
                    "flex items-center justify-center size-9 rounded-full border-2 transition-all duration-200",
                    isCompleted && "bg-brand border-brand text-white",
                    isCurrent && "border-brand text-brand",
                    !isCompleted && !isCurrent && "border-border text-muted-foreground"
                  )}
                >
                  {isCompleted ? <CheckIcon className="size-4" /> : <StepIcon className="size-4" />}
                </div>
                <span
                  className={cn(
                    "text-xs font-medium transition-colors",
                    isCurrent && "text-brand-dark",
                    isCompleted && "text-foreground",
                    !isCompleted && !isCurrent && "text-muted-foreground"
                  )}
                >
                  {s.label}
                </span>
              </button>
              {i < STEPS.length - 1 && (
                <div className={cn("flex-1 h-0.5 mx-2 mb-5 transition-colors", i < step ? "bg-brand" : "bg-border")} />
              )}
            </div>
          );
        })}
      </div>

      <div className="glass-card rounded-2xl p-6 sm:p-8">
        {erro && (
          <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2 mb-6">
            <p className="text-sm text-destructive" role="alert">{erro}</p>
          </div>
        )}

        {step === 0 && (
          <div className="space-y-5 animate-fade-in">
            <div className="space-y-2">
              <Label htmlFor="cliente" className="text-sm font-medium text-muted-foreground">Cliente</Label>
              <select
                id="cliente"
                className="flex h-10 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm transition-colors focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                value={clientId}
                onChange={(e) => { setClientId(e.target.value); setPersonaId(""); }}
                disabled={enviando || carregandoClientes}
              >
                <option value="">Selecione um cliente</option>
                {clientes.filter((c) => c.ativo).map((c) => (
                  <option key={c.id} value={c.id}>{c.nome}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end">
              <Link href="/clientes/novo" className={buttonVariants({ variant: "link", size: "sm" })}>
                Cadastrar novo cliente
              </Link>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="persona" className="text-sm font-medium text-muted-foreground">
                  <TermoComAjuda termo="persona" />
                </Label>
                {clientId && (
                  <Link href={`/clientes/${clientId}`} className={buttonVariants({ variant: "link", size: "sm" })}>
                    Gerenciar personas
                  </Link>
                )}
              </div>
              <select
                id="persona"
                className="flex h-10 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm transition-colors focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                value={personaId}
                onChange={(e) => setPersonaId(e.target.value)}
                disabled={enviando || !clientId}
              >
                <option value="">Padrão do cliente (Persona Global)</option>
                {personas.map((p, i) => (
                  <option key={i} value={p.nome}>{p.nome}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5 animate-fade-in">
            <div className="space-y-2">
              <Label htmlFor="topico" className="text-sm font-medium text-muted-foreground">Tópico *</Label>
              <Textarea
                id="topico"
                placeholder="Ex: Guia completo de SEO local para clinicas odontologicas"
                required
                maxLength={500}
                value={topico}
                onChange={(e) => setTopico(e.target.value)}
                disabled={enviando}
                rows={2}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="palavra-chave" className="text-sm font-medium text-muted-foreground">Palavra-chave principal *</Label>
              <Input
                id="palavra-chave"
                placeholder="Ex: seo local para clinicas"
                required
                maxLength={200}
                value={palavraChave}
                onChange={(e) => setPalavraChave(e.target.value)}
                disabled={enviando}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="secundarias" className="text-sm font-medium text-muted-foreground">
                Palavras-chave secundárias <span className="normal-case text-muted-foreground">(Enter para adicionar)</span>
              </Label>
              <Input
                id="secundarias"
                placeholder="Digite e pressione Enter"
                onKeyDown={addNovaSecundaria}
                disabled={enviando}
              />
              {palavrasSecundarias && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {palavrasSecundarias.split(",").map((w) => w.trim()).filter(Boolean).map((w, i) => (
                    <span key={i} className="inline-flex items-center gap-1 rounded-full bg-brand/10 border border-brand/20 px-2.5 py-0.5 text-xs text-brand-dark">
                      {w}
                      <button type="button" onClick={() => removeSecundaria(i)} aria-label="Remover palavra-chave" className="text-brand-dark/60 hover:text-brand-dark">&times;</button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="tipo-conteudo" className="text-sm font-medium text-muted-foreground">Tipo de conteúdo</Label>
                <select
                  id="tipo-conteudo"
                  className="flex h-10 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm transition-colors focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  value={tipoConteudo}
                  onChange={(e) => setTipoConteudo(e.target.value)}
                  disabled={enviando}
                >
                  {TIPOS_CONTEUDO.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="meta-palavras" className="text-sm font-medium text-muted-foreground">Meta de palavras</Label>
                <Input
                  id="meta-palavras"
                  type="number"
                  min={300}
                  max={5000}
                  value={metaPalavras}
                  onChange={(e) => setMetaPalavras(Number(e.target.value))}
                  disabled={enviando}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="objetivo" className="text-sm font-medium text-muted-foreground">Objetivo</Label>
              <Textarea
                id="objetivo"
                placeholder="Ex: Educar gestores sobre a importancia de SEO local"
                maxLength={1000}
                value={objetivo}
                onChange={(e) => setObjetivo(e.target.value)}
                disabled={enviando}
                rows={2}
              />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5 animate-fade-in">
            <p className="text-sm font-medium text-muted-foreground">Campos opcionais — forneça mais contexto para obter melhores resultados</p>
            <div className="space-y-2">
              <Label htmlFor="artigo-intro" className="text-sm font-medium text-muted-foreground">Artigo introdutório</Label>
              <Textarea
                id="artigo-intro"
                placeholder="Cole aqui um artigo de referência para orientar a IA..."
                maxLength={2000}
                value={artigoIntrodutorio}
                onChange={(e) => setArtigoIntrodutorio(e.target.value)}
                disabled={enviando}
                rows={4}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="perguntas" className="text-sm font-medium text-muted-foreground">Perguntas de clientes</Label>
              <Textarea
                id="perguntas"
                placeholder="Quanto custa SEO? Quanto tempo leva para aparecer no Google?"
                maxLength={2000}
                value={perguntasClientes}
                onChange={(e) => setPerguntasClientes(e.target.value)}
                disabled={enviando}
                rows={3}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="instrucoes" className="text-sm font-medium text-muted-foreground">Instruções adicionais para IA</Label>
              <Textarea
                id="instrucoes"
                placeholder="Ex: Inclua dados estatísticos sobre busca local"
                maxLength={2000}
                value={instrucoesAdicionais}
                onChange={(e) => setInstrucoesAdicionais(e.target.value)}
                disabled={enviando}
                rows={3}
              />
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-5 animate-fade-in">
            <div className="rounded-xl border bg-surface-light p-5 space-y-3">
              <h4 className="text-sm font-semibold text-muted-foreground">Resumo</h4>
              <div className="grid gap-3 text-sm">
                {[
                  ["Cliente", clienteSelecionado?.nome],
                  ["Persona", personaId],
                  ["Tópico", topico],
                  ["Palavra-chave", palavraChave],
                  ["Tipo", TIPOS_CONTEUDO.find((t) => t.value === tipoConteudo)?.label],
                  ["Meta", `${metaPalavras} palavras`],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4">
                    <span className="text-muted-foreground shrink-0">{label}</span>
                    <span className="text-right truncate font-medium">{value || "—"}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-brand/20 bg-brand/5 p-5 space-y-3">
              <h4 className="text-sm font-semibold text-muted-foreground">Custo estimado</h4>
              <div className="text-sm space-y-1.5 text-muted-foreground">
                <p className="font-semibold text-foreground">20-38 créditos</p>
                <p className="pl-3">Geração base: 15 créditos (fixo)</p>
                <p className="pl-3">Revisões: 3 créditos cada (0-6 possíveis)</p>
                <p className="pl-3">Imagem: 5 créditos (fixo)</p>
              </div>
              <div className="pt-2 border-t border-brand/20">
                <p className="text-sm">
                  Seu saldo atual: <span className={cn("font-bold", saldo !== null && saldo < 20 ? "text-destructive" : "text-brand-dark")}>{saldo ?? "..."}</span> créditos
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between mt-8 pt-6 border-t border-border">
          <div>
            {step > 0 && (
              <Button type="button" variant="ghost" onClick={() => setStep((s) => s - 1)} disabled={enviando}>
                Voltar
              </Button>
            )}
          </div>
          <div>
            {step < STEPS.length - 1 ? (
              <Button
                type="button"
                className="gradient-bg border-0 hover:opacity-90 transition-opacity"
                onClick={() => setStep((s) => s + 1)}
                disabled={!canAdvance() || enviando}
              >
                Próximo
              </Button>
            ) : (
              <Button
                type="button"
                className="gradient-bg border-0 hover:opacity-90 transition-opacity"
                onClick={handleSubmit}
                disabled={enviando || (saldo !== null && saldo < 20)}
              >
                {enviando ? "Gerando..." : "Gerar Artigo"}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

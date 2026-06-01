"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { mensagemErroAmigavel } from "@/lib/api";
import {
  gerarParecer,
  buscarExecucaoParecer,
  buscarParecerDoc,
  exportarParecer,
  type GerarParecerReq,
  type ParecerExecucao,
} from "@/lib/api/parecer";

const POLL_INTERVAL = 2000;
const POLL_TIMEOUT = 10 * 60 * 1000;

type ParecerEstado = "idle" | "gerando" | "pronto" | "erro";

export function useParecer() {
  const [estado, setEstado] = useState<ParecerEstado>("idle");
  const [execucaoId, setExecucaoId] = useState<string | null>(null);
  const [parecerId, setParecerId] = useState<string | null>(null);
  const [etapaAtual, setEtapaAtual] = useState<string | null>(null);
  const [html, setHtml] = useState<string>("");
  const erroRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const canceladoRef = useRef(false);

  useEffect(() => {
    return () => {
      canceladoRef.current = true;
      if (erroRef.current) clearTimeout(erroRef.current);
    };
  }, []);

  const aguardarConclusao = useCallback(async (id: string): Promise<ParecerExecucao> => {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      let errosSeguidos = 0;
      const poll = async () => {
        if (canceladoRef.current) return;
        if (Date.now() - start > POLL_TIMEOUT) {
          reject(new Error("Timeout ao gerar o parecer"));
          return;
        }
        try {
          const dados = await buscarExecucaoParecer(id);
          errosSeguidos = 0;
          if (dados.status === "concluida" || dados.status === "falhou" || dados.status === "cancelada") {
            resolve(dados);
          } else {
            if (dados.etapa_atual) setEtapaAtual(dados.etapa_atual);
            erroRef.current = setTimeout(poll, POLL_INTERVAL);
          }
        } catch {
          errosSeguidos += 1;
          if (errosSeguidos >= 3) {
            reject(new Error("Falha de comunicacao ao verificar status do parecer"));
            return;
          }
          erroRef.current = setTimeout(poll, POLL_INTERVAL);
        }
      };
      poll();
    });
  }, []);

  const gerar = useCallback(async (req: GerarParecerReq) => {
    setEstado("gerando");
    setEtapaAtual(null);
    try {
      const { id } = await gerarParecer(req);
      setExecucaoId(id);
      const final = await aguardarConclusao(id);
      if (final.status === "concluida" && final.parecer_id) {
        const doc = await buscarParecerDoc(final.parecer_id);
        setParecerId(final.parecer_id);
        setHtml(doc.parecer_html);
        setEstado("pronto");
        setEtapaAtual(null);
        toast.success("Parecer gerado com sucesso!");
      } else {
        toast.error(final.erro_msg || "Falha ao gerar o parecer");
        setEstado("erro");
        setEtapaAtual(null);
      }
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
      setEstado("erro");
      setEtapaAtual(null);
    }
  }, [aguardarConclusao]);

  const baixar = useCallback(async (nome?: string) => {
    if (!parecerId) return;
    try {
      const blob = await exportarParecer(parecerId, html, nome);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${nome ?? "parecer-tecnico"}.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(mensagemErroAmigavel(e));
    }
  }, [parecerId, html]);

  const reset = useCallback(() => {
    if (erroRef.current) clearTimeout(erroRef.current);
    erroRef.current = null;
    canceladoRef.current = false;
    setEstado("idle");
    setExecucaoId(null);
    setParecerId(null);
    setEtapaAtual(null);
    setHtml("");
  }, []);

  return { estado, html, setHtml, etapaAtual, gerar, baixar, reset };
}

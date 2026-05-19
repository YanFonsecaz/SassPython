import { ExecucaoDetalheConteudo } from "@/components/ferramentas/execucao-detalhe-conteudo";

export async function generateStaticParams() {
  return [{ id: "placeholder" }];
}

export default function ExecucaoDetalhePage() {
  return <ExecucaoDetalheConteudo />;
}
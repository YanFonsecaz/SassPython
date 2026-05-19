import { ClienteDetalheConteudo } from "@/components/clientes/cliente-detalhe-conteudo";

export async function generateStaticParams() {
  return [{ id: "placeholder" }];
}

export default function ClienteDetalhePage() {
  return <ClienteDetalheConteudo />;
}
import { CwvHistoricoClient } from "@/components/cwv/cwv-historico-client";

export async function generateStaticParams() {
  return [{ clienteId: "placeholder" }];
}

export default function CwvHistoricoPage() {
  return <CwvHistoricoClient />;
}

import { CwvExecucaoClient } from "@/components/cwv/cwv-execucao-client";

export async function generateStaticParams() {
  return [{ id: "placeholder" }];
}

export default function CwvExecucaoPage() {
  return <CwvExecucaoClient />;
}

import { CwvAuditoriaClient } from "@/components/cwv/cwv-auditoria-client";

export async function generateStaticParams() {
  return [{ auditoriaId: "placeholder" }];
}

export default function CwvAuditoriaPage() {
  return <CwvAuditoriaClient />;
}

import { SeotecAuditoriaClient } from "@/components/seotec/seotec-auditoria-client";

export async function generateStaticParams() {
  return [{ auditoriaId: "placeholder" }];
}

export default function SeotecAuditoriaPage() {
  return <SeotecAuditoriaClient />;
}

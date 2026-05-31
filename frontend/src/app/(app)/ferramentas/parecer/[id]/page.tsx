import { ParecerViewClient } from "@/components/ferramentas/parecer-view-client";

export async function generateStaticParams() {
  return [{ id: "placeholder" }];
}

export default function ParecerDetalhePage() {
  return <ParecerViewClient />;
}

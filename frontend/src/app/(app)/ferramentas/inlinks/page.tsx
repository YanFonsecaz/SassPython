import { Suspense } from "react";
import { InlinksPageUnificada } from "@/components/ferramentas/inlinks-page-unificada";

export default function InlinksPage() {
  return (
    <Suspense fallback={null}>
      <InlinksPageUnificada />
    </Suspense>
  );
}

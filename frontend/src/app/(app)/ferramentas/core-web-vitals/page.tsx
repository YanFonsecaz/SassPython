import { Suspense } from "react";
import { CwvFormPage } from "@/components/cwv/cwv-form";

export default function CwvPage() {
  return (
    <Suspense fallback={null}>
      <CwvFormPage />
    </Suspense>
  );
}

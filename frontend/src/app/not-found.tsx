import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";
import { FileQuestionIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="p-6 max-w-lg mx-auto">
      <EmptyState
        icon={FileQuestionIcon}
        title="Página não encontrada"
        description="A URL que você acessou não existe ou foi removida."
        action={
          <Link href="/ferramentas" className={buttonVariants()}>
            Voltar ao início
          </Link>
        }
      />
    </div>
  );
}

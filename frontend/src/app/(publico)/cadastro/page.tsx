import { FormularioCadastro } from "@/components/auth/formulario-cadastro";

export default function CadastroPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center px-4 bg-surface overflow-hidden">
      <div className="pointer-events-none absolute -top-40 -left-40 h-[500px] w-[500px] rounded-full bg-brand/20 blur-[120px]" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-[400px] w-[400px] rounded-full bg-brand-dark/30 blur-[100px]" />
      <div className="absolute inset-0 bg-dot-pattern opacity-30" />

      <div className="relative z-10 w-full max-w-md animate-slide-up">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex items-center justify-center size-12 rounded-xl gradient-bg glow-md">
            <svg className="size-6 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold">SEO SaaS</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Comece a criar conteudo otimizado agora
          </p>
        </div>
        <FormularioCadastro />
      </div>
    </div>
  );
}

import * as React from "react";
import { cn } from "@/lib/utils";

interface ErrorStateProps extends React.ComponentProps<"div"> {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}

export function ErrorState({ title = "Algo deu errado", description = "Não foi possível carregar os dados. Tente novamente.", action, className, ...props }: ErrorStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center py-16 text-center animate-fade-in", className)} {...props}>
      <div className="flex items-center justify-center size-16 rounded-2xl bg-destructive/10 border border-destructive/20 mb-4">
        <svg className="size-7 text-destructive" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg>
      </div>
      <h3 className="text-lg font-semibold">{title}</h3>
      {description && (
        <p className="mt-1 text-sm text-muted-foreground max-w-sm">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

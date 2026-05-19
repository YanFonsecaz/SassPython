import * as React from "react";
import { cn } from "@/lib/utils";

interface PageHeaderProps extends React.ComponentProps<"div"> {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, description, action, className, ...props }: PageHeaderProps) {
  return (
    <div className={cn("flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between", className)} {...props}>
      <div className="pl-12 lg:pl-0">
        <h1 className="font-heading text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
          {title}
        </h1>
        {description && (
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">{description}</p>
        )}
      </div>
      {action && <div className="pl-12 lg:pl-0 mt-3 sm:mt-0">{action}</div>}
    </div>
  );
}

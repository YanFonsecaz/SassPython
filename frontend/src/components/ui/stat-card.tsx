import * as React from "react";
import { cn } from "@/lib/utils";

interface StatCardProps extends React.ComponentProps<"div"> {
  label: string;
  value: string | number;
  icon: React.ElementType;
  trend?: { value: string; positive: boolean };
  variant?: "default" | "success" | "warning" | "danger";
}

const variantStyles = {
  default: "border-border hover:border-brand/40",
  success: "border-success/20 hover:border-success/40",
  warning: "border-warning/30 hover:border-warning/50",
  danger: "border-destructive/30 hover:border-destructive/50",
};

const iconBgStyles = {
  default: "bg-surface-light text-brand-dark border border-border",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-destructive/10 text-destructive",
};

export function StatCard({ label, value, icon: Icon, trend, variant = "default", className, ...props }: StatCardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border bg-card p-5 transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 animate-fade-in",
        variantStyles[variant],
        className
      )}
      {...props}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 min-w-0">
          <p className="text-[10.5px] font-semibold text-muted-foreground uppercase tracking-[0.08em]">
            {label}
          </p>
          <p className="font-heading text-3xl font-bold tracking-tight text-foreground tabular-nums">
            {value}
          </p>
          {trend && (
            <p className={cn("text-xs font-medium", trend.positive ? "text-success" : "text-destructive")}>
              {trend.positive ? "+" : ""}{trend.value}
            </p>
          )}
        </div>
        <div className={cn("flex items-center justify-center size-10 rounded-xl shrink-0", iconBgStyles[variant])}>
          <Icon className="size-5" />
        </div>
      </div>
    </div>
  );
}

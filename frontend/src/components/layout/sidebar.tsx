"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { useCreditos } from "@/hooks/use-creditos";
import {
  LayoutDashboardIcon,
  PenToolIcon,
  Link2Icon,
  ClockIcon,
  UsersIcon,
  CreditCardIcon,
  SettingsIcon,
  LogOutIcon,
  MenuIcon,
  XIcon,
  SparklesIcon,
  GaugeIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/ferramentas", label: "Dashboard", icon: LayoutDashboardIcon },
  { href: "/ferramentas/gerar-artigo", label: "Gerar Artigo", icon: PenToolIcon },
  { href: "/ferramentas/inlinks", label: "Inlinks", icon: Link2Icon },
  { href: "/ferramentas/core-web-vitals", label: "Core Web Vitals", icon: GaugeIcon },
  { href: "/ferramentas/historico", label: "Histórico", icon: ClockIcon },
  { href: "/clientes", label: "Clientes", icon: UsersIcon },
  { href: "/creditos", label: "Créditos", icon: CreditCardIcon },
  { href: "/perfil", label: "Perfil", icon: SettingsIcon },
];

function NavItemComponent({ item, active, onClick }: { item: NavItem; active: boolean; onClick?: () => void }) {
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
        active
          ? "gradient-bg text-white shadow-sm"
          : "text-muted-foreground hover:bg-accent hover:text-foreground"
      )}
    >
      <Icon className="size-4 shrink-0" />
      <span>{item.label}</span>
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { usuario, logout } = useAuth();
  const { saldo } = useCreditos();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) => {
    if (href === "/ferramentas") {
      return pathname === "/ferramentas" || pathname === "/dashboard";
    }
    return pathname.startsWith(href);
  };

  const saldoTotal = saldo?.saldo_total ?? 0;

  const navContent = (onClick?: () => void) => (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2.5 px-4 py-5 border-b border-sidebar-border">
        <div className="flex items-center justify-center size-9 rounded-lg gradient-bg shadow-sm">
          <SparklesIcon className="size-4 text-white" />
        </div>
        <div className="flex flex-col">
          <span className="font-heading text-sm font-semibold text-sidebar-foreground tracking-tight">SEO SaaS</span>
          <span className="text-xs font-medium text-muted-foreground">Inteligência Artificial</span>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <NavItemComponent
            key={item.href}
            item={item}
            active={isActive(item.href)}
            onClick={onClick}
          />
        ))}
      </nav>

      <div className="px-3 pb-3 space-y-2 border-t border-sidebar-border pt-3">
        <div className="rounded-lg bg-surface-light px-3 py-2.5 border border-sidebar-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Créditos</span>
            <span className={cn(
              "text-sm font-bold tabular-nums",
              saldoTotal < 20 ? "text-destructive" : "text-brand-deep"
            )}>
              {saldoTotal}
            </span>
          </div>
          <div className="mt-2 h-1.5 rounded-full bg-surface-lighter overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                saldoTotal < 20 ? "bg-destructive" : "gradient-bg"
              )}
              style={{ width: `${Math.min((saldoTotal / 100) * 100, 100)}%` }}
            />
          </div>
        </div>

        <div className="rounded-lg bg-accent/40 px-3 py-2.5 border border-sidebar-border">
          <p className="text-xs font-medium text-muted-foreground/80">Logado como</p>
          <p className="text-xs font-medium text-foreground truncate mt-0.5">
            {usuario?.nome || usuario?.email || "Usuário"}
          </p>
        </div>

        <button
          onClick={logout}
          className="flex items-center gap-3 w-full rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
        >
          <LogOutIcon className="size-4 shrink-0" />
          <span>Sair</span>
        </button>
      </div>
    </div>
  );

  return (
    <>
      <button
        onClick={() => setMobileOpen(true)}
        aria-label="Abrir menu"
        className="fixed top-4 left-4 z-50 flex items-center justify-center size-9 rounded-lg bg-surface-light border border-border lg:hidden"
      >
        <MenuIcon className="size-4" />
      </button>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-64 bg-sidebar border-r border-sidebar-border animate-slide-in-left">
            {navContent(() => setMobileOpen(false))}
          </aside>
        </div>
      )}

      <aside className="hidden lg:flex lg:flex-col lg:fixed lg:inset-y-0 lg:left-0 lg:w-64 bg-sidebar border-r border-sidebar-border">
        {navContent()}
      </aside>
    </>
  );
}

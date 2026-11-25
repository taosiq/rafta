"use client";

import clsx from "clsx";
import {
  Boxes,
  Database,
  FlaskConical,
  Grid3x3,
  LayoutDashboard,
  LineChart,
  Menu,
  MessageSquare,
  Monitor,
  Moon,
  Sun,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogoMark } from "./logo";
import { Suspense, useEffect, useState, type ReactNode } from "react";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/products", label: "Products", icon: Boxes },
  { href: "/classification", label: "ABC / XYZ", icon: Grid3x3 },
  { href: "/forecasts", label: "Forecasts", icon: LineChart },
  { href: "/simulation", label: "Policy simulation", icon: FlaskConical },
  { href: "/assistant", label: "Assistant", icon: MessageSquare },
  { href: "/data", label: "Data & jobs", icon: Database },
];

type Theme = "light" | "dark" | "system";

/** Runs in <head> before first paint so there is never a flash of the wrong theme. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("theme")||"system";var d=t==="dark"||(t==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",d);document.documentElement.dataset.theme=t}catch(e){}})()`;

function applyTheme(theme: Theme) {
  const dark =
    theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.dataset.theme = theme;
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    // Sync React state with what the inline script already applied (external store).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme((document.documentElement.dataset.theme as Theme) || "system");
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if ((localStorage.getItem("theme") ?? "system") === "system") applyTheme("system");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const choose = (t: Theme) => {
    setTheme(t);
    localStorage.setItem("theme", t);
    applyTheme(t);
  };

  const options: { value: Theme; icon: typeof Sun; label: string }[] = [
    { value: "light", icon: Sun, label: "Light theme" },
    { value: "dark", icon: Moon, label: "Dark theme" },
    { value: "system", icon: Monitor, label: "System theme" },
  ];
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-md border border-border p-0.5">
      {options.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          role="radio"
          aria-checked={theme === value}
          aria-label={label}
          title={label}
          onClick={() => choose(value)}
          className={clsx(
            "grid size-7 place-items-center rounded transition-colors",
            theme === value ? "bg-surface-2 text-fg" : "text-muted hover:text-fg",
          )}
        >
          <Icon size={14} aria-hidden />
        </button>
      ))}
    </div>
  );
}

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-2 text-fg">
      <LogoMark size={24} />
      <span className="text-[15px] font-semibold tracking-tight">Rafta</span>
    </Link>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  // The pathname is request data on dynamic routes: stream it in, prerender the plain list.
  return (
    <Suspense fallback={<NavList pathname={null} onNavigate={onNavigate} />}>
      <ActiveNavList onNavigate={onNavigate} />
    </Suspense>
  );
}

function ActiveNavList({ onNavigate }: { onNavigate?: () => void }) {
  return <NavList pathname={usePathname()} onNavigate={onNavigate} />;
}

function NavList({ pathname, onNavigate }: { pathname: string | null; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname !== null && (href === "/" ? pathname === "/" : pathname.startsWith(href));
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors",
              active ? "bg-surface-2 font-medium text-fg" : "text-fg-2 hover:bg-surface-2 hover:text-fg",
            )}
          >
            <Icon size={16} aria-hidden className={active ? "text-accent" : "text-muted"} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col justify-between border-r border-border bg-bg px-3 py-4 lg:flex">
        <div className="flex flex-col gap-6">
          <Logo />
          <NavLinks />
        </div>
        <div className="flex items-center justify-between px-2">
          <span className="text-xs text-muted">Inventory optimisation</span>
          <ThemeToggle />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-bg/90 px-4 backdrop-blur lg:hidden">
          <Logo />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <button
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              onClick={() => setOpen((o) => !o)}
              className="grid size-9 place-items-center rounded-md text-fg-2 hover:bg-surface-2"
            >
              {open ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
        {open && (
          <div className="border-b border-border bg-bg px-3 py-3 lg:hidden">
            <NavLinks onNavigate={() => setOpen(false)} />
          </div>
        )}
        <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-8 sm:px-8">{children}</main>
      </div>
    </div>
  );
}

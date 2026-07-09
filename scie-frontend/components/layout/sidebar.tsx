"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Radio,
  History,
  LineChart,
  Fingerprint,
  Users,
  Settings,
  Terminal,
  Activity,
  Moon,
  Sun
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Live Interview", href: "/live", icon: Radio },
  { name: "Interviews", href: "/interviews", icon: History },
  { name: "Analytics", href: "/analytics", icon: LineChart },
  { name: "Evidence", href: "/evidence", icon: Fingerprint },
  { name: "Participants", href: "/participants", icon: Users },
  { name: "Settings", href: "/settings", icon: Settings },
  { name: "Logs", href: "/logs", icon: Terminal },
  { name: "System Health", href: "/health", icon: Activity },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 h-screen flex flex-col hidden md:flex sticky top-0">
      <div className="p-6">
        <h2 className="text-xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent flex items-center gap-2">
          <Fingerprint className="h-6 w-6 text-primary" />
          Sherlock AI
        </h2>
      </div>

      <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors relative",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <item.icon className={cn("h-4 w-4", isActive ? "text-primary" : "text-muted-foreground")} />
              {item.name}
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-primary rounded-r-full" />
              )}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-border/40">
        <button className="flex w-full items-center gap-3 px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors rounded-md hover:bg-muted">
          <Moon className="h-4 w-4" />
          Dark Mode
        </button>
      </div>
    </aside>
  );
}

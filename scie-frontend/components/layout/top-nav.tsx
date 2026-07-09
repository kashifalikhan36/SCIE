"use client";

import { Bell, Database, Cpu, HardDrive } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

export function TopNav() {
  return (
    <header className="sticky top-0 md:top-0 top-14 z-30 flex h-14 w-full items-center justify-between border-b border-border/40 bg-background/95 px-4 md:px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">

      {/* Status indicators — hidden on mobile, visible from lg */}
      <div className="hidden lg:flex items-center gap-4 text-xs font-medium text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          <span>Backend</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Database className="h-3.5 w-3.5 text-blue-500" />
          <span>Redis: OK</span>
        </div>
        <div className="flex items-center gap-1.5">
          <HardDrive className="h-3.5 w-3.5 text-green-500" />
          <span>Mongo: OK</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Cpu className="h-3.5 w-3.5 text-purple-500" />
          <span>GPU: 32%</span>
        </div>
      </div>

      {/* Minimal status for small screens */}
      <div className="flex lg:hidden items-center gap-3 text-xs font-medium text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          <span>Online</span>
        </div>
      </div>

      {/* Right: notifications + user */}
      <div className="flex items-center gap-3">
        <button className="relative p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
          <Bell className="h-4 w-4" />
          <span className="absolute top-1 right-1 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-primary text-[7px] text-primary-foreground font-bold">
            3
          </span>
        </button>

        <div className="flex items-center gap-2.5 pl-3 border-l border-border/40">
          <div className="text-right hidden sm:block">
            <div className="text-sm font-semibold leading-tight">Admin</div>
            <div className="text-[11px] text-muted-foreground">Operations</div>
          </div>
          <Avatar className="h-8 w-8 border border-border/50">
            <AvatarImage src="https://api.dicebear.com/7.x/avataaars/svg?seed=Admin" alt="Admin" />
            <AvatarFallback className="text-xs">AD</AvatarFallback>
          </Avatar>
        </div>
      </div>
    </header>
  );
}

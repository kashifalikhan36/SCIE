import { Bell, Search, Database, Cpu, HardDrive } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

export function TopNav() {
  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-border/40 bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      
      <div className="flex items-center gap-4 flex-1">
        <div className="relative w-64 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="search"
            placeholder="Search meetings..."
            className="h-9 w-full rounded-md border border-input bg-background/50 pl-9 pr-4 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>
      </div>

      <div className="flex items-center gap-6">
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

        <div className="flex items-center gap-4 border-l border-border/40 pl-6">
          <button className="relative text-muted-foreground hover:text-foreground transition-colors">
            <Bell className="h-5 w-5" />
            <span className="absolute -top-1 -right-1 flex h-3 w-3 items-center justify-center rounded-full bg-primary text-[8px] text-primary-foreground font-bold">
              3
            </span>
          </button>
          
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-semibold">Admin</div>
              <div className="text-xs text-muted-foreground">Operations</div>
            </div>
            <Avatar className="h-9 w-9 border border-border/50">
              <AvatarImage src="https://api.dicebear.com/7.x/avataaars/svg?seed=Admin" alt="Admin" />
              <AvatarFallback>AD</AvatarFallback>
            </Avatar>
          </div>
        </div>
      </div>
    </header>
  );
}

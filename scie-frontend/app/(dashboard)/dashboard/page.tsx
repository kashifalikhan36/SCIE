"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchDashboardStats } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Activity, Server, Radio, Users, Loader2, AlertCircle } from "lucide-react";

function StatCard({
  title,
  value,
  sub,
  icon: Icon,
  accent,
  loading,
}: {
  title: string;
  value: string | number;
  sub: string;
  icon: React.ElementType;
  accent?: string;
  loading?: boolean;
}) {
  return (
    <Card className="bg-background/60 backdrop-blur border-border/40">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        ) : (
          <>
            <div className={`text-2xl font-bold ${accent ?? ""}`}>{value}</div>
            <p className="text-xs text-muted-foreground mt-1">{sub}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function DashboardOverview() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: fetchDashboardStats,
    refetchInterval: 15000, // refresh every 15s
  });

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between border-b border-border/40 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">System Overview</h1>
          <p className="text-muted-foreground text-sm">Live telemetry for all active operations</p>
        </div>
        {error && (
          <div className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4" />
            Backend unavailable
          </div>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="System Status"
          value={error ? "Degraded" : "Operational"}
          sub={error ? "Cannot reach backend" : "All intelligence engines online"}
          icon={Server}
          accent={error ? "text-red-500" : "text-green-500"}
          loading={isLoading}
        />
        <StatCard
          title="Active Interviews"
          value={stats?.active_interviews ?? 0}
          sub="Sessions with events in last 60s"
          icon={Radio}
          loading={isLoading}
        />
        <StatCard
          title="Historical Meetings"
          value={stats?.total_meetings?.toLocaleString() ?? 0}
          sub={`${stats?.total_participants ?? 0} unique participants`}
          icon={Users}
          loading={isLoading}
        />
        <StatCard
          title="Avg Fusion Confidence"
          value={stats?.avg_confidence_pct ? `${stats.avg_confidence_pct}%` : "—"}
          sub="Across all ranking snapshots"
          icon={Activity}
          loading={isLoading}
        />
      </div>
    </div>
  );
}

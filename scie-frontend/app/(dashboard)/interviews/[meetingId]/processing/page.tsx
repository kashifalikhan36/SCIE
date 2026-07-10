"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Loader2, Activity, Terminal, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export default function ProcessingPage() {
  const { meetingId } = useParams();
  const router = useRouter();
  const [status, setStatus] = useState<any>({
    status: "Initializing Processing Pipeline...",
    progress: 0,
    estimated_time_remaining: "Calculating...",
    logs: ["[INFO] Connecting to backend..."],
    stats: {}
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!meetingId) return;

    let ws: WebSocket;
    let reconnectTimer: NodeJS.Timeout;

    const connect = () => {
      // Connect to the dashboard WebSocket
      ws = new WebSocket(`ws://127.0.0.1:8000/api/v1/ws/dashboard/${meetingId}`);

      ws.onopen = () => {
        setStatus((prev: any) => ({
          ...prev,
          logs: [...prev.logs, "[SUCCESS] Connected to live telemetry."]
        }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === "progress") {
            setStatus(data.data);
            
            if (data.data.status === "Completed") {
              setTimeout(() => {
                router.push(`/interviews/${meetingId}`);
              }, 2000); // give them a moment to see 100%
            }
          } else if (data.type === "error") {
            setError(data.message);
          }
        } catch (e) {
          // ignore non-json messages (like 'pong')
        }
      };

      ws.onerror = () => {
        console.error("WebSocket error");
      };

      ws.onclose = (event) => {
        // If not completed or cleanly closed, try reconnecting
        if (event.code !== 1000 && status.status !== "Completed") {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };
    };

    connect();

    return () => {
      if (ws) ws.close();
      clearTimeout(reconnectTimer);
    };
  }, [meetingId, router]);

  return (
    <div className="max-w-5xl mx-auto py-8 px-4">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Analyzing Interview</h1>
        <p className="text-muted-foreground flex items-center gap-2">
          <Activity className="h-4 w-4 animate-pulse text-primary" />
          Sherlock AI Engine is currently processing session <span className="font-mono text-xs">{meetingId}</span>
        </p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 text-destructive border border-destructive/20 rounded-lg flex items-start gap-3">
          <AlertCircle className="h-5 w-5 mt-0.5" />
          <div>
            <h4 className="font-semibold">Processing Error</h4>
            <p className="text-sm">{error}</p>
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {/* Main Progress */}
          <Card className="bg-background/60 backdrop-blur border-primary/20 shadow-lg shadow-primary/5">
            <CardHeader className="pb-4">
              <CardTitle className="text-xl flex justify-between items-center">
                <span>Current Stage: <span className="text-primary">{status.status}</span></span>
                {status.status === "Completed" ? (
                  <CheckCircle2 className="h-6 w-6 text-green-500" />
                ) : (
                  <Loader2 className="h-6 w-6 text-primary animate-spin" />
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Overall Progress</span>
                <span className="font-bold text-lg">{Math.round(status.progress)}%</span>
              </div>
              <Progress value={status.progress} className="h-3 bg-secondary" />
              
              <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border/40">
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground flex items-center gap-1"><Clock className="h-3 w-3" /> Estimated Remaining</span>
                  <p className="text-lg font-mono">{status.estimated_time_remaining}</p>
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Speed</span>
                  <p className="text-sm">Real-time processing active</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Live Telemetry / Pipeline Visualization */}
          <Card className="bg-background/60 backdrop-blur">
            <CardHeader>
              <CardTitle className="text-lg">Pipeline Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="p-3 bg-muted/50 rounded-lg text-center">
                  <div className="text-xs text-muted-foreground mb-1">Faces Detected</div>
                  <div className="text-xl font-bold">{status.stats?.faces_detected ?? 0}</div>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg text-center">
                  <div className="text-xs text-muted-foreground mb-1">Speakers Found</div>
                  <div className="text-xl font-bold">{status.stats?.speakers_detected ?? 0}</div>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg text-center">
                  <div className="text-xs text-muted-foreground mb-1">Evidence Points</div>
                  <div className="text-xl font-bold">{status.stats?.evidence_count ?? 0}</div>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg text-center">
                  <div className="text-xs text-muted-foreground mb-1">AI Confidence</div>
                  <div className="text-xl font-bold">{status.stats?.confidence ? `${status.stats.confidence}%` : "Calculating"}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Live Logs Terminal */}
        <div className="lg:col-span-1 h-full">
          <Card className="bg-zinc-950 text-zinc-300 border-zinc-800 shadow-2xl h-full flex flex-col">
            <CardHeader className="pb-3 border-b border-zinc-800">
              <CardTitle className="text-sm font-mono flex items-center gap-2 text-zinc-100">
                <Terminal className="h-4 w-4" /> Live Engine Logs
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 p-0 relative overflow-hidden">
              <div className="absolute inset-0 p-4 overflow-y-auto font-mono text-[11px] leading-relaxed flex flex-col gap-1.5 custom-scrollbar">
                {status.logs.map((log: string, idx: number) => {
                  let colorClass = "text-zinc-300";
                  if (log.startsWith("[INFO]")) colorClass = "text-blue-400";
                  if (log.startsWith("[SUCCESS]")) colorClass = "text-green-400";
                  if (log.startsWith("[WARN]")) colorClass = "text-yellow-400";
                  if (log.startsWith("[ERROR]")) colorClass = "text-red-400";
                  return (
                    <div key={idx} className={`${colorClass} whitespace-pre-wrap`}>
                      {log}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

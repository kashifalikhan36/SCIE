"use client";

import { useEffect, useState, useRef } from "react";
import { useLiveStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Loader2, Fingerprint, Activity, Radio, Search } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

// Format elapsed seconds as MM:SS
function formatDuration(seconds: number) {
  const m = Math.floor(seconds / 60).toString().padStart(2, "0");
  const s = (seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export default function LiveDashboard() {
  const [mounted, setMounted] = useState(false);
  const [targetMeeting, setTargetMeeting] = useState("mtg_interview_live_001");
  const [connecting, setConnecting] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [confidenceHistory, setConfidenceHistory] = useState<{ time: string; confidence: number }[]>([]);
  const [lastEvidence, setLastEvidence] = useState<string | null>(null);

  const { isConnected, ranking, participants, setConnectionStatus, setMeetingId, updateLiveState, clearState } =
    useLiveStore();

  useEffect(() => {
    setMounted(true);
  }, []);

  // Elapsed timer
  useEffect(() => {
    if (!isConnected) {
      setElapsed(0);
      setStartTime(null);
      return;
    }
    if (!startTime) setStartTime(Date.now());
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - (startTime ?? Date.now())) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [isConnected, startTime]);

  // Track confidence history for the chart from live state
  useEffect(() => {
    if (!ranking?.confidence) return;
    const now = new Date();
    const label = `${now.getHours()}:${now.getMinutes().toString().padStart(2, "0")}:${now.getSeconds().toString().padStart(2, "0")}`;
    setConfidenceHistory((prev) => {
      const next = [...prev, { time: label, confidence: Math.round(ranking.confidence * 100) }];
      return next.slice(-30); // keep last 30 data points
    });

    // Extract last evidence from ranking explanation if present
    if (ranking?.explanation) {
      setLastEvidence(ranking.explanation);
    } else if (ranking?.ranked_participants?.[0]) {
      const topId = ranking.ranked_participants[0];
      const topState = participants[topId];
      if (topState?.last_evidence_type) {
        setLastEvidence(`${topState.last_evidence_type} (${(topState.last_evidence_score ?? 0).toFixed(2)})`);
      }
    }
  }, [ranking, participants]);

  // WebSocket connection
  useEffect(() => {
    if (!targetMeeting) return;
    clearState();
    setConnecting(true);
    setConfidenceHistory([]);
    setLastEvidence(null);
    setElapsed(0);
    setStartTime(null);

    const ws = new WebSocket(`ws://localhost:8000/ws/dashboard/${targetMeeting}`);

    ws.onopen = () => {
      setConnectionStatus(true);
      setMeetingId(targetMeeting);
      setConnecting(false);
      setStartTime(Date.now());
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "live_state_update") {
          updateLiveState(payload.data);
        }
      } catch (err) {
        console.error("Failed to parse websocket message", err);
      }
    };

    ws.onclose = () => {
      setConnectionStatus(false);
      setConnecting(false);
    };

    ws.onerror = () => {
      setConnecting(false);
    };

    return () => ws.close();
  }, [targetMeeting, setConnectionStatus, setMeetingId, updateLiveState, clearState]);

  const topCandidateId = ranking?.ranked_participants?.[0] ?? null;
  const participantCount = Object.keys(participants).length;

  // Build evidence weights from real participant state if available
  const evidenceDomains = ["Identity", "Visual", "Voice", "Behavior", "Transcript"];
  const topState = topCandidateId ? participants[topCandidateId] : null;
  const evidenceWeights: Record<string, number> = topState?.evidence_weights ?? {};

  const chartData =
    confidenceHistory.length > 0
      ? confidenceHistory
      : [{ time: "—", confidence: 0 }];

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Live Interview</h1>
          <p className="text-muted-foreground text-sm">Monitor real-time candidate evidence fusion</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 sm:flex-none">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Meeting ID..."
              value={targetMeeting}
              onChange={(e) => setTargetMeeting(e.target.value)}
              className="h-9 w-full sm:w-56 rounded-md border border-input bg-background/50 pl-9 pr-4 text-sm focus:outline-none"
            />
          </div>
          {connecting ? (
            <Badge variant="outline" className="gap-1.5 whitespace-nowrap">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Connecting...
            </Badge>
          ) : isConnected ? (
            <Badge variant="default" className="bg-green-500 hover:bg-green-600 gap-1.5 whitespace-nowrap">
              <Radio className="h-3.5 w-3.5 animate-pulse" /> Live
            </Badge>
          ) : (
            <Badge variant="destructive" className="whitespace-nowrap">Offline</Badge>
          )}
        </div>
      </div>

      {/* Top cards */}
      <div className="grid gap-6 md:grid-cols-3">
        {/* Primary Candidate */}
        <Card className="md:col-span-2 border-primary/20 bg-gradient-to-br from-background to-primary/5 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 right-0 p-32 bg-primary/10 rounded-full blur-[100px] pointer-events-none" />
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground uppercase tracking-wider flex items-center gap-2">
              <Fingerprint className="h-4 w-4 text-primary" />
              Primary Identified Candidate
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4 sm:gap-6">
              <Avatar className="h-16 w-16 sm:h-24 sm:w-24 border-2 border-primary flex-shrink-0">
                <AvatarFallback className="text-2xl sm:text-3xl bg-primary/10 text-primary">
                  {topCandidateId ? topCandidateId.substring(0, 2).toUpperCase() : "?"}
                </AvatarFallback>
              </Avatar>
              <div>
                <h2 className="text-xl sm:text-3xl font-bold break-all">
                  {topCandidateId ? topCandidateId.replace(/_/g, " ") : "Waiting for data…"}
                </h2>
                {topCandidateId && (
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <Badge variant="outline" className="border-primary/30 text-primary bg-primary/10">
                      Rank #1
                    </Badge>
                    <span className="text-xs text-muted-foreground font-mono">{topCandidateId}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="text-left sm:text-right">
              <div className="text-sm font-medium text-muted-foreground mb-1">Confidence</div>
              <div className="text-4xl sm:text-6xl font-bold tracking-tighter bg-clip-text text-transparent bg-gradient-to-r from-primary to-blue-600">
                {ranking?.confidence != null ? `${(ranking.confidence * 100).toFixed(1)}%` : "—"}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Meeting Context — all real data */}
        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader>
            <CardTitle className="text-sm font-medium">Meeting Context</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Status</span>
              {isConnected ? (
                <Badge variant="outline" className="border-green-500/30 text-green-500">Live</Badge>
              ) : connecting ? (
                <Badge variant="outline" className="border-yellow-500/30 text-yellow-500">Connecting</Badge>
              ) : (
                <Badge variant="outline" className="border-border text-muted-foreground">Idle</Badge>
              )}
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Meeting ID</span>
              <span className="font-mono text-xs truncate max-w-[120px]" title={targetMeeting}>
                {targetMeeting || "—"}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Participants</span>
              <span className="font-medium">{participantCount > 0 ? participantCount : "—"}</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Duration</span>
              <span className="font-medium font-mono">
                {isConnected ? formatDuration(elapsed) : "—"}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Last Evidence</span>
              <span className="font-mono text-green-500 text-xs text-right max-w-[130px]">
                {lastEvidence ?? "—"}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bottom row */}
      <div className="grid gap-6 md:grid-cols-4">
        {/* Confidence Timeline — real accumulated data */}
        <Card className="md:col-span-3 bg-background/60 backdrop-blur border-border/40">
          <CardHeader>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Confidence Timeline
              {!isConnected && <span className="text-xs text-muted-foreground ml-2">(connect to see live data)</span>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[260px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                  <XAxis dataKey="time" stroke="#888888" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis
                    stroke="#888888"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    domain={[0, 100]}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "rgba(0,0,0,0.85)", border: "none", borderRadius: "8px", color: "#fff", fontSize: 12 }}
                    formatter={(v: any) => [`${v}%`, "Confidence"]}
                  />
                  <Line
                    type="monotone"
                    dataKey="confidence"
                    stroke="#3b82f6"
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{ r: 5 }}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Evidence Weights — real data or graceful empty state */}
        <Card className="bg-background/60 backdrop-blur border-border/40 flex flex-col">
          <CardHeader>
            <CardTitle className="text-sm font-medium">Evidence Weights</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 space-y-3">
            <AnimatePresence>
              {mounted && topCandidateId ? (
                evidenceDomains.map((domain, i) => {
                  const key = domain.toLowerCase();
                  const weight = evidenceWeights[key] != null ? Math.round(evidenceWeights[key] * 100) : null;
                  return (
                    <motion.div
                      key={domain}
                      initial={{ opacity: 0, x: 16 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                      className="space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-xs font-medium">
                        <span>{domain}</span>
                        <span className="text-muted-foreground">
                          {weight != null ? `${weight}%` : "no data"}
                        </span>
                      </div>
                      <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary transition-all duration-700"
                          style={{ width: weight != null ? `${weight}%` : "0%" }}
                        />
                      </div>
                    </motion.div>
                  );
                })
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center py-6">
                  <Fingerprint className="h-8 w-8 text-muted-foreground/30 mb-2" />
                  <p className="text-xs text-muted-foreground">
                    {isConnected ? "Waiting for evidence…" : "Connect to see weights"}
                  </p>
                </div>
              )}
            </AnimatePresence>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

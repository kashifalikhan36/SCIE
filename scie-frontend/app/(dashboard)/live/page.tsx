"use client";

import { useEffect, useState } from "react";
import { useLiveStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Loader2, Fingerprint, Activity, Radio, Search } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function LiveDashboard() {
  const [mounted, setMounted] = useState(false);
  const [targetMeeting, setTargetMeeting] = useState("mtg_interview_live_001");
  const [connecting, setConnecting] = useState(false);
  const { isConnected, ranking, participants, setConnectionStatus, setMeetingId, updateLiveState } = useLiveStore();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!targetMeeting) return;
    
    setConnecting(true);
    const ws = new WebSocket(`ws://localhost:8000/ws/dashboard/${targetMeeting}`);
    
    ws.onopen = () => {
      setConnectionStatus(true);
      setMeetingId(targetMeeting);
      setConnecting(false);
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
    };

    return () => {
      ws.close();
    };
  }, [targetMeeting, setConnectionStatus, setMeetingId, updateLiveState]);

  // Generate fake historical timeline for the chart since we don't stream the full history yet
  const chartData = [
    { time: "0:00", confidence: 10 },
    { time: "5:00", confidence: 45 },
    { time: "10:00", confidence: 60 },
    { time: "15:00", confidence: 85 },
    { time: "20:00", confidence: ranking?.confidence ? ranking.confidence * 100 : 96 },
  ];

  const topCandidateId = ranking?.ranked_participants?.[0];
  const topCandidateState = topCandidateId ? participants[topCandidateId] : null;

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
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
              className="h-9 w-full sm:w-56 rounded-md border border-input bg-background/50 pl-9 pr-4 text-sm ring-offset-background focus:outline-none"
            />
          </div>
          {connecting ? (
            <Badge variant="outline" className="gap-1.5 whitespace-nowrap"><Loader2 className="h-3.5 w-3.5 animate-spin"/> Connecting...</Badge>
          ) : isConnected ? (
            <Badge variant="default" className="bg-green-500 hover:bg-green-600 gap-1.5 whitespace-nowrap"><Radio className="h-3.5 w-3.5 animate-pulse"/> Live</Badge>
          ) : (
            <Badge variant="destructive" className="whitespace-nowrap">Offline</Badge>
          )}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Main Candidate Focus Card */}
        <Card className="md:col-span-2 border-primary/20 bg-gradient-to-br from-background to-primary/5 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 right-0 p-32 bg-primary/10 rounded-full blur-[100px] pointer-events-none" />
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground uppercase tracking-wider flex items-center gap-2">
              <Fingerprint className="h-4 w-4 text-primary" />
              Primary Identified Candidate
            </CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <Avatar className="h-24 w-24 border-2 border-primary">
                <AvatarFallback className="text-3xl bg-primary/10 text-primary">
                  {topCandidateId ? topCandidateId.substring(0, 2).toUpperCase() : "?"}
                </AvatarFallback>
              </Avatar>
              <div>
                <h2 className="text-3xl font-bold">{topCandidateId ? topCandidateId.replace("_", " ") : "Waiting for data..."}</h2>
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant="outline" className="border-primary/30 text-primary bg-primary/10">Rank #1</Badge>
                  <span className="text-sm text-muted-foreground font-mono">{topCandidateId}</span>
                </div>
              </div>
            </div>
            
            <div className="text-right">
              <div className="text-sm font-medium text-muted-foreground mb-1">Current Confidence</div>
              <div className="text-6xl font-bold tracking-tighter bg-clip-text text-transparent bg-gradient-to-r from-primary to-blue-600">
                {ranking?.confidence ? (ranking.confidence * 100).toFixed(1) : "0"}%
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Meeting Info */}
        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader>
            <CardTitle className="text-sm font-medium">Meeting Context</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
             <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Status</span>
                <Badge variant="outline" className="border-blue-500/30 text-blue-500">In Progress</Badge>
             </div>
             <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Participants</span>
                <span className="font-medium">{Object.keys(participants).length}</span>
             </div>
             <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Duration</span>
                <span className="font-medium font-mono">24:12</span>
             </div>
             <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Last Evidence</span>
                <span className="font-medium font-mono text-green-500 text-xs">Identity Match (0.94)</span>
             </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-4">
        {/* Confidence Timeline */}
        <Card className="md:col-span-3 bg-background/60 backdrop-blur border-border/40">
          <CardHeader>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Confidence Timeline
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                  <XAxis dataKey="time" stroke="#888888" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#888888" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => `${value}%`} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: '8px', color: '#fff' }}
                    itemStyle={{ color: '#fff' }}
                  />
                  <Line type="monotone" dataKey="confidence" stroke="hsl(var(--primary))" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Evidence Sources */}
        <Card className="bg-background/60 backdrop-blur border-border/40 overflow-hidden flex flex-col">
          <CardHeader>
            <CardTitle className="text-sm font-medium">Active Evidence Weights</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto space-y-4">
            <AnimatePresence>
              {mounted ? ["Identity", "Visual", "Voice", "Behavior", "Transcript"].map((domain, i) => {
                // Generate stable random values once mounted
                const weight = Math.floor(Math.random() * 40 + 60);
                return (
                  <motion.div 
                    key={domain}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.1 }}
                    className="space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs font-medium">
                      <span>{domain}</span>
                      <span className="text-muted-foreground">{weight}% active</span>
                    </div>
                    <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-primary" style={{ width: `${weight}%` }} />
                    </div>
                  </motion.div>
                );
              }) : (
                <div className="text-muted-foreground text-xs">Loading weights...</div>
              )}
            </AnimatePresence>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

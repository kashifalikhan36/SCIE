"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchMeetingAnalytics } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, ArrowLeft, BarChart3, Activity } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

export default function AnalyticsPage() {
  const { meetingId } = useParams();
  const id = meetingId as string;

  const { data: analytics, isLoading } = useQuery({
    queryKey: ["meeting", id, "analytics"],
    queryFn: () => fetchMeetingAnalytics(id),
  });

  if (isLoading) {
    return <div className="p-20 text-center"><Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" /></div>;
  }

  const explanations = analytics?.explanations || [];
  
  // Fake chart data to demonstrate the production UI since the current explanations collection is text based
  const latencyData = [
    { engine: "Identity", latency: 12 },
    { engine: "Visual", latency: 45 },
    { engine: "Voice", latency: 28 },
    { engine: "Behavior", latency: 34 },
    { engine: "Transcript", latency: 18 },
    { engine: "Fusion", latency: 8 },
  ];

  const evidenceData = [
    { domain: "Identity", count: Math.floor(Math.random() * 10) + 2 },
    { domain: "Visual", count: Math.floor(Math.random() * 150) + 50 },
    { domain: "Voice", count: Math.floor(Math.random() * 100) + 30 },
    { domain: "Behavior", count: Math.floor(Math.random() * 80) + 20 },
    { domain: "Transcript", count: Math.floor(Math.random() * 40) + 10 },
  ];

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-4 border-b border-border/40 pb-4">
        <Link href={`/interviews/${id}`} className="p-2 hover:bg-muted rounded-full transition-colors">
          <ArrowLeft className="h-5 w-5 text-muted-foreground" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-blue-500" />
            Performance & Analytics
          </h1>
          <p className="text-muted-foreground font-mono text-sm">{id}</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Engine Processing Latency (ms)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={latencyData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#333" />
                  <XAxis type="number" stroke="#888" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis dataKey="engine" type="category" stroke="#888" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: '8px', color: '#fff' }} />
                  <Bar dataKey="latency" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Evidence Density by Domain
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={evidenceData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#333" />
                  <XAxis dataKey="domain" stroke="#888" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#888" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: '8px', color: '#fff' }} />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} barSize={40} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="bg-background/60 backdrop-blur border-border/40">
        <CardHeader>
          <CardTitle className="text-sm font-medium">GPT Confidence Explanations</CardTitle>
        </CardHeader>
        <CardContent>
           <div className="space-y-4">
              {explanations.length > 0 ? explanations.map((ex: any, idx: number) => (
                <div key={idx} className="p-4 rounded-lg bg-muted/30 border border-border/50 text-sm">
                  <div className="font-semibold mb-2 text-primary">{ex.title || "Confidence Assessment"}</div>
                  <div className="text-muted-foreground whitespace-pre-wrap">{ex.text || JSON.stringify(ex)}</div>
                </div>
              )) : (
                <div className="text-muted-foreground text-sm text-center py-8 border border-dashed rounded-md">
                  No GPT Explanations generated for this meeting.
                </div>
              )}
           </div>
        </CardContent>
      </Card>
    </div>
  );
}

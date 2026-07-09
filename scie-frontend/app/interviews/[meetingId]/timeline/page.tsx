"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchMeetingTimeline } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, ArrowLeft, PlayCircle, Clock } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { format } from "date-fns";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function TimelinePage() {
  const { meetingId } = useParams();
  const id = meetingId as string;

  const { data: timelineData, isLoading } = useQuery({
    queryKey: ["meeting", id, "timeline"],
    queryFn: () => fetchMeetingTimeline(id),
  });

  if (isLoading) {
    return <div className="p-20 text-center"><Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" /></div>;
  }

  const events = timelineData?.events || [];
  const confidenceHistory = timelineData?.confidence_history || [];

  // Format history for Recharts
  const chartData = confidenceHistory.map((item: any) => ({
    time: format(new Date(item.timestamp), "HH:mm:ss"),
    confidence: item.confidence * 100,
    participant: item.participant_id,
  }));

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-4 border-b border-border/40 pb-4">
        <Link href={`/interviews/${id}`} className="p-2 hover:bg-muted rounded-full transition-colors">
          <ArrowLeft className="h-5 w-5 text-muted-foreground" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <PlayCircle className="h-6 w-6 text-primary" />
            Replay Mode & Timeline
          </h1>
          <p className="text-muted-foreground font-mono text-sm">{id}</p>
        </div>
      </div>

      <Card className="bg-background/60 backdrop-blur border-border/40">
        <CardHeader>
          <CardTitle className="text-sm font-medium">Confidence Replay Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] w-full">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                  <XAxis dataKey="time" stroke="#888888" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#888888" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: '8px', color: '#fff' }}
                  />
                  <Line type="stepAfter" dataKey="confidence" stroke="hsl(var(--primary))" strokeWidth={3} dot={false} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-muted-foreground border border-dashed rounded-md">
                No confidence history data available.
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="bg-background/60 backdrop-blur border-border/40">
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center gap-2">
             <Clock className="h-4 w-4" />
             Fusion Audit Log
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {events.length > 0 ? events.map((ev: any, idx: number) => (
              <div key={idx} className="flex gap-4 p-4 rounded-lg border border-border/40 bg-background/50 hover:bg-muted/50 transition-colors">
                 <div className="text-xs text-muted-foreground font-mono w-24 pt-1 flex-shrink-0">
                    {format(new Date(ev.timestamp), "HH:mm:ss.SSS")}
                 </div>
                 <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" className="uppercase text-[10px]">{ev.source_type}</Badge>
                      <span className="font-medium text-sm">{ev.participant_id.replace("_", " ")}</span>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Processed evidence <span className="font-mono text-xs bg-muted px-1 py-0.5 rounded">{ev.incoming_evidence_id}</span> with incoming score: <strong className="text-foreground">{ev.incoming_score}</strong>. 
                      Resulting Confidence: <strong className="text-primary">{ev.result_confidence ? (ev.result_confidence * 100).toFixed(1) + "%" : "N/A"}</strong>
                    </div>
                 </div>
              </div>
            )) : (
               <div className="text-muted-foreground text-sm text-center py-10">No fusion events recorded.</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

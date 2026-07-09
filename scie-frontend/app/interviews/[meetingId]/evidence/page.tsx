"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchMeetingTimeline } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, ArrowLeft, BrainCircuit } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";

export default function EvidencePage() {
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

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-4 border-b border-border/40 pb-4">
        <Link href={`/interviews/${id}`} className="p-2 hover:bg-muted rounded-full transition-colors">
          <ArrowLeft className="h-5 w-5 text-muted-foreground" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <BrainCircuit className="h-6 w-6 text-purple-500" />
            Evidence Inspector
          </h1>
          <p className="text-muted-foreground font-mono text-sm">{id}</p>
        </div>
      </div>

      <div className="space-y-6">
         {events.length > 0 ? events.map((ev: any, idx: number) => (
           <Card key={idx} className="bg-background/60 backdrop-blur border-border/40">
             <CardHeader className="py-3 px-4 border-b border-border/40 bg-muted/20">
               <div className="flex items-center justify-between">
                 <div className="flex items-center gap-3">
                   <Badge variant="default" className="bg-primary/20 text-primary hover:bg-primary/30 uppercase text-[10px]">
                     {ev.source_type} Engine
                   </Badge>
                   <span className="font-mono text-xs text-muted-foreground">{ev.event_id}</span>
                 </div>
                 <div className="text-xs text-muted-foreground">
                   Processed at: {new Date(ev.timestamp).toISOString()}
                 </div>
               </div>
             </CardHeader>
             <CardContent className="p-0">
                <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border/40">
                   <div className="p-4 space-y-4">
                     <div>
                       <div className="text-xs font-medium text-muted-foreground mb-1 uppercase tracking-wider">Incoming Signal</div>
                       <div className="flex items-center gap-4">
                          <div className="text-sm">
                            <span className="text-muted-foreground">Evidence ID: </span>
                            <span className="font-mono bg-muted/50 px-1 py-0.5 rounded">{ev.incoming_evidence_id}</span>
                          </div>
                          <div className="text-sm">
                            <span className="text-muted-foreground">Candidate: </span>
                            <span className="font-medium">{ev.participant_id}</span>
                          </div>
                       </div>
                     </div>
                     <div className="grid grid-cols-2 gap-4 bg-muted/10 p-3 rounded-md border border-border/20">
                        <div>
                          <div className="text-xs text-muted-foreground">Engine Score</div>
                          <div className="font-bold text-lg">{ev.incoming_score}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">Engine Reliability</div>
                          <div className="font-bold text-lg">{ev.incoming_reliability}</div>
                        </div>
                     </div>
                   </div>
                   
                   <div className="p-4 space-y-4">
                     <div>
                       <div className="text-xs font-medium text-muted-foreground mb-1 uppercase tracking-wider">Fusion Result</div>
                       <div className="text-sm">
                         <span className="text-muted-foreground">Status: </span>
                         <Badge variant="outline" className={ev.status === "SUCCESS" ? "text-green-500 border-green-500/30 bg-green-500/10" : "text-destructive"}>
                           {ev.status}
                         </Badge>
                       </div>
                     </div>
                     <div className="grid grid-cols-2 gap-4 bg-primary/5 p-3 rounded-md border border-primary/20">
                        <div>
                          <div className="text-xs text-muted-foreground">State Confidence</div>
                          <div className="font-bold text-lg text-primary">{ev.result_confidence ? (ev.result_confidence * 100).toFixed(1) + "%" : "N/A"}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">Aggregated Score</div>
                          <div className="font-bold text-lg text-primary">{ev.result_score ? ev.result_score.toFixed(3) : "N/A"}</div>
                        </div>
                     </div>
                   </div>
                </div>
             </CardContent>
           </Card>
         )) : (
            <div className="text-center py-20 text-muted-foreground border border-dashed rounded-lg">
               No evidence blobs recorded for this meeting.
            </div>
         )}
      </div>
    </div>
  );
}

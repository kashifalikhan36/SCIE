"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchMeetingSummary, fetchMeetingParticipants } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, ArrowLeft, Play, LayoutDashboard, BrainCircuit, Activity } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export default function MeetingSummaryPage() {
  const { meetingId } = useParams();
  const id = meetingId as string;

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => fetchMeetingSummary(id),
    refetchInterval: 5000,
  });

  const { data: participants, isLoading: loadingParticipants } = useQuery({
    queryKey: ["meeting", id, "participants"],
    queryFn: () => fetchMeetingParticipants(id),
    refetchInterval: 5000,
  });

  if (loadingSummary) {
    return <div className="p-20 text-center"><Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" /></div>;
  }

  if (!summary) {
    return <div className="p-20 text-center text-destructive">Failed to load meeting summary.</div>;
  }

  const { meeting, latest_ranking, latest_explanation } = summary;
  const topCandidate = latest_ranking?.ranked_participants?.[0] || latest_ranking?.ranking?.[0]?.participant_id;

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-4 border-b border-border/40 pb-4">
        <Link href="/interviews" className="p-2 hover:bg-muted rounded-full transition-colors">
          <ArrowLeft className="h-5 w-5 text-muted-foreground" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Meeting Overview</h1>
          <p className="text-muted-foreground font-mono text-sm">{id}</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-4">
        <div className="md:col-span-1 flex flex-col gap-4">
          <Link href={`/interviews/${id}/timeline`}>
            <Card className="hover:border-primary/50 transition-colors bg-primary/5 cursor-pointer">
              <CardContent className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-2 font-medium">
                  <Play className="h-4 w-4 text-primary" />
                  Replay Mode
                </div>
              </CardContent>
            </Card>
          </Link>
          <Link href={`/interviews/${id}/analytics`}>
            <Card className="hover:border-primary/50 transition-colors bg-background/60 cursor-pointer">
              <CardContent className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-2 font-medium">
                  <Activity className="h-4 w-4 text-blue-500" />
                  Analytics
                </div>
              </CardContent>
            </Card>
          </Link>
          <Link href={`/interviews/${id}/evidence`}>
            <Card className="hover:border-primary/50 transition-colors bg-background/60 cursor-pointer">
              <CardContent className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-2 font-medium">
                  <BrainCircuit className="h-4 w-4 text-purple-500" />
                  Evidence Inspector
                </div>
              </CardContent>
            </Card>
          </Link>
        </div>

        <div className="md:col-span-3 space-y-6">
          <Card className="bg-background/60 backdrop-blur border-border/40 overflow-hidden relative">
             <div className="absolute top-0 right-0 p-32 bg-primary/5 rounded-full blur-[100px] pointer-events-none" />
             <CardHeader>
               <CardTitle>Final Identification Result</CardTitle>
             </CardHeader>
             <CardContent className="flex flex-col gap-6">
                <div className="flex items-center gap-6">
                  <Avatar className="h-20 w-20 border-2 border-primary">
                    <AvatarFallback className="text-2xl bg-primary/10 text-primary">
                      {topCandidate ? topCandidate.substring(0, 2).toUpperCase() : "?"}
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <h2 className="text-3xl font-bold">{topCandidate ? topCandidate.replace("_", " ") : "Undetermined"}</h2>
                    <div className="flex items-center gap-2 mt-2">
                      <Badge variant="outline" className="border-primary/30 text-primary bg-primary/10">Rank #1</Badge>
                      <span className="text-sm text-muted-foreground font-mono">{topCandidate}</span>
                    </div>
                  </div>
                  <div className="ml-auto text-right">
                    <div className="text-sm font-medium text-muted-foreground mb-1">Final Confidence</div>
                    <div className="text-5xl font-bold tracking-tighter text-primary">
                      {latest_ranking?.confidence ? (latest_ranking.confidence * 100).toFixed(1) : "0"}%
                    </div>
                  </div>
                </div>

                {latest_explanation && (
                  <div className="mt-4 pt-6 border-t border-border/40 grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <h3 className="text-sm font-semibold text-green-500 mb-3 flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-green-500" /> Key Strengths
                      </h3>
                      <ul className="space-y-2">
                        {latest_explanation.key_strengths?.length > 0 ? latest_explanation.key_strengths.map((str: string, i: number) => (
                          <li key={i} className="text-sm text-muted-foreground bg-green-500/10 px-3 py-2 rounded-md border border-green-500/20">
                            {str}
                          </li>
                        )) : <li className="text-sm text-muted-foreground">No strengths identified yet.</li>}
                      </ul>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-amber-500 mb-3 flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-amber-500" /> Missing / Ambiguous Information
                      </h3>
                      <ul className="space-y-2">
                        {latest_explanation.key_gaps?.length > 0 ? latest_explanation.key_gaps.map((gap: string, i: number) => (
                          <li key={i} className="text-sm text-muted-foreground bg-amber-500/10 px-3 py-2 rounded-md border border-amber-500/20">
                            {gap}
                          </li>
                        )) : <li className="text-sm text-muted-foreground">No gaps identified.</li>}
                      </ul>
                    </div>
                  </div>
                )}
             </CardContent>
          </Card>

          <Card className="bg-background/60 backdrop-blur border-border/40">
            <CardHeader>
              <CardTitle>Participants</CardTitle>
            </CardHeader>
            <CardContent>
               {loadingParticipants ? (
                 <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
               ) : participants && participants.length > 0 ? (
                 <div className="grid gap-4 md:grid-cols-2">
                   {participants.map((p: any) => (
                     <div key={p.participant_id} className="p-4 rounded-lg border border-border/40 bg-background/50 flex items-center justify-between">
                       <div className="flex items-center gap-3">
                         <Avatar>
                           <AvatarFallback>{p.participant_id.substring(0, 2).toUpperCase()}</AvatarFallback>
                         </Avatar>
                         <span className="font-medium">{p.participant_id.replace("_", " ")}</span>
                       </div>
                       {p.participant_id === topCandidate && (
                         <Badge>Primary</Badge>
                       )}
                     </div>
                   ))}
                 </div>
               ) : (
                 <div className="text-muted-foreground text-sm">No participant data found.</div>
               )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

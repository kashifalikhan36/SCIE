"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchMeetings, deleteMeeting } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { format } from "date-fns";
import { Loader2, Search, ArrowRight, History, Trash2 } from "lucide-react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Upload } from "lucide-react";

export default function InterviewsPage() {
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: meetings, isLoading, error } = useQuery({
    queryKey: ["meetings"],
    queryFn: fetchMeetings,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteMeeting,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
    },
  });

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Interview History</h1>
          <p className="text-muted-foreground text-sm">Historical records of all Sherlock AI candidate evaluations</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              type="search"
              placeholder="Search candidates or IDs..."
              className="h-9 w-full sm:w-64 rounded-md border border-input bg-background/50 pl-9 pr-4 text-sm ring-offset-background focus:outline-none"
            />
          </div>
          <Link href="/interviews/upload">
            <Button className="gap-2">
              <Upload className="h-4 w-4" />
              Upload Video
            </Button>
          </Link>
        </div>
      </div>

      {isLoading && (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin mb-4" />
          <p>Loading historical records...</p>
        </div>
      )}

      {error && (
        <div className="p-4 border border-destructive bg-destructive/10 rounded-md text-destructive">
          Failed to load meetings. Ensure the backend REST API is running.
        </div>
      )}

      {meetings && meetings.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground border border-dashed rounded-lg">
          <History className="h-12 w-12 mb-4 opacity-20" />
          <p>No historical meetings found.</p>
        </div>
      )}

      {meetings && meetings.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {meetings.map((meeting: any, index: number) => (
            <motion.div
              key={meeting.meeting_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <Link href={`/interviews/${meeting.meeting_id}`}>
                <Card className="group hover:border-primary/50 transition-colors bg-background/60 backdrop-blur cursor-pointer overflow-hidden">
                  <div className="h-1 w-full bg-secondary">
                    <div className="h-full bg-primary" style={{ width: '100%' }} />
                  </div>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg flex justify-between items-start">
                      <span className="font-mono text-sm">{meeting.meeting_id}</span>
                      <div className="flex items-center gap-2">
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-all"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            if (confirm('Are you sure you want to delete this meeting?')) {
                              deleteMutation.mutate(meeting.meeting_id);
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                        <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                      </div>
                    </CardTitle>
                    <div className="text-xs text-muted-foreground">
                      {meeting.created_at ? format(new Date(meeting.created_at), "MMM d, yyyy 'at' h:mm a") : "Unknown Date"}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-2">
                      <Badge variant="outline" className="bg-primary/5">Completed</Badge>
                      {meeting.extra_data?.candidate && (
                        <Badge variant="secondary">{meeting.extra_data.candidate}</Badge>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

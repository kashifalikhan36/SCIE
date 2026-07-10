"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Upload, FileVideo, Plus, Trash2, ArrowRight, Loader2, Sparkles } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function UploadInterviewPage() {
  const router = useRouter();
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // External Metadata
  const [candidateName, setCandidateName] = useState("");
  const [candidateEmail, setCandidateEmail] = useState("");
  const [calendarInvite, setCalendarInvite] = useState("");
  const [interviewSchedule, setInterviewSchedule] = useState("");
  const [interviewerNames, setInterviewerNames] = useState("");

  // Participants
  const [participants, setParticipants] = useState<any[]>([]);

  // Transcript (optional text)
  const [transcriptText, setTranscriptText] = useState("");

  const addParticipant = () => {
    setParticipants([...participants, {
      id: crypto.randomUUID(),
      participantId: "",
      displayName: "",
      joinEvent: "",
      leaveEvent: "",
      webcamOnOff: "",
      screenShareEvents: "",
      separateAudioStream: null,
      speakingActivity: "",
      speakingDuration: "",
      separateWebcamStream: null,
    }]);
  };

  const updateParticipant = (index: number, field: string, value: any) => {
    const updated = [...participants];
    updated[index] = { ...updated[index], [field]: value };
    setParticipants(updated);
  };

  const removeParticipant = (index: number) => {
    const updated = [...participants];
    updated.splice(index, 1);
    setParticipants(updated);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!videoFile) {
      setError("Main Interview Video is required.");
      return;
    }
    setError(null);
    setIsSubmitting(true);

    const formData = new FormData();
    formData.append("video", videoFile);

    const metadata = {
      candidate: candidateName,
      candidate_email: candidateEmail,
      calendar_invite: calendarInvite,
      interview_schedule: interviewSchedule,
      interviewers: interviewerNames.split(",").map(n => n.trim()).filter(Boolean),
    };
    formData.append("metadata", JSON.stringify(metadata));

    formData.append("participants", JSON.stringify(participants.map(p => ({
      participant_id: p.participantId,
      display_name: p.displayName,
      extra_data: {
        join_event: p.joinEvent,
        leave_event: p.leaveEvent,
        webcam: p.webcamOnOff,
        screen_share: p.screenShareEvents,
        speaking_activity: p.speakingActivity,
        speaking_duration: p.speakingDuration,
      }
    }))));

    try {
      const res = await fetch("http://127.0.0.1:8000/api/v1/interviews/upload", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      
      if (data.meeting_id) {
        router.push(`/interviews/${data.meeting_id}/processing`);
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to start processing.");
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto py-8 px-4">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Upload Interview</h1>
        <p className="text-muted-foreground">Submit a pre-recorded interview video and associated metadata for comprehensive AI analysis.</p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 text-destructive border border-destructive/20 rounded-lg">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Main Video Upload */}
        <Card className="bg-background/60 backdrop-blur border-primary/20 shadow-lg shadow-primary/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl">
              <FileVideo className="h-5 w-5 text-primary" />
              Main Interview Video <span className="text-destructive">*</span>
            </CardTitle>
            <CardDescription>Primary video recording of the interview session.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="border-2 border-dashed border-border rounded-xl p-10 flex flex-col items-center justify-center text-center hover:bg-muted/50 transition-colors relative">
              <input
                type="file"
                required
                accept="video/mp4,video/webm,video/x-matroska,video/quicktime,video/avi"
                onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                <Upload className="h-8 w-8 text-primary" />
              </div>
              <h3 className="text-lg font-medium mb-1">
                {videoFile ? videoFile.name : "Drag & drop video file here"}
              </h3>
              <p className="text-sm text-muted-foreground">
                {videoFile ? `${(videoFile.size / (1024 * 1024)).toFixed(2)} MB` : "Supports MP4, MOV, AVI, MKV up to 5GB"}
              </p>
            </div>
          </CardContent>
        </Card>

        <div className="grid md:grid-cols-2 gap-8">
          {/* External Metadata */}
          <Card className="bg-background/60 backdrop-blur">
            <CardHeader>
              <CardTitle>External Metadata</CardTitle>
              <CardDescription>Contextual information about the interview.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Candidate Name</label>
                <input value={candidateName} onChange={e => setCandidateName(e.target.value)} required placeholder="e.g. John Doe" className="w-full h-10 px-3 rounded-md border border-input bg-background focus:ring-2 focus:ring-primary/20 outline-none transition-all" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Candidate Email</label>
                <input value={candidateEmail} onChange={e => setCandidateEmail(e.target.value)} type="email" placeholder="e.g. john@example.com" className="w-full h-10 px-3 rounded-md border border-input bg-background focus:ring-2 focus:ring-primary/20 outline-none transition-all" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Interviewer Names</label>
                <input value={interviewerNames} onChange={e => setInterviewerNames(e.target.value)} placeholder="e.g. Alice, Bob (comma separated)" className="w-full h-10 px-3 rounded-md border border-input bg-background focus:ring-2 focus:ring-primary/20 outline-none transition-all" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Interview Schedule / Calendar</label>
                <input value={interviewSchedule} onChange={e => setInterviewSchedule(e.target.value)} placeholder="e.g. Oct 12, 2:00 PM EST" className="w-full h-10 px-3 rounded-md border border-input bg-background focus:ring-2 focus:ring-primary/20 outline-none transition-all" />
              </div>
            </CardContent>
          </Card>

          {/* Transcript */}
          <Card className="bg-background/60 backdrop-blur">
            <CardHeader>
              <CardTitle>Transcript</CardTitle>
              <CardDescription>Upload or paste speaker-attributed transcript (optional).</CardDescription>
            </CardHeader>
            <CardContent className="h-full flex flex-col gap-4">
              <textarea 
                value={transcriptText} 
                onChange={e => setTranscriptText(e.target.value)}
                placeholder="[00:00] Alice: Welcome to the interview...&#10;[00:05] Bob: Thank you!"
                className="w-full flex-1 min-h-[220px] p-3 rounded-md border border-input bg-background focus:ring-2 focus:ring-primary/20 outline-none transition-all resize-y font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Sparkles className="h-3 w-3" /> Leave empty to let the AI auto-generate the transcript.
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Participants */}
        <Card className="bg-background/60 backdrop-blur">
          <CardHeader className="flex flex-row justify-between items-center">
            <div>
              <CardTitle>Participant Information</CardTitle>
              <CardDescription>Add specific streams and metadata for each participant.</CardDescription>
            </div>
            <Button type="button" onClick={addParticipant} variant="outline" className="gap-2">
              <Plus className="h-4 w-4" /> Add Participant
            </Button>
          </CardHeader>
          <CardContent className="space-y-6">
            <AnimatePresence>
              {participants.length === 0 && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-8 text-muted-foreground border border-dashed rounded-lg">
                  No participants added yet. The system will auto-detect speakers and faces.
                </motion.div>
              )}
              {participants.map((p, index) => (
                <motion.div 
                  key={p.id}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="p-5 border border-border rounded-xl bg-card/50 relative overflow-hidden"
                >
                  <Button type="button" onClick={() => removeParticipant(index)} variant="ghost" size="icon" className="absolute top-2 right-2 text-muted-foreground hover:text-destructive">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                  <h4 className="font-semibold mb-4">Participant {index + 1}</h4>
                  <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">Participant ID</label>
                      <input value={p.participantId} onChange={e => updateParticipant(index, 'participantId', e.target.value)} className="w-full h-8 px-2 text-sm rounded border bg-background" placeholder="e.g. p_123" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">Display Name</label>
                      <input value={p.displayName} onChange={e => updateParticipant(index, 'displayName', e.target.value)} className="w-full h-8 px-2 text-sm rounded border bg-background" placeholder="e.g. John Doe" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">Join/Leave Events</label>
                      <input value={p.joinEvent} onChange={e => updateParticipant(index, 'joinEvent', e.target.value)} className="w-full h-8 px-2 text-sm rounded border bg-background" placeholder="e.g. Joined 0:00, Left 30:00" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">Webcam On/Off</label>
                      <input value={p.webcamOnOff} onChange={e => updateParticipant(index, 'webcamOnOff', e.target.value)} className="w-full h-8 px-2 text-sm rounded border bg-background" placeholder="e.g. On 0:00-30:00" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">Screen Share Events</label>
                      <input value={p.screenShareEvents} onChange={e => updateParticipant(index, 'screenShareEvents', e.target.value)} className="w-full h-8 px-2 text-sm rounded border bg-background" placeholder="e.g. Shared 5:00-10:00" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">Speaking Activity / Duration</label>
                      <input value={p.speakingActivity} onChange={e => updateParticipant(index, 'speakingActivity', e.target.value)} className="w-full h-8 px-2 text-sm rounded border bg-background" placeholder="e.g. Spoke 45%, 12 mins total" />
                    </div>
                    {/* File Inputs for Audio/Video streams */}
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">Separate Audio Stream <span className="text-[10px] bg-secondary text-secondary-foreground px-1 py-0.5 rounded">Optional</span></label>
                      <input type="file" accept="audio/*" onChange={e => updateParticipant(index, 'separateAudioStream', e.target.files?.[0])} className="w-full text-xs" />
                    </div>
                    <div className="space-y-1 md:col-span-2">
                      <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">Separate Webcam Stream <span className="text-[10px] bg-secondary text-secondary-foreground px-1 py-0.5 rounded">Optional</span></label>
                      <input type="file" accept="video/*" onChange={e => updateParticipant(index, 'separateWebcamStream', e.target.files?.[0])} className="w-full text-xs" />
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </CardContent>
        </Card>

        {/* Submit */}
        <div className="flex justify-end pt-6 border-t border-border/40">
          <Button type="submit" size="lg" disabled={isSubmitting || !videoFile} className="w-full sm:w-auto min-w-[200px] text-lg gap-2 shadow-lg shadow-primary/20">
            {isSubmitting ? <Loader2 className="h-5 w-5 animate-spin" /> : "Start Processing"}
            {!isSubmitting && <ArrowRight className="h-5 w-5" />}
          </Button>
        </div>
      </form>
    </div>
  );
}

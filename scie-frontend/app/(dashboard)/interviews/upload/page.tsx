"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Upload, FileVideo, ArrowRight, Loader2, Sparkles, ShieldCheck, Info, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function UploadInterviewPage() {
  const router = useRouter();
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only the 3 fields Sherlock genuinely needs as prior knowledge
  const [candidateName, setCandidateName] = useState("");
  const [candidateEmail, setCandidateEmail] = useState("");
  const [interviewerNames, setInterviewerNames] = useState("");

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith("video/")) {
      setVideoFile(file);
      setError(null);
    } else {
      setError("Please drop a valid video file.");
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!videoFile) { setError("Please select an interview video."); return; }
    if (!candidateName.trim()) { setError("Candidate name is required."); return; }

    setError(null);
    setIsSubmitting(true);

    const formData = new FormData();
    formData.append("video", videoFile);
    formData.append("metadata", JSON.stringify({
      candidate: candidateName.trim(),
      candidate_email: candidateEmail.trim(),
      interviewers: interviewerNames.split(",").map(n => n.trim()).filter(Boolean),
    }));
    // No participants sent — Sherlock auto-detects from the video
    formData.append("participants", JSON.stringify([]));

    try {
      const res = await fetch("http://127.0.0.1:8000/api/v1/interviews/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      if (data.meeting_id) router.push(`/interviews/${data.meeting_id}/processing`);
    } catch (err: any) {
      setError(err.message || "Failed to start processing.");
      setIsSubmitting(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  return (
    <div className="max-w-3xl mx-auto py-10 px-4">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Upload Interview</h1>
            <p className="text-sm text-muted-foreground">Sherlock will automatically identify the candidate and analyse the session.</p>
          </div>
        </div>

        {/* Auto-detection banner */}
        <div className="flex items-start gap-3 p-4 rounded-xl bg-primary/5 border border-primary/20 text-sm">
          <Sparkles className="h-4 w-4 text-primary mt-0.5 shrink-0" />
          <div>
            <span className="font-medium text-primary">AI handles the rest.</span>
            <span className="text-muted-foreground ml-1">
              Speaker identification, transcript, talking time, join/leave events, screen share activity, and webcam usage are all extracted automatically from the video.
            </span>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="mb-6 p-4 bg-destructive/10 text-destructive border border-destructive/20 rounded-xl flex items-start gap-2"
          >
            <Info className="h-4 w-4 mt-0.5 shrink-0" />
            <span className="text-sm">{error}</span>
            <button onClick={() => setError(null)} className="ml-auto"><X className="h-4 w-4" /></button>
          </motion.div>
        )}
      </AnimatePresence>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* ── Step 1: Video Drop Zone ── */}
        <div className="space-y-2">
          <label className="text-sm font-semibold flex items-center gap-1.5">
            <FileVideo className="h-4 w-4 text-primary" />
            Interview Recording <span className="text-destructive">*</span>
          </label>
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
            className={`relative border-2 border-dashed rounded-2xl transition-all duration-200 ${
              isDragging
                ? "border-primary bg-primary/10 scale-[1.01]"
                : videoFile
                ? "border-primary/40 bg-primary/5"
                : "border-border hover:border-primary/40 hover:bg-muted/30"
            }`}
          >
            <input
              type="file"
              required
              accept="video/mp4,video/webm,video/x-matroska,video/quicktime,video/avi"
              onChange={(e) => { setVideoFile(e.target.files?.[0] || null); setError(null); }}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
            />
            <div className="flex flex-col items-center justify-center py-12 px-6 text-center pointer-events-none">
              <AnimatePresence mode="wait">
                {videoFile ? (
                  <motion.div key="file" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col items-center gap-3">
                    <div className="w-14 h-14 rounded-2xl bg-primary/15 flex items-center justify-center">
                      <FileVideo className="h-7 w-7 text-primary" />
                    </div>
                    <div>
                      <p className="font-semibold text-foreground">{videoFile.name}</p>
                      <p className="text-sm text-muted-foreground mt-1">{formatSize(videoFile.size)} · Ready to analyse</p>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-primary font-medium">
                      <ShieldCheck className="h-3.5 w-3.5" /> Click to change file
                    </div>
                  </motion.div>
                ) : (
                  <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-3">
                    <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center">
                      <Upload className="h-7 w-7 text-muted-foreground" />
                    </div>
                    <div>
                      <p className="font-semibold">Drag & drop your video here</p>
                      <p className="text-sm text-muted-foreground mt-1">MP4, MOV, MKV, AVI, WebM · Up to 5 GB</p>
                    </div>
                    <span className="text-xs bg-primary/10 text-primary px-3 py-1 rounded-full font-medium">Browse files</span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

        {/* ── Step 2: Identity Anchors ── */}
        <div className="rounded-2xl border border-border bg-card/60 backdrop-blur p-6 space-y-5">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
              <ShieldCheck className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h2 className="font-semibold text-base">Candidate Identity</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Sherlock uses these as identity anchors. Even if the candidate joins with a nickname, wrong display name, or from a different device — Sherlock will still identify them.
              </p>
            </div>
          </div>

          <div className="space-y-4">
            {/* Candidate Name — required */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1">
                Candidate Name <span className="text-destructive">*</span>
              </label>
              <input
                value={candidateName}
                onChange={e => setCandidateName(e.target.value)}
                required
                placeholder="e.g. John Doe"
                className="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-primary/25 outline-none transition-all"
              />
              <p className="text-xs text-muted-foreground">The expected candidate's full name as it appears on the calendar invite or application.</p>
            </div>

            {/* Candidate Email — optional */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-2">
                Candidate Email
                <span className="text-[10px] font-normal bg-muted text-muted-foreground px-2 py-0.5 rounded-full">Optional</span>
              </label>
              <input
                value={candidateEmail}
                onChange={e => setCandidateEmail(e.target.value)}
                type="email"
                placeholder="e.g. john.doe@gmail.com"
                className="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-primary/25 outline-none transition-all"
              />
              <p className="text-xs text-muted-foreground">Enables deterministic email matching — strongest identity signal.</p>
            </div>

            {/* Interviewer Names — optional */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-2">
                Interviewer Names
                <span className="text-[10px] font-normal bg-muted text-muted-foreground px-2 py-0.5 rounded-full">Optional</span>
              </label>
              <input
                value={interviewerNames}
                onChange={e => setInterviewerNames(e.target.value)}
                placeholder="e.g. Alice Chen, Bob Smith"
                className="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-primary/25 outline-none transition-all"
              />
              <p className="text-xs text-muted-foreground">Comma-separated. Helps Sherlock exclude known interviewers when identifying the candidate.</p>
            </div>
          </div>
        </div>

        {/* ── Submit ── */}
        <Button
          type="submit"
          size="lg"
          disabled={isSubmitting || !videoFile || !candidateName.trim()}
          className="w-full h-12 text-base font-semibold gap-2 shadow-lg shadow-primary/20"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Uploading &amp; starting analysis...
            </>
          ) : (
            <>
              <Sparkles className="h-5 w-5" />
              Analyse Interview
              <ArrowRight className="h-5 w-5 ml-auto" />
            </>
          )}
        </Button>

        {!isSubmitting && videoFile && candidateName.trim() && (
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center text-xs text-muted-foreground">
            Sherlock will process the video and automatically detect all participants, transcripts, and speaking activity.
          </motion.p>
        )}
      </form>
    </div>
  );
}

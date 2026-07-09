"use client";

import { GlowyWavesHero } from "@/components/ui/glowy-waves-hero-shadcnui";
import { Button } from "@/components/ui/button";
import { Fingerprint, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background relative selection:bg-primary/30 overflow-x-hidden">

      {/* Top Navbar */}
      <header className="absolute top-0 left-0 right-0 z-50 flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-border/10 bg-background/5 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary/90 flex items-center justify-center">
            <Fingerprint className="h-4 w-4 text-white" />
          </div>
          <h2 className="text-lg sm:text-xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
            Sherlock AI
          </h2>
        </div>
        <Link href="/dashboard">
          <Button
            variant="default"
            size="sm"
            className="gap-2 bg-primary hover:bg-primary/90 rounded-full sm:px-6 shadow-[0_0_20px_rgba(59,130,246,0.3)] text-sm"
          >
            Dashboard
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </Link>
      </header>

      {/* Hero Section — full viewport height */}
      <main className="h-screen w-full relative">
        <GlowyWavesHero />
      </main>

    </div>
  );
}

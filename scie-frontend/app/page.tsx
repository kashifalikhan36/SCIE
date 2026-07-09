"use client";

import { GlowyWavesHero } from "@/components/ui/glowy-waves-hero-shadcnui";
import { Button } from "@/components/ui/button";
import { Fingerprint, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background relative selection:bg-primary/30">
      
      {/* Top Navbar */}
      <header className="absolute top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 border-b border-border/10 bg-background/5 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <Fingerprint className="h-6 w-6 text-primary" />
          <h2 className="text-xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
            Sherlock AI
          </h2>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/dashboard">
            <Button variant="default" className="gap-2 bg-primary hover:bg-primary/90 rounded-full px-6 shadow-[0_0_20px_rgba(59,130,246,0.3)]">
              Open Dashboard
              <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <main className="h-screen w-full relative">
        <GlowyWavesHero />
      </main>

    </div>
  );
}

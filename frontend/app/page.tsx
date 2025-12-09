"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Github, Zap, Loader2 } from "lucide-react";
import LiquidEther from "@/components/LiquidEther";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Navbar from "@/components/Navbar";
import FlyingPumpkin from "@/components/FlyingPumpkin";
import FlyingGhost from "@/components/FlyingGhost";

export default function Home() {
  const router = useRouter();
  const [repoUrl, setRepoUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleAnalyze = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!repoUrl.trim()) return;
    setIsLoading(true);
    router.push(`/playground?repo=${encodeURIComponent(repoUrl)}`);
  };

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background text-foreground">
      <FlyingPumpkin />
      <FlyingGhost />
      <Navbar />

      {/* Hero Section with LiquidEther */}
      <section className="relative flex-1 w-full overflow-hidden flex flex-col items-center justify-center text-center min-h-0">
        {/* Background */}
        <div className="absolute inset-0 z-0">
          <LiquidEther
            colors={['#5227FF', '#FF9FFC', '#B19EEF']}
            mouseForce={20}
            cursorSize={100}
            isViscous={false}
            viscous={30}
            iterationsViscous={32}
            iterationsPoisson={32}
            resolution={0.5}
            isBounce={false}
            autoDemo={true}
            autoSpeed={0.5}
            autoIntensity={2.2}
            takeoverDuration={0.25}
            autoResumeDelay={3000}
            autoRampDuration={0.6}
          />
        </div>

        {/* Content Overlay */}
        <div className="relative z-10 container mx-auto px-4">
          <div className="inline-flex items-center gap-2 bg-background/50 backdrop-blur-sm border border-primary/20 text-primary px-4 py-2 rounded-full text-sm mb-8 shadow-sm">
            <Zap className="w-4 h-4" />
            Immortal Code Architecture
          </div>
          <h1 className="text-5xl md:text-7xl font-bold mb-6 text-foreground drop-shadow-md">
            Grant Eternal Life<br />to Your Codebase
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-12 drop-shadow-sm">
            Transform vibe-coded corpses into undying, maintainable masterpieces.
            No code stays dead forever.
          </p>

          {/* Simple Input Panel */}
          <div className="max-w-xl mx-auto rounded-lg overflow-hidden shadow-2xl border border-neutral-700/50">
            {/* Title Bar with Traffic Lights */}
            <div className="bg-[#3a3a3c] px-4 py-3 flex items-center">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-[#ff5f57]"></div>
                <div className="w-3 h-3 rounded-full bg-[#febc2e]"></div>
                <div className="w-3 h-3 rounded-full bg-[#28c840]"></div>
              </div>
            </div>
            
            {/* Content Area */}
            <div className="bg-[#2d2d2d] px-6 py-6">
              <label className="block text-neutral-300 text-sm mb-4">
                Enter GitHub Repository URL:
              </label>
              <form onSubmit={handleAnalyze} className="flex items-center gap-3">
                <Input
                  type="text"
                  placeholder="https://github.com/username/repo"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  className="flex-1 h-10 px-3 bg-[#1e1e1e] border border-neutral-600 rounded text-neutral-300 font-mono text-sm placeholder:text-neutral-500 focus:ring-0 focus:border-neutral-500 focus-visible:ring-0 focus-visible:ring-offset-0"
                />
                <Button
                  type="submit"
                  onClick={handleAnalyze}
                  className="h-10 px-4 bg-[#3a3a3c] hover:bg-[#4a4a4c] text-neutral-200 text-sm border border-neutral-600 rounded shadow-none"
                  disabled={isLoading || !repoUrl.trim()}
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      Analyze Code
                      <Github className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              </form>
            </div>
          </div>
        </div>
      </section>





      {/* Footer - IDE Status Bar Style */}
      <footer className="bg-[#1e1e1e] border-t border-neutral-700/50 py-2 shrink-0 z-50">
        <div className="container mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="Necromancer" className="w-5 h-5 opacity-70" />
            <span className="text-neutral-500 text-xs font-mono">© 2025 Necromancer</span>
            <span className="text-neutral-600 text-xs">|</span>
            <span className="text-neutral-500 text-xs font-mono">v1.0.0</span>
          </div>
          <div className="flex items-center gap-4 text-xs font-mono">
            <Link href="/privacy" className="text-neutral-500 hover:text-neutral-300 transition-colors">
              Privacy
            </Link>
            <span className="text-neutral-600">|</span>
            <Link href="/terms" className="text-neutral-500 hover:text-neutral-300 transition-colors">
              Terms
            </Link>
            <span className="text-neutral-600">|</span>
            <Link href="https://github.com/eizorerad/n9r" className="text-neutral-500 hover:text-neutral-300 transition-colors flex items-center gap-1">
              <Github className="w-3 h-3" />
              GitHub
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

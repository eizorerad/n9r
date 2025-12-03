"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Github, Zap, ArrowRight, Search, Loader2 } from "lucide-react";
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
            AI-Powered Code Quality Platform
          </div>
          <h1 className="text-5xl md:text-7xl font-bold mb-6 text-foreground drop-shadow-md">
            AI Code Detox &<br />Auto-Healing Platform
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-12 drop-shadow-sm">
            Automatically clean up AI-generated and legacy code, keeping your software
            projects architecturally healthy and maintainable.
          </p>

          {/* Input Panel */}
          <div className="max-w-2xl mx-auto bg-background/60 backdrop-blur-md p-2 rounded-xl border border-border/50 shadow-2xl">
            <form onSubmit={handleAnalyze} className="flex flex-col sm:flex-row gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-3.5 h-5 w-5 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="https://github.com/owner/repo"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  className="pl-10 h-12 bg-background/50 border-border/50 focus:ring-primary/20 text-lg"
                />
              </div>
              <Button
                type="submit"
                size="lg"
                className="h-12 px-8 text-lg font-semibold shadow-lg shadow-primary/20"
                disabled={isLoading || !repoUrl.trim()}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    Redirecting...
                  </>
                ) : (
                  <>
                    Analyze Now
                    <ArrowRight className="ml-2 w-5 h-5" />
                  </>
                )}
              </Button>
            </form>
            <p className="text-xs text-muted-foreground mt-3 text-center">
              Try popular repos like <span className="font-mono text-primary cursor-pointer hover:underline" onClick={() => setRepoUrl("https://github.com/facebook/react")}>facebook/react</span> or <span className="font-mono text-primary cursor-pointer hover:underline" onClick={() => setRepoUrl("https://github.com/vercel/next.js")}>vercel/next.js</span>
            </p>
          </div>
        </div>
      </section>





      {/* Footer */}
      <footer className="border-t border-border/50 py-4 shrink-0 bg-background/80 backdrop-blur-md z-50">
        <div className="container mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground rounded flex items-center justify-center text-xs font-bold shadow-sm">
              n9
            </div>
            <span className="text-muted-foreground text-xs">© 2025 n9r. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-6 text-xs text-muted-foreground">
            <Link href="/privacy" className="hover:text-foreground transition-colors">
              Privacy
            </Link>
            <Link href="/terms" className="hover:text-foreground transition-colors">
              Terms
            </Link>
            <Link href="https://github.com/n9r" className="hover:text-foreground transition-colors">
              GitHub
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Loader2, Search, AlertCircle, CheckCircle, BarChart3, Shield, Code2, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import Navbar from "@/components/Navbar";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface LanguageMetrics {
  files: number;
  lines: number;
  avg_complexity: number;
  functions: number;
}

interface ScanResult {
  scan_id: string;
  repo_url: string;
  status: "pending" | "running" | "completed" | "failed";
  vci_score?: number;
  tech_debt_level?: string;
  metrics?: {
    total_files: number;
    total_lines: number;
    complexity_score: number;
    maintainability_score: number;
    duplication_score: number;
    architecture_score: number;
    avg_complexity: number;
    high_complexity_functions: number;
    by_language?: Record<string, LanguageMetrics>;
  };
  top_issues?: Array<{
    type: string;
    severity: string;
    title: string;
    description: string;
  }>;
  ai_report?: string;
  error?: string;
}

function getGrade(score: number): { grade: string; color: string; bgColor: string; borderColor: string } {
  if (score >= 90) return { grade: "A", color: "text-emerald-500", bgColor: "bg-emerald-500/10", borderColor: "border-emerald-500/20" };
  if (score >= 80) return { grade: "B", color: "text-blue-500", bgColor: "bg-blue-500/10", borderColor: "border-blue-500/20" };
  if (score >= 70) return { grade: "C", color: "text-amber-500", bgColor: "bg-amber-500/10", borderColor: "border-amber-500/20" };
  if (score >= 60) return { grade: "D", color: "text-orange-500", bgColor: "bg-orange-500/10", borderColor: "border-orange-500/20" };
  return { grade: "F", color: "text-destructive", bgColor: "bg-destructive/10", borderColor: "border-destructive/20" };
}

function getLanguageIcon(lang: string): string {
  const icons: Record<string, string> = {
    python: '🐍',
    javascript: '📜',
    typescript: '💠',
    java: '☕',
    go: '🐹',
    ruby: '💎',
    php: '🐘',
    c: '⚙️',
    cpp: '⚙️',
  };
  return icons[lang.toLowerCase()] || '📄';
}

function PlaygroundContent() {
  const searchParams = useSearchParams();
  const [repoUrl, setRepoUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [scanId, setScanId] = useState<string | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasAutoScanned, setHasAutoScanned] = useState(false);

  const handleScan = async (urlToScan?: string) => {
    const targetUrl = urlToScan || repoUrl;
    if (!targetUrl.trim()) return;

    setIsLoading(true);
    setError(null);
    setResult(null);
    setScanId(null);

    try {
      const response = await fetch(`${API_URL}/playground/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: targetUrl }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Scan failed");
      }

      const data = await response.json();
      setScanId(data.scan_id);
      setResult({
        scan_id: data.scan_id,
        repo_url: data.repo_url,
        status: "pending",
      });
    } catch (err: any) {
      setError(err.message);
      setIsLoading(false);
    }
  };

  // Handle URL query param
  useEffect(() => {
    const repoParam = searchParams.get("repo");
    if (repoParam && !hasAutoScanned) {
      setRepoUrl(repoParam);
      // Auto-trigger scan if repo param is present
      handleScan(repoParam);
      setHasAutoScanned(true);
    }
  }, [searchParams, hasAutoScanned]);

  // Poll for results
  useEffect(() => {
    if (!scanId || result?.status === "completed" || result?.status === "failed") {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/playground/scan/${scanId}`);
        const data = await response.json();
        setResult(data);

        if (data.status === "completed" || data.status === "failed") {
          setIsLoading(false);
        }
      } catch (err) {
        console.error("Poll error:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [scanId, result?.status]);

  const { grade, color, bgColor, borderColor } = result?.vci_score ? getGrade(result.vci_score) : { grade: "-", color: "text-muted-foreground", bgColor: "bg-muted", borderColor: "border-border" };

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background text-foreground">
      <Navbar />

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto pt-20">
        <main className="container max-w-5xl mx-auto px-4 py-8 md:py-12">
          <div className="text-center mb-12 space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/5 border border-primary/10 text-primary text-sm font-medium">
              <Activity className="h-4 w-4" />
              Live Code Analysis
            </div>
            <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
              Code Health Playground
            </h1>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
              Scan any public GitHub repository and get a VCI score instantly.
              No sign-up required.
            </p>
          </div>

          {/* Input Section */}
          <Card className="glass-panel border-border/50 mb-8 max-w-3xl mx-auto shadow-lg shadow-primary/5">
            <CardContent className="pt-6">
              <div className="flex flex-col md:flex-row gap-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    type="text"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/owner/repo"
                    className="pl-9 h-12 bg-background/50 border-border/50 focus:ring-primary/20"
                    onKeyDown={(e) => e.key === "Enter" && handleScan()}
                  />
                </div>
                <Button
                  onClick={() => handleScan()}
                  disabled={isLoading || !repoUrl.trim()}
                  className="h-12 px-8 bg-[#008236] hover:bg-[#008236]/90 text-white shadow-lg shadow-[#008236]/20 font-medium"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Scanning...
                    </>
                  ) : (
                    "Analyze Repository"
                  )}
                </Button>
              </div>
              {error && (
                <div className="mt-4 flex items-center gap-2 text-destructive text-sm bg-destructive/10 p-3 rounded-md border border-destructive/20">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </div>
              )}
              <p className="text-xs text-muted-foreground mt-4 text-center">
                Try popular repos like <span className="font-mono text-primary cursor-pointer hover:underline" onClick={() => { setRepoUrl("https://github.com/facebook/react"); handleScan("https://github.com/facebook/react"); }}>facebook/react</span> or <span className="font-mono text-primary cursor-pointer hover:underline" onClick={() => { setRepoUrl("https://github.com/vercel/next.js"); handleScan("https://github.com/vercel/next.js"); }}>vercel/next.js</span>
              </p>
            </CardContent>
          </Card>

          {/* Progress */}
          {result && (result.status === "pending" || result.status === "running") && (
            <Card className="glass-panel border-border/50 mb-8 max-w-3xl mx-auto">
              <CardContent className="py-12">
                <div className="flex flex-col items-center justify-center gap-4">
                  <div className="relative">
                    <div className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Activity className="h-6 w-6 text-primary animate-pulse" />
                    </div>
                  </div>
                  <div className="text-center space-y-1">
                    <h3 className="text-lg font-medium">
                      {result.status === "pending" ? "Queuing analysis..." : "Analyzing repository..."}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      This usually takes 10-30 seconds depending on repository size
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Error Result */}
          {result?.status === "failed" && (
            <Card className="bg-destructive/5 border-destructive/20 mb-8 max-w-3xl mx-auto">
              <CardContent className="py-8">
                <div className="text-center">
                  <div className="w-12 h-12 bg-destructive/10 rounded-full flex items-center justify-center mx-auto mb-4">
                    <AlertCircle className="h-6 w-6 text-destructive" />
                  </div>
                  <h3 className="text-xl font-bold text-destructive mb-2">Scan Failed</h3>
                  <p className="text-muted-foreground">{result.error || "An unexpected error occurred during analysis."}</p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Success Result */}
          {result?.status === "completed" && result.vci_score && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
              {/* VCI Score Card */}
              <Card className="glass-panel border-border/50 overflow-hidden">
                <div className={`absolute top-0 left-0 w-full h-1 ${bgColor}`} />
                <CardContent className="p-8">
                  <div className="flex flex-col md:flex-row items-center justify-between gap-8">
                    <div className="space-y-2 text-center md:text-left">
                      <h3 className="text-lg font-medium text-muted-foreground flex items-center gap-2 justify-center md:justify-start">
                        <Activity className="h-4 w-4" />
                        Vibe-Code Index
                      </h3>
                      <div className="flex items-baseline gap-2 justify-center md:justify-start">
                        <span className="text-6xl font-bold tracking-tighter">
                          {result.vci_score.toFixed(0)}
                        </span>
                        <span className="text-xl text-muted-foreground">/100</span>
                      </div>
                      <div className="flex items-center gap-2 justify-center md:justify-start">
                        <span className="text-muted-foreground">Tech Debt Level:</span>
                        <span className={cn("font-medium capitalize px-2 py-0.5 rounded text-sm", bgColor, color)}>
                          {result.tech_debt_level || "Unknown"}
                        </span>
                      </div>
                    </div>

                    <div className="h-16 w-px bg-border hidden md:block" />

                    <div className="flex flex-col items-center">
                      <div className={cn("text-8xl font-black tracking-tighter leading-none", color)}>
                        {grade}
                      </div>
                      <span className="text-sm text-muted-foreground font-medium mt-2">Overall Grade</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Metrics Grid */}
              {result.metrics && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Card className="glass-panel border-border/50 hover:border-primary/20 transition-colors">
                    <CardContent className="p-6 text-center space-y-2">
                      <div className="w-10 h-10 bg-blue-500/10 rounded-lg flex items-center justify-center mx-auto mb-2">
                        <Activity className="h-5 w-5 text-blue-500" />
                      </div>
                      <p className="text-3xl font-bold">{result.metrics.complexity_score.toFixed(0)}</p>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Complexity</p>
                    </CardContent>
                  </Card>
                  <Card className="glass-panel border-border/50 hover:border-primary/20 transition-colors">
                    <CardContent className="p-6 text-center space-y-2">
                      <div className="w-10 h-10 bg-emerald-500/10 rounded-lg flex items-center justify-center mx-auto mb-2">
                        <Shield className="h-5 w-5 text-emerald-500" />
                      </div>
                      <p className="text-3xl font-bold">{result.metrics.maintainability_score.toFixed(0)}</p>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Maintainability</p>
                    </CardContent>
                  </Card>
                  <Card className="glass-panel border-border/50 hover:border-primary/20 transition-colors">
                    <CardContent className="p-6 text-center space-y-2">
                      <div className="w-10 h-10 bg-amber-500/10 rounded-lg flex items-center justify-center mx-auto mb-2">
                        <Code2 className="h-5 w-5 text-amber-500" />
                      </div>
                      <p className="text-3xl font-bold">{result.metrics.duplication_score.toFixed(0)}</p>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Duplication</p>
                    </CardContent>
                  </Card>
                  <Card className="glass-panel border-border/50 hover:border-primary/20 transition-colors">
                    <CardContent className="p-6 text-center space-y-2">
                      <div className="w-10 h-10 bg-purple-500/10 rounded-lg flex items-center justify-center mx-auto mb-2">
                        <BarChart3 className="h-5 w-5 text-purple-500" />
                      </div>
                      <p className="text-3xl font-bold">{result.metrics.architecture_score.toFixed(0)}</p>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Architecture</p>
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Codebase Stats */}
              {result.metrics && (
                <div className="grid md:grid-cols-2 gap-6">
                  <Card className="glass-panel border-border/50">
                    <CardHeader>
                      <CardTitle className="text-base font-medium flex items-center gap-2">
                        <Code2 className="h-4 w-4 text-muted-foreground" />
                        Codebase Overview
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-6">
                        <div className="space-y-1">
                          <p className="text-2xl font-bold">{result.metrics.total_files}</p>
                          <p className="text-xs text-muted-foreground uppercase">Files</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-2xl font-bold">{result.metrics.total_lines.toLocaleString()}</p>
                          <p className="text-xs text-muted-foreground uppercase">Lines of Code</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-2xl font-bold text-amber-500">{result.metrics.avg_complexity.toFixed(1)}</p>
                          <p className="text-xs text-muted-foreground uppercase">Avg Complexity</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-2xl font-bold text-destructive">{result.metrics.high_complexity_functions}</p>
                          <p className="text-xs text-muted-foreground uppercase">Complex Functions</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  {/* By Language Breakdown */}
                  {result.metrics?.by_language && Object.keys(result.metrics.by_language).length > 0 && (
                    <Card className="glass-panel border-border/50">
                      <CardHeader>
                        <CardTitle className="text-base font-medium flex items-center gap-2">
                          <BarChart3 className="h-4 w-4 text-muted-foreground" />
                          Language Breakdown
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-4">
                          {Object.entries(result.metrics.by_language).slice(0, 3).map(([lang, data]) => (
                            <div key={lang} className="flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <span className="text-xl">{getLanguageIcon(lang)}</span>
                                <div>
                                  <p className="font-medium capitalize text-sm">{lang}</p>
                                  <p className="text-xs text-muted-foreground">{data.files} files</p>
                                </div>
                              </div>
                              <div className="text-right">
                                <p className="font-mono text-sm font-medium">{data.lines.toLocaleString()}</p>
                                <p className="text-xs text-muted-foreground">lines</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </div>
              )}

              {/* Issues */}
              {result.top_issues && result.top_issues.length > 0 && (
                <Card className="glass-panel border-border/50">
                  <CardHeader>
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-muted-foreground" />
                      Top Issues Found
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {result.top_issues.map((issue, idx) => (
                        <div key={idx} className="flex items-start gap-3 p-4 bg-muted/30 rounded-lg border border-border/50 hover:bg-muted/50 transition-colors">
                          <span className={cn("mt-0.5",
                            issue.severity === "high" ? "text-destructive" :
                              issue.severity === "medium" ? "text-amber-500" : "text-blue-500"
                          )}>
                            <AlertCircle className="h-5 w-5" />
                          </span>
                          <div>
                            <p className="font-medium text-sm">{issue.title}</p>
                            <p className="text-sm text-muted-foreground mt-1">{issue.description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* CTA */}
              <Card className="bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/20">
                <CardContent className="py-10 text-center">
                  <h3 className="text-2xl font-bold mb-3">
                    Want to fix these issues automatically?
                  </h3>
                  <p className="text-muted-foreground mb-8 max-w-lg mx-auto">
                    Sign up for n9r to get AI-powered auto-healing PRs, deep architectural analysis, and continuous monitoring.
                  </p>
                  <Link href="/login">
                    <Button className="h-12 px-8 text-lg bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/20">
                      Get Started Free
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default function PlaygroundPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>}>
      <PlaygroundContent />
    </Suspense>
  );
}

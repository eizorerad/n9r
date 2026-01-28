"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Image from "next/image";
import { Loader2, Search, AlertCircle, BarChart3, Shield, Code2, Activity, Sparkles, Network, Cpu, Binary } from "lucide-react";
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

function getGrade(score: number): { grade: string; color: string; bgColor: string } {
  if (score >= 90) return { grade: "A", color: "text-emerald-500", bgColor: "bg-emerald-500/10" };
  if (score >= 80) return { grade: "B", color: "text-blue-500", bgColor: "bg-blue-500/10" };
  if (score >= 70) return { grade: "C", color: "text-amber-500", bgColor: "bg-amber-500/10" };
  if (score >= 60) return { grade: "D", color: "text-orange-500", bgColor: "bg-orange-500/10" };
  return { grade: "F", color: "text-destructive", bgColor: "bg-destructive/10" };
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const { grade, color, bgColor } = result?.vci_score ? getGrade(result.vci_score) : { grade: "-", color: "text-muted-foreground", bgColor: "bg-muted" };

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background text-foreground">
      <Navbar />

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto pt-20">
        <main className="container max-w-5xl mx-auto px-4 py-8 md:py-12">
          <div className="text-center mb-12 space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-neutral-800 border border-neutral-700 text-neutral-300 text-sm font-mono">
              <Activity className="h-4 w-4" />
              Live Code Analysis
            </div>
            <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
              Code Analysis Playground
            </h1>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
              Scan any public GitHub repository and discover its quality score.
              No sign-up required.
            </p>
          </div>

          {/* IDE-Style Input Section */}
          <div className="mb-8 max-w-3xl mx-auto rounded-lg overflow-hidden shadow-2xl border border-neutral-700/50">
            {/* Title Bar */}
            <div className="bg-[#323233] px-4 py-2 flex items-center gap-2 border-b border-neutral-700/50">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-[#ff5f57]"></div>
                <div className="w-3 h-3 rounded-full bg-[#febc2e]"></div>
                <div className="w-3 h-3 rounded-full bg-[#28c840]"></div>
              </div>
              <div className="flex-1 text-center">
                <span className="text-neutral-400 text-xs font-mono">n9r — playground</span>
              </div>
              <div className="w-12"></div>
            </div>
            
            {/* Tab Bar */}
            <div className="bg-[#252526] flex items-center border-b border-neutral-700/30">
              <div className="px-4 py-2 bg-[#1e1e1e] border-r border-neutral-700/30 flex items-center gap-2">
                <Search className="w-3.5 h-3.5 text-neutral-400" />
                <span className="text-neutral-300 text-xs font-mono">scan.ts</span>
                <span className="text-neutral-500 text-xs ml-2">×</span>
              </div>
            </div>
            
            {/* Editor Area */}
            <div className="bg-[#1e1e1e] p-4">
              {/* Line Numbers + Code */}
              <div className="flex items-start gap-4">
                <div className="flex flex-col text-right text-neutral-600 text-sm font-mono select-none">
                  <span>1</span>
                  <span>2</span>
                  <span>3</span>
                  <span>4</span>
                </div>
                <div className="flex-1 font-mono text-sm">
                  <div className="text-neutral-500 mb-1">
                    <span className="text-[#c586c0]">import</span> <span className="text-neutral-400">{"{"}</span> <span className="text-[#9cdcfe]">analyze</span> <span className="text-neutral-400">{"}"}</span> <span className="text-[#c586c0]">from</span> <span className="text-[#ce9178]">&quot;n9r&quot;</span><span className="text-neutral-400">;</span>
                  </div>
                  <div className="text-neutral-500 mb-1">&nbsp;</div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[#569cd6]">const</span>
                    <span className="text-[#9cdcfe]">target</span>
                    <span className="text-neutral-400">=</span>
                    <span className="text-[#ce9178]">&quot;</span>
                    <Input
                      type="text"
                      value={repoUrl}
                      onChange={(e) => setRepoUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo"
                      className="flex-1 h-6 px-1 py-0 bg-transparent border-0 border-b border-neutral-600 rounded-none text-[#ce9178] font-mono text-sm placeholder:text-neutral-600 focus:ring-0 focus:border-neutral-400 focus-visible:ring-0 focus-visible:ring-offset-0"
                      onKeyDown={(e) => e.key === "Enter" && handleScan()}
                    />
                    <span className="text-[#ce9178]">&quot;</span>
                    <span className="text-neutral-400">;</span>
                  </div>
                  <div className="text-neutral-500">
                    <span className="text-[#569cd6]">await</span> <span className="text-[#dcdcaa]">analyze</span><span className="text-neutral-400">(</span><span className="text-[#9cdcfe]">target</span><span className="text-neutral-400">);</span> <span className="text-[#6a9955]">{"// Deep code analysis"}</span>
                  </div>
                </div>
              </div>
              
              {error && (
                <div className="mt-4 flex items-center gap-2 text-red-400 text-xs font-mono bg-red-500/10 p-3 rounded border border-red-500/20">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </div>
              )}
              
              {/* Action Bar */}
              <div className="mt-4 pt-4 border-t border-neutral-700/30 flex items-center justify-between">
                <div className="flex items-center gap-3 text-xs text-neutral-500 font-mono">
                  <span 
                    className="cursor-pointer hover:text-neutral-300 transition-colors" 
                    onClick={() => { setRepoUrl("https://github.com/facebook/react"); handleScan("https://github.com/facebook/react"); }}
                  >
                    facebook/react
                  </span>
                  <span className="text-neutral-600">|</span>
                  <span 
                    className="cursor-pointer hover:text-neutral-300 transition-colors" 
                    onClick={() => { setRepoUrl("https://github.com/vercel/next.js"); handleScan("https://github.com/vercel/next.js"); }}
                  >
                    vercel/next.js
                  </span>
                </div>
                <Button
                  onClick={() => handleScan()}
                  disabled={isLoading || !repoUrl.trim()}
                  size="sm"
                  className="h-8 px-4 bg-neutral-700 hover:bg-neutral-600 text-neutral-200 font-mono text-xs border border-neutral-600 shadow-none"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <span className="text-[#89d185] mr-1">▶</span>
                      Run Analysis
                    </>
                  )}
                </Button>
              </div>
            </div>
            
            {/* Status Bar */}
            <div className="bg-[#252526] px-4 py-1 flex items-center justify-between text-xs text-neutral-400 border-t border-neutral-700/30">
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1">
                  <Search className="w-3 h-3" />
                  scan
                </span>
                <span>UTF-8</span>
              </div>
              <div className="flex items-center gap-4">
                <span>TypeScript</span>
                <span>n9r v1.0</span>
              </div>
            </div>
          </div>

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

              {/* AI Methods Section */}
              {/* Combined AI & CTA Panel */}
              <Card className="glass-panel border-border/50 mb-8 overflow-hidden relative">
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-primary/5 pointer-events-none" />

                <CardHeader className="pb-2">
                  <CardTitle className="text-2xl font-bold text-center flex items-center justify-center gap-2">
                    <Cpu className="h-6 w-6 text-primary" />
                    Deep Code Analysis Engines
                  </CardTitle>
                </CardHeader>

                <CardContent className="space-y-10 relative pt-6">
                  {/* Analysis Engines Grid */}
                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="flex gap-4 p-4 rounded-lg bg-background/40 border border-border/50 hover:border-primary/20 transition-colors group">
                      <div className="mt-1 p-2 rounded-md bg-primary/5 group-hover:bg-primary/10 transition-colors">
                        <Binary className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <h4 className="font-semibold mb-1">Deductive Analysis</h4>
                        <p className="text-sm text-muted-foreground">Uses formal logic and control flow analysis to mathematically prove bug existence.</p>
                      </div>
                    </div>
                    <div className="flex gap-4 p-4 rounded-lg bg-background/40 border border-border/50 hover:border-primary/20 transition-colors group">
                      <div className="mt-1 p-2 rounded-md bg-primary/5 group-hover:bg-primary/10 transition-colors">
                        <Sparkles className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <h4 className="font-semibold mb-1">Heuristic Analysis</h4>
                        <p className="text-sm text-muted-foreground">Applies pattern recognition and best-practice models to identify potential issues.</p>
                      </div>
                    </div>
                    <div className="flex gap-4 p-4 rounded-lg bg-background/40 border border-border/50 hover:border-primary/20 transition-colors group">
                      <div className="mt-1 p-2 rounded-md bg-primary/5 group-hover:bg-primary/10 transition-colors">
                        <Network className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <h4 className="font-semibold mb-1">Holistic Analysis</h4>
                        <p className="text-sm text-muted-foreground">Analyzes the entire codebase context to find structural issues and architectural debts.</p>
                      </div>
                    </div>
                    <div className="flex gap-4 p-4 rounded-lg bg-background/40 border border-border/50 hover:border-primary/20 transition-colors group">
                      <div className="mt-1 p-2 rounded-md bg-primary/5 group-hover:bg-primary/10 transition-colors">
                        <Search className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <h4 className="font-semibold mb-1">Semantic Code Search</h4>
                        <p className="text-sm text-muted-foreground">Vector-based clustering to understand code relationships and meaning beyond syntax.</p>
                      </div>
                    </div>
                  </div>

                  {/* Divider */}
                  <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />

                  {/* CTA Section */}
                  <div className="text-center space-y-6">
                    <div className="space-y-2">
                      <h3 className="text-2xl font-bold">
                        Ready to transform your codebase?
                      </h3>
                      <p className="text-muted-foreground max-w-lg mx-auto">
                        Sign up for n9r to get AI-powered fix PRs, deep architectural analysis, and continuous code quality monitoring.
                      </p>
                    </div>
                    <Link href="/login">
                      <Button className="h-12 px-8 text-lg bg-neutral-700 hover:bg-neutral-600 text-neutral-200 font-mono border border-neutral-600 shadow-none transition-all hover:scale-105">
                        Get Started
                      </Button>
                    </Link>

                    <div className="mt-12 relative w-full max-w-4xl mx-auto rounded-xl overflow-hidden shadow-2xl border border-neutral-700/50 group">
                      <div className="absolute inset-0 bg-gradient-to-t from-background/80 to-transparent z-10 pointer-events-none" />
                      <Image
                        src="/Screenshot_3123.png"
                        alt="n9r Dashboard Preview"
                        width={1200}
                        height={800}
                        className="w-full h-auto transform group-hover:scale-[1.02] transition-transform duration-700"
                      />
                    </div>
                  </div>
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

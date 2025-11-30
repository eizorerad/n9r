"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

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

function getGrade(score: number): { grade: string; color: string } {
  if (score >= 90) return { grade: "A", color: "text-green-500" };
  if (score >= 80) return { grade: "B", color: "text-blue-500" };
  if (score >= 70) return { grade: "C", color: "text-yellow-500" };
  if (score >= 60) return { grade: "D", color: "text-orange-500" };
  return { grade: "F", color: "text-red-500" };
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

export default function PlaygroundPage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [scanId, setScanId] = useState<string | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const handleScan = async () => {
    if (!repoUrl.trim()) return;

    setIsLoading(true);
    setError(null);
    setResult(null);
    setScanId(null);

    try {
      const response = await fetch(`${API_URL}/playground/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl }),
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

  const { grade, color } = result?.vci_score ? getGrade(result.vci_score) : { grade: "-", color: "text-gray-400" };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      {/* Header */}
      <header className="border-b border-gray-700 bg-gray-900/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="text-2xl font-bold text-white">
            n9r<span className="text-blue-500">.ai</span>
          </Link>
          <Link href="/login">
            <Button variant="outline" className="text-white border-gray-600">
              Sign In
            </Button>
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 py-12">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-white mb-4">
            🧪 Code Health Playground
          </h1>
          <p className="text-xl text-gray-400">
            Scan any public GitHub repository and get a VCI score instantly
          </p>
          <p className="text-sm text-gray-500 mt-2">
            Free • No sign-up required • 5 scans per hour
          </p>
        </div>

        {/* Input Section */}
        <Card className="bg-gray-800 border-gray-700 mb-8">
          <CardContent className="pt-6">
            <div className="flex gap-4">
              <input
                type="text"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="flex-1 px-4 py-3 bg-gray-900 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                onKeyDown={(e) => e.key === "Enter" && handleScan()}
              />
              <Button
                onClick={handleScan}
                disabled={isLoading || !repoUrl.trim()}
                className="px-8 bg-blue-600 hover:bg-blue-700 text-white"
              >
                {isLoading ? "Scanning..." : "Analyze"}
              </Button>
            </div>
            {error && (
              <p className="mt-3 text-red-400 text-sm">{error}</p>
            )}
          </CardContent>
        </Card>

        {/* Progress */}
        {result && (result.status === "pending" || result.status === "running") && (
          <Card className="bg-gray-800 border-gray-700 mb-8">
            <CardContent className="py-8">
              <div className="flex items-center justify-center gap-4">
                <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-gray-300">
                  {result.status === "pending" ? "Starting scan..." : "Analyzing repository..."}
                </span>
              </div>
              <p className="text-center text-gray-500 text-sm mt-4">
                This may take 10-30 seconds depending on repository size
              </p>
            </CardContent>
          </Card>
        )}

        {/* Error Result */}
        {result?.status === "failed" && (
          <Card className="bg-red-900/20 border-red-700 mb-8">
            <CardContent className="py-6">
              <div className="text-center">
                <span className="text-4xl">❌</span>
                <h3 className="text-xl font-bold text-red-400 mt-2">Scan Failed</h3>
                <p className="text-gray-400 mt-2">{result.error}</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Success Result */}
        {result?.status === "completed" && result.vci_score && (
          <div className="space-y-6">
            {/* VCI Score Card */}
            <Card className="bg-gray-800 border-gray-700">
              <CardContent className="py-8">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg text-gray-400">Vibe-Code Index</h3>
                    <p className="text-5xl font-bold text-white mt-2">
                      {result.vci_score.toFixed(1)}
                      <span className="text-2xl text-gray-500">/100</span>
                    </p>
                    <p className="text-gray-500 mt-2 capitalize">
                      Tech Debt: {result.tech_debt_level}
                    </p>
                  </div>
                  <div className={`text-8xl font-bold ${color}`}>
                    {grade}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Metrics */}
            {result.metrics && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card className="bg-gray-800 border-gray-700">
                  <CardContent className="py-4 text-center">
                    <p className="text-2xl font-bold text-white">{result.metrics.complexity_score.toFixed(0)}</p>
                    <p className="text-sm text-gray-400">Complexity</p>
                  </CardContent>
                </Card>
                <Card className="bg-gray-800 border-gray-700">
                  <CardContent className="py-4 text-center">
                    <p className="text-2xl font-bold text-white">{result.metrics.maintainability_score.toFixed(0)}</p>
                    <p className="text-sm text-gray-400">Maintainability</p>
                  </CardContent>
                </Card>
                <Card className="bg-gray-800 border-gray-700">
                  <CardContent className="py-4 text-center">
                    <p className="text-2xl font-bold text-white">{result.metrics.duplication_score.toFixed(0)}</p>
                    <p className="text-sm text-gray-400">Duplication</p>
                  </CardContent>
                </Card>
                <Card className="bg-gray-800 border-gray-700">
                  <CardContent className="py-4 text-center">
                    <p className="text-2xl font-bold text-white">{result.metrics.architecture_score.toFixed(0)}</p>
                    <p className="text-sm text-gray-400">Architecture</p>
                  </CardContent>
                </Card>
              </div>
            )}

            {/* Codebase Stats */}
            {result.metrics && (
              <Card className="bg-gray-800 border-gray-700">
                <CardHeader>
                  <CardTitle className="text-white">Codebase Overview</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                    <div>
                      <p className="text-2xl font-bold text-blue-400">{result.metrics.total_files}</p>
                      <p className="text-sm text-gray-400">Files</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-green-400">{result.metrics.total_lines.toLocaleString()}</p>
                      <p className="text-sm text-gray-400">Lines of Code</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-yellow-400">{result.metrics.avg_complexity.toFixed(1)}</p>
                      <p className="text-sm text-gray-400">Avg Complexity</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-red-400">{result.metrics.high_complexity_functions}</p>
                      <p className="text-sm text-gray-400">Complex Functions</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* By Language Breakdown */}
            {result.metrics?.by_language && Object.keys(result.metrics.by_language).length > 0 && (
              <Card className="bg-gray-800 border-gray-700">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2">
                    📊 By Language
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {Object.entries(result.metrics.by_language).map(([lang, data]) => (
                      <div key={lang} className="flex items-center justify-between p-3 bg-gray-900 rounded-lg">
                        <div className="flex items-center gap-3">
                          <span className="text-lg">{getLanguageIcon(lang)}</span>
                          <span className="font-medium text-white capitalize">{lang}</span>
                        </div>
                        <div className="flex gap-6 text-sm">
                          <div className="text-center">
                            <p className="text-gray-400">Files</p>
                            <p className="font-bold text-white">{data.files}</p>
                          </div>
                          <div className="text-center">
                            <p className="text-gray-400">Lines</p>
                            <p className="font-bold text-white">{data.lines.toLocaleString()}</p>
                          </div>
                          <div className="text-center">
                            <p className="text-gray-400">Avg CC</p>
                            <p className="font-bold text-white">{data.avg_complexity.toFixed(1)}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Issues */}
            {result.top_issues && result.top_issues.length > 0 && (
              <Card className="bg-gray-800 border-gray-700">
                <CardHeader>
                  <CardTitle className="text-white">Top Issues Found</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {result.top_issues.map((issue, idx) => (
                      <div key={idx} className="flex items-start gap-3 p-3 bg-gray-900 rounded-lg">
                        <span className={`text-xl ${
                          issue.severity === "high" ? "text-red-500" :
                          issue.severity === "medium" ? "text-yellow-500" : "text-blue-500"
                        }`}>
                          {issue.severity === "high" ? "🔴" : issue.severity === "medium" ? "🟡" : "🔵"}
                        </span>
                        <div>
                          <p className="font-medium text-white">{issue.title}</p>
                          <p className="text-sm text-gray-400">{issue.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* CTA */}
            <Card className="bg-gradient-to-r from-blue-900 to-purple-900 border-0">
              <CardContent className="py-8 text-center">
                <h3 className="text-2xl font-bold text-white mb-2">
                  Want to fix these issues automatically?
                </h3>
                <p className="text-gray-300 mb-6">
                  Sign up for n9r to get AI-powered auto-healing PRs
                </p>
                <Link href="/login">
                  <Button className="bg-white text-gray-900 hover:bg-gray-100 px-8 py-3 text-lg">
                    Get Started Free →
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}

import { Suspense } from 'react'
import Link from 'next/link'
import { ArrowLeft, GitBranch, RefreshCw, ExternalLink, AlertCircle, Loader2, Brain } from 'lucide-react'
import { RunAnalysisButton } from '@/components/run-analysis-button'
import { SemanticAnalysisSection } from '@/components/semantic-analysis-section'
import { CommitTimeline } from '@/components/commit-timeline'
import { RepoTabs } from '@/components/repo-tabs'
import { VCISectionClient } from '@/components/vci-section-client'
import { MetricsSectionClient } from '@/components/metrics-section-client'
import { IssuesSectionClient } from '@/components/issues-section-client'
import { SelectedCommitIndicator } from '@/components/selected-commit-indicator'
import { AIInsightsPanel } from '@/components/ai-insights-panel'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { getRepository } from '@/lib/data/repositories'
import { getSession } from '@/lib/session'
import { redirect, notFound } from 'next/navigation'

const API_BASE_URL = process.env.API_URL || 'http://localhost:8000/v1'

// Fetch analyses for VCI history
async function getVCIHistory(repoId: string, token: string) {
  try {
    const response = await fetch(`${API_BASE_URL}/repositories/${repoId}/analyses?per_page=10`, {
      headers: { Authorization: `Bearer ${token}` },
      next: { revalidate: 60 },
    })

    if (!response.ok) {
      return { data_points: [], trend: 'stable' as const }
    }

    const result = await response.json()
    const analyses = result.data || []

    const data_points = analyses
      .filter((a: { vci_score: number | null }) => a.vci_score !== null)
      .map((a: { created_at: string; vci_score: number; commit_sha: string }) => ({
        date: new Date(a.created_at).toISOString().split('T')[0],
        vci_score: a.vci_score,
        grade: getGrade(a.vci_score),
        commit_sha: a.commit_sha?.slice(0, 7) || '',
      }))
      .reverse()

    // Calculate trend
    let trend: 'improving' | 'declining' | 'stable' = 'stable'
    if (data_points.length >= 2) {
      const latest = data_points[data_points.length - 1].vci_score
      const previous = data_points[data_points.length - 2].vci_score
      if (latest > previous + 2) trend = 'improving'
      else if (latest < previous - 2) trend = 'declining'
    }

    return { data_points, trend }
  } catch {
    return { data_points: [], trend: 'stable' as const }
  }
}

// Fetch issues for repository
async function getIssues(repoId: string, token: string) {
  try {
    const response = await fetch(`${API_BASE_URL}/repositories/${repoId}/issues?status=open&per_page=20`, {
      headers: { Authorization: `Bearer ${token}` },
      next: { revalidate: 60 },
    })

    if (!response.ok) {
      return { data: [] }
    }

    const result = await response.json()
    return { data: result.data || [] }
  } catch {
    return { data: [] }
  }
}

function getGrade(score: number): string {
  if (score >= 90) return 'A'
  if (score >= 80) return 'B'
  if (score >= 70) return 'C'
  if (score >= 60) return 'D'
  return 'F'
}

// Repository Header Component (left side info only)
async function RepositoryHeader({ id }: { id: string }) {
  const session = await getSession()
  const [repo, latestAnalysis] = await Promise.all([
    getRepository(id),
    session?.accessToken ? getLatestAnalysis(id, session.accessToken) : null
  ])

  if (!repo) {
    notFound()
  }

  // Fetch HEAD commit SHA for "Latest" badge comparison
  const headCommitSha = session?.accessToken
    ? await getHeadCommitSha(id, session.accessToken, repo.default_branch)
    : null

  const htmlUrl = `https://github.com/${repo.full_name}`

  // Determine status display
  let statusDisplay = (
    <span className="text-amber-500 font-medium">Not analyzed yet</span>
  )

  // Helper to format commit SHA display
  const formatCommitSha = (sha: string | null | undefined) => {
    if (!sha) return null
    return sha.slice(0, 7)
  }

  if (latestAnalysis) {
    if (latestAnalysis.status === 'failed') {
      statusDisplay = (
        <span className="text-red-500 font-medium flex items-center gap-1" title={latestAnalysis.error_message || "Analysis failed"}>
          <AlertCircle className="h-3 w-3" />
          Analysis failed
        </span>
      )
    } else if (['pending', 'running', 'queued'].includes(latestAnalysis.status)) {
      statusDisplay = (
        <span className="text-blue-500 font-medium flex items-center gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          Analysis in progress
        </span>
      )
    } else if (latestAnalysis.status === 'completed' && latestAnalysis.completed_at) {
      const shortSha = formatCommitSha(latestAnalysis.commit_sha)
      statusDisplay = (
        <span className="flex items-center gap-1.5">
          Last analyzed: {new Date(latestAnalysis.completed_at).toLocaleDateString()}
          {shortSha && (
            <code className="text-xs font-mono text-muted-foreground bg-muted/50 px-1 py-0.5 rounded">
              {shortSha}
            </code>
          )}
        </span>
      )
    }
  } else if (repo.last_analysis_at) {
    statusDisplay = (
      <span>
        Last analyzed: {new Date(repo.last_analysis_at).toLocaleDateString()}
      </span>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 sm:gap-3">
        <Link href="/dashboard" className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <h1 className="text-lg sm:text-xl font-bold tracking-tight truncate">{repo.full_name}</h1>
        <SelectedCommitIndicator headCommitSha={headCommitSha} />
        <a
          href={htmlUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <GitBranch className="h-3.5 w-3.5" />
          {repo.default_branch}
        </span>
        {repo.mode && (
          <span className="px-2 py-0.5 rounded-md bg-secondary text-secondary-foreground text-xs font-medium capitalize border border-border/50">
            {repo.mode.replace('_', ' ')}
          </span>
        )}
        {statusDisplay}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <RunAnalysisButton
          repositoryId={id}
          hasAnalysis={!!repo.last_analysis_at}
        />
        <Link href={`/dashboard/repository/${id}/ide`}>
          <Button variant="outline" size="sm" className="flex items-center gap-2 shadow-sm text-xs h-8">
            <RefreshCw className="h-3 w-3" />
            IDE
          </Button>
        </Link>
      </div>
    </div>
  )
}

// Fetch latest analysis with metrics
async function getLatestAnalysis(repoId: string, token: string) {
  try {
    const response = await fetch(`${API_BASE_URL}/repositories/${repoId}/analyses?per_page=1`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store', // Don't cache to get fresh data
    })

    if (!response.ok) {
      console.log('getLatestAnalysis failed:', response.status)
      return null
    }

    const result = await response.json()
    console.log('Latest analysis:', JSON.stringify(result.data?.[0]?.metrics || 'no metrics'))
    return result.data?.[0] || null
  } catch (error) {
    console.error('getLatestAnalysis error:', error)
    return null
  }
}

// Fetch HEAD commit SHA for the default branch
async function getHeadCommitSha(repoId: string, token: string, branch: string): Promise<string | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/repositories/${repoId}/commits?branch=${branch}&per_page=1`, {
      headers: { Authorization: `Bearer ${token}` },
      next: { revalidate: 60 },
    })

    if (!response.ok) {
      return null
    }

    const result = await response.json()
    return result.commits?.[0]?.sha || null
  } catch {
    return null
  }
}

// VCI Section Component - Client wrapper that subscribes to commit selection
async function VCISection({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) redirect('/login')

  const history = await getVCIHistory(id, session.accessToken)

  return (
    <VCISectionClient
      repositoryId={id}
      token={session.accessToken}
      initialHistory={history.data_points}
      initialTrend={history.trend}
    />
  )
}

// Metrics Section Component - Client wrapper that subscribes to commit selection
async function MetricsSection({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) redirect('/login')

  return <MetricsSectionClient repositoryId={id} token={session.accessToken} />
}

// Issues Section Component - Client wrapper that subscribes to commit selection
async function IssuesSection({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) redirect('/login')

  return <IssuesSectionClient repositoryId={id} token={session.accessToken} />
}

// AI Insights Section Wrapper (passes token from server)
async function AIInsightsSection({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) redirect('/login')

  return <AIInsightsPanel repositoryId={id} token={session.accessToken} />
}

// Semantic Analysis Section Wrapper (passes token from server)
async function SemanticAnalysisSectionWrapper({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) {
    return <SemanticAnalysisSection repositoryId={id} />
  }

  return <SemanticAnalysisSection repositoryId={id} token={session.accessToken} />
}

// Commit Timeline Section Wrapper (passes token, defaultBranch, and currentAnalysisCommit from server)
async function CommitTimelineSectionWrapper({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) {
    return <div className="text-muted-foreground text-sm">Please log in to view commit history.</div>
  }

  const [repo, latestAnalysis] = await Promise.all([
    getRepository(id),
    getLatestAnalysis(id, session.accessToken),
  ])

  if (!repo) {
    return <div className="text-muted-foreground text-sm">Repository not found.</div>
  }

  // Get the commit SHA of the currently displayed analysis
  const currentAnalysisCommit = latestAnalysis?.status === 'completed' ? latestAnalysis.commit_sha : null

  return (
    <CommitTimeline
      repositoryId={id}
      defaultBranch={repo.default_branch}
      token={session.accessToken}
      currentAnalysisCommit={currentAnalysisCommit}
    />
  )
}

// Loading skeletons
function HeaderSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-8 w-64 bg-muted rounded mb-3" />
      <div className="h-4 w-48 bg-muted rounded" />
    </div>
  )
}

function VCISkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="h-64 bg-card/50 border-border/50 animate-pulse" />
      <Card className="h-64 bg-card/50 border-border/50 animate-pulse" />
    </div>
  )
}

function IssuesSkeleton() {
  return (
    <Card className="border-border/50 bg-card/50 animate-pulse">
      <div className="p-6 border-b border-border/50">
        <div className="h-5 w-24 bg-muted rounded" />
      </div>
      <div className="p-6 space-y-6">
        {[1, 2, 3].map(i => (
          <div key={i} className="flex gap-4">
            <div className="h-10 w-10 bg-muted rounded" />
            <div className="flex-1">
              <div className="h-5 w-48 bg-muted rounded mb-2" />
              <div className="h-4 w-32 bg-muted rounded" />
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

// Main Page Component
export default async function RepositoryPage({
  params
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const session = await getSession()

  if (!session) {
    redirect('/login')
  }

  return (
    <div className="min-h-screen bg-background text-foreground">

      {/* Content */}
      <main className="container mx-auto px-3 sm:px-4 py-4 sm:py-6 max-w-[1600px]">
        {/* Repository Header + Code Health Row */}
        <div className="flex flex-col lg:flex-row lg:items-start gap-4 mb-4 sm:mb-6">
          {/* Left: Repository Info */}
          <div className="flex-1 min-w-0">
            <Suspense fallback={<HeaderSkeleton />}>
              <RepositoryHeader id={id} />
            </Suspense>
          </div>

          {/* Right: Compact Code Health Panel - Sticky */}
          <div className="fixed top-4 right-4 z-40">
            <Suspense fallback={<div className="h-20 w-[160px] bg-muted/30 rounded-xl animate-pulse" />}>
              <VCISection id={id} />
            </Suspense>
          </div>
        </div>

        {/* Tabs Layout */}
        <div className="flex-1 min-h-0 bg-[#1e1e1e] rounded-lg overflow-hidden border border-[#2b2b2b] shadow-sm">
          <RepoTabs
            aiScanContent={
              <div className="h-full p-4 overflow-hidden">
                <Suspense fallback={<div className="h-64 bg-muted/30 rounded-lg animate-pulse" />}>
                  <AIInsightsSection id={id} />
                </Suspense>
              </div>
            }
            semanticAnalysisContent={
              <div className="h-full p-4 overflow-hidden">
                <Suspense fallback={<div className="h-48 bg-muted/30 rounded-lg animate-pulse" />}>
                  <SemanticAnalysisSectionWrapper id={id} />
                </Suspense>
              </div>
            }
            staticAnalysisContent={
              <div className="h-full p-4 overflow-y-auto flex flex-col gap-6">
                {/* Issues Section */}
                <div className="bg-card/50 border border-border/50 rounded-xl p-4">
                  <h3 className="text-sm font-semibold mb-4 px-1">Issues</h3>
                  <div className="max-h-[400px] overflow-y-auto">
                    <Suspense fallback={<IssuesSkeleton />}>
                      <IssuesSection id={id} />
                    </Suspense>
                  </div>
                </div>

                {/* Metrics Section */}
                <div className="bg-card/50 border border-border/50 rounded-xl p-4">
                  <h3 className="text-sm font-semibold mb-4 px-1">Metrics</h3>
                  <Suspense fallback={<div className="h-64 bg-muted/30 rounded-lg animate-pulse" />}>
                    <MetricsSection id={id} />
                  </Suspense>
                </div>
              </div>
            }
          />
        </div>
      </main>
    </div>
  )
}

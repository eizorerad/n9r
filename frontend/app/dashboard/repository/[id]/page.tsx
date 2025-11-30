import { Suspense } from 'react'
import Link from 'next/link'
import { ArrowLeft, GitBranch, RefreshCw, ExternalLink } from 'lucide-react'
import { VCIScoreCard } from '@/components/vci-score-card'
import { VCITrendChart } from '@/components/vci-trend-chart'
import { IssuesList } from '@/components/issues-list'
import { RunAnalysisButton } from '@/components/run-analysis-button'
import { AnalysisMetrics } from '@/components/analysis-metrics'
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

// Repository Header Component
async function RepositoryHeader({ id }: { id: string }) {
  const repo = await getRepository(id)

  if (!repo) {
    notFound()
  }

  const htmlUrl = `https://github.com/${repo.full_name}`
  const grade = repo.vci_score ? getGrade(repo.vci_score) : null

  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <Link href="/dashboard" className="text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <h1 className="text-2xl font-bold tracking-tight">{repo.full_name}</h1>
          <a
            href={htmlUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <GitBranch className="h-4 w-4" />
            {repo.default_branch}
          </span>
          {repo.mode && (
            <span className="px-2.5 py-0.5 rounded-md bg-secondary text-secondary-foreground text-xs font-medium capitalize border border-border/50">
              {repo.mode.replace('_', ' ')}
            </span>
          )}
          {repo.last_analysis_at ? (
            <span>
              Last analyzed: {new Date(repo.last_analysis_at).toLocaleDateString()}
            </span>
          ) : (
            <span className="text-amber-500 font-medium">Not analyzed yet</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <RunAnalysisButton
          repositoryId={id}
          hasAnalysis={!!repo.last_analysis_at}
        />
        <Link href={`/dashboard/repository/${id}/ide`}>
          <Button variant="outline" className="flex items-center gap-2 shadow-sm">
            <RefreshCw className="h-4 w-4" />
            Open IDE
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

// VCI Section Component
async function VCISection({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) redirect('/login')

  const [repo, history] = await Promise.all([
    getRepository(id),
    getVCIHistory(id, session.accessToken),
  ])

  if (!repo) {
    return <div className="text-muted-foreground">Repository not found</div>
  }

  const grade = repo.vci_score ? getGrade(repo.vci_score) : null

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <VCIScoreCard
        score={repo.vci_score || null}
        grade={grade}
        trend={history.trend}
      />
      <VCITrendChart data={history.data_points} />
    </div>
  )
}

// Metrics Section Component  
async function MetricsSection({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) redirect('/login')

  const analysis = await getLatestAnalysis(id, session.accessToken)

  return <AnalysisMetrics metrics={analysis?.metrics || null} />
}

// Issues Section Component
async function IssuesSection({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) redirect('/login')

  const issues = await getIssues(id, session.accessToken)

  return (
    <IssuesList issues={issues.data} />
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
      {/* Header */}
      <header className="sticky top-0 z-50 glass-header border-b border-border/40">
        <div className="container mx-auto px-6 py-4">
          <Link href="/dashboard" className="flex items-center gap-3 group w-fit">
            <div className="w-9 h-9 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground rounded-xl flex items-center justify-center font-bold text-sm shadow-lg shadow-primary/20 group-hover:scale-105 transition-transform">
              n9
            </div>
            <span className="text-xl font-bold tracking-tight">n9r</span>
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-6 py-10">
        <div className="space-y-10">
          {/* Repository Header */}
          <Suspense fallback={<HeaderSkeleton />}>
            <RepositoryHeader id={id} />
          </Suspense>

          {/* VCI Section */}
          <section>
            <h2 className="text-2xl font-bold tracking-tight mb-6">Code Health</h2>
            <Suspense fallback={<VCISkeleton />}>
              <VCISection id={id} />
            </Suspense>
          </section>

          {/* Metrics Section */}
          <section>
            <h2 className="text-2xl font-bold tracking-tight mb-6">Analysis Details</h2>
            <Suspense fallback={<VCISkeleton />}>
              <MetricsSection id={id} />
            </Suspense>
          </section>

          {/* Issues Section */}
          <section>
            <h2 className="text-2xl font-bold tracking-tight mb-6">Issues</h2>
            <Suspense fallback={<IssuesSkeleton />}>
              <IssuesSection id={id} />
            </Suspense>
          </section>
        </div>
      </main>
    </div>
  )
}

import { Suspense } from 'react'
import { SemanticAnalysisSection } from '@/components/semantic-analysis-section'
import { RepoTabs } from '@/components/repo-tabs'
import { VCISectionClient } from '@/components/vci-section-client'
import { MetricsSectionClient } from '@/components/metrics-section-client'
import { IssuesSectionClient } from '@/components/issues-section-client'
import { AIInsightsPanel } from '@/components/ai-insights-panel'
import { Card } from '@/components/ui/card'
import { getSession } from '@/lib/session'
import { redirect } from 'next/navigation'

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



function getGrade(score: number): string {
  if (score >= 90) return 'A'
  if (score >= 80) return 'B'
  if (score >= 70) return 'C'
  if (score >= 60) return 'D'
  return 'F'
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

  return <MetricsSectionClient token={session.accessToken} />
}

// Issues Section Component - Client wrapper that subscribes to commit selection
async function IssuesSection({ id }: { id: string }) {
  const session = await getSession()
  if (!session?.accessToken) redirect('/login')

  return <IssuesSectionClient token={session.accessToken} />
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
      {/* Code Health Panel - Fixed position */}
      <div className="fixed top-4 right-4 z-40">
        <Suspense fallback={<div className="h-20 w-[160px] bg-muted/30 rounded-xl animate-pulse" />}>
          <VCISection id={id} />
        </Suspense>
      </div>

      {/* Content */}
      <main className="container mx-auto px-3 sm:px-4 py-4 sm:py-6 max-w-[1600px]">
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

import { Suspense } from 'react'
import Link from 'next/link'
import { Plus, GitBranch, AlertCircle, GitPullRequest, TrendingUp } from 'lucide-react'
import { getRepositories, getDashboardStats } from '@/lib/data/repositories'
import { RepositoriesTableServer } from './repositories-table-server'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

// Dashboard Stats Component - async Server Component
async function DashboardStats() {
  const stats = await getDashboardStats()

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card className="bg-gray-900/50 border-gray-800">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-gray-400">
            Total Repositories
          </CardTitle>
          <GitBranch className="h-4 w-4 text-gray-400" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.total_repositories}</div>
          <p className="text-xs text-gray-500 mt-1">
            {stats.healthy_repos} healthy
          </p>
        </CardContent>
      </Card>

      <Card className="bg-gray-900/50 border-gray-800">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-gray-400">
            Avg VCI Score
          </CardTitle>
          <TrendingUp className="h-4 w-4 text-gray-400" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {stats.avg_vci_score !== null ? stats.avg_vci_score.toFixed(0) : '—'}
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {stats.repos_needing_attention} need attention
          </p>
        </CardContent>
      </Card>

      <Card className="bg-gray-900/50 border-gray-800">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-gray-400">
            Open Issues
          </CardTitle>
          <AlertCircle className="h-4 w-4 text-gray-400" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.open_issues}</div>
          <p className="text-xs text-gray-500 mt-1">Across all repos</p>
        </CardContent>
      </Card>

      <Card className="bg-gray-900/50 border-gray-800">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-gray-400">
            Pending PRs
          </CardTitle>
          <GitPullRequest className="h-4 w-4 text-gray-400" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.pending_prs}</div>
          <p className="text-xs text-gray-500 mt-1">Awaiting review</p>
        </CardContent>
      </Card>
    </div>
  )
}

// Stats Skeleton
function StatsSkeleleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {[1, 2, 3, 4].map((i) => (
        <Card key={i} className="bg-gray-900/50 border-gray-800 animate-pulse">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div className="h-4 w-24 bg-gray-800 rounded" />
            <div className="h-4 w-4 bg-gray-800 rounded" />
          </CardHeader>
          <CardContent>
            <div className="h-8 w-16 bg-gray-800 rounded mb-2" />
            <div className="h-3 w-20 bg-gray-800 rounded" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// Repositories List Component - async Server Component
async function RepositoriesList() {
  const repos = await getRepositories()
  return <RepositoriesTableServer initialData={repos.data} />
}

// Table Skeleton
function TableSkeleton() {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/50">
      <div className="p-4 border-b border-gray-800">
        <div className="h-6 w-32 bg-gray-800 rounded animate-pulse" />
      </div>
      <div className="divide-y divide-gray-800">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="p-4 flex items-center gap-4 animate-pulse">
            <div className="h-4 w-4 bg-gray-800 rounded" />
            <div className="flex-1">
              <div className="h-4 w-48 bg-gray-800 rounded mb-2" />
              <div className="h-3 w-24 bg-gray-800 rounded" />
            </div>
            <div className="h-6 w-16 bg-gray-800 rounded-full" />
            <div className="h-4 w-20 bg-gray-800 rounded" />
          </div>
        ))}
      </div>
    </div>
  )
}

// Main Dashboard Page - Server Component
export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center font-bold text-sm">
                n9
              </div>
              <span className="text-xl font-semibold">n9r</span>
            </Link>
            <span className="text-gray-400">/</span>
            <span className="text-gray-300">Dashboard</span>
          </div>
          <Link href="/dashboard/connect">
            <Button className="flex items-center gap-2 bg-green-600 hover:bg-green-700">
              <Plus className="h-4 w-4" />
              Connect Repository
            </Button>
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-4 py-8">
        <div className="space-y-8">
          {/* Stats Section - Streamed */}
          <section>
            <h2 className="text-lg font-semibold mb-4">Overview</h2>
            <Suspense fallback={<StatsSkeleleton />}>
              <DashboardStats />
            </Suspense>
          </section>

          {/* Repositories Section - Streamed */}
          <section>
            <h2 className="text-lg font-semibold mb-4">Repositories</h2>
            <Suspense fallback={<TableSkeleton />}>
              <RepositoriesList />
            </Suspense>
          </section>
        </div>
      </main>
    </div>
  )
}

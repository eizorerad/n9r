import { Suspense } from 'react'
import Link from 'next/link'
import { Plus, GitBranch, AlertCircle, GitPullRequest, TrendingUp } from 'lucide-react'
import { getRepositories, getDashboardStats } from '@/lib/data/repositories'
import { RepositoriesTableServer } from './repositories-table-server'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

// Repositories List Component - async Server Component
async function RepositoriesList() {
  const repos = await getRepositories()
  return <RepositoriesTableServer initialData={repos.data} />
}

// Table Skeleton
function TableSkeleton() {
  return (
    <Card className="border-border/50 bg-card/50 backdrop-blur-sm overflow-hidden">
      <div className="p-6 border-b border-border/50">
        <div className="h-6 w-32 bg-muted rounded animate-pulse" />
      </div>
      <div className="divide-y divide-border/50">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="p-6 flex items-center gap-6 animate-pulse">
            <div className="h-4 w-4 bg-muted rounded" />
            <div className="flex-1">
              <div className="h-4 w-48 bg-muted rounded mb-2" />
              <div className="h-3 w-24 bg-muted rounded" />
            </div>
            <div className="h-6 w-16 bg-muted rounded-full" />
            <div className="h-4 w-20 bg-muted rounded" />
          </div>
        ))}
      </div>
    </Card>
  )
}

// Main Dashboard Page - Server Component
export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="sticky top-0 z-50 glass-header border-b border-border/40">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="flex items-center gap-3 group">
              <div className="w-9 h-9 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground rounded-xl flex items-center justify-center font-bold text-sm shadow-lg shadow-primary/20 group-hover:scale-105 transition-transform">
                n9
              </div>
              <span className="text-xl font-bold tracking-tight">n9r</span>
            </Link>
            <span className="text-muted-foreground/50 text-xl font-light">/</span>
            <span className="text-muted-foreground font-medium">Dashboard</span>
          </div>
          <Link href="/dashboard/connect">
            <Button className="flex items-center gap-2 shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all bg-primary hover:bg-primary/90 text-primary-foreground">
              <Plus className="h-4 w-4" />
              Connect Repository
            </Button>
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-6 py-10">
        <div className="space-y-10">
          {/* Repositories Section - Streamed */}
          <section>
            <h2 className="text-2xl font-bold tracking-tight mb-6">Repositories</h2>
            <Suspense fallback={<TableSkeleton />}>
              <RepositoriesList />
            </Suspense>
          </section>
        </div>
      </main>
    </div>
  )
}


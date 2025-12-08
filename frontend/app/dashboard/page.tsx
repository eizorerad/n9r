import { Suspense } from 'react'
import Link from 'next/link'
import { Plus } from 'lucide-react'
import { getRepositories } from '@/lib/data/repositories'
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
      <header className="sticky top-0 z-50 bg-[#1e1e1e] border-b border-neutral-700/50">
        <div className="container mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="flex items-center gap-3 group">
              <img 
                src="/logo.svg" 
                alt="Necromancer" 
                className="w-8 h-8 group-hover:scale-105 transition-transform"
              />
              <span className="text-lg font-semibold tracking-tight text-neutral-200">Necromancer</span>
            </Link>
            <span className="text-neutral-600 text-lg font-light">/</span>
            <span className="text-neutral-400 font-mono text-sm">Dashboard</span>
          </div>
          <Link href="/dashboard/connect">
            <Button className="flex items-center gap-2 h-8 px-4 bg-neutral-700 hover:bg-neutral-600 text-neutral-200 font-mono text-xs border border-neutral-600 shadow-none">
              <Plus className="h-3 w-3" />
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

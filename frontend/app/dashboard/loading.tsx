import { Card } from '@/components/ui/card'

export default function DashboardLoading() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header Skeleton */}
      <header className="sticky top-0 z-50 border-b border-border/40 bg-background/80 backdrop-blur-md">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-9 h-9 bg-muted rounded-xl animate-pulse" />
            <div className="h-6 w-24 bg-muted rounded animate-pulse" />
            <span className="text-muted-foreground/50 text-xl font-light">/</span>
            <div className="h-5 w-24 bg-muted rounded animate-pulse" />
          </div>
          <div className="h-10 w-40 bg-muted rounded-lg animate-pulse" />
        </div>
      </header>

      {/* Content Skeleton */}
      <main className="container mx-auto px-6 py-10">
        <div className="space-y-10">
          {/* Repositories Section */}
          <section>
            <div className="h-8 w-32 bg-muted rounded mb-6 animate-pulse" />
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
          </section>
        </div>
      </main>
    </div>
  )
}

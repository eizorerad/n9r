import { Card, CardContent, CardHeader } from '@/components/ui/card'

export default function DashboardLoading() {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header Skeleton */}
      <header className="border-b border-gray-800 bg-gray-900/50">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-8 h-8 bg-gray-800 rounded-lg animate-pulse" />
            <div className="h-6 w-16 bg-gray-800 rounded animate-pulse" />
            <span className="text-gray-600">/</span>
            <div className="h-5 w-24 bg-gray-800 rounded animate-pulse" />
          </div>
          <div className="h-10 w-40 bg-gray-800 rounded-lg animate-pulse" />
        </div>
      </header>

      {/* Content Skeleton */}
      <main className="container mx-auto px-4 py-8">
        <div className="space-y-8">
          {/* Stats Section */}
          <section>
            <div className="h-6 w-24 bg-gray-800 rounded mb-4 animate-pulse" />
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
          </section>

          {/* Repositories Section */}
          <section>
            <div className="h-6 w-28 bg-gray-800 rounded mb-4 animate-pulse" />
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
          </section>
        </div>
      </main>
    </div>
  )
}

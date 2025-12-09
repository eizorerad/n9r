'use client'

import { useState } from 'react'
import dynamic from 'next/dynamic'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

// Dynamic import for ClusterGraph to optimize bundle size
const ClusterGraph = dynamic(
  () => import('./cluster-graph').then(mod => ({ default: mod.ClusterGraph })),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-[400px]">
        <div className="text-muted-foreground">Loading graph...</div>
      </div>
    ),
  }
)

interface ClusterInfo {
  id: number
  name: string
  file_count: number
  chunk_count: number
  cohesion: number
  top_files: string[]
  dominant_language: string | null
  status: string
}

interface OutlierInfo {
  file_path: string
  chunk_name: string | null
  chunk_type: string | null
  nearest_similarity: number
  nearest_file: string | null
  suggestion: string
  confidence: number
  confidence_factors: string[]
  tier: string
}

interface CachedArchitectureData {
  clusters: ClusterInfo[]
  outliers: OutlierInfo[]
  overall_score?: number
  total_chunks?: number
  total_files?: number
}

interface ClusterMapProps {
  repositoryId: string
  token: string
  className?: string
  cachedData?: CachedArchitectureData
  hasSemanticCache?: boolean
  onClusterClick?: (cluster: ClusterInfo) => void
}

export function ClusterMap({ className, cachedData, hasSemanticCache = false, onClusterClick }: ClusterMapProps) {
  const [selectedCluster, setSelectedCluster] = useState<ClusterInfo | null>(null)

  const handleClusterClick = (cluster: ClusterInfo) => {
    setSelectedCluster(cluster)
    onClusterClick?.(cluster)
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleGraphNodeClick = (node: any) => {
    if (node.type === 'cluster' && node.data) {
      handleClusterClick(node.data as ClusterInfo)
    }
  }

  // Check if we have valid cached data
  const hasCachedData = cachedData && Array.isArray(cachedData.clusters)

  // Show message if no cached data available
  if (!hasCachedData) {
    const isOldCache = hasSemanticCache && !cachedData

    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardContent className="p-6">
          <div className="text-center py-8">
            <div className="text-3xl mb-3">🗺️</div>
            <h3 className="text-base font-semibold mb-2">Cluster Map</h3>
            {isOldCache ? (
              <>
                <p className="text-sm text-muted-foreground mb-2">
                  Cluster visualization requires a newer analysis.
                </p>
                <p className="text-xs text-muted-foreground">
                  Re-run the analysis to view the cluster map.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground mb-2">
                  Cluster data not available yet.
                </p>
                <p className="text-xs text-muted-foreground">
                  Run an analysis for this commit to view code clusters.
                </p>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  const clusters = cachedData.clusters
  const outliers = cachedData.outliers || []

  return (
    <Card className={cn('glass-panel border-border/50', className)}>
      <CardContent className="p-6">
        {/* Header */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold">Cluster Map</h3>
          <p className="text-sm text-muted-foreground">
            Visual overview of code clusters and their relationships
          </p>
        </div>

        {/* Graph View */}
        {clusters.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>No clusters detected</p>
            <p className="text-sm mt-1">Repository may need more code or embeddings</p>
          </div>
        ) : (
          <div className="rounded-lg border border-border/50 bg-background/30 overflow-hidden">
            <ClusterGraph
              clusters={clusters}
              outliers={outliers}
              onNodeClick={handleGraphNodeClick}
              height={400}
            />
          </div>
        )}

        {/* Selected Cluster Details */}
        {selectedCluster && (
          <div className="mt-6 p-4 rounded-lg bg-background/30 border border-border/50">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-semibold">{selectedCluster.name}</h4>
              <Badge
                variant="outline"
                className={cn(
                  selectedCluster.status === 'healthy' && 'bg-emerald-500/10 text-emerald-400',
                  selectedCluster.status === 'moderate' && 'bg-amber-500/10 text-amber-400',
                  selectedCluster.status === 'scattered' && 'bg-red-500/10 text-red-400'
                )}
              >
                {selectedCluster.status}
              </Badge>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
              <div>
                <span className="text-muted-foreground">Files: </span>
                <span className="font-medium">{selectedCluster.file_count}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Chunks: </span>
                <span className="font-medium">{selectedCluster.chunk_count}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Cohesion: </span>
                <span className="font-medium">{Math.round(selectedCluster.cohesion * 100)}%</span>
              </div>
            </div>

            {selectedCluster.top_files.length > 0 && (
              <div>
                <p className="text-sm text-muted-foreground mb-2">Top files:</p>
                <div className="space-y-1">
                  {selectedCluster.top_files.slice(0, 5).map((file, idx) => (
                    <code key={idx} className="block text-xs p-1.5 rounded bg-background/50 truncate">
                      {file}
                    </code>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

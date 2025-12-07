'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

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

const statusColors: Record<string, string> = {
  healthy: 'bg-emerald-500',
  moderate: 'bg-amber-500',
  scattered: 'bg-red-500',
}

const statusBgColors: Record<string, string> = {
  healthy: 'bg-emerald-500/10 border-emerald-500/30',
  moderate: 'bg-amber-500/10 border-amber-500/30',
  scattered: 'bg-red-500/10 border-red-500/30',
}

export function ClusterMap({ className, cachedData, hasSemanticCache = false, onClusterClick }: ClusterMapProps) {
  const [selectedCluster, setSelectedCluster] = useState<ClusterInfo | null>(null)

  const handleClusterClick = (cluster: ClusterInfo) => {
    setSelectedCluster(cluster)
    onClusterClick?.(cluster)
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

  // Calculate max values for sizing
  const maxChunks = Math.max(...clusters.map(c => c.chunk_count), 1)

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

        {/* Legend */}
        <div className="flex items-center gap-4 mb-6 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-emerald-500" />
            <span className="text-muted-foreground">Healthy</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-amber-500" />
            <span className="text-muted-foreground">Moderate</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-red-500" />
            <span className="text-muted-foreground">Scattered</span>
          </div>
          <div className="flex items-center gap-2 ml-4">
            <div className="w-3 h-3 rounded-full bg-slate-500 ring-2 ring-amber-500" />
            <span className="text-muted-foreground">Outlier</span>
          </div>
        </div>

        {/* Cluster Grid */}
        {clusters.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>No clusters detected</p>
            <p className="text-sm mt-1">Repository may need more code or embeddings</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {clusters.map((cluster) => {
              const sizeRatio = cluster.chunk_count / maxChunks
              const minSize = 80
              const maxSize = 160
              const size = minSize + (maxSize - minSize) * sizeRatio

              return (
                <div
                  key={cluster.id}
                  className={cn(
                    'relative rounded-xl border-2 cursor-pointer transition-all',
                    'hover:scale-105 hover:shadow-lg',
                    statusBgColors[cluster.status] || statusBgColors.moderate,
                    selectedCluster?.id === cluster.id && 'ring-2 ring-primary'
                  )}
                  style={{ 
                    minHeight: size,
                    aspectRatio: '1',
                  }}
                  onClick={() => handleClusterClick(cluster)}
                >
                  {/* Status indicator */}
                  <div className={cn(
                    'absolute top-2 right-2 w-3 h-3 rounded-full',
                    statusColors[cluster.status] || statusColors.moderate
                  )} />

                  {/* Content */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center p-3 text-center">
                    <span className="font-medium text-sm truncate max-w-full">
                      {cluster.name}
                    </span>
                    <span className="text-xs text-muted-foreground mt-1">
                      {cluster.file_count} files
                    </span>
                    <span className={cn(
                      'text-lg font-bold mt-2',
                      cluster.cohesion >= 0.7 ? 'text-emerald-400' : 
                      cluster.cohesion >= 0.5 ? 'text-amber-400' : 'text-red-400'
                    )}>
                      {Math.round(cluster.cohesion * 100)}%
                    </span>
                  </div>
                </div>
              )
            })}

            {/* Outliers indicator */}
            {outliers.length > 0 && (
              <div
                className={cn(
                  'relative rounded-xl border-2 border-dashed border-amber-500/50',
                  'bg-amber-500/5 cursor-pointer transition-all hover:bg-amber-500/10'
                )}
                style={{ minHeight: 80, aspectRatio: '1' }}
              >
                <div className="absolute inset-0 flex flex-col items-center justify-center p-3 text-center">
                  <span className="text-amber-400 text-2xl">⚠</span>
                  <span className="font-medium text-sm text-amber-400">
                    Outliers
                  </span>
                  <span className="text-xs text-muted-foreground mt-1">
                    {outliers.length} items
                  </span>
                </div>
              </div>
            )}
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

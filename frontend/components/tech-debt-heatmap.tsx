'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

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

interface CouplingHotspot {
  file_path: string
  clusters_connected: number
  cluster_names: string[]
  suggestion: string
}

interface CachedArchitectureData {
  clusters: ClusterInfo[]
  outliers: OutlierInfo[]
  coupling_hotspots: CouplingHotspot[]
  overall_score?: number
  total_chunks?: number
  total_files?: number
  metrics?: Record<string, number>
}

interface TechDebtHeatmapProps {
  repositoryId: string
  token: string
  className?: string
  cachedData?: CachedArchitectureData
  hasSemanticCache?: boolean
}

const riskColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-400 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  medium: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  low: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
}

const healthColors: Record<string, string> = {
  good: 'text-emerald-400',
  moderate: 'text-amber-400',
  poor: 'text-red-400',
}

export function TechDebtHeatmap({ className, cachedData, hasSemanticCache = false }: TechDebtHeatmapProps) {
  const [view, setView] = useState<'hotspots' | 'clusters'>('hotspots')

  // Check if we have valid cached data
  const hasCachedData = cachedData && (Array.isArray(cachedData.clusters) || Array.isArray(cachedData.coupling_hotspots))

  // Show message if no cached data available
  if (!hasCachedData) {
    const isOldCache = hasSemanticCache && !cachedData
    
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardContent className="p-6">
          <div className="text-center py-8">
            <div className="text-3xl mb-3">🔥</div>
            <h3 className="text-base font-semibold mb-2">Technical Debt Heatmap</h3>
            {isOldCache ? (
              <>
                <p className="text-sm text-muted-foreground mb-2">
                  Tech debt analysis requires a newer analysis.
                </p>
                <p className="text-xs text-muted-foreground">
                  Re-run the analysis to view technical debt.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground mb-2">
                  Tech debt data not available yet.
                </p>
                <p className="text-xs text-muted-foreground">
                  Run an analysis for this commit to view technical debt.
                </p>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  // Calculate debt score from architecture health (inverse of overall_score)
  const overallScore = cachedData.overall_score ?? 50
  const debtScore = 100 - overallScore

  // Build hotspots from coupling_hotspots and outliers
  const hotspots = buildHotspots(cachedData)
  
  // Build cluster health data
  const clusterHealth = buildClusterHealth(cachedData.clusters || [])

  const getDebtColor = (score: number) => {
    if (score <= 20) return 'text-emerald-400'
    if (score <= 40) return 'text-blue-400'
    if (score <= 60) return 'text-amber-400'
    return 'text-red-400'
  }

  const getDebtGradient = (score: number) => {
    if (score <= 20) return 'from-emerald-500 to-emerald-600'
    if (score <= 40) return 'from-blue-500 to-blue-600'
    if (score <= 60) return 'from-amber-500 to-amber-600'
    return 'from-red-500 to-red-600'
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Debt Score Card */}
      <Card className="glass-panel border-border/50 relative overflow-hidden">
        <div className={cn(
          'absolute inset-0 opacity-5 bg-gradient-to-br',
          getDebtGradient(debtScore)
        )} />
        <CardContent className="relative p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold mb-1">Technical Debt</h3>
              <p className="text-sm text-muted-foreground">
                {hotspots.length} hotspots · {clusterHealth.length} clusters
              </p>
            </div>
            <div className="text-right">
              <div className={cn('text-4xl font-bold', getDebtColor(debtScore))}>
                {debtScore}
              </div>
              <div className="text-sm text-muted-foreground">debt score</div>
            </div>
          </div>

          {/* Debt level indicator */}
          <div className="mt-4">
            <div className="h-2 rounded-full bg-background/50 overflow-hidden">
              <div 
                className={cn('h-full rounded-full bg-gradient-to-r', getDebtGradient(debtScore))}
                style={{ width: `${debtScore}%` }}
              />
            </div>
            <div className="flex justify-between mt-1 text-xs text-muted-foreground">
              <span>Low debt</span>
              <span>High debt</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* View Toggle */}
      <div className="flex gap-2">
        <Button
          variant={view === 'hotspots' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setView('hotspots')}
        >
          Debt Hotspots ({hotspots.length})
        </Button>
        <Button
          variant={view === 'clusters' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setView('clusters')}
        >
          By Cluster ({clusterHealth.length})
        </Button>
      </div>

      {/* Content */}
      <Card className="glass-panel border-border/50">
        <CardContent className="p-4">
          {view === 'hotspots' ? (
            <HotspotsView hotspots={hotspots} />
          ) : (
            <ClustersView clusters={clusterHealth} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

interface TechDebtHotspot {
  file_path: string
  risk: string
  suggestion: string
  bridges_clusters: number
  cohesion: number | null
}

function buildHotspots(data: CachedArchitectureData): TechDebtHotspot[] {
  const hotspots: TechDebtHotspot[] = []

  // Add coupling hotspots as critical/high
  for (const hotspot of data.coupling_hotspots || []) {
    hotspots.push({
      file_path: hotspot.file_path,
      risk: hotspot.clusters_connected >= 4 ? 'critical' : 'high',
      suggestion: hotspot.suggestion,
      bridges_clusters: hotspot.clusters_connected,
      cohesion: null,
    })
  }

  // Add outliers as medium risk (limit to 10)
  for (const outlier of (data.outliers || []).slice(0, 10)) {
    if (outlier.nearest_similarity < 0.4) {
      hotspots.push({
        file_path: outlier.file_path,
        risk: 'medium',
        suggestion: outlier.suggestion,
        bridges_clusters: 0,
        cohesion: outlier.nearest_similarity,
      })
    }
  }

  return hotspots
}

interface ClusterHealthInfo {
  cluster: string
  cohesion: number
  health: string
  avg_complexity: number
}

function buildClusterHealth(clusters: ClusterInfo[]): ClusterHealthInfo[] {
  return clusters.map(c => ({
    cluster: c.name,
    cohesion: c.cohesion,
    health: c.cohesion >= 0.7 ? 'good' : c.cohesion >= 0.5 ? 'moderate' : 'poor',
    avg_complexity: 0, // Not available in cached data
  }))
}

function HotspotsView({ hotspots }: { hotspots: TechDebtHotspot[] }) {
  if (hotspots.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p className="text-emerald-400">✓ No debt hotspots</p>
        <p className="text-sm mt-1">Codebase is in good shape</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {hotspots.map((hotspot, idx) => (
        <div
          key={idx}
          className={cn(
            'p-4 rounded-lg bg-background/30 border border-border/50',
            hotspot.risk === 'critical' && 'border-l-2 border-l-red-500',
            hotspot.risk === 'high' && 'border-l-2 border-l-orange-500',
            hotspot.risk === 'medium' && 'border-l-2 border-l-amber-500'
          )}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <code className="text-sm">{hotspot.file_path}</code>
                <Badge 
                  variant="outline" 
                  className={riskColors[hotspot.risk] || riskColors.medium}
                >
                  {hotspot.risk}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">{hotspot.suggestion}</p>
            </div>
            <div className="text-right shrink-0">
              {hotspot.bridges_clusters > 0 && (
                <div className="text-sm">
                  <span className="text-muted-foreground">Bridges: </span>
                  <span className="font-medium">{hotspot.bridges_clusters}</span>
                </div>
              )}
              {hotspot.cohesion !== null && (
                <div className="text-sm">
                  <span className="text-muted-foreground">Cohesion: </span>
                  <span className="font-medium">{Math.round(hotspot.cohesion * 100)}%</span>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function ClustersView({ clusters }: { clusters: ClusterHealthInfo[] }) {
  if (clusters.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p>No cluster data available</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {clusters.map((cluster, idx) => (
        <div
          key={idx}
          className="p-4 rounded-lg bg-background/30 border border-border/50"
        >
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium">{cluster.cluster}</h4>
              <div className="flex items-center gap-4 mt-1 text-sm">
                <span>
                  <span className="text-muted-foreground">Cohesion: </span>
                  <span className={cn(
                    'font-medium',
                    cluster.cohesion >= 0.7 ? 'text-emerald-400' : 
                    cluster.cohesion >= 0.5 ? 'text-amber-400' : 'text-red-400'
                  )}>
                    {Math.round(cluster.cohesion * 100)}%
                  </span>
                </span>
                {cluster.avg_complexity > 0 && (
                  <span>
                    <span className="text-muted-foreground">Avg CC: </span>
                    <span className="font-medium">{cluster.avg_complexity.toFixed(1)}</span>
                  </span>
                )}
              </div>
            </div>
            <span className={cn('font-medium', healthColors[cluster.health] || healthColors.moderate)}>
              {cluster.health}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

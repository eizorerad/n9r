'use client'

import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  semanticApi, 
  TechDebtHeatmapResponse, 
  TechDebtHotspot,
  TechDebtByCluster 
} from '@/lib/semantic-api'

interface TechDebtHeatmapProps {
  repositoryId: string
  token: string
  className?: string
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

export function TechDebtHeatmap({ repositoryId, token, className }: TechDebtHeatmapProps) {
  const [data, setData] = useState<TechDebtHeatmapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'hotspots' | 'clusters'>('hotspots')

  useEffect(() => {
    fetchData()
  }, [repositoryId, token])

  const fetchData = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await semanticApi.techDebtHeatmap(token, repositoryId)
      setData(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

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

  if (loading) {
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardContent className="p-6">
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            <span className="ml-3 text-muted-foreground">Analyzing tech debt...</span>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardContent className="p-6">
          <div className="text-center py-8">
            <p className="text-red-400 mb-4">{error}</p>
            <Button onClick={fetchData} variant="outline">Retry</Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  return (
    <div className={cn('space-y-6', className)}>
      {/* Debt Score Card */}
      <Card className="glass-panel border-border/50 relative overflow-hidden">
        <div className={cn(
          'absolute inset-0 opacity-5 bg-gradient-to-br',
          getDebtGradient(data.debt_score)
        )} />
        <CardContent className="relative p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold mb-1">Technical Debt</h3>
              <p className="text-sm text-muted-foreground">
                {data.hotspots.length} hotspots · {data.by_cluster.length} clusters
              </p>
            </div>
            <div className="text-right">
              <div className={cn('text-4xl font-bold', getDebtColor(data.debt_score))}>
                {data.debt_score}
              </div>
              <div className="text-sm text-muted-foreground">debt score</div>
            </div>
          </div>

          {/* Debt level indicator */}
          <div className="mt-4">
            <div className="h-2 rounded-full bg-background/50 overflow-hidden">
              <div 
                className={cn('h-full rounded-full bg-gradient-to-r', getDebtGradient(data.debt_score))}
                style={{ width: `${data.debt_score}%` }}
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
          Hotspots ({data.hotspots.length})
        </Button>
        <Button
          variant={view === 'clusters' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setView('clusters')}
        >
          By Cluster ({data.by_cluster.length})
        </Button>
      </div>

      {/* Content */}
      <Card className="glass-panel border-border/50">
        <CardContent className="p-4">
          {view === 'hotspots' ? (
            <HotspotsView hotspots={data.hotspots} />
          ) : (
            <ClustersView clusters={data.by_cluster} />
          )}
        </CardContent>
      </Card>
    </div>
  )
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

function ClustersView({ clusters }: { clusters: TechDebtByCluster[] }) {
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

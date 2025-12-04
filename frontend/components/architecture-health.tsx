'use client'

import { useState, useEffect, useMemo, memo } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  semanticApi, 
  ArchitectureHealthResponse, 
  ClusterInfo, 
  OutlierInfo,
  CouplingHotspot 
} from '@/lib/semantic-api'

// Cached data may have optional overall_score (for backward compatibility with 'score' field)
type CachedArchitectureHealth = Omit<ArchitectureHealthResponse, 'overall_score'> & {
  overall_score?: number
  score?: number  // Legacy field
}

interface ArchitectureHealthProps {
  repositoryId: string
  token: string
  className?: string
  cachedData?: CachedArchitectureHealth
}

const statusColors: Record<string, string> = {
  healthy: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  moderate: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  scattered: 'bg-red-500/10 text-red-400 border-red-500/20',
}

const riskColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-400 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  medium: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  low: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
}

function ArchitectureHealthComponent({ repositoryId, token, className, cachedData }: ArchitectureHealthProps) {
  const [data, setData] = useState<ArchitectureHealthResponse | null>(cachedData || null)
  const [loading, setLoading] = useState(!cachedData)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'clusters' | 'issues' | 'hotspots'>('clusters')

  // Memoize cachedData check to prevent re-running effect on every parent render
  const hasCachedData = useMemo(() => !!cachedData, [cachedData])
  const cachedDataString = useMemo(() => JSON.stringify(cachedData), [cachedData])

  useEffect(() => {
    // If we have cached data, use it directly
    if (cachedData) {
      setData(cachedData)
      setLoading(false)
      setError(null)
      return
    }
    
    // Only fetch from API if no cached data
    fetchData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repositoryId, token, cachedDataString])

  const fetchData = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await semanticApi.architectureHealth(token, repositoryId)
      setData(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-emerald-400'
    if (score >= 60) return 'text-amber-400'
    return 'text-red-400'
  }

  const getScoreGradient = (score: number) => {
    if (score >= 80) return 'from-emerald-500 to-emerald-600'
    if (score >= 60) return 'from-amber-500 to-amber-600'
    return 'from-red-500 to-red-600'
  }

  if (loading) {
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardContent className="p-6">
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            <span className="ml-3 text-muted-foreground">Analyzing architecture...</span>
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

  // Memoize derived values to prevent recalculation on every render
  const computedValues = useMemo(() => {
    // Handle both 'overall_score' and legacy 'score' field for backward compatibility
    const scoreValue = data.overall_score ?? (data as unknown as { score?: number }).score
    const issueCount = data.outliers.length + data.coupling_hotspots.length
    const hasScore = typeof scoreValue === 'number'
    const displayScore = hasScore ? scoreValue : 0
    
    return { scoreValue, issueCount, hasScore, displayScore }
  }, [data.overall_score, data.outliers.length, data.coupling_hotspots.length])
  
  const { scoreValue, issueCount, hasScore, displayScore } = computedValues

  return (
    <div className={cn('space-y-6', className)}>
      {/* Overall Score Card */}
      <Card className="glass-panel border-border/50 relative overflow-hidden">
        <div className={cn(
          'absolute inset-0 opacity-5 bg-gradient-to-br',
          getScoreGradient(displayScore)
        )} />
        <CardContent className="relative p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold mb-1">Architecture Health</h3>
              <p className="text-sm text-muted-foreground">
                {data.total_files} files · {data.total_chunks} code chunks
              </p>
            </div>
            <div className="text-right">
              <div className={cn('text-4xl font-bold', hasScore ? getScoreColor(displayScore) : 'text-muted-foreground')}>
                {hasScore ? displayScore : '—'}
              </div>
              <div className="text-sm text-muted-foreground">/100</div>
            </div>
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-3 gap-4 mt-6">
            <div className="text-center p-3 rounded-lg bg-background/30">
              <div className="text-2xl font-bold text-blue-400">
                {data.metrics.cluster_count || data.clusters.length}
              </div>
              <div className="text-xs text-muted-foreground">Clusters</div>
            </div>
            <div className="text-center p-3 rounded-lg bg-background/30">
              <div className="text-2xl font-bold text-emerald-400">
                {Math.round((data.metrics.avg_cohesion || 0) * 100)}%
              </div>
              <div className="text-xs text-muted-foreground">Avg Cohesion</div>
            </div>
            <div className="text-center p-3 rounded-lg bg-background/30">
              <div className="text-2xl font-bold text-amber-400">
                {Math.round(data.metrics.outlier_percentage || 0)}%
              </div>
              <div className="text-xs text-muted-foreground">Outliers</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <div className="flex gap-2">
        <Button
          variant={activeTab === 'clusters' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveTab('clusters')}
        >
          Clusters ({data.clusters.length})
        </Button>
        <Button
          variant={activeTab === 'issues' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveTab('issues')}
        >
          Issues ({issueCount})
        </Button>
        <Button
          variant={activeTab === 'hotspots' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveTab('hotspots')}
        >
          Hotspots ({data.coupling_hotspots.length})
        </Button>
      </div>

      {/* Tab Content */}
      <Card className="glass-panel border-border/50">
        <CardContent className="p-4">
          {activeTab === 'clusters' && (
            <ClustersTab clusters={data.clusters} />
          )}
          {activeTab === 'issues' && (
            <IssuesTab outliers={data.outliers} />
          )}
          {activeTab === 'hotspots' && (
            <HotspotsTab hotspots={data.coupling_hotspots} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function ClustersTab({ clusters }: { clusters: ClusterInfo[] }) {
  if (clusters.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p>No clusters detected</p>
        <p className="text-sm mt-1">Repository may need more code or embeddings</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {clusters.map((cluster) => (
        <div
          key={cluster.id}
          className="p-4 rounded-lg bg-background/30 border border-border/50"
        >
          <div className="flex items-start justify-between mb-3">
            <div>
              <h4 className="font-medium">{cluster.name}</h4>
              <p className="text-sm text-muted-foreground">
                {cluster.file_count} files · {cluster.chunk_count} chunks
              </p>
            </div>
            <Badge 
              variant="outline" 
              className={statusColors[cluster.status] || statusColors.moderate}
            >
              {cluster.status}
            </Badge>
          </div>

          <div className="flex items-center gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Cohesion: </span>
              <span className={cn(
                'font-medium',
                cluster.cohesion >= 0.7 ? 'text-emerald-400' : 
                cluster.cohesion >= 0.5 ? 'text-amber-400' : 'text-red-400'
              )}>
                {Math.round(cluster.cohesion * 100)}%
              </span>
            </div>
            {cluster.dominant_language && (
              <Badge variant="outline" className="text-xs">
                {cluster.dominant_language}
              </Badge>
            )}
          </div>

          {cluster.top_files.length > 0 && (
            <div className="mt-3">
              <p className="text-xs text-muted-foreground mb-1">Top files:</p>
              <div className="flex flex-wrap gap-1">
                {cluster.top_files.slice(0, 3).map((file, idx) => (
                  <code key={idx} className="text-xs px-2 py-0.5 rounded bg-background/50">
                    {file.split('/').pop()}
                  </code>
                ))}
                {cluster.top_files.length > 3 && (
                  <span className="text-xs text-muted-foreground">
                    +{cluster.top_files.length - 3} more
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const tierColors: Record<string, { border: string; icon: string; badge: string }> = {
  critical: {
    border: 'border-l-red-500',
    icon: 'text-red-400',
    badge: 'bg-red-500/10 text-red-400 border-red-500/20',
  },
  recommended: {
    border: 'border-l-amber-500',
    icon: 'text-amber-400',
    badge: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  },
  informational: {
    border: 'border-l-blue-500',
    icon: 'text-blue-400',
    badge: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  },
}

const tierIcons: Record<string, string> = {
  critical: '🔴',
  recommended: '⚠',
  informational: 'ℹ',
}

function IssuesTab({ outliers }: { outliers: OutlierInfo[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  if (outliers.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p className="text-emerald-400">✓ No outliers detected</p>
        <p className="text-sm mt-1">All code appears well-organized</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {outliers.map((outlier, idx) => {
        const tier = outlier.tier || 'recommended'
        const colors = tierColors[tier] || tierColors.recommended
        const icon = tierIcons[tier] || '⚠'
        const confidencePercent = Math.round((outlier.confidence || 0.5) * 100)
        const isExpanded = expandedIdx === idx

        return (
          <div
            key={idx}
            className={cn(
              'p-4 rounded-lg bg-background/30 border-l-2 border border-border/50',
              colors.border
            )}
          >
            <div className="flex items-start gap-3">
              <span className={cn('mt-0.5', colors.icon)}>{icon}</span>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <code className="text-sm">{outlier.file_path}</code>
                  {outlier.chunk_name && (
                    <>
                      <span className="text-muted-foreground/50">→</span>
                      <span className="text-sm font-medium">{outlier.chunk_name}</span>
                    </>
                  )}
                  {outlier.chunk_type && (
                    <Badge variant="outline" className="text-xs">
                      {outlier.chunk_type}
                    </Badge>
                  )}
                  <Badge variant="outline" className={cn('text-xs capitalize', colors.badge)}>
                    {tier}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {confidencePercent}% confidence
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">{outlier.suggestion}</p>
                {outlier.nearest_file && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Nearest: {outlier.nearest_file} ({Math.round(outlier.nearest_similarity * 100)}% similar)
                  </p>
                )}
                {outlier.confidence_factors && outlier.confidence_factors.length > 0 && (
                  <div className="mt-2">
                    <button
                      onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                      className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                    >
                      {isExpanded ? '▼' : '▶'} {isExpanded ? 'Hide' : 'Show'} confidence factors ({outlier.confidence_factors.length})
                    </button>
                    {isExpanded && (
                      <ul className="mt-2 space-y-1 text-xs text-muted-foreground pl-4">
                        {outlier.confidence_factors.map((factor, i) => (
                          <li key={i} className="list-disc list-inside">{factor}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function HotspotsTab({ hotspots }: { hotspots: CouplingHotspot[] }) {
  if (hotspots.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p className="text-emerald-400">✓ No coupling hotspots</p>
        <p className="text-sm mt-1">Good separation of concerns</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {hotspots.map((hotspot, idx) => (
        <div
          key={idx}
          className="p-4 rounded-lg bg-background/30 border-l-2 border-l-red-500 border border-border/50"
        >
          <div className="flex items-start gap-3">
            <span className="text-red-400 mt-0.5">⚡</span>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <code className="text-sm">{hotspot.file_path}</code>
                <Badge 
                  variant="outline" 
                  className={hotspot.clusters_connected >= 4 ? riskColors.critical : riskColors.high}
                >
                  {hotspot.clusters_connected} clusters
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">{hotspot.suggestion}</p>
              <div className="flex flex-wrap gap-1 mt-2">
                {hotspot.cluster_names.slice(0, 4).map((name, i) => (
                  <code key={i} className="text-xs px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">
                    {name}
                  </code>
                ))}
                {hotspot.cluster_names.length > 4 && (
                  <span className="text-xs text-muted-foreground">
                    +{hotspot.cluster_names.length - 4} more
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// Memoize component to prevent unnecessary re-renders
// Only re-render when actual props change
export const ArchitectureHealth = memo(ArchitectureHealthComponent, (prevProps, nextProps) => {
  // Deep comparison for cachedData since it's an object
  const prevCacheString = JSON.stringify(prevProps.cachedData)
  const nextCacheString = JSON.stringify(nextProps.cachedData)
  
  return (
    prevProps.repositoryId === nextProps.repositoryId &&
    prevProps.token === nextProps.token &&
    prevProps.className === nextProps.className &&
    prevCacheString === nextCacheString
  )
})

ArchitectureHealth.displayName = 'ArchitectureHealth'

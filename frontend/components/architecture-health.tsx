'use client'

import { useState, useMemo, memo } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  ArchitectureHealthResponse,
  ClusterInfo,
  OutlierInfo,
  CouplingHotspot
} from '@/lib/semantic-api'
import { AlertCircle, AlertTriangle, Info, ChevronDown, ChevronRight, FileCode, Zap, GitBranch } from 'lucide-react'

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
  hasSemanticCache?: boolean
}

const statusColors: Record<string, string> = {
  healthy: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  moderate: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  scattered: 'bg-red-500/10 text-red-400 border-red-500/20',
}

// Normalize cached data to ensure overall_score is always a number
function normalizeCachedData(cached: CachedArchitectureHealth | undefined): ArchitectureHealthResponse | null {
  if (!cached) return null
  return {
    ...cached,
    overall_score: cached.overall_score ?? cached.score ?? 0,
  }
}

function ArchitectureHealthComponent({ className, cachedData, hasSemanticCache = false }: ArchitectureHealthProps) {
  const [activeTab, setActiveTab] = useState<'issues' | 'hotspots'>('issues')

  // Normalize cached data
  const data = useMemo(() => normalizeCachedData(cachedData), [cachedData])

  // Memoize derived values to prevent recalculation on every render
  const computedValues = useMemo(() => {
    if (!data) return null
    // Handle both 'overall_score' and legacy 'score' field for backward compatibility
    const scoreValue = data.overall_score ?? (data as unknown as { score?: number }).score
    // Issues tab shows only outliers, Hotspots tab shows coupling_hotspots
    const outlierCount = data.outliers.length
    const hasScore = typeof scoreValue === 'number'
    const displayScore = hasScore ? scoreValue : 0

    return { scoreValue, outlierCount, hasScore, displayScore }
  }, [data])

  // Show message if no cached data available
  if (!data || !computedValues) {
    const isOldCache = hasSemanticCache && !cachedData

    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardContent className="p-6">
          <div className="text-center py-8">
            <div className="text-3xl mb-3">🏗️</div>
            <h3 className="text-base font-semibold mb-2">Architecture Health</h3>
            {isOldCache ? (
              <>
                <p className="text-sm text-muted-foreground mb-2">
                  Architecture analysis requires a newer analysis.
                </p>
                <p className="text-xs text-muted-foreground">
                  Re-run the analysis to view architecture health.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground mb-2">
                  Architecture data not available yet.
                </p>
                <p className="text-xs text-muted-foreground">
                  Run an analysis for this commit to view architecture health.
                </p>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  const { outlierCount, hasScore, displayScore } = computedValues

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Compact Header */}
      <div className="flex-none flex items-center justify-between px-3 pt-2 pb-2">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-primary" />
          <span className="text-xs font-medium">
            {data.total_files} files · {data.total_chunks} chunks
          </span>
          <Badge variant="outline" className={cn(
            'text-[10px] px-2 py-0.5 rounded-full',
            hasScore && displayScore >= 80 ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
              hasScore && displayScore >= 60 ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                'bg-red-500/10 text-red-400 border-red-500/20'
          )}>
            Score: {hasScore ? displayScore : '—'}/100
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant={activeTab === 'issues' ? 'default' : 'ghost'}
            size="sm"
            className="h-6 px-2 text-[10px]"
            onClick={() => setActiveTab('issues')}
          >
            Issues ({outlierCount})
          </Button>
          <Button
            variant={activeTab === 'hotspots' ? 'default' : 'ghost'}
            size="sm"
            className="h-6 px-2 text-[10px]"
            onClick={() => setActiveTab('hotspots')}
          >
            Coupling ({data.coupling_hotspots.length})
          </Button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {activeTab === 'issues' && (
          <IssuesTab outliers={data.outliers} />
        )}
        {activeTab === 'hotspots' && (
          <HotspotsTab hotspots={data.coupling_hotspots} />
        )}
      </div>
    </div>
  )
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function _ClustersTab({ clusters }: { clusters: ClusterInfo[] }) {
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

const priorityConfig = {
  critical: {
    icon: AlertCircle,
    color: 'text-white',
    iconColor: 'text-red-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Critical',
  },
  recommended: {
    icon: AlertTriangle,
    color: 'text-white',
    iconColor: 'text-amber-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Recommended',
  },
  informational: {
    icon: Info,
    color: 'text-white',
    iconColor: 'text-blue-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Info',
  },
}

function IssuesTab({ outliers }: { outliers: OutlierInfo[] }) {
  if (outliers.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-1 py-8">
        <span className="text-emerald-400 text-sm">✓ No outliers detected</span>
        <span className="text-xs">All code appears well-organized</span>
      </div>
    )
  }

  return (
    <div className="space-y-0 divide-y divide-border/50">
      {outliers.map((outlier, idx) => (
        <OutlierCard key={idx} outlier={outlier} />
      ))}
    </div>
  )
}

function OutlierCard({ outlier }: { outlier: OutlierInfo }) {
  const [isOpen, setIsOpen] = useState(true)
  const tier = outlier.tier || 'recommended'
  const config = priorityConfig[tier as keyof typeof priorityConfig] || priorityConfig.recommended
  const PriorityIcon = config.icon
  const confidencePercent = Math.round((outlier.confidence || 0.5) * 100)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="w-full p-3 hover:bg-muted/30 transition-colors text-left group">
          <div className="flex items-start gap-3">
            <div className={cn('p-1.5 rounded-md shrink-0', config.bg)}>
              <PriorityIcon className={cn('h-3.5 w-3.5', config.iconColor)} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[9px] uppercase tracking-wider font-bold px-1.5 py-0 rounded-full border',
                    config.bg,
                    config.border,
                    config.color
                  )}
                >
                  {config.label}
                </Badge>
                <span className="flex items-center gap-1 text-[10px] text-white">
                  <Zap className="h-3 w-3 text-purple-400" />
                  Outlier
                </span>
                {outlier.chunk_type && (
                  <Badge variant="outline" className="text-[9px] px-1.5 py-0 rounded-full bg-transparent text-white border-white/30">
                    {outlier.chunk_type}
                  </Badge>
                )}
                <span className="text-[10px] text-muted-foreground">
                  {confidencePercent}% confidence
                </span>
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {outlier.chunk_name || outlier.file_path.split('/').pop()}
              </h4>
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono mt-1">
                <FileCode className="h-2.5 w-2.5" />
                <span className="truncate">{outlier.file_path}</span>
              </div>
            </div>
            {isOpen ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            )}
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-3 pb-3 space-y-2">
          <p className="text-xs text-muted-foreground">{outlier.suggestion}</p>
          {outlier.nearest_file && (
            <div className="text-[10px] text-muted-foreground">
              Nearest: {outlier.nearest_file} ({Math.round(outlier.nearest_similarity * 100)}% similar)
            </div>
          )}
          {outlier.confidence_factors && outlier.confidence_factors.length > 0 && (
            <div className="space-y-1">
              <div className="text-[10px] text-muted-foreground font-medium">Confidence factors:</div>
              <ul className="text-[10px] text-muted-foreground space-y-0.5 pl-3">
                {outlier.confidence_factors.map((factor, i) => (
                  <li key={i} className="list-disc list-inside">{factor}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function HotspotsTab({ hotspots }: { hotspots: CouplingHotspot[] }) {
  if (hotspots.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-1 py-8">
        <span className="text-emerald-400 text-sm">✓ No coupling hotspots</span>
        <span className="text-xs">Good separation of concerns</span>
      </div>
    )
  }

  return (
    <div className="space-y-0 divide-y divide-border/50">
      {hotspots.map((hotspot, idx) => (
        <CouplingHotspotCard key={idx} hotspot={hotspot} />
      ))}
    </div>
  )
}

function CouplingHotspotCard({ hotspot }: { hotspot: CouplingHotspot }) {
  const [isOpen, setIsOpen] = useState(true)
  const level = hotspot.clusters_connected >= 4 ? 'critical' : 'recommended'
  const config = priorityConfig[level as keyof typeof priorityConfig]
  const PriorityIcon = config.icon

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="w-full p-3 hover:bg-muted/30 transition-colors text-left group">
          <div className="flex items-start gap-3">
            <div className={cn('p-1.5 rounded-md shrink-0', config.bg)}>
              <PriorityIcon className={cn('h-3.5 w-3.5', config.iconColor)} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[9px] uppercase tracking-wider font-bold px-1.5 py-0 rounded-full border',
                    config.bg,
                    config.border,
                    config.color
                  )}
                >
                  {config.label}
                </Badge>
                <span className="flex items-center gap-1 text-[10px] text-white">
                  <GitBranch className="h-3 w-3 text-orange-400" />
                  Coupling
                </span>
                <Badge variant="outline" className="text-[9px] px-1.5 py-0 rounded-full bg-transparent text-white border-white/30">
                  {hotspot.clusters_connected} clusters
                </Badge>
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {hotspot.file_path.split('/').pop()}
              </h4>
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono mt-1">
                <FileCode className="h-2.5 w-2.5" />
                <span className="truncate">{hotspot.file_path}</span>
              </div>
            </div>
            {isOpen ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            )}
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-3 pb-3 space-y-2">
          <p className="text-xs text-muted-foreground">{hotspot.suggestion}</p>
          <div className="flex flex-wrap gap-1">
            {hotspot.cluster_names.slice(0, 6).map((name, i) => (
              <Badge key={i} variant="outline" className="text-[9px] px-1.5 py-0 rounded-full bg-primary/10 text-primary border-primary/30">
                {name}
              </Badge>
            ))}
            {hotspot.cluster_names.length > 6 && (
              <span className="text-[10px] text-muted-foreground">
                +{hotspot.cluster_names.length - 6} more
              </span>
            )}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
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

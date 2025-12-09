'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Flame, ChevronDown, ChevronRight, FileCode, AlertCircle, AlertTriangle, Info, Zap } from 'lucide-react'

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

// Priority config matching AI Scan pattern
const priorityConfig = {
  critical: {
    icon: AlertCircle,
    color: 'text-white',
    iconColor: 'text-red-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Critical',
  },
  high: {
    icon: AlertTriangle,
    color: 'text-white',
    iconColor: 'text-orange-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'High',
  },
  medium: {
    icon: AlertTriangle,
    color: 'text-white',
    iconColor: 'text-amber-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Medium',
  },
  low: {
    icon: Info,
    color: 'text-white',
    iconColor: 'text-blue-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Low',
  },
}

export function TechDebtHeatmap({ className, cachedData, hasSemanticCache = false }: TechDebtHeatmapProps) {
  const [view, setView] = useState<'hotspots' | 'clusters'>('hotspots')

  const hasCachedData = cachedData && (Array.isArray(cachedData.clusters) || Array.isArray(cachedData.coupling_hotspots))

  if (!hasCachedData) {
    const isOldCache = hasSemanticCache && !cachedData

    return (
      <div className={cn('flex flex-col items-center justify-center h-full text-muted-foreground gap-2 p-8', className)}>
        <Flame className="w-8 h-8 text-muted-foreground/30" />
        <span className="text-sm">{isOldCache ? 'Re-run analysis for tech debt data' : 'No tech debt data available'}</span>
      </div>
    )
  }

  const overallScore = cachedData.overall_score ?? 50
  const debtScore = 100 - overallScore
  const hotspots = buildHotspots(cachedData)
  const clusterHealth = buildClusterHealth(cachedData.clusters || [])

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex-none flex items-center justify-between px-3 pt-2 pb-2">
        <div className="flex items-center gap-2">
          <Flame className="h-4 w-4 text-primary" />
          <span className="text-xs font-medium">
            Debt Score: {debtScore}
          </span>
          <Badge variant="outline" className={cn(
            'text-[10px] px-2 py-0.5 rounded-full',
            debtScore <= 20 ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
              debtScore <= 40 ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                debtScore <= 60 ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                  'bg-red-500/10 text-red-400 border-red-500/20'
          )}>
            {debtScore <= 20 ? 'Low' : debtScore <= 40 ? 'Moderate' : debtScore <= 60 ? 'High' : 'Critical'}
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant={view === 'hotspots' ? 'default' : 'ghost'}
            size="sm"
            className="h-6 px-2 text-[10px]"
            onClick={() => setView('hotspots')}
          >
            Hotspots ({hotspots.length})
          </Button>
          <Button
            variant={view === 'clusters' ? 'default' : 'ghost'}
            size="sm"
            className="h-6 px-2 text-[10px]"
            onClick={() => setView('clusters')}
          >
            Clusters ({clusterHealth.length})
          </Button>
        </div>
      </div>

      {/* Content */}
      {view === 'hotspots' ? (
        <HotspotsView hotspots={hotspots} />
      ) : (
        <ClustersView clusters={clusterHealth} />
      )}
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

  for (const hotspot of data.coupling_hotspots || []) {
    hotspots.push({
      file_path: hotspot.file_path,
      risk: hotspot.clusters_connected >= 4 ? 'critical' : 'high',
      suggestion: hotspot.suggestion,
      bridges_clusters: hotspot.clusters_connected,
      cohesion: null,
    })
  }

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
    avg_complexity: 0,
  }))
}

function HotspotsView({ hotspots }: { hotspots: TechDebtHotspot[] }) {
  if (hotspots.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-1">
        <span className="text-emerald-400 text-sm">✓ No debt hotspots</span>
        <span className="text-xs">Codebase is in good shape</span>
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-border/50">
      {hotspots.map((hotspot, idx) => (
        <HotspotCard key={idx} hotspot={hotspot} />
      ))}
    </div>
  )
}

function HotspotCard({ hotspot }: { hotspot: TechDebtHotspot }) {
  const [isOpen, setIsOpen] = useState(true)
  const config = priorityConfig[hotspot.risk as keyof typeof priorityConfig] || priorityConfig.medium
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
                  <Zap className="h-3 w-3 text-orange-400" />
                  Tech Debt
                </span>
                {hotspot.bridges_clusters > 0 && (
                  <Badge variant="outline" className="text-[9px] px-1.5 py-0 rounded-full bg-transparent text-white border-white/30">
                    {hotspot.bridges_clusters} clusters
                  </Badge>
                )}
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
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
            {hotspot.bridges_clusters > 0 && (
              <span>Bridges {hotspot.bridges_clusters} clusters</span>
            )}
            {hotspot.cohesion !== null && (
              <span>Cohesion: {Math.round(hotspot.cohesion * 100)}%</span>
            )}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function ClustersView({ clusters }: { clusters: ClusterHealthInfo[] }) {
  if (clusters.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-1">
        <span className="text-sm">No cluster data available</span>
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-border/50">
      {clusters.map((cluster, idx) => (
        <ClusterCard key={idx} cluster={cluster} />
      ))}
    </div>
  )
}

function ClusterCard({ cluster }: { cluster: ClusterHealthInfo }) {
  const [isOpen, setIsOpen] = useState(true)
  const level = cluster.health === 'good' ? 'low' : cluster.health === 'moderate' ? 'medium' : 'high'
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
                  {cluster.health}
                </Badge>
                <span className="flex items-center gap-1 text-[10px] text-white">
                  <Flame className="h-3 w-3 text-purple-400" />
                  Cluster
                </span>
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {cluster.cluster}
              </h4>
            </div>
            <div className="text-right shrink-0">
              <span className={cn(
                'text-sm font-bold',
                cluster.cohesion >= 0.7 ? 'text-emerald-400' :
                  cluster.cohesion >= 0.5 ? 'text-amber-400' : 'text-red-400'
              )}>
                {Math.round(cluster.cohesion * 100)}%
              </span>
              <div className="text-[10px] text-muted-foreground">cohesion</div>
            </div>
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-3 pb-3 space-y-2">
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
            <span>Cohesion: {Math.round(cluster.cohesion * 100)}%</span>
            {cluster.avg_complexity > 0 && (
              <span>Avg Complexity: {cluster.avg_complexity.toFixed(1)}</span>
            )}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

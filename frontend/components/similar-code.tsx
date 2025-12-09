'use client'

import { useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Copy, ChevronDown, ChevronRight, FileCode, AlertCircle, AlertTriangle, Info } from 'lucide-react'

interface CachedSimilarCodeData {
  groups?: Array<{
    similarity: number
    suggestion: string
    chunks: Array<{
      file: string
      name: string
      lines: [number, number]
      chunk_type: string
    }>
  }>
  total_groups: number
  potential_loc_reduction: number
}

interface SimilarCodeProps {
  repositoryId: string
  token: string
  className?: string
  cachedData?: CachedSimilarCodeData
  hasSemanticCache?: boolean
}

// Priority config matching AI Scan pattern
const priorityConfig = {
  high: {
    icon: AlertCircle,
    color: 'text-white',
    iconColor: 'text-red-500',
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

function getSimilarityLevel(similarity: number): 'high' | 'medium' | 'low' {
  if (similarity >= 0.95) return 'high'
  if (similarity >= 0.90) return 'medium'
  return 'low'
}

export function SimilarCode({ className, cachedData, hasSemanticCache = false }: SimilarCodeProps) {
  const [threshold, setThreshold] = useState(0.85)

  // Filter groups by threshold from cached data
  const { groups, potentialLoc } = useMemo(() => {
    if (!cachedData || !cachedData.groups) {
      return { groups: [], potentialLoc: 0 }
    }

    const filteredGroups = cachedData.groups.filter(g => g.similarity >= threshold)

    const loc = filteredGroups.reduce((sum, g) => {
      const groupLoc = g.chunks.slice(1).reduce((chunkSum, c) => {
        return chunkSum + (c.lines[1] - c.lines[0])
      }, 0)
      return sum + groupLoc
    }, 0)

    return { groups: filteredGroups, potentialLoc: loc }
  }, [cachedData, threshold])

  const hasSimilarCodeData = cachedData && Array.isArray(cachedData.groups)

  if (!hasSimilarCodeData) {
    const isOldCache = hasSemanticCache && !cachedData

    return (
      <div className={cn('flex flex-col items-center justify-center h-full text-muted-foreground gap-2 p-8', className)}>
        <Copy className="w-8 h-8 text-muted-foreground/30" />
        <span className="text-sm">{isOldCache ? 'Re-run analysis for duplicate detection' : 'No duplicate data available'}</span>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex-none flex items-center justify-between px-3 pt-2 pb-2">
        <div className="flex items-center gap-2">
          <Copy className="h-4 w-4 text-primary" />
          <span className="text-xs font-medium">
            {groups.length} duplicate group{groups.length !== 1 ? 's' : ''}
          </span>
          {potentialLoc > 0 && (
            <Badge variant="outline" className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
              ~{potentialLoc} LOC reduction
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          {[0.80, 0.85, 0.90, 0.95].map((t) => (
            <Button
              key={t}
              variant={threshold === t ? 'default' : 'ghost'}
              size="sm"
              className="h-6 px-2 text-[10px]"
              onClick={() => setThreshold(t)}
            >
              {Math.round(t * 100)}%
            </Button>
          ))}
        </div>
      </div>

      {/* Results list */}
      {groups.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-1">
          <span className="text-emerald-400 text-sm">✓ No duplicates found</span>
          <span className="text-xs">No code above {Math.round(threshold * 100)}% similarity</span>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-border/50">
          {groups.map((group, idx) => (
            <DuplicateCard key={idx} group={group} />
          ))}
        </div>
      )}
    </div>
  )
}

interface DuplicateCardProps {
  group: {
    similarity: number
    suggestion: string
    chunks: Array<{
      file: string
      name: string
      lines: [number, number]
      chunk_type: string
    }>
  }
}

function DuplicateCard({ group }: DuplicateCardProps) {
  const [isOpen, setIsOpen] = useState(true)
  const level = getSimilarityLevel(group.similarity)
  const config = priorityConfig[level]
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
                  {Math.round(group.similarity * 100)}% Similar
                </Badge>
                <span className="flex items-center gap-1 text-[10px] text-white">
                  <Copy className="h-3 w-3 text-purple-400" />
                  {group.chunks.length} chunks
                </span>
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {group.suggestion}
              </h4>
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono mt-1">
                <FileCode className="h-2.5 w-2.5" />
                <span className="truncate">{group.chunks[0]?.file.split('/').pop()}</span>
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
          {group.chunks.map((chunk, i) => (
            <div
              key={i}
              className="flex items-center gap-2 p-2 rounded bg-muted/30 text-xs"
            >
              <FileCode className="h-3 w-3 text-muted-foreground shrink-0" />
              <code className="flex-1 truncate text-muted-foreground">{chunk.file}</code>
              {chunk.name && (
                <span className="font-medium text-foreground">{chunk.name}</span>
              )}
              <Badge variant="outline" className="text-[9px] px-1.5 py-0 rounded-full bg-transparent text-white border-white/30">
                {chunk.chunk_type}
              </Badge>
              <span className="text-[10px] text-muted-foreground shrink-0">
                L{chunk.lines[0]}-{chunk.lines[1]}
              </span>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

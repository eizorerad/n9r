'use client'

import { useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

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

export function SimilarCode({ className, cachedData, hasSemanticCache = false }: SimilarCodeProps) {
  const [threshold, setThreshold] = useState(0.85)

  // Filter groups by threshold from cached data
  const { groups, potentialLoc } = useMemo(() => {
    if (!cachedData || !cachedData.groups) {
      return { groups: [], potentialLoc: 0 }
    }

    // Filter groups that meet the threshold
    const filteredGroups = cachedData.groups.filter(g => g.similarity >= threshold)
    
    // Recalculate LOC reduction for filtered groups
    const loc = filteredGroups.reduce((sum, g) => {
      const groupLoc = g.chunks.slice(1).reduce((chunkSum, c) => {
        return chunkSum + (c.lines[1] - c.lines[0])
      }, 0)
      return sum + groupLoc
    }, 0)

    return { groups: filteredGroups, potentialLoc: loc }
  }, [cachedData, threshold])

  const getSimilarityColor = (similarity: number) => {
    if (similarity >= 0.95) return 'text-red-400'
    if (similarity >= 0.90) return 'text-orange-400'
    return 'text-amber-400'
  }

  // Check if similar code data exists in cache
  // cachedData.groups being undefined means the analysis hasn't computed similar code yet
  const hasSimilarCodeData = cachedData && Array.isArray(cachedData.groups)

  // Show message if no cached data available or similar code wasn't computed
  if (!hasSimilarCodeData) {
    // Different message depending on whether semantic cache exists
    const isOldCache = hasSemanticCache && !cachedData
    
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardContent className="p-6">
          <div className="text-center py-8">
            <div className="text-3xl mb-3">🔍</div>
            <h3 className="text-base font-semibold mb-2">Similar Code Detection</h3>
            {isOldCache ? (
              <>
                <p className="text-sm text-muted-foreground mb-2">
                  Similar code detection requires a newer analysis.
                </p>
                <p className="text-xs text-muted-foreground">
                  Re-run the analysis to enable duplicate detection.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground mb-2">
                  Similar code data not available yet.
                </p>
                <p className="text-xs text-muted-foreground">
                  Run an analysis for this commit to detect code duplicates.
                </p>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn('glass-panel border-border/50', className)}>
      <CardContent className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-semibold">Similar Code Detection</h3>
            <p className="text-sm text-muted-foreground">
              Find potential duplicates for DRY refactoring
            </p>
          </div>
          {potentialLoc > 0 && (
            <div className="text-right">
              <div className="text-2xl font-bold text-emerald-400">~{potentialLoc}</div>
              <div className="text-xs text-muted-foreground">LOC reduction</div>
            </div>
          )}
        </div>

        {/* Threshold selector */}
        <div className="flex items-center gap-2 mb-4">
          <span className="text-sm text-muted-foreground">Threshold:</span>
          {[0.80, 0.85, 0.90, 0.95].map((t) => (
            <Button
              key={t}
              variant={threshold === t ? 'default' : 'outline'}
              size="sm"
              onClick={() => setThreshold(t)}
            >
              {Math.round(t * 100)}%
            </Button>
          ))}
        </div>

        {/* Results */}
        {groups.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p className="text-emerald-400">✓ No duplicates found</p>
            <p className="text-sm mt-1">
              No code chunks above {Math.round(threshold * 100)}% similarity
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {groups.map((group, idx) => (
              <div
                key={idx}
                className="p-4 rounded-lg bg-background/30 border border-border/50"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className={cn('text-lg font-bold', getSimilarityColor(group.similarity))}>
                      {Math.round(group.similarity * 100)}%
                    </span>
                    <span className="text-sm text-muted-foreground">similar</span>
                    <Badge variant="outline" className="text-xs">
                      {group.chunks.length} chunks
                    </Badge>
                  </div>
                  <span className="text-sm text-muted-foreground">{group.suggestion}</span>
                </div>

                <div className="space-y-2">
                  {group.chunks.map((chunk, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-3 p-2 rounded bg-background/50"
                    >
                      <code className="text-sm flex-1 truncate">{chunk.file}</code>
                      {chunk.name && (
                        <span className="text-sm font-medium">{chunk.name}</span>
                      )}
                      <Badge variant="outline" className="text-xs shrink-0">
                        {chunk.chunk_type}
                      </Badge>
                      <span className="text-xs text-muted-foreground shrink-0">
                        L{chunk.lines[0]}-{chunk.lines[1]}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

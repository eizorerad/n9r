'use client'

import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { semanticApi, SimilarCodeGroup } from '@/lib/semantic-api'

interface SimilarCodeProps {
  repositoryId: string
  token: string
  className?: string
}

export function SimilarCode({ repositoryId, token, className }: SimilarCodeProps) {
  const [groups, setGroups] = useState<SimilarCodeGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [threshold, setThreshold] = useState(0.85)
  const [potentialLoc, setPotentialLoc] = useState(0)

  useEffect(() => {
    fetchData()
  }, [repositoryId, token, threshold])

  const fetchData = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await semanticApi.similarCode(token, repositoryId, threshold, 20)
      setGroups(response.groups)
      setPotentialLoc(response.potential_loc_reduction)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const getSimilarityColor = (similarity: number) => {
    if (similarity >= 0.95) return 'text-red-400'
    if (similarity >= 0.90) return 'text-orange-400'
    return 'text-amber-400'
  }

  if (loading) {
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardContent className="p-6">
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            <span className="ml-3 text-muted-foreground">Finding similar code...</span>
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

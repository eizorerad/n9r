'use client'

import { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { semanticApi, SemanticSearchResult } from '@/lib/semantic-api'

interface SemanticSearchProps {
  repositoryId: string
  token: string
  className?: string
  onResultClick?: (result: SemanticSearchResult) => void
}

const chunkTypeColors: Record<string, string> = {
  function: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  method: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  class: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  module: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  block: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
}

export function SemanticSearch({ 
  repositoryId, 
  token, 
  className,
  onResultClick 
}: SemanticSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SemanticSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchTime, setSearchTime] = useState<number | null>(null)

  const handleSearch = useCallback(async () => {
    if (!query.trim() || query.length < 2) return

    setLoading(true)
    setError(null)
    const startTime = Date.now()

    try {
      const response = await semanticApi.search(token, repositoryId, query, 20)
      setResults(response.results)
      setSearchTime(Date.now() - startTime)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [query, token, repositoryId])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const getSimilarityColor = (similarity: number) => {
    if (similarity >= 0.8) return 'text-emerald-400'
    if (similarity >= 0.6) return 'text-blue-400'
    if (similarity >= 0.4) return 'text-amber-400'
    return 'text-slate-400'
  }

  return (
    <Card className={cn('glass-panel border-border/50', className)}>
      <CardContent className="p-6">
        {/* Search Header */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-2">Semantic Code Search</h3>
          <p className="text-sm text-muted-foreground">
            Search your codebase using natural language
          </p>
        </div>

        {/* Search Input */}
        <div className="flex gap-2 mb-4">
          <Input
            placeholder="e.g., 'user authentication', 'database connection'"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-background/50"
          />
          <Button 
            onClick={handleSearch} 
            disabled={loading || query.length < 2}
          >
            {loading ? 'Searching...' : 'Search'}
          </Button>
        </div>

        {/* Search Stats */}
        {searchTime !== null && (
          <div className="text-xs text-muted-foreground mb-4">
            Found {results.length} results in {searchTime}ms
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="p-3 mb-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Results */}
        <div className="space-y-3 max-h-[500px] overflow-y-auto">
          {results.map((result, index) => (
            <div
              key={index}
              className={cn(
                'p-4 rounded-lg bg-background/30 border border-border/50',
                'hover:bg-background/50 transition-colors cursor-pointer'
              )}
              onClick={() => onResultClick?.(result)}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* File path and name */}
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <code className="text-sm text-muted-foreground truncate">
                      {result.file_path}
                    </code>
                    {result.qualified_name && (
                      <>
                        <span className="text-muted-foreground/50">→</span>
                        <code className="text-sm font-medium text-foreground">
                          {result.qualified_name}
                        </code>
                      </>
                    )}
                  </div>

                  {/* Content preview */}
                  {result.content && (
                    <pre className="text-xs bg-background/50 p-2 rounded border border-border/30 overflow-x-auto whitespace-pre-wrap max-h-24">
                      {result.content.length > 200
                        ? result.content.substring(0, 200) + '...'
                        : result.content}
                    </pre>
                  )}

                  {/* Metadata */}
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    {result.chunk_type && (
                      <Badge 
                        variant="outline" 
                        className={cn('text-xs', chunkTypeColors[result.chunk_type] || chunkTypeColors.block)}
                      >
                        {result.chunk_type}
                      </Badge>
                    )}
                    {result.language && (
                      <Badge variant="outline" className="text-xs">
                        {result.language}
                      </Badge>
                    )}
                    {result.line_start && result.line_end && (
                      <span className="text-xs text-muted-foreground">
                        Lines {result.line_start}-{result.line_end}
                      </span>
                    )}
                  </div>
                </div>

                {/* Similarity score */}
                <div className="text-right shrink-0">
                  <div className={cn('text-xl font-bold', getSimilarityColor(result.similarity))}>
                    {Math.round(result.similarity * 100)}%
                  </div>
                  <div className="text-xs text-muted-foreground">match</div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Empty state */}
        {!loading && results.length === 0 && query && (
          <div className="text-center py-8 text-muted-foreground">
            <p>No results found for "{query}"</p>
            <p className="text-sm mt-1">Try different keywords</p>
          </div>
        )}

        {/* Example queries */}
        {!query && (
          <div className="mt-4 p-4 rounded-lg bg-blue-500/5 border border-blue-500/10">
            <p className="text-sm font-medium text-blue-400 mb-2">Example searches:</p>
            <div className="flex flex-wrap gap-2">
              {['user authentication', 'database connection', 'error handling', 'API endpoints'].map((example) => (
                <button
                  key={example}
                  onClick={() => setQuery(example)}
                  className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

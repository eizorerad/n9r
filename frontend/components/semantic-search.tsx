'use client'

import { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { semanticApi, SemanticSearchResult } from '@/lib/semantic-api'
import { Search, ChevronDown, ChevronRight, FileCode, Code, Sparkles, AlertTriangle, Info } from 'lucide-react'

interface SemanticSearchProps {
  repositoryId: string
  token: string
  className?: string
  onResultClick?: (result: SemanticSearchResult) => void
}

// Priority config matching AI Scan pattern
const priorityConfig = {
  high: {
    icon: Sparkles,
    color: 'text-white',
    iconColor: 'text-emerald-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Best',
  },
  medium: {
    icon: AlertTriangle,
    color: 'text-white',
    iconColor: 'text-blue-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Good',
  },
  low: {
    icon: Info,
    color: 'text-white',
    iconColor: 'text-slate-400',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Match',
  },
}

// Category config for chunk types
const chunkTypeConfig: Record<string, { icon: typeof Code; iconColor: string }> = {
  function: { icon: Code, iconColor: 'text-blue-400' },
  method: { icon: Code, iconColor: 'text-purple-400' },
  class: { icon: Code, iconColor: 'text-emerald-400' },
  module: { icon: Code, iconColor: 'text-amber-400' },
  block: { icon: Code, iconColor: 'text-slate-400' },
}

function getSimilarityLevel(similarity: number): 'high' | 'medium' | 'low' {
  if (similarity >= 0.8) return 'high'
  if (similarity >= 0.6) return 'medium'
  return 'low'
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

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header with search */}
      <div className="flex-none px-3 pt-2 pb-3 space-y-2">
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 text-primary" />
          <span className="text-xs font-medium">Semantic Search</span>
          {searchTime !== null && (
            <span className="text-[10px] text-muted-foreground">
              {results.length} results in {searchTime}ms
            </span>
          )}
        </div>

        {/* Search Input */}
        <div className="flex gap-2">
          <Input
            placeholder="Search with natural language..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 h-8 text-xs bg-muted/30"
          />
          <Button
            onClick={handleSearch}
            disabled={loading || query.length < 2}
            size="sm"
            className="h-8 px-3"
          >
            {loading ? '...' : 'Search'}
          </Button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex-none mx-3 mb-2 p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Results */}
      {results.length > 0 ? (
        <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-border/50">
          {results.map((result, index) => (
            <SearchResultCard
              key={index}
              result={result}
              onClick={() => onResultClick?.(result)}
            />
          ))}
        </div>
      ) : !loading && query && searchTime !== null ? (
        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-1">
          <span className="text-sm">No results for &quot;{query}&quot;</span>
          <span className="text-xs">Try different keywords</span>
        </div>
      ) : !query ? (
        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3 p-4">
          <Search className="w-8 h-8 text-muted-foreground/30" />
          <span className="text-xs text-center">Search your codebase using natural language</span>
          <div className="flex flex-wrap gap-1 justify-center">
            {['user authentication', 'database connection', 'error handling', 'API endpoints'].map((example) => (
              <button
                key={example}
                onClick={() => setQuery(example)}
                className="text-[10px] px-2 py-1 rounded bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

interface SearchResultCardProps {
  result: SemanticSearchResult
  onClick: () => void
}

function SearchResultCard({ result, onClick }: SearchResultCardProps) {
  const [isOpen, setIsOpen] = useState(true)
  const level = getSimilarityLevel(result.similarity)
  const config = priorityConfig[level]
  const PriorityIcon = config.icon
  const chunkConfig = chunkTypeConfig[result.chunk_type || 'block'] || chunkTypeConfig.block
  const ChunkIcon = chunkConfig.icon

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="w-full p-3 hover:bg-muted/30 transition-colors text-left group" onClick={onClick}>
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
                  {Math.round(result.similarity * 100)}%
                </Badge>
                {result.chunk_type && (
                  <span className="flex items-center gap-1 text-[10px] text-white">
                    <ChunkIcon className={cn('h-3 w-3', chunkConfig.iconColor)} />
                    {result.chunk_type}
                  </span>
                )}
                {result.language && (
                  <Badge variant="outline" className="text-[9px] px-1.5 py-0 rounded-full bg-transparent text-white border-white/30">
                    {result.language}
                  </Badge>
                )}
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {result.qualified_name || result.file_path.split('/').pop()}
              </h4>
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono mt-1">
                <FileCode className="h-2.5 w-2.5" />
                <span className="truncate">{result.file_path}</span>
                {result.line_start && (
                  <span className="text-muted-foreground/60">:{result.line_start}</span>
                )}
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
          {result.content && (
            <pre className="text-[10px] bg-muted/50 p-2 rounded-md overflow-x-auto font-mono max-h-24">
              {result.content.length > 300
                ? result.content.substring(0, 300) + '...'
                : result.content}
            </pre>
          )}
          {result.line_start && result.line_end && (
            <div className="text-[10px] text-muted-foreground">
              Lines {result.line_start}-{result.line_end}
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

'use client'

import { cn } from '@/lib/utils'
import { Info } from 'lucide-react'

interface VCIHistoryPoint {
  date: string
  vci_score: number
  grade: string
  commit_sha: string
}

interface VCIScoreCardCompactProps {
  score: number | null
  grade: string | null
  trend?: 'improving' | 'stable' | 'declining'
  historyData?: VCIHistoryPoint[]
  className?: string
}

export function VCIScoreCardCompact({
  score,
  grade,
  className
}: VCIScoreCardCompactProps) {
  const displayScore = score !== null && typeof score === 'number' ? score.toFixed(1) : '—'

  return (
    <div className={cn(
      'glass-panel border border-border/50 rounded-xl overflow-hidden max-w-[160px]',
      className
    )}>
      <div className="relative p-3">
        {/* Header with info icon */}
        <div className="flex items-center gap-1.5 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50" />
          <span className="text-xs font-medium text-muted-foreground">Code Health</span>
          <span 
            className="cursor-help"
            title="VCI = Complexity (25%) + Duplication (25%) + Heuristics (30%) + Architecture (20%)"
          >
            <Info className="h-3 w-3 text-muted-foreground/50" />
          </span>
        </div>

        {/* Score display */}
        <div className="flex items-center gap-2">
          <div className="min-w-0">
            <div className="flex items-baseline gap-0.5">
              <span className="text-2xl font-bold tracking-tight text-foreground">
                {displayScore}
              </span>
              <span className="text-xs text-muted-foreground">/100</span>
            </div>
            <p className="text-[10px] text-muted-foreground truncate">
              {grade === 'A' && 'Excellent'}
              {grade === 'B' && 'Good'}
              {grade === 'C' && 'Fair'}
              {grade === 'D' && 'Needs Work'}
              {grade === 'F' && 'Critical'}
              {!grade && 'No data'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

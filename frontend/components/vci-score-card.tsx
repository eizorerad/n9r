'use client'

import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'

interface VCIScoreCardProps {
  score: number | null
  grade: string | null
  trend?: 'improving' | 'stable' | 'declining'
  className?: string
}

const gradeColors: Record<string, string> = {
  A: 'from-emerald-500 to-emerald-600',
  B: 'from-blue-500 to-cyan-600',
  C: 'from-amber-500 to-orange-600',
  D: 'from-orange-500 to-red-500',
  F: 'from-red-600 to-rose-700',
}

const gradeTextColors: Record<string, string> = {
  A: 'text-emerald-400',
  B: 'text-blue-400',
  C: 'text-amber-400',
  D: 'text-orange-400',
  F: 'text-red-400',
}

export function VCIScoreCard({ score, grade, trend, className }: VCIScoreCardProps) {
  const displayGrade = grade || '—'
  const displayScore = score !== null ? score : '—'
  const gradientClass = grade ? gradeColors[grade] : 'from-muted to-muted/50'
  const textColor = grade ? gradeTextColors[grade] : 'text-muted-foreground'

  return (
    <Card className={cn('relative overflow-hidden border-border/50 glass-panel', className)}>
      {/* Background gradient */}
      <div className={cn(
        'absolute inset-0 opacity-5 bg-gradient-to-br',
        gradientClass
      )} />

      <CardContent className="relative p-8">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2">Vibe-Code Index</p>
            <div className="flex items-baseline gap-2">
              <span className={cn('text-6xl font-bold tracking-tighter', textColor)}>
                {displayScore}
              </span>
              <span className="text-xl text-muted-foreground/60 font-medium">/100</span>
            </div>
          </div>

          <div className={cn(
            'w-24 h-24 rounded-2xl flex items-center justify-center bg-gradient-to-br shadow-lg',
            gradientClass
          )}>
            <span className="text-4xl font-bold text-white shadow-sm">{displayGrade}</span>
          </div>
        </div>

        {trend && (
          <div className="mt-6 flex items-center gap-2 p-2 rounded-lg bg-background/40 w-fit border border-border/50">
            {trend === 'improving' && (
              <>
                <span className="text-emerald-400">↑</span>
                <span className="text-sm text-emerald-400 font-medium">Improving</span>
              </>
            )}
            {trend === 'stable' && (
              <>
                <span className="text-muted-foreground">→</span>
                <span className="text-sm text-muted-foreground font-medium">Stable</span>
              </>
            )}
            {trend === 'declining' && (
              <>
                <span className="text-red-400">↓</span>
                <span className="text-sm text-red-400 font-medium">Needs attention</span>
              </>
            )}
          </div>
        )}

        {grade && (
          <p className="mt-4 text-sm text-muted-foreground">
            {grade === 'A' && 'Excellent code health! Well maintained.'}
            {grade === 'B' && 'Good code health. Minor improvements possible.'}
            {grade === 'C' && 'Fair code health. Some areas need attention.'}
            {grade === 'D' && 'Below average. Improvements recommended.'}
            {grade === 'F' && 'Poor health. Immediate attention required.'}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

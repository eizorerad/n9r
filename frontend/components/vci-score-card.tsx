'use client'

import { cn } from '@/lib/utils'

interface VCIScoreCardProps {
  score: number | null
  grade: string | null
  trend?: 'improving' | 'stable' | 'declining'
  className?: string
}

const gradeColors: Record<string, string> = {
  A: 'from-green-500 to-emerald-600',
  B: 'from-blue-500 to-cyan-600',
  C: 'from-yellow-500 to-amber-600',
  D: 'from-orange-500 to-red-500',
  F: 'from-red-600 to-rose-700',
}

const gradeTextColors: Record<string, string> = {
  A: 'text-green-400',
  B: 'text-blue-400',
  C: 'text-yellow-400',
  D: 'text-orange-400',
  F: 'text-red-400',
}

export function VCIScoreCard({ score, grade, trend, className }: VCIScoreCardProps) {
  const displayGrade = grade || '—'
  const displayScore = score !== null ? score : '—'
  const gradientClass = grade ? gradeColors[grade] : 'from-gray-600 to-gray-700'
  const textColor = grade ? gradeTextColors[grade] : 'text-gray-400'

  return (
    <div className={cn('relative overflow-hidden rounded-xl border border-gray-800 bg-gray-900/50', className)}>
      {/* Background gradient */}
      <div className={cn(
        'absolute inset-0 opacity-10 bg-gradient-to-br',
        gradientClass
      )} />
      
      <div className="relative p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-400 mb-1">Vibe-Code Index</p>
            <div className="flex items-baseline gap-2">
              <span className={cn('text-5xl font-bold', textColor)}>
                {displayScore}
              </span>
              <span className="text-lg text-gray-500">/100</span>
            </div>
          </div>
          
          <div className={cn(
            'w-20 h-20 rounded-full flex items-center justify-center bg-gradient-to-br',
            gradientClass
          )}>
            <span className="text-3xl font-bold text-white">{displayGrade}</span>
          </div>
        </div>
        
        {trend && (
          <div className="mt-4 flex items-center gap-2">
            {trend === 'improving' && (
              <>
                <span className="text-green-400">↑</span>
                <span className="text-sm text-green-400">Improving</span>
              </>
            )}
            {trend === 'stable' && (
              <>
                <span className="text-gray-400">→</span>
                <span className="text-sm text-gray-400">Stable</span>
              </>
            )}
            {trend === 'declining' && (
              <>
                <span className="text-red-400">↓</span>
                <span className="text-sm text-red-400">Needs attention</span>
              </>
            )}
          </div>
        )}
        
        {grade && (
          <p className="mt-3 text-sm text-gray-500">
            {grade === 'A' && 'Excellent code health! Well maintained.'}
            {grade === 'B' && 'Good code health. Minor improvements possible.'}
            {grade === 'C' && 'Fair code health. Some areas need attention.'}
            {grade === 'D' && 'Below average. Improvements recommended.'}
            {grade === 'F' && 'Poor health. Immediate attention required.'}
          </p>
        )}
      </div>
    </div>
  )
}

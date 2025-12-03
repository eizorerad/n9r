'use client'

import { cn } from '@/lib/utils'
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'

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

const gradeBorderColors: Record<string, string> = {
  A: 'border-emerald-500/30',
  B: 'border-blue-500/30',
  C: 'border-amber-500/30',
  D: 'border-orange-500/30',
  F: 'border-red-500/30',
}

const gradeLineColors: Record<string, string> = {
  A: '#10b981',
  B: '#3b82f6',
  C: '#f59e0b',
  D: '#f97316',
  F: '#ef4444',
}

export function VCIScoreCardCompact({ 
  score, 
  grade, 
  trend, 
  historyData = [],
  className 
}: VCIScoreCardCompactProps) {
  const displayGrade = grade || '—'
  const displayScore = score !== null && typeof score === 'number' ? score.toFixed(1) : '—'
  const gradientClass = grade ? gradeColors[grade] : 'from-muted to-muted/50'
  const textColor = grade ? gradeTextColors[grade] : 'text-muted-foreground'
  const borderColor = grade ? gradeBorderColors[grade] : 'border-border/50'
  const lineColor = grade ? gradeLineColors[grade] : '#71717a'

  const formattedData = historyData.map(d => ({
    ...d,
    date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  return (
    <div className={cn(
      'glass-panel border rounded-xl overflow-hidden',
      borderColor,
      className
    )}>
      {/* Background gradient */}
      <div className={cn(
        'absolute inset-0 opacity-5 bg-gradient-to-br pointer-events-none',
        gradientClass
      )} />

      <div className="relative p-3">
        {/* Header */}
        <div className="flex items-center gap-1.5 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-primary/80" />
          <span className="text-xs font-medium text-muted-foreground">Code Health</span>
          {trend && (
            <span className={cn(
              'ml-auto text-[10px] font-medium flex items-center gap-0.5',
              trend === 'improving' && 'text-emerald-400',
              trend === 'stable' && 'text-muted-foreground',
              trend === 'declining' && 'text-red-400'
            )}>
              {trend === 'improving' && '↑'}
              {trend === 'stable' && '→'}
              {trend === 'declining' && '↓'}
              {trend === 'improving' && 'Improving'}
              {trend === 'stable' && 'Stable'}
              {trend === 'declining' && 'Declining'}
            </span>
          )}
        </div>

        {/* Main content row */}
        <div className="flex items-center gap-3">
          {/* Score + Grade */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className={cn(
              'w-10 h-10 rounded-lg flex items-center justify-center bg-gradient-to-br shadow-md',
              gradientClass
            )}>
              <span className="text-lg font-bold text-white">{displayGrade}</span>
            </div>
            <div className="min-w-0">
              <div className="flex items-baseline gap-0.5">
                <span className={cn('text-2xl font-bold tracking-tight', textColor)}>
                  {displayScore}
                </span>
                <span className="text-xs text-muted-foreground/60">/100</span>
              </div>
              <p className="text-[10px] text-muted-foreground truncate">
                {grade === 'A' && 'Excellent'}
                {grade === 'B' && 'Good'}
                {grade === 'C' && 'Fair'}
                {grade === 'D' && 'Below avg'}
                {grade === 'F' && 'Poor'}
                {!grade && 'No data'}
              </p>
            </div>
          </div>

          {/* Mini trend chart */}
          {formattedData.length > 1 && (
            <div className="flex-1 h-12 min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={formattedData}>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#18181b',
                      border: '1px solid #27272a',
                      borderRadius: '6px',
                      fontSize: '10px',
                      padding: '4px 8px',
                    }}
                    labelStyle={{ color: '#a1a1aa', fontSize: '9px' }}
                    content={({ active, payload, label }) => {
                      if (!active || !payload || payload.length === 0) return null
                      const dataPoint = payload[0].payload as VCIHistoryPoint
                      return (
                        <div className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 shadow-lg">
                          <p className="text-zinc-400 text-[9px]">{label}</p>
                          <p className="text-[10px] font-medium" style={{ color: lineColor }}>
                            VCI: {dataPoint.vci_score}
                          </p>
                        </div>
                      )
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="vci_score"
                    stroke={lineColor}
                    strokeWidth={1.5}
                    dot={false}
                    activeDot={{ fill: lineColor, strokeWidth: 0, r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

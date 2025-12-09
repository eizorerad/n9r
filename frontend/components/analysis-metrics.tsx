'use client'

import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Activity,
  FileCode,
  AlertTriangle,
  CheckCircle,
  Code2,
  Gauge,
  Brain,
  TrendingUp,
} from 'lucide-react'

interface LanguageMetrics {
  files: number
  lines: number
  avg_complexity: number
  functions: number
}

interface AnalysisMetricsProps {
  metrics: {
    complexity_score?: number
    maintainability_score?: number
    duplication_score?: number
    architecture_score?: number
    heuristics_score?: number
    total_files?: number
    total_lines?: number
    total_comments?: number
    python_files?: number
    python_lines?: number
    js_ts_files?: number
    js_ts_lines?: number
    avg_complexity?: number
    max_complexity?: number
    high_complexity_functions?: number
    generic_names?: number
    magic_numbers?: number
    todo_comments?: number
    missing_docstrings?: number
    missing_type_hints?: number
    complexity_distribution?: Record<string, number>
    top_complex_functions?: Array<{
      name: string
      file: string
      line: number
      complexity: number
      rank: string
    }>
    halstead?: {
      total_volume?: number
      avg_difficulty?: number
      avg_effort?: number
      bugs_estimate?: number
    }
    maintainability_index?: {
      avg_mi?: number
      files_below_65?: number
      files_by_grade?: Record<string, number>
    }
    raw_metrics?: {
      loc?: number
      lloc?: number
      sloc?: number
      comments?: number
      multi?: number
      blank?: number
    }
    by_language?: Record<string, LanguageMetrics>
  } | null
}

function getLanguageIcon(lang: string): string {
  const icons: Record<string, string> = {
    python: '🐍',
    javascript: '📜',
    typescript: '💠',
    java: '☕',
    go: '🐹',
    ruby: '💎',
    php: '🐘',
    c: '⚙️',
    cpp: '⚙️',
  }
  return icons[lang.toLowerCase()] || '📄'
}

export function AnalysisMetrics({ metrics }: AnalysisMetricsProps) {
  if (!metrics) {
    return (
      <Card className="glass-panel border-border/50">
        <CardContent className="py-12 text-center text-muted-foreground">
          No analysis data yet. Run an analysis to see detailed metrics.
        </CardContent>
      </Card>
    )
  }

  const ccDist = metrics.complexity_distribution || {}
  const halstead = metrics.halstead || {}
  const mi = metrics.maintainability_index || {}
  const raw = metrics.raw_metrics || {}

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">

        {/* VCI Score Components - large panel */}
        <BentoCard className="col-span-2 lg:col-span-3" title="VCI Score Components" icon={Activity} iconColor="text-primary">
          <div className="grid grid-cols-5 gap-4">
            <ScoreItem label="Complexity" score={metrics.complexity_score || 0} />
            <ScoreItem label="Maintainability" score={metrics.maintainability_score || 0} />
            <ScoreItem label="Duplication" score={metrics.duplication_score || 0} />
            <ScoreItem label="Heuristics" score={metrics.heuristics_score || 0} />
            <ScoreItem label="Architecture" score={metrics.architecture_score || 0} />
          </div>
        </BentoCard>

        {/* Maintainability Index */}
        <BentoCard title="MI Score" icon={Gauge} iconColor="text-purple-500">
          <div className="text-center">
            <div className={cn(
              'text-3xl font-bold',
              (mi.avg_mi || 0) >= 65 ? 'text-emerald-400' :
                (mi.avg_mi || 0) >= 50 ? 'text-amber-400' : 'text-red-400'
            )}>
              {(mi.avg_mi || 0).toFixed(0)}
            </div>
            <div className="flex justify-center gap-2 mt-2 text-xs">
              <Badge variant="outline" className="bg-transparent text-white border-white/30">
                <span className="text-emerald-400 font-bold mr-1">{mi.files_by_grade?.A || 0}</span>A
              </Badge>
              <Badge variant="outline" className="bg-transparent text-white border-white/30">
                <span className="text-amber-400 font-bold mr-1">{mi.files_by_grade?.B || 0}</span>B
              </Badge>
              <Badge variant="outline" className="bg-transparent text-white border-white/30">
                <span className="text-red-400 font-bold mr-1">{mi.files_by_grade?.C || 0}</span>C
              </Badge>
            </div>
            {(mi.files_below_65 || 0) > 0 && (
              <p className="text-xs text-amber-400 mt-2">⚠️ {mi.files_below_65} files hard to maintain</p>
            )}
          </div>
        </BentoCard>

        {/* Cyclomatic Complexity Distribution */}
        <BentoCard className="col-span-2" title="Cyclomatic Complexity" icon={TrendingUp} iconColor="text-blue-500">
          <div className="grid grid-cols-6 gap-2">
            {['A', 'B', 'C', 'D', 'E', 'F'].map(grade => (
              <div key={grade} className="text-center p-2 rounded-lg bg-muted/20">
                <div className={cn(
                  'text-lg font-bold',
                  grade === 'A' ? 'text-emerald-400' :
                    grade === 'B' ? 'text-blue-400' :
                      grade === 'C' ? 'text-amber-400' :
                        grade === 'D' ? 'text-orange-400' :
                          'text-red-400'
                )}>{grade}</div>
                <div className="text-lg font-bold text-white">{ccDist[grade] || 0}</div>
              </div>
            ))}
          </div>
        </BentoCard>

        {/* Halstead Metrics */}
        <BentoCard className="col-span-2" title="Halstead Metrics" icon={Brain} iconColor="text-pink-500">
          <div className="grid grid-cols-4 gap-3">
            <MetricCell label="Volume" value={(halstead.total_volume || 0).toLocaleString()} />
            <MetricCell label="Difficulty" value={(halstead.avg_difficulty || 0).toFixed(1)} />
            <MetricCell label="Effort" value={(halstead.avg_effort || 0).toLocaleString()} />
            <MetricCell
              label="Est. Bugs"
              value={(halstead.bugs_estimate || 0).toFixed(1)}
              highlight={(halstead.bugs_estimate || 0) > 5}
            />
          </div>
        </BentoCard>

        {/* Raw Metrics */}
        <BentoCard className="col-span-2" title="Raw Metrics" icon={FileCode} iconColor="text-cyan-500">
          <div className="grid grid-cols-6 gap-2">
            <MetricCell label="LOC" value={(raw.loc || metrics.total_lines || 0).toLocaleString()} />
            <MetricCell label="LLOC" value={(raw.lloc || 0).toLocaleString()} />
            <MetricCell label="SLOC" value={(raw.sloc || 0).toLocaleString()} />
            <MetricCell label="Comments" value={(raw.comments || 0).toLocaleString()} />
            <MetricCell label="Blank" value={(raw.blank || 0).toLocaleString()} />
            <MetricCell label="Docstrings" value={(raw.multi || 0).toLocaleString()} />
          </div>
        </BentoCard>

        {/* Hard Heuristics */}
        <BentoCard className="col-span-2" title="Hard Heuristics" icon={CheckCircle} iconColor="text-green-500">
          <div className="grid grid-cols-5 gap-3">
            <HeuristicCell label="Generic Names" value={metrics.generic_names || 0} warn={10} />
            <HeuristicCell label="Magic Numbers" value={metrics.magic_numbers || 0} warn={20} />
            <HeuristicCell label="TODO/FIXME" value={metrics.todo_comments || 0} warn={10} />
            <HeuristicCell label="Missing Docs" value={metrics.missing_docstrings || 0} warn={5} />
            <HeuristicCell label="Missing Types" value={metrics.missing_type_hints || 0} warn={20} />
          </div>
        </BentoCard>

        {/* By Language */}
        {metrics.by_language && Object.keys(metrics.by_language).length > 0 && (
          <BentoCard className="col-span-2 lg:col-span-4" title="By Language" icon={Code2} iconColor="text-orange-500">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {Object.entries(metrics.by_language).map(([lang, data]) => (
                <div key={lang} className="flex items-center gap-3 p-3 rounded-lg bg-muted/20">
                  <span className="text-2xl">{getLanguageIcon(lang)}</span>
                  <div>
                    <div className="text-sm font-medium capitalize text-white">{lang}</div>
                    <div className="flex gap-3 text-xs text-muted-foreground">
                      <span><span className="text-white font-bold">{data.files}</span> files</span>
                      <span><span className="text-white font-bold">{data.lines.toLocaleString()}</span> lines</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </BentoCard>
        )}

        {/* Top Complex Functions */}
        {metrics.top_complex_functions && metrics.top_complex_functions.length > 0 && (
          <BentoCard className="col-span-2 lg:col-span-4" title="Top Complex Functions" icon={AlertTriangle} iconColor="text-red-500">
            <div className="space-y-2">
              {metrics.top_complex_functions.slice(0, 8).map((func, i) => (
                <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-muted/20">
                  <div className="flex items-center gap-3">
                    <span className="text-muted-foreground w-6">{i + 1}.</span>
                    <span className="font-mono text-blue-400">{func.name}</span>
                    <span className="text-xs text-muted-foreground truncate max-w-[200px]">{func.file}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-bold text-white">{func.complexity}</span>
                    <Badge variant="outline" className={cn(
                      'bg-transparent border-white/30',
                      func.rank === 'A' ? 'text-emerald-400' :
                        func.rank === 'B' ? 'text-blue-400' :
                          func.rank === 'C' ? 'text-amber-400' :
                            'text-red-400'
                    )}>{func.rank}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </BentoCard>
        )}
      </div>
    </div>
  )
}

function BentoCard({
  children,
  title,
  icon: Icon,
  iconColor,
  className
}: {
  children: React.ReactNode
  title: string
  icon: React.ElementType
  iconColor: string
  className?: string
}) {
  return (
    <div className={cn(
      'bg-muted/10 rounded-xl border border-border/30 p-4',
      className
    )}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className={cn('h-4 w-4', iconColor)} />
        <span className="text-sm font-medium text-white">{title}</span>
      </div>
      {children}
    </div>
  )
}

function ScoreItem({ label, score }: { label: string; score: number }) {
  return (
    <div className="text-center p-2 rounded-lg bg-muted/20">
      <div className={cn(
        'text-2xl font-bold',
        score >= 80 ? 'text-emerald-400' :
          score >= 60 ? 'text-amber-400' : 'text-red-400'
      )}>{score}</div>
      <div className="text-xs text-muted-foreground mt-1">{label}</div>
    </div>
  )
}

function MetricCell({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="text-center">
      <div className={cn('text-lg font-bold', highlight ? 'text-amber-400' : 'text-white')}>
        {value}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

function HeuristicCell({ label, value, warn }: { label: string; value: number; warn: number }) {
  return (
    <div className="text-center">
      <div className={cn('text-xl font-bold', value > warn ? 'text-amber-400' : 'text-emerald-400')}>
        {value}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

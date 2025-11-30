'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Activity,
  FileCode,
  AlertTriangle,
  CheckCircle,
  Code2,
  FileText,
  Gauge,
  Bug,
  Brain,
  TrendingUp,
  List
} from 'lucide-react'

interface LanguageMetrics {
  files: number
  lines: number
  avg_complexity: number
  functions: number
}

interface AnalysisMetricsProps {
  metrics: {
    // Score components
    complexity_score?: number
    maintainability_score?: number
    duplication_score?: number
    architecture_score?: number
    heuristics_score?: number
    // Raw metrics
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
    // Extended Radon metrics
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
    // Per-language breakdown
    by_language?: Record<string, LanguageMetrics>
  } | null
}

function ScoreBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground font-medium">{label}</span>
        <span className="font-mono font-medium">{score.toFixed(0)}/100</span>
      </div>
      <div className="h-2 bg-secondary rounded-full overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-500`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  )
}

function MetricItem({ icon: Icon, label, value, unit = '', color = '' }: {
  icon: React.ElementType;
  label: string;
  value: number | string;
  unit?: string
  color?: string
}) {
  return (
    <div className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg border border-border/50">
      <div className="p-2 bg-background rounded-md shadow-sm">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div>
        <p className="text-xs text-muted-foreground font-medium">{label}</p>
        <p className={`text-lg font-bold tracking-tight ${color}`}>{value}{unit}</p>
      </div>
    </div>
  )
}

function GradeBadge({ grade }: { grade: string }) {
  const colors: Record<string, string> = {
    A: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
    B: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    C: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
    D: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
    E: 'bg-red-500/10 text-red-500 border-red-500/20',
    F: 'bg-rose-700/10 text-rose-500 border-rose-700/20',
  }
  return (
    <span className={`px-2 py-0.5 text-xs font-bold rounded border ${colors[grade] || colors.C}`}>
      {grade}
    </span>
  )
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
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Score Components */}
      <Card className="glass-panel border-border/50">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
            <Activity className="h-4 w-4" />
            VCI Score Components
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <ScoreBar
            label="Complexity"
            score={metrics.complexity_score || 0}
            color="bg-[#008236]"
          />
          <ScoreBar
            label="Maintainability"
            score={metrics.maintainability_score || 0}
            color="bg-[#008236]"
          />
          <ScoreBar
            label="Duplication"
            score={metrics.duplication_score || 0}
            color="bg-[#008236]"
          />
          <ScoreBar
            label="Heuristics"
            score={metrics.heuristics_score || 0}
            color="bg-[#008236]"
          />
          <ScoreBar
            label="Architecture"
            score={metrics.architecture_score || 0}
            color="bg-[#008236]"
          />
        </CardContent>
      </Card>

      {/* Cyclomatic Complexity Distribution */}
      <Card className="glass-panel border-border/50">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
            <TrendingUp className="h-4 w-4" />
            Cyclomatic Complexity Distribution
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-6 gap-2 mb-6">
            {['A', 'B', 'C', 'D', 'E', 'F'].map(grade => (
              <div key={grade} className="text-center p-2 rounded-lg bg-muted/20">
                <GradeBadge grade={grade} />
                <p className="text-lg font-bold mt-2">{ccDist[grade] || 0}</p>
              </div>
            ))}
          </div>
          <div className="text-xs text-muted-foreground space-y-1.5 p-3 rounded-lg bg-muted/30 border border-border/50">
            <p>A (1-5): Simple • B (6-10): Low • C (11-20): Moderate</p>
            <p>D (21-30): High • E (31-40): Very High • F (41+): Untestable</p>
          </div>
        </CardContent>
      </Card>

      {/* Halstead Metrics */}
      <Card className="glass-panel border-border/50">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
            <Brain className="h-4 w-4" />
            Halstead Metrics
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <MetricItem
              icon={Code2}
              label="Volume"
              value={(halstead.total_volume || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            />
            <MetricItem
              icon={Gauge}
              label="Avg Difficulty"
              value={(halstead.avg_difficulty || 0).toFixed(1)}
            />
            <MetricItem
              icon={Activity}
              label="Avg Effort"
              value={(halstead.avg_effort || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            />
            <MetricItem
              icon={Bug}
              label="Est. Bugs"
              value={(halstead.bugs_estimate || 0).toFixed(2)}
              color={halstead.bugs_estimate && halstead.bugs_estimate > 5 ? 'text-amber-500' : ''}
            />
          </div>
          <div className="text-xs text-muted-foreground p-3 bg-muted/30 rounded-lg border border-border/50">
            <p><strong>Volume:</strong> Information content of code</p>
            <p><strong>Difficulty:</strong> How hard to understand</p>
            <p><strong>Effort:</strong> Work needed to understand/maintain</p>
          </div>
        </CardContent>
      </Card>

      {/* Maintainability Index */}
      <Card className="glass-panel border-border/50">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
            <Gauge className="h-4 w-4" />
            Maintainability Index (MI)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-center py-4">
            <div className="relative text-center">
              <div className={`text-6xl font-bold tracking-tighter ${(mi.avg_mi || 0) >= 65 ? 'text-emerald-500' :
                (mi.avg_mi || 0) >= 50 ? 'text-amber-500' : 'text-destructive'
                }`}>
                {(mi.avg_mi || 0).toFixed(0)}
              </div>
              <p className="text-sm text-muted-foreground mt-2 font-medium uppercase tracking-wide">Avg MI Score</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/10">
              <p className="text-2xl font-bold text-emerald-500">{mi.files_by_grade?.A || 0}</p>
              <p className="text-xs text-muted-foreground font-medium mt-1">A (MI ≥ 20)</p>
            </div>
            <div className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/10">
              <p className="text-2xl font-bold text-amber-500">{mi.files_by_grade?.B || 0}</p>
              <p className="text-xs text-muted-foreground font-medium mt-1">B (10-20)</p>
            </div>
            <div className="p-3 rounded-lg bg-destructive/5 border border-destructive/10">
              <p className="text-2xl font-bold text-destructive">{mi.files_by_grade?.C || 0}</p>
              <p className="text-xs text-muted-foreground font-medium mt-1">C (&lt;10)</p>
            </div>
          </div>
          {(mi.files_below_65 || 0) > 0 && (
            <p className="text-sm text-amber-500 text-center font-medium bg-amber-500/10 py-2 rounded-lg border border-amber-500/20">
              ⚠️ {mi.files_below_65} files with MI &lt; 65 (hard to maintain)
            </p>
          )}
        </CardContent>
      </Card>

      {/* Raw Metrics */}
      <Card className="glass-panel border-border/50">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
            <FileCode className="h-4 w-4" />
            Raw Metrics (Radon)
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-3 gap-4">
          <div className="text-center p-3 bg-muted/30 rounded-lg border border-border/50">
            <p className="text-xl font-bold">{(raw.loc || metrics.total_lines || 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground font-medium mt-1">LOC</p>
          </div>
          <div className="text-center p-3 bg-muted/30 rounded-lg border border-border/50">
            <p className="text-xl font-bold">{(raw.lloc || 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground font-medium mt-1">LLOC</p>
          </div>
          <div className="text-center p-3 bg-muted/30 rounded-lg border border-border/50">
            <p className="text-xl font-bold">{(raw.sloc || 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground font-medium mt-1">SLOC</p>
          </div>
          <div className="text-center p-3 bg-muted/30 rounded-lg border border-border/50">
            <p className="text-xl font-bold">{(raw.comments || metrics.total_comments || 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground font-medium mt-1">Comments</p>
          </div>
          <div className="text-center p-3 bg-muted/30 rounded-lg border border-border/50">
            <p className="text-xl font-bold">{(raw.blank || 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground font-medium mt-1">Blank</p>
          </div>
          <div className="text-center p-3 bg-muted/30 rounded-lg border border-border/50">
            <p className="text-xl font-bold">{(raw.multi || 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground font-medium mt-1">Docstrings</p>
          </div>
        </CardContent>
      </Card>

      {/* Hard Heuristics */}
      <Card className="glass-panel border-border/50">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
            <CheckCircle className="h-4 w-4" />
            Hard Heuristics
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex justify-between items-center p-3 bg-muted/30 rounded-lg border border-border/50 hover:bg-muted/50 transition-colors">
            <span className="text-muted-foreground font-medium">Generic Names</span>
            <span className={`text-xl font-bold ${(metrics.generic_names || 0) > 10 ? 'text-amber-500' : 'text-emerald-500'}`}>
              {metrics.generic_names || 0}
            </span>
          </div>
          <div className="flex justify-between items-center p-3 bg-muted/30 rounded-lg border border-border/50 hover:bg-muted/50 transition-colors">
            <span className="text-muted-foreground font-medium">Magic Numbers</span>
            <span className={`text-xl font-bold ${(metrics.magic_numbers || 0) > 20 ? 'text-amber-500' : 'text-emerald-500'}`}>
              {metrics.magic_numbers || 0}
            </span>
          </div>
          <div className="flex justify-between items-center p-3 bg-muted/30 rounded-lg border border-border/50 hover:bg-muted/50 transition-colors">
            <span className="text-muted-foreground font-medium">TODO/FIXME</span>
            <span className={`text-xl font-bold ${(metrics.todo_comments || 0) > 10 ? 'text-amber-500' : 'text-emerald-500'}`}>
              {metrics.todo_comments || 0}
            </span>
          </div>
          <div className="flex justify-between items-center p-3 bg-muted/30 rounded-lg border border-border/50 hover:bg-muted/50 transition-colors">
            <span className="text-muted-foreground font-medium">Missing Docstrings</span>
            <span className={`text-xl font-bold ${(metrics.missing_docstrings || 0) > 5 ? 'text-amber-500' : 'text-emerald-500'}`}>
              {metrics.missing_docstrings || 0}
            </span>
          </div>
          <div className="flex justify-between items-center p-3 bg-muted/30 rounded-lg border border-border/50 hover:bg-muted/50 transition-colors">
            <span className="text-muted-foreground font-medium">Missing Type Hints</span>
            <span className={`text-xl font-bold ${(metrics.missing_type_hints || 0) > 20 ? 'text-amber-500' : 'text-emerald-500'}`}>
              {metrics.missing_type_hints || 0}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* By Language Breakdown */}
      {metrics.by_language && Object.keys(metrics.by_language).length > 0 && (
        <Card className="glass-panel border-border/50">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
              <Code2 className="h-4 w-4" />
              By Language
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(metrics.by_language).map(([lang, data]) => (
                <div key={lang} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg border border-border/50">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">{getLanguageIcon(lang)}</span>
                    <span className="font-medium capitalize">{lang}</span>
                  </div>
                  <div className="flex gap-6 text-sm">
                    <div className="text-center">
                      <p className="text-muted-foreground text-xs">Files</p>
                      <p className="font-bold">{data.files}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-muted-foreground text-xs">Lines</p>
                      <p className="font-bold">{data.lines.toLocaleString()}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-muted-foreground text-xs">Avg CC</p>
                      <p className="font-bold">{data.avg_complexity.toFixed(1)}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top Complex Functions */}
      {metrics.top_complex_functions && metrics.top_complex_functions.length > 0 && (
        <Card className="glass-panel border-border/50 lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
              <AlertTriangle className="h-4 w-4" />
              Top Complex Functions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground border-b border-border/50">
                    <th className="text-left py-3 px-4 font-medium">#</th>
                    <th className="text-left py-3 px-4 font-medium">Function</th>
                    <th className="text-left py-3 px-4 font-medium">File</th>
                    <th className="text-center py-3 px-4 font-medium">CC</th>
                    <th className="text-center py-3 px-4 font-medium">Grade</th>
                  </tr>
                </thead>
                <tbody>
                  {metrics.top_complex_functions.slice(0, 10).map((func, i) => (
                    <tr key={i} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4 text-muted-foreground">{i + 1}</td>
                      <td className="py-3 px-4 font-mono text-blue-400">{func.name}</td>
                      <td className="py-3 px-4 text-muted-foreground truncate max-w-[200px]" title={func.file}>
                        {func.file}:{func.line}
                      </td>
                      <td className="py-3 px-4 text-center font-bold">{func.complexity}</td>
                      <td className="py-3 px-4 text-center"><GradeBadge grade={func.rank} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

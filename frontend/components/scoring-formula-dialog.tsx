'use client'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

/**
 * ScoringFormulaDialog displays explanations of how architecture findings are scored.
 *
 * **Feature: transparent-scoring-formula**
 * **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
 */

interface ScoringFormulaDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ScoringFormulaDialog({ open, onOpenChange }: ScoringFormulaDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl">How Findings Are Scored</DialogTitle>
          <DialogDescription>
            All scores use transparent, explainable formulas so you can understand and trust the prioritization.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 mt-4">
          {/* Dead Code Impact Score */}
          <section>
            <h3 className="text-lg font-semibold flex items-center gap-2 mb-3">
              <span className="text-purple-400">🗑️</span>
              Dead Code Impact Score (DCI)
            </h3>
            <p className="text-sm text-muted-foreground mb-3">
              Prioritizes which dead code to remove first based on importance.
            </p>
            
            <div className="bg-background/50 rounded-lg p-4 font-mono text-sm mb-3">
              <span className="text-brand-green">DCI</span> = (Size × <span className="text-amber-400">0.40</span>) + 
              (Location × <span className="text-amber-400">0.30</span>) + 
              (Recency × <span className="text-amber-400">0.20</span>) + 
              (Complexity × <span className="text-amber-400">0.10</span>)
            </div>

            <div className="space-y-2 text-sm">
              <FormulaComponent
                name="Size"
                weight="40%"
                formula="min(100, line_count × 2)"
                description="Larger dead code blocks have more impact when removed"
              />
              <FormulaComponent
                name="Location"
                weight="30%"
                formula="lookup table"
                description="Core business logic (services=100) scores higher than utilities (40) or tests (20)"
              />
              <FormulaComponent
                name="Recency"
                weight="20%"
                formula="max(0, 100 - days_since_modified)"
                description="Recently modified files are more actively maintained"
              />
              <FormulaComponent
                name="Complexity"
                weight="10%"
                formula="complexity score or 50"
                description="More complex code benefits more from cleanup"
              />
            </div>

            <div className="mt-3 p-3 bg-purple-500/10 rounded-lg border border-purple-500/20">
              <div className="text-sm flex items-start gap-2">
                <Badge variant="outline" className="shrink-0 bg-purple-500/10 text-purple-400 border-purple-500/20">
                  call-graph proven
                </Badge>
                <span>
                  Dead code detected via AST call-graph analysis has 100% confidence - 
                  the function is provably unreachable from any entry point.
                </span>
              </div>
            </div>
          </section>

          <Separator />

          {/* Hot Spot Risk Score */}
          <section>
            <h3 className="text-lg font-semibold flex items-center gap-2 mb-3">
              <span className="text-orange-400">🔥</span>
              Hot Spot Risk Score (HSR)
            </h3>
            <p className="text-sm text-muted-foreground mb-3">
              Identifies high-risk files that need attention based on churn and coverage.
            </p>
            
            <div className="bg-background/50 rounded-lg p-4 font-mono text-sm mb-3">
              <span className="text-brand-green">HSR</span> = (Churn × <span className="text-amber-400">0.30</span>) + 
              (Coverage × <span className="text-amber-400">0.30</span>) + 
              (Location × <span className="text-amber-400">0.20</span>) + 
              (Volatility × <span className="text-amber-400">0.20</span>)
            </div>

            <div className="space-y-2 text-sm">
              <FormulaComponent
                name="Churn"
                weight="30%"
                formula="min(100, changes_90d × 3)"
                description="Files changed frequently in the last 90 days are higher risk"
              />
              <FormulaComponent
                name="Coverage"
                weight="30%"
                formula="100 - (coverage_rate × 100)"
                description="Lower test coverage = higher risk (inverted scale)"
              />
              <FormulaComponent
                name="Location"
                weight="20%"
                formula="lookup table"
                description="Same as DCI - core business logic scores higher"
              />
              <FormulaComponent
                name="Volatility"
                weight="20%"
                formula="min(100, unique_authors × 15)"
                description="More authors = higher volatility and coordination risk"
              />
            </div>
          </section>

          <Separator />

          {/* Architecture Health Score */}
          <section>
            <h3 className="text-lg font-semibold flex items-center gap-2 mb-3">
              <span className="text-emerald-400">💚</span>
              Architecture Health Score (AHS)
            </h3>
            <p className="text-sm text-muted-foreground mb-3">
              Overall repository health calculated from penalties for issues found.
            </p>
            
            <div className="bg-background/50 rounded-lg p-4 font-mono text-sm mb-3">
              <span className="text-brand-green">AHS</span> = 100 - (Dead Code Penalty + Hot Spot Penalty + Outlier Penalty)
            </div>

            <div className="space-y-2 text-sm">
              <FormulaComponent
                name="Dead Code Penalty"
                weight="max 40"
                formula="min(40, (dead_code_count / total_functions) × 80)"
                description="Penalizes repositories with high dead code ratio"
              />
              <FormulaComponent
                name="Hot Spot Penalty"
                weight="max 30"
                formula="min(30, (hot_spot_count / total_files) × 60)"
                description="Penalizes repositories with many high-churn files"
              />
              <FormulaComponent
                name="Outlier Penalty"
                weight="max 20"
                formula="min(20, (outlier_count / total_chunks) × 40)"
                description="Penalizes repositories with architectural inconsistencies"
              />
            </div>

            <div className="mt-3 grid grid-cols-4 gap-2 text-xs">
              <HealthBadge score="80-100" color="green" label="Healthy" />
              <HealthBadge score="60-79" color="amber" label="Moderate" />
              <HealthBadge score="40-59" color="orange" label="Concerning" />
              <HealthBadge score="0-39" color="red" label="Critical" />
            </div>
          </section>

          <Separator />

          {/* Location Score Table */}
          <section>
            <h3 className="text-lg font-semibold mb-3">📍 Location Score Lookup</h3>
            <p className="text-sm text-muted-foreground mb-3">
              File paths are scored based on their importance to the codebase.
            </p>
            
            <div className="grid grid-cols-2 gap-2 text-sm">
              <LocationRow path="services/" score={100} />
              <LocationRow path="api/, routes/" score={90} />
              <LocationRow path="models/" score={80} />
              <LocationRow path="workers/, tasks/" score={70} />
              <LocationRow path="components/" score={60} />
              <LocationRow path="(default)" score={50} />
              <LocationRow path="lib/, utils/, helpers/" score={40} />
              <LocationRow path="tests/, __tests__/" score={20} />
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  )
}

interface FormulaComponentProps {
  name: string
  weight: string
  formula: string
  description: string
}

function FormulaComponent({ name, weight, formula, description }: FormulaComponentProps) {
  return (
    <div className="flex items-start gap-3 p-2 rounded bg-background/30">
      <div className="flex items-center gap-2 min-w-[140px]">
        <span className="font-medium">{name}</span>
        <Badge variant="outline" className="text-xs">{weight}</Badge>
      </div>
      <div className="flex-1">
        <code className="text-xs text-muted-foreground">{formula}</code>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
    </div>
  )
}

interface HealthBadgeProps {
  score: string
  color: 'green' | 'amber' | 'orange' | 'red'
  label: string
}

function HealthBadge({ score, color, label }: HealthBadgeProps) {
  const colorClasses = {
    green: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    orange: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    red: 'bg-red-500/10 text-red-400 border-red-500/20',
  }

  return (
    <div className={`p-2 rounded border text-center ${colorClasses[color]}`}>
      <div className="font-mono font-medium">{score}</div>
      <div className="text-xs opacity-80">{label}</div>
    </div>
  )
}

interface LocationRowProps {
  path: string
  score: number
}

function LocationRow({ path, score }: LocationRowProps) {
  return (
    <div className="flex items-center justify-between p-2 rounded bg-background/30">
      <code className="text-xs">{path}</code>
      <Badge variant="outline" className="text-xs font-mono">{score}</Badge>
    </div>
  )
}

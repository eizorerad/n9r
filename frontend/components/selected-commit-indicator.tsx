'use client'

import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { Badge } from '@/components/ui/badge'
import { GitCommit } from 'lucide-react'

interface SelectedCommitIndicatorProps {
  headCommitSha?: string | null
}

export function SelectedCommitIndicator({ headCommitSha }: SelectedCommitIndicatorProps) {
  const { selectedCommitSha } = useCommitSelectionStore()

  if (!selectedCommitSha) {
    return null
  }

  const shortSha = selectedCommitSha.slice(0, 7)
  const isLatest = headCommitSha && selectedCommitSha === headCommitSha

  return (
    <div className="flex items-center gap-1.5">
      <GitCommit className="h-3.5 w-3.5 text-muted-foreground" />
      <code className="text-xs font-mono text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
        {shortSha}
      </code>
      {isLatest && (
        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
          Latest
        </Badge>
      )}
    </div>
  )
}

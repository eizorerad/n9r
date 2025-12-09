"use client"

import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Workbench } from "@/components/layout/workbench"
import { Sidebar } from "@/components/layout/sidebar"
import { CommitTimeline } from "@/components/commit-timeline"
import { SemanticSearch } from "@/components/semantic-search"
import { Bug } from "lucide-react"
import { useStatusBarStore } from "@/lib/stores/status-bar-store"
import { useEffect } from "react"
import { AnalysisStatusSyncer } from "@/components/analysis-status-syncer"

// Types for the passed data
interface RepositoryShellProps {
    children: React.ReactNode
    repositoryId: string
    defaultBranch?: string
    token: string
    currentAnalysisCommit?: string | null
    hasAnalysis?: boolean
}

export function RepositoryShell({
    children,
    repositoryId,
    defaultBranch,
    token,
    currentAnalysisCommit,
    hasAnalysis = false,
}: RepositoryShellProps) {
    const router = useRouter()
    const pathname = usePathname()
    const searchParams = useSearchParams()

    // Status bar state
    const { setBranch, reset } = useStatusBarStore()

    // Initialize/Update status bar
    useEffect(() => {
        setBranch(defaultBranch || 'main')
        return () => {
            reset()
        }
    }, [defaultBranch, setBranch, reset])

    // ... rest of component

    // Determine active view based on URL and query params
    const isIdeView = pathname?.includes("/ide")
    const viewParam = searchParams.get('view')

    let activeView = "source-control" // Default
    if (isIdeView) {
        activeView = "explorer"
    } else if (viewParam === "search") {
        activeView = "search"
    }

    const handleViewChange = (view: string) => {
        if (view === "explorer") {
            router.push(`/dashboard/repository/${repositoryId}/ide`)
        } else if (view === "source-control") {
            router.push(`/dashboard/repository/${repositoryId}`)
        } else if (view === "search") {
            router.push(`/dashboard/repository/${repositoryId}?view=search`)
        }
        // Other views could be handled here
    }

    // Determine sidebar content
    let sidebarContent: React.ReactNode | null = null

    const handleSearchResultClick = (result: { file_path: string }) => {
        // Navigate to IDE view with the file selected
        // We pass the file path as a query parameter so the IDE can open it
        // Note: We need to ensure IDEClient reads this parameter
        const encodedPath = encodeURIComponent(result.file_path)
        router.push(`/dashboard/repository/${repositoryId}/ide?file=${encodedPath}`)
    }

    if (activeView === "source-control") {
        sidebarContent = (
            <Sidebar title="TIMELINE">
                <div className="p-2 h-full overflow-y-auto">
                    <CommitTimeline
                        repositoryId={repositoryId}
                        defaultBranch={defaultBranch || 'main'}
                        token={token}
                        currentAnalysisCommit={currentAnalysisCommit}
                        hasAnalysis={hasAnalysis}
                    />
                </div>
            </Sidebar>
        )
    } else if (activeView === "explorer") {
        // IDE handles its own sidebar
        sidebarContent = null
    } else if (activeView === "search") {
        sidebarContent = (
            <Sidebar title="SEMANTIC SEARCH">
                <div className="h-full overflow-y-auto p-2">
                    <SemanticSearch
                        repositoryId={repositoryId}
                        token={token}
                        className="bg-transparent border-none shadow-none p-0"
                        onResultClick={handleSearchResultClick}
                    />
                </div>
            </Sidebar>
        )
    } else {
        sidebarContent = (
            <Sidebar title={String(activeView).toUpperCase()}>
                <div className="p-4 text-center text-muted-foreground text-sm">
                    <Bug className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p>View not implemented</p>
                </div>
            </Sidebar>
        )
    }

    return (
        <Workbench
            sidebar={sidebarContent}
            activeView={activeView}
            onViewChange={handleViewChange}
        >
            <AnalysisStatusSyncer token={token} />
            {children}
        </Workbench>
    )
}

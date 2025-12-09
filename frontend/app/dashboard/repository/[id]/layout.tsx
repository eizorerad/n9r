import { getSession } from "@/lib/session"
import { getRepository } from "@/lib/data/repositories"
import { notFound, redirect } from "next/navigation"
import { RepositoryShell } from "@/components/repository-shell"

const API_BASE_URL = process.env.API_URL || 'http://localhost:8000/v1'

async function fetchLatestAnalysis(repoId: string, token: string) {
    try {
        const response = await fetch(`${API_BASE_URL}/repositories/${repoId}/analyses?per_page=1`, {
            headers: { Authorization: `Bearer ${token}` },
            cache: 'no-store',
        })

        if (!response.ok) return null
        const result = await response.json()
        return result.data?.[0] || null
    } catch {
        return null
    }
}



export default async function RepositoryLayout({
    children,
    params,
}: {
    children: React.ReactNode
    params: Promise<{ id: string }>
}) {
    const { id } = await params
    const session = await getSession()

    if (!session?.accessToken) {
        redirect("/login")
    }

    // Fetch critical data for the sidebar
    const [repo, latestAnalysis] = await Promise.all([
        getRepository(id),
        fetchLatestAnalysis(id, session.accessToken),
    ])

    if (!repo) {
        notFound()
    }

    const currentAnalysisCommit = latestAnalysis?.status === 'completed' ? latestAnalysis.commit_sha : null
    const hasAnalysis = !!repo.last_analysis_at

    return (
        <RepositoryShell
            repositoryId={id}
            defaultBranch={repo.default_branch}
            token={session.accessToken}
            currentAnalysisCommit={currentAnalysisCommit}
            hasAnalysis={hasAnalysis}
        >
            {children}
        </RepositoryShell>
    )
}

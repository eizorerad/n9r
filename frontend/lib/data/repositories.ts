import { getSession } from '@/lib/session'

const API_BASE_URL = process.env.API_URL || 'http://localhost:8000/v1'

export interface Repository {
  id: string
  github_id: number
  name: string
  full_name: string
  default_branch: string
  mode: string
  is_active: boolean
  vci_score: number | null
  tech_debt_level: string | null
  last_analysis_at: string | null
  pending_prs_count: number
  open_issues_count: number
}

export interface PaginatedRepositories {
  data: Repository[]
  pagination: {
    page: number
    per_page: number
    total: number
    total_pages: number
  }
}

async function getToken(): Promise<string | null> {
  const session = await getSession()
  return session?.accessToken || null
}

export async function getRepositories(params?: {
  org_id?: string
  is_active?: boolean
  page?: number
  per_page?: number
}): Promise<PaginatedRepositories> {
  const token = await getToken()
  if (!token) {
    return { data: [], pagination: { page: 1, per_page: 20, total: 0, total_pages: 0 } }
  }

  const searchParams = new URLSearchParams()
  if (params?.org_id) searchParams.set('org_id', params.org_id)
  if (params?.is_active !== undefined) searchParams.set('is_active', String(params.is_active))
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.per_page) searchParams.set('per_page', String(params.per_page))

  const query = searchParams.toString()
  
  const response = await fetch(
    `${API_BASE_URL}/repositories${query ? `?${query}` : ''}`,
    {
      headers: { Authorization: `Bearer ${token}` },
      next: { revalidate: 60 }, // Revalidate every 60 seconds
    }
  )

  if (!response.ok) {
    return { data: [], pagination: { page: 1, per_page: 20, total: 0, total_pages: 0 } }
  }

  return response.json()
}

export async function getRepository(repoId: string) {
  const token = await getToken()
  if (!token) return null

  const response = await fetch(`${API_BASE_URL}/repositories/${repoId}`, {
    headers: { Authorization: `Bearer ${token}` },
    next: { revalidate: 30 }, // Revalidate every 30 seconds
  })

  if (!response.ok) return null

  return response.json()
}

export async function getAvailableRepositories() {
  const token = await getToken()
  if (!token) return { data: [] }

  const response = await fetch(`${API_BASE_URL}/repositories/available`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store', // Always fresh data
  })

  if (!response.ok) return { data: [] }

  return response.json()
}

// Dashboard stats
export async function getDashboardStats() {
  const token = await getToken()
  if (!token) {
    return {
      total_repositories: 0,
      healthy_repos: 0,
      repos_needing_attention: 0,
      pending_prs: 0,
      open_issues: 0,
      avg_vci_score: null,
    }
  }

  // Fetch repositories and calculate stats
  const repos = await getRepositories({ per_page: 100 })
  
  const stats = {
    total_repositories: repos.pagination.total,
    healthy_repos: repos.data.filter(r => r.vci_score && r.vci_score >= 80).length,
    repos_needing_attention: repos.data.filter(r => r.vci_score && r.vci_score < 60).length,
    pending_prs: repos.data.reduce((sum, r) => sum + r.pending_prs_count, 0),
    open_issues: repos.data.reduce((sum, r) => sum + r.open_issues_count, 0),
    avg_vci_score: repos.data.length > 0
      ? repos.data.reduce((sum, r) => sum + (r.vci_score || 0), 0) / repos.data.length
      : null,
  }

  return stats
}

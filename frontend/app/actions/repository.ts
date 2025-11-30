'use server'

import { revalidatePath } from 'next/cache'
import { getSession } from '@/lib/session'

const API_BASE_URL = process.env.API_URL || 'http://localhost:8000/v1'

async function getToken(): Promise<string | null> {
  const session = await getSession()
  return session?.accessToken || null
}

// Connect a repository
export async function connectRepository(formData: FormData) {
  const token = await getToken()
  if (!token) {
    return { error: 'Unauthorized' }
  }

  const githubId = formData.get('github_id')
  const mode = formData.get('mode') || 'view_only'
  const orgId = formData.get('org_id')

  try {
    const response = await fetch(`${API_BASE_URL}/repositories`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        github_id: Number(githubId),
        mode,
        org_id: orgId || undefined,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { error: error.message || 'Failed to connect repository' }
    }

    revalidatePath('/dashboard')
    
    return { success: true }
  } catch (error) {
    return { error: 'Network error. Please try again.' }
  }
}

// Update repository settings
export async function updateRepository(repoId: string, formData: FormData) {
  const token = await getToken()
  if (!token) {
    return { error: 'Unauthorized' }
  }

  const mode = formData.get('mode')
  const isActive = formData.get('is_active')

  try {
    const response = await fetch(`${API_BASE_URL}/repositories/${repoId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        mode: mode || undefined,
        is_active: isActive !== null ? isActive === 'true' : undefined,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { error: error.message || 'Failed to update repository' }
    }

    revalidatePath('/dashboard')
    revalidatePath(`/repo/${repoId}`)
    
    return { success: true }
  } catch (error) {
    return { error: 'Network error. Please try again.' }
  }
}

// Disconnect repository
export async function disconnectRepository(repoId: string) {
  const token = await getToken()
  if (!token) {
    return { error: 'Unauthorized' }
  }

  try {
    const response = await fetch(`${API_BASE_URL}/repositories/${repoId}`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })

    if (!response.ok) {
      const error = await response.json()
      return { error: error.message || 'Failed to disconnect repository' }
    }

    revalidatePath('/dashboard')
    
    return { success: true }
  } catch (error) {
    return { error: 'Network error. Please try again.' }
  }
}

// Get available repositories from GitHub
export async function getAvailableRepositories() {
  const token = await getToken()
  if (!token) {
    return { error: 'Unauthorized', repositories: [] }
  }

  try {
    const response = await fetch(`${API_BASE_URL}/repositories/available`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: 'no-store',
    })

    if (!response.ok) {
      const error = await response.json()
      return { error: error.detail || 'Failed to load repositories', repositories: [] }
    }

    const result = await response.json()
    // Backend returns { data: [...] }
    const repositories = result.data || result
    return { repositories, error: null }
  } catch (error) {
    return { error: 'Network error. Please try again.', repositories: [] }
  }
}

// Start analysis
export async function startAnalysis(repoId: string, formData: FormData) {
  const token = await getToken()
  if (!token) {
    return { error: 'Unauthorized' }
  }

  const commitSha = formData.get('commit_sha')

  try {
    const response = await fetch(`${API_BASE_URL}/repositories/${repoId}/analyses`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        commit_sha: commitSha || undefined,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { error: error.message || 'Failed to start analysis' }
    }

    const analysis = await response.json()
    
    revalidatePath(`/repo/${repoId}`)
    revalidatePath('/dashboard')
    
    return { success: true, analysisId: analysis.id }
  } catch (error) {
    return { error: 'Network error. Please try again.' }
  }
}

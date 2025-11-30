'use server'

import { getSession } from '@/lib/session'
import { revalidatePath } from 'next/cache'

const API_BASE_URL = process.env.API_URL || 'http://localhost:8000/v1'

// Export API URL for client-side SSE connection
export async function getApiUrl(): Promise<string> {
  return API_BASE_URL
}

// Export access token for client-side SSE connection  
export async function getAccessToken(): Promise<string | null> {
  const session = await getSession()
  return session?.accessToken || null
}

export async function runAnalysis(repositoryId: string): Promise<{ success: boolean; error?: string; analysisId?: string }> {
  const session = await getSession()
  
  if (!session?.accessToken) {
    return { success: false, error: 'Not authenticated' }
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/analyses`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${session.accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}),
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      return { success: false, error: error.detail || `Error: ${response.status}` }
    }
    
    const result = await response.json()
    
    // Revalidate the repository page to show new analysis
    revalidatePath(`/dashboard/repository/${repositoryId}`)
    
    return { success: true, analysisId: result.id }
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Network error' }
  }
}

export async function getAnalysisStatus(analysisId: string): Promise<{
  status: 'pending' | 'running' | 'completed' | 'failed';
  error_message?: string;
  vci_score?: number;
}> {
  const session = await getSession()
  
  if (!session?.accessToken) {
    return { status: 'failed', error_message: 'Not authenticated' }
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/analyses/${analysisId}`, {
      headers: {
        'Authorization': `Bearer ${session.accessToken}`,
      },
      cache: 'no-store',
    })
    
    if (!response.ok) {
      return { status: 'failed', error_message: `Error: ${response.status}` }
    }
    
    const data = await response.json()
    return {
      status: data.status,
      error_message: data.error_message,
      vci_score: data.vci_score,
    }
  } catch (error) {
    return { status: 'failed', error_message: error instanceof Error ? error.message : 'Network error' }
  }
}

/**
 * Revalidate repository page cache after analysis completion.
 * Called from the client when SSE reports analysis is done.
 */
export async function revalidateRepositoryPage(repositoryId: string): Promise<void> {
  revalidatePath(`/dashboard/repository/${repositoryId}`)
  // Also revalidate the main dashboard in case it shows VCI scores
  revalidatePath('/dashboard')
}

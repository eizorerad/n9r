'use server'

import { redirect } from 'next/navigation'
import { createSession, deleteSession } from '@/lib/session'

const API_BASE_URL = process.env.API_URL || 'http://localhost:8000/v1'
const GITHUB_CLIENT_ID = process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'

// Generate GitHub OAuth URL
export async function getGitHubAuthUrl() {
  const params = new URLSearchParams({
    client_id: GITHUB_CLIENT_ID!,
    redirect_uri: `${APP_URL}/auth/callback`,
    scope: 'user:email read:user repo',
    state: crypto.randomUUID(), // CSRF protection
  })
  
  return `https://github.com/login/oauth/authorize?${params.toString()}`
}

// Handle GitHub OAuth callback
export async function handleGitHubCallback(code: string) {
  try {
    // Exchange code for token via backend
    const response = await fetch(`${API_BASE_URL}/auth/github/exchange`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { error: error.message || 'Authentication failed' }
    }

    const data = await response.json()
    
    // Create session with user data
    await createSession({
      userId: data.user.id,
      login: data.user.login,
      name: data.user.name,
      avatarUrl: data.user.avatar_url,
      accessToken: data.access_token,
    })

    return { success: true }
  } catch (error) {
    console.error('GitHub callback error:', error)
    return { error: 'Network error. Please try again.' }
  }
}

// Logout action
export async function logout() {
  await deleteSession()
  redirect('/login')
}

// Login redirect action
export async function loginWithGitHub() {
  const url = await getGitHubAuthUrl()
  redirect(url)
}

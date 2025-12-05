import 'server-only'

import { SignJWT, jwtVerify } from 'jose'
import { cookies } from 'next/headers'
import { cache } from 'react'
import { redirect } from 'next/navigation'

const secretKey = process.env.SESSION_SECRET
const encodedKey = new TextEncoder().encode(secretKey)

export interface SessionPayload {
  userId: string
  login: string
  name: string | null
  avatarUrl: string | null
  accessToken: string
  expiresAt: Date
}

// Encrypt session data into JWT
export async function encrypt(payload: SessionPayload): Promise<string> {
  return new SignJWT({ ...payload, expiresAt: payload.expiresAt.toISOString() })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('7d')
    .sign(encodedKey)
}

// Decrypt JWT to session data
export async function decrypt(session: string | undefined): Promise<SessionPayload | null> {
  if (!session) return null
  
  try {
    const { payload } = await jwtVerify(session, encodedKey, {
      algorithms: ['HS256'],
    })
    return {
      userId: payload.userId as string,
      login: payload.login as string,
      name: payload.name as string | null,
      avatarUrl: payload.avatarUrl as string | null,
      accessToken: payload.accessToken as string,
      expiresAt: new Date(payload.expiresAt as string),
    }
  } catch {
    return null
  }
}

// Create session and store in cookie
export async function createSession(data: Omit<SessionPayload, 'expiresAt'>) {
  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000) // 7 days
  const session = await encrypt({ ...data, expiresAt })
  
  // Only use secure cookies if explicitly using HTTPS
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || ''
  const useSecure = appUrl.startsWith('https://')
  
  const cookieStore = await cookies()
  cookieStore.set('n9r_session', session, {
    httpOnly: true,
    secure: useSecure,
    expires: expiresAt,
    sameSite: 'lax',
    path: '/',
  })
}

// Update session expiration
export async function updateSession() {
  const cookieStore = await cookies()
  const session = cookieStore.get('n9r_session')?.value
  const payload = await decrypt(session)

  if (!session || !payload) {
    return null
  }

  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  const newSession = await encrypt({ ...payload, expiresAt })

  cookieStore.set('n9r_session', newSession, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    expires: expiresAt,
    sameSite: 'lax',
    path: '/',
  })
}

// Delete session
export async function deleteSession() {
  const cookieStore = await cookies()
  cookieStore.delete('n9r_session')
}

// Verify session - cached for render pass
export const verifySession = cache(async () => {
  const cookieStore = await cookies()
  const session = cookieStore.get('n9r_session')?.value
  const payload = await decrypt(session)

  if (!payload?.userId) {
    redirect('/login')
  }

  return {
    isAuth: true,
    userId: payload.userId,
    login: payload.login,
    name: payload.name,
    avatarUrl: payload.avatarUrl,
  }
})

// Get session without redirect
export const getSession = cache(async () => {
  const cookieStore = await cookies()
  const session = cookieStore.get('n9r_session')?.value
  return decrypt(session)
})

// Validate session with backend - checks if token is still valid
export async function validateSession(): Promise<boolean> {
  const session = await getSession()
  if (!session?.accessToken) {
    return false
  }

  try {
    const API_BASE_URL = process.env.API_URL || 'http://localhost:8000/v1'
    const response = await fetch(`${API_BASE_URL}/users/me`, {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
      cache: 'no-store',
    })

    if (!response.ok) {
      // Token is invalid - clear the session
      await deleteSession()
      return false
    }

    return true
  } catch {
    // Network error - don't clear session, might be temporary
    return false
  }
}

// Get validated session - redirects if invalid
export async function getValidatedSession() {
  const session = await getSession()
  if (!session?.accessToken) {
    redirect('/login')
  }

  try {
    const API_BASE_URL = process.env.API_URL || 'http://localhost:8000/v1'
    const response = await fetch(`${API_BASE_URL}/users/me`, {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
      cache: 'no-store',
    })

    if (!response.ok) {
      // Token is invalid - clear the session and redirect
      await deleteSession()
      redirect('/login')
    }

    return session
  } catch {
    // Network error - still return session (might be temporary issue)
    return session
  }
}

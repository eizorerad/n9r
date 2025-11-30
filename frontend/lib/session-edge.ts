import { SignJWT, jwtVerify } from 'jose'

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

// Decrypt JWT to session data (Edge-compatible)
export async function decryptEdge(session: string | undefined): Promise<SessionPayload | null> {
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
